#!/usr/bin/env python3
"""Read-only bounded ELF32 ARM dynamic metadata audit inside hotdog vendor ZIP.

Loads the single designated ELF member into memory (never to disk), parses
PT_DYNAMIC and DT_NEEDED using stdlib struct. Never executes or modifies it.
No firmware/AVB/signing/Soong compatibility claims.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import zipfile

MEMBER = "proprietary/odm/lib/hw/audio.primary.msmnile.so"
OLD_NEEDED = "/vendor/lib/liba2dpoffload.so"
NEW_NEEDED = "/odm/lib/liba2dpoffload.so"
MAX_ZIP_ENTRIES = 100000
MAX_ARCHIVE_BYTES = 8 * 1024**3
MAX_ELF_BYTES = 64 * 1024**2
MAX_PHDRS = 256
MAX_DYNAMIC_BYTES = 1024 * 1024
MAX_DYNAMIC_TAGS = 8192
MAX_STRTAB_BYTES = 16 * 1024 * 1024
MAX_NEEDED_COUNT = 256
MAX_STRING_BYTES = 512
PT_LOAD = 1
PT_DYNAMIC = 2
DT_NULL = 0
DT_NEEDED = 1
DT_STRTAB = 5
DT_STRSZ = 10
DT_SONAME = 14


class ElfAuditError(ValueError):
    pass


def bounded_region(blob, offset, size, label):
    if offset < 0 or size < 0 or offset > len(blob) or size > len(blob) - offset:
        raise ElfAuditError("Invalid bounds for " + label)
    return blob[offset:offset + size]


def parse_elf_dynamic(blob):
    if len(blob) < 52 or blob[:4] != b"\x7fELF":
        raise ElfAuditError("Not an ELF header")
    if blob[4] != 1 or blob[5] != 1 or blob[6] != 1:
        raise ElfAuditError("Expected ELFCLASS32, little-endian, EV_CURRENT")
    (e_type, e_machine, e_version, _, e_phoff, _, _,
     e_ehsize, e_phentsize, e_phnum, _, _, _) = struct.unpack_from(
        "<HHIIIIIHHHHHH", blob, 16
    )
    if e_type != 3 or e_machine != 40 or e_version != 1:
        raise ElfAuditError("Expected 32-bit ARM ET_DYN shared library")
    if e_ehsize < 52 or e_phentsize < 32 or not 0 < e_phnum <= MAX_PHDRS:
        raise ElfAuditError("Invalid ELF program-header layout")
    bounded_region(blob, e_phoff, e_phentsize * e_phnum, "program header table")

    loads = []
    dynamic = []
    for i in range(e_phnum):
        start = e_phoff + i * e_phentsize
        (p_type, p_offset, p_vaddr, _, p_filesz, p_memsz, _,
         _) = struct.unpack_from("<IIIIIIII", blob, start)
        if p_type in (PT_LOAD, PT_DYNAMIC):
            bounded_region(blob, p_offset, p_filesz, "load/dynamic segment")
        if p_type == PT_LOAD:
            loads.append((p_offset, p_vaddr, p_filesz, p_memsz))
        elif p_type == PT_DYNAMIC:
            if p_filesz <= 0 or p_filesz > MAX_DYNAMIC_BYTES or p_filesz % 8:
                raise ElfAuditError("Unbounded or malformed PT_DYNAMIC")
            dynamic.append((p_offset, p_filesz))
    if not loads or len(dynamic) != 1:
        raise ElfAuditError("Expected load segments and exactly one PT_DYNAMIC")

    dyn_off, dyn_size = dynamic[0]
    tags = []
    saw_null = False
    for j in range(min(dyn_size // 8, MAX_DYNAMIC_TAGS)):
        d_tag, d_val = struct.unpack_from("<II", blob, dyn_off + 8 * j)
        if d_tag == DT_NULL:
            saw_null = True
            break
        tags.append((d_tag, d_val))
    if not saw_null:
        raise ElfAuditError("Missing DT_NULL terminator or too many dynamic tags")
    needed_offsets = [v for tag, v in tags if tag == DT_NEEDED]
    if not needed_offsets or len(needed_offsets) > MAX_NEEDED_COUNT:
        raise ElfAuditError("No DT_NEEDED or unreasonable dependency count")
    tables = [v for tag, v in tags if tag == DT_STRTAB]
    sizes = [v for tag, v in tags if tag == DT_STRSZ]
    if len(tables) != 1 or len(sizes) != 1 or not 0 < sizes[0] <= MAX_STRTAB_BYTES:
        raise ElfAuditError("Missing/ambiguous bounded dynamic string table")
    str_vaddr, str_size = tables[0], sizes[0]
    location = None
    for p_offset, p_vaddr, p_filesz, _ in loads:
        if p_vaddr <= str_vaddr and str_size <= p_filesz - (str_vaddr - p_vaddr):
            candidate = p_offset + str_vaddr - p_vaddr
            if location is not None and location != candidate:
                raise ElfAuditError("Ambiguous PT_LOAD dynamic string mapping")
            location = candidate
    if location is None:
        raise ElfAuditError("DT_STRTAB not file-backed by a PT_LOAD")
    strings = bounded_region(blob, location, str_size, "dynamic string table")

    def dyn_string(offset):
        if not 0 <= offset < str_size:
            raise ElfAuditError("Out-of-bounds DT_NEEDED/DT_SONAME offset")
        end = strings.find(b"\x00", offset, min(str_size, offset + MAX_STRING_BYTES + 1))
        if end < 0 or end - offset > MAX_STRING_BYTES:
            raise ElfAuditError("Unterminated or oversized dynamic string")
        raw = strings[offset:end]
        if not raw or any(byte < 32 or byte > 126 for byte in raw):
            raise ElfAuditError("Non-printable dynamic library name")
        return raw.decode("ascii")

    needed = [dyn_string(v) for v in needed_offsets]
    sonames = [dyn_string(v) for tag, v in tags if tag == DT_SONAME]
    if len(sonames) > 1:
        raise ElfAuditError("Multiple DT_SONAME entries")
    return {
        "elf_class": "ELF32",
        "elf_endianness": "little",
        "machine": "EM_ARM",
        "elf_type": "ET_DYN",
        "needed_count": len(needed),
        "needed_names": needed,
        "soname": sonames[0] if sonames else None,
        "elf_sha256": hashlib.sha256(blob).hexdigest(),
        "elf_bytes": len(blob),
    }


def inspect_archive(path, expected_archive_sha256=None):
    path = Path(path)
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_ARCHIVE_BYTES:
        raise ElfAuditError("Vendor ZIP missing, empty or excessively large")
    sha_verified = False
    if expected_archive_sha256 is not None:
        if (len(expected_archive_sha256) != 64 or
            any(c not in "0123456789abcdef" for c in expected_archive_sha256)):
            raise ElfAuditError("Malformed expected ZIP SHA256")
        hasher = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                hasher.update(chunk)
        if hasher.hexdigest() != expected_archive_sha256:
            raise ElfAuditError("Local hotdog ZIP differs from recorded SHA256")
        sha_verified = True

    with zipfile.ZipFile(path) as archive:
        info = archive.infolist()
        if not 0 < len(info) <= MAX_ZIP_ENTRIES:
            raise ElfAuditError("Invalid ZIP member count")
        roots = set()
        candidates = []
        for entry in info:
            name = entry.filename
            if not name or name.startswith("/") or "\\" in name or "\x00" in name or len(name) > 1024:
                raise ElfAuditError("Unsafe ZIP member filename")
            parts = name.rstrip("/").split("/")
            if any(p in ("", ".", "..") for p in parts):
                raise ElfAuditError("Unsafe ZIP member path")
            roots.add(parts[0])
            if len(parts) == 2 and parts[1] == MEMBER and not entry.is_dir():
                candidates.append(entry)
        if len(roots) != 1 or roots.pop() != "proprietary_vendor_oneplus_hotdog-17.0":
            raise ElfAuditError("Unexpected hotdog ZIP root")
        if len(candidates) != 1:
            raise ElfAuditError("Expected exactly one hotdog audio ELF")
        entry = candidates[0]
        if not 52 <= entry.file_size <= MAX_ELF_BYTES:
            raise ElfAuditError("Audio ELF exceeds size bounds")
        with archive.open(entry) as stream:
            blob = stream.read(MAX_ELF_BYTES + 1)
        if len(blob) != entry.file_size or len(blob) > MAX_ELF_BYTES:
            raise ElfAuditError("Truncated or oversized ELF member")
    observed = parse_elf_dynamic(blob)
    needed = observed["needed_names"]
    old, new = OLD_NEEDED in needed, NEW_NEEDED in needed
    if new and not old:
        status = "EXPECTED_ODM_NEEDED_PATH_PRESENT"
    elif old and not new:
        status = "LEGACY_VENDOR_NEEDED_PATH_PRESENT"
    elif old and new:
        status = "BOTH_LEGACY_AND_ODM_NEEDED_PATHS"
    else:
        status = "EXPECTED_FULLPATH_NEEDED_NOT_OBSERVED"
    return {
        "schema": "op7t-hotdog-audio-dynamic-elf-v1",
        "device": "hotdog",
        "source_member": MEMBER,
        "local_zip_sha256_verified": sha_verified,
        "expected_old_needed": OLD_NEEDED,
        "expected_new_needed": NEW_NEEDED,
        **observed,
        "old_needed_present": old,
        "new_needed_present": new,
        "status": status,
        "expected_dynamic_fixup_verified": status == "EXPECTED_ODM_NEEDED_PATH_PRESENT",
        "elf_read_from_archive_in_memory": True,
        "elf_executed": False,
        "elf_written_to_disk": False,
        "common_vendor_library_binary_examined": False,
        "installed_rom_compatibility_verified": False,
        "flash_ready": False,
        "limitations": "Reads only the hotdog audio ELF's static metadata; not ELF signatures, dependency resolution, Android bionic linker behavior, build provenance, firmware, AVB or module ABI."
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("archive", type=Path)
    p.add_argument("--expect-archive-sha256")
    args = p.parse_args(argv)
    try:
        result = inspect_archive(args.archive, args.expect_archive_sha256)
    except (OSError, ValueError, RuntimeError, NotImplementedError, zipfile.BadZipFile,
            struct.error) as exc:
        print(f"Audio ELF dynamic audit FAILED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
