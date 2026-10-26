#!/usr/bin/env python3
"""Read-only ELF32 ARM A2DP path segment/section and dlopen import probe.

Loads only the designated audio ELF member from an existing ZIP into bounded
memory. Verifies supplied SHA256s. No ELF execution, writing, flashing,
disassembly or claim of a runtime call path.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import zipfile

MEMBER = "proprietary/odm/lib/hw/audio.primary.msmnile.so"
WRAPPER = "proprietary_vendor_oneplus_hotdog-17.0/"
TARGET = b"/odm/lib/liba2dpoffload.so"
MAX_ARCHIVE = 8 * 1024**3
MAX_BLOB = 8 * 1024**2
MAX_ENTRIES = 100000
MAX_PHDR = 256
MAX_SHDR = 8192
MAX_SYMBOLS = 100000
MAX_STRING_TABLE = 4 * 1024**2
WATCH_SYMBOLS = ("dlopen", "dlsym", "android_dlopen_ext")


class ElfReferenceError(ValueError):
    pass


def check_region(data, start, size, label):
    if start < 0 or size < 0 or start > len(data) or size > len(data) - start:
        raise ElfReferenceError("Out-of-bounds " + label)
    return data[start:start + size]


def digest_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_audio_zip(path):
    with zipfile.ZipFile(path) as z:
        entries = z.infolist()
        if not 0 < len(entries) <= MAX_ENTRIES:
            raise ElfReferenceError("Bad ZIP directory")
        roots = set()
        chosen = []
        for entry in entries:
            name = entry.filename
            if not name or name.startswith("/") or "\\" in name or "\x00" in name or len(name) > 1024:
                raise ElfReferenceError("Unsafe ZIP entry")
            parts = name.rstrip("/").split("/")
            if any(p in ("", ".", "..") for p in parts):
                raise ElfReferenceError("Unsafe ZIP path component")
            roots.add(parts[0])
            if name == WRAPPER + MEMBER and not entry.is_dir():
                chosen.append(entry)
        if roots != {WRAPPER[:-1]} or len(chosen) != 1:
            raise ElfReferenceError("Unexpected ZIP root or audio member")
        entry = chosen[0]
        if not 52 <= entry.file_size <= MAX_BLOB:
            raise ElfReferenceError("Unexpected audio ELF size")
        with z.open(entry) as f:
            data = f.read(MAX_BLOB + 1)
        if len(data) != entry.file_size:
            raise ElfReferenceError("ELF payload truncation")
        return data


def bounded_cstring(data, offset, max_length=300):
    if not 0 <= offset < len(data):
        raise ElfReferenceError("Invalid string offset")
    nul = data.find(b"\x00", offset, min(len(data), offset + max_length + 1))
    if nul < 0:
        raise ElfReferenceError("Unterminated or overlong ELF string")
    value = data[offset:nul]
    if any(c < 32 or c > 126 for c in value):
        raise ElfReferenceError("Non-ASCII ELF symbol or section name")
    return value.decode("ascii")


def inspect_elf(data):
    if len(data) < 52 or data[:7] != b"\x7fELF\x01\x01\x01":
        raise ElfReferenceError("Expected ELF32 little-endian")
    header = struct.unpack_from("<HHIIIIIHHHHHH", data, 16)
    (e_type, e_machine, e_version, _, phoff, shoff, _, e_ehsize,
     phentsize, phnum, shentsize, shnum, shstrndx) = header
    if (e_type != 3 or e_machine != 40 or e_version != 1 or e_ehsize < 52 or
        phentsize < 32 or not 0 < phnum <= MAX_PHDR):
        raise ElfReferenceError("Not expected shared ARM ELF32")
    check_region(data, phoff, phentsize * phnum, "program header table")

    loads = []
    for idx in range(phnum):
        record = struct.unpack_from("<IIIIIIII", data, phoff + idx * phentsize)
        p_type, p_off, p_vaddr, _, p_size, _, p_flags, _ = record
        if p_type == 1:
            check_region(data, p_off, p_size, "PT_LOAD")
            loads.append({
                "file_start": p_off,
                "file_end": p_off + p_size,
                "vaddr": p_vaddr,
                "flags": "".join(ch for flag, ch in ((4, "R"), (2, "W"), (1, "X"))
                                 if p_flags & flag),
            })

    target_offsets = []
    pos = 0
    while True:
        pos = data.find(TARGET, pos)
        if pos == -1:
            break
        target_offsets.append(pos)
        pos += 1
        if len(target_offsets) > 8:
            raise ElfReferenceError("Too many repeated A2DP path strings")
    if len(target_offsets) != 1:
        raise ElfReferenceError("Expected exactly one embedded ODM A2DP path")
    offset = target_offsets[0]
    if offset == 0 or data[offset - 1] != 0 or data[offset + len(TARGET):offset + len(TARGET) + 1] != b"\x00":
        raise ElfReferenceError("Target is not a complete NUL-delimited ASCII string")
    mapped = [{
        "virtual_address": segment["vaddr"] + offset - segment["file_start"],
        "segment_file_start": segment["file_start"],
        "segment_flags": segment["flags"],
    } for segment in loads if segment["file_start"] <= offset < segment["file_end"]]
    if len(mapped) > 1:
        raise ElfReferenceError("Ambiguous PT_LOAD file offset mapping")

    sections = []
    symbol_info = {name: {"dynsym_name_count": 0, "undefined_dynsym_count": 0}
                   for name in WATCH_SYMBOLS}
    has_sections = bool(shoff and shnum)
    if has_sections:
        if shentsize < 40 or shnum > MAX_SHDR or shstrndx >= shnum:
            raise ElfReferenceError("Invalid section table metadata")
        check_region(data, shoff, shentsize * shnum, "section header table")
        raw = [
            struct.unpack_from("<IIIIIIIIII", data, shoff + i * shentsize)
            for i in range(shnum)
        ]
        if raw[shstrndx][1] != 3 or raw[shstrndx][5] > MAX_STRING_TABLE:
            raise ElfReferenceError("Invalid section-name string table")
        section_name_data = check_region(data, raw[shstrndx][4],
                                         raw[shstrndx][5], "section names")
        for idx, entry in enumerate(raw):
            sh_name, sh_type, sh_flags, sh_addr, sh_offset, sh_size, sh_link, _, _, sh_entsize = entry
            if sh_name >= len(section_name_data):
                raise ElfReferenceError("Invalid section name")
            name = bounded_cstring(section_name_data, sh_name)
            if sh_type != 8 and sh_size:
                check_region(data, sh_offset, sh_size, "section data")
            if sh_type != 8 and sh_offset <= offset < sh_offset + sh_size:
                sections.append({"index": idx, "name": name,
                                 "file_start": sh_offset, "file_end": sh_offset + sh_size,
                                 "sh_addr": sh_addr})
            if sh_type != 11:
                continue
            if (sh_entsize < 16 or sh_link >= shnum or
                sh_size // sh_entsize > MAX_SYMBOLS or sh_size % sh_entsize):
                raise ElfReferenceError("Bad SHT_DYNSYM")
            strings_section = raw[sh_link]
            if strings_section[1] != 3 or strings_section[5] > MAX_STRING_TABLE:
                raise ElfReferenceError("Bad dynsym linked string table")
            symbol_names = check_region(data, strings_section[4],
                                        strings_section[5], "dynsym strings")
            for n in range(sh_size // sh_entsize):
                st_name, _, _, _, _, st_shndx = struct.unpack_from(
                    "<IIIBBH", data, sh_offset + n * sh_entsize
                )
                if st_name >= len(symbol_names):
                    raise ElfReferenceError("Symbol name index out of range")
                name = bounded_cstring(symbol_names, st_name, 300)
                if name in symbol_info:
                    symbol_info[name]["dynsym_name_count"] += 1
                    if st_shndx == 0:
                        symbol_info[name]["undefined_dynsym_count"] += 1

    dlopen_imported = symbol_info["dlopen"]["undefined_dynsym_count"] > 0 if has_sections else None
    return {
        "schema": "op7t-hotdog-odm-audio-elf-path-segment-v1",
        "path": TARGET.decode(),
        "path_file_offset": offset,
        "path_file_offset_hex": hex(offset),
        "load_segment_mapping": mapped,
        "containing_sections": sections,
        "section_table_available": has_sections,
        "observed_dynamic_symbols": symbol_info,
        "dlopen_undefined_import_observed": dlopen_imported,
        "status": ("PATH_MAPPED_AND_DLOPEN_IMPORT_OBSERVED" if mapped and dlopen_imported
                   else "PATH_MAPPED_DLOPEN_IMPORT_UNVERIFIED" if mapped
                   else "PATH_NOT_MAPPED"),
        "proves_reference_from_code_to_path": False,
        "proves_runtime_dlopen_path_argument": False,
        "proves_library_loaded_at_runtime": False,
        "binary_executed": False,
        "binary_extracted": False,
        "flash_ready": False,
        "limitations": "File-offset-to-ELF-vaddr mapping is not a code cross-reference or runtime/ASLR address. Dynamic symbol imports alone do not bind the A2DP path to dlopen.",
    }


def inspect(zip_path, expect_zip_sha256, expect_elf_sha256):
    p = Path(zip_path)
    if not p.is_file() or not 0 < p.stat().st_size <= MAX_ARCHIVE:
        raise ElfReferenceError("ZIP missing or oversized")
    for digest in (expect_zip_sha256, expect_elf_sha256):
        if not digest or len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ElfReferenceError("Expected 64-char lowercase SHA256")
    if digest_file(p) != expect_zip_sha256:
        raise ElfReferenceError("ZIP SHA256 mismatch")
    data = read_audio_zip(p)
    if hashlib.sha256(data).hexdigest() != expect_elf_sha256:
        raise ElfReferenceError("Audio ELF SHA256 mismatch")
    result = inspect_elf(data)
    result["archive_sha256_matches_expected"] = True
    result["elf_sha256_matches_expected"] = True
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("archive", type=Path)
    p.add_argument("--expect-archive-sha256", required=True)
    p.add_argument("--expect-elf-sha256", required=True)
    args = p.parse_args(argv)
    try:
        report = inspect(args.archive, args.expect_archive_sha256, args.expect_elf_sha256)
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile,
            struct.error) as exc:
        print(f"ELF path/symbol probe FAILED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
