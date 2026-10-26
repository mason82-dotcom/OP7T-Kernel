#!/usr/bin/env python3
"""Bounded, read-only ELF32 ARM A2DP string pointer/relocation candidate probe.

This is not a disassembler. It NEVER proves that a given instruction uses the
A2DP path or that the library is loaded by dlopen at runtime. Reads precisely
one ZIP member in memory, checks pinned ZIP/ELF SHA-256, writes JSON only.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import zipfile

ZIP_ROOT = "proprietary_vendor_oneplus_hotdog-17.0/"
MEMBER = "proprietary/odm/lib/hw/audio.primary.msmnile.so"
NEEDLE = b"/odm/lib/liba2dpoffload.so"
MAX_ARCHIVE_BYTES = 8 * 1024**3
MAX_ELF_BYTES = 8 * 1024 * 1024
MAX_ZIP_FILES = 100000
MAX_PROGRAM_HEADERS = 256
MAX_SECTION_HEADERS = 8192
MAX_RELOCATIONS = 200000
MAX_CANDIDATE_SAMPLES = 24
SHT_RELA = 4
SHT_REL = 9


class ProbeError(ValueError):
    pass


def checked_region(blob, offset, length, what):
    if offset < 0 or length < 0 or offset > len(blob) or length > len(blob) - offset:
        raise ProbeError("Invalid range for " + what)
    return blob[offset:offset + length]


def sha256_file(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def expected_digest(value, label):
    if not isinstance(value, str) or len(value) != 64 or any(
        c not in "0123456789abcdef" for c in value
    ):
        raise ProbeError("Expected lowercase SHA256 for " + label)


def zip_audio(path):
    with zipfile.ZipFile(path) as z:
        entries = z.infolist()
        if not 0 < len(entries) <= MAX_ZIP_FILES:
            raise ProbeError("Invalid ZIP entry count")
        roots = set()
        selected = []
        for entry in entries:
            name = entry.filename
            if not name or name.startswith("/") or "\\" in name or "\x00" in name or len(name) > 1024:
                raise ProbeError("Unsafe ZIP entry name")
            parts = name.rstrip("/").split("/")
            if any(piece in ("", ".", "..") for piece in parts):
                raise ProbeError("Unsafe ZIP path component")
            roots.add(parts[0])
            if name == ZIP_ROOT + MEMBER and not entry.is_dir():
                selected.append(entry)
        if roots != {ZIP_ROOT[:-1]} or len(selected) != 1:
            raise ProbeError("Unexpected ZIP root or audio member")
        member = selected[0]
        if not 52 <= member.file_size <= MAX_ELF_BYTES:
            raise ProbeError("Audio ELF exceeds size bounds")
        with z.open(member) as f:
            blob = f.read(MAX_ELF_BYTES + 1)
        if len(blob) != member.file_size:
            raise ProbeError("Audio member is truncated or oversized")
    return blob


def c_string(data, offset):
    if not 0 <= offset < len(data):
        raise ProbeError("Invalid ELF section-name offset")
    end = data.find(b"\x00", offset, min(len(data), offset + 160))
    if end == -1:
        raise ProbeError("Unterminated ELF section name")
    raw = data[offset:end]
    if any(c < 32 or c > 126 for c in raw):
        raise ProbeError("Nonprintable ELF section name")
    return raw.decode("ascii")


def parse_elf(data):
    if len(data) < 52 or data[:7] != b"\x7fELF\x01\x01\x01":
        raise ProbeError("Not an ELF32 little-endian EV_CURRENT file")
    header = struct.unpack_from("<HHIIIIIHHHHHH", data, 16)
    (e_type, e_machine, version, _, phoff, shoff, _, ehsize, phentsize,
     phnum, shentsize, shnum, shstridx) = header
    if (e_type != 3 or e_machine != 40 or version != 1 or ehsize < 52 or
        phentsize < 32 or not 0 < phnum <= MAX_PROGRAM_HEADERS):
        raise ProbeError("Expected ARM32 ET_DYN with bounded program headers")
    checked_region(data, phoff, phentsize * phnum, "program header table")
    loads = []
    for i in range(phnum):
        p_type, p_offset, p_vaddr, _, p_filesz, _, p_flags, _ = struct.unpack_from(
            "<IIIIIIII", data, phoff + i * phentsize
        )
        if p_type == 1:
            checked_region(data, p_offset, p_filesz, "PT_LOAD")
            loads.append((p_offset, p_vaddr, p_filesz, p_flags))
    if not loads:
        raise ProbeError("No PT_LOAD segments")

    occurrences = []
    cursor = 0
    while True:
        cursor = data.find(NEEDLE, cursor)
        if cursor == -1:
            break
        occurrences.append(cursor)
        cursor += 1
        if len(occurrences) > 8:
            raise ProbeError("Unexpected repeated A2DP path")
    if len(occurrences) != 1:
        raise ProbeError("Require one complete A2DP path string")
    offset = occurrences[0]
    if (offset == 0 or data[offset - 1] != 0 or
        data[offset + len(NEEDLE):offset + len(NEEDLE) + 1] != b"\x00"):
        raise ProbeError("A2DP path is not exactly NUL delimited")
    origins = [
        p_vaddr + offset - p_off
        for p_off, p_vaddr, p_size, _ in loads
        if p_off <= offset and offset + len(NEEDLE) <= p_off + p_size
    ]
    if len(set(origins)) != 1 or not origins:
        raise ProbeError("Ambiguous/unmapped A2DP virtual address")
    target_va = origins[0]
    if target_va > 0xffffffff:
        raise ProbeError("Target virtual address overflow")

    def virtual_to_file(va, width):
        found = []
        for p_off, p_vaddr, p_size, _ in loads:
            if p_vaddr <= va and width <= p_size - (va - p_vaddr):
                found.append(p_off + va - p_vaddr)
        if len(set(found)) != 1:
            return None
        return found[0]

    sections = []
    section_rows = []
    section_names = None
    if shoff or shnum:
        if (not shoff or not shnum or shentsize < 40 or
            shnum > MAX_SECTION_HEADERS or shstridx >= shnum):
            raise ProbeError("Invalid section-header layout")
        checked_region(data, shoff, shentsize * shnum, "section header table")
        section_rows = [
            struct.unpack_from("<IIIIIIIIII", data, shoff + j * shentsize)
            for j in range(shnum)
        ]
        name_row = section_rows[shstridx]
        if name_row[1] != 3 or name_row[5] > 4 * 1024 * 1024:
            raise ProbeError("Invalid section name string table")
        section_names = checked_region(data, name_row[4], name_row[5], "section-name table")
        for i, row in enumerate(section_rows):
            sh_name, sh_type, _, sh_addr, sh_offset, sh_size, _, _, _, _ = row
            if sh_name >= len(section_names):
                raise ProbeError("Invalid section-name index")
            name = c_string(section_names, sh_name)
            if sh_type != 8 and sh_size:
                checked_region(data, sh_offset, sh_size, "section data")
            sections.append({
                "name": name,
                "index": i,
                "type": sh_type,
                "offset": sh_offset,
                "size": sh_size,
                "address": sh_addr
            })

    containing_sections = [
        row["name"] for row in sections
        if row["type"] != 8 and row["offset"] <= offset
        and offset + len(NEEDLE) <= row["offset"] + row["size"]
    ]
    # Pure equality scan: these are candidate encoded 32-bit *values*, not
    # instructions or validated pointers. Only 4-byte-aligned positions.
    encoded = struct.pack("<I", target_va)
    candidate_offsets = [
        i for i in range(0, len(data) - 3, 4)
        if data[i:i + 4] == encoded
    ]
    candidate_samples = []
    for i in candidate_offsets[:MAX_CANDIDATE_SAMPLES]:
        mapped_sections = [
            row["name"] for row in sections
            if row["type"] != 8 and row["offset"] <= i < row["offset"] + row["size"]
        ]
        candidate_samples.append({
            "file_offset": i,
            "hex": hex(i),
            "section_names": mapped_sections[:5],
        })

    reloc_sections = []
    matching_relocs = []
    parsed_relocs = 0
    for row in section_rows:
        (name_idx, typ, _, _, sec_off, sec_size, _, _, _, entsize) = row
        if typ not in (SHT_REL, SHT_RELA):
            continue
        min_size = 8 if typ == SHT_REL else 12
        if entsize < min_size or sec_size % entsize:
            raise ProbeError("Invalid ELF relocation entry layout")
        count = sec_size // entsize
        parsed_relocs += count
        if parsed_relocs > MAX_RELOCATIONS:
            raise ProbeError("Too many ELF relocation entries")
        name = c_string(section_names, name_idx)
        matched = 0
        for i in range(count):
            entry = sec_off + i * entsize
            r_va, info = struct.unpack_from("<II", data, entry)
            r_type = info & 0xff
            r_symbol_index = info >> 8
            if typ == SHT_RELA:
                addend = struct.unpack_from("<i", data, entry + 8)[0] & 0xffffffff
            else:
                slot_file = virtual_to_file(r_va, 4)
                if slot_file is None:
                    continue
                addend = struct.unpack_from("<I", data, slot_file)[0]
            if addend == target_va:
                matched += 1
                if len(matching_relocs) < MAX_CANDIDATE_SAMPLES:
                    matching_relocs.append({
                        "relocation_section": name,
                        "relocation_target_vaddr": hex(r_va),
                        "type_id": r_type,
                        "symbol_index": r_symbol_index,
                        "raw_addend_equals_path_vaddr": True
                    })
        reloc_sections.append({"name": name, "entries": count,
                               "equal_a2dp_addend_count": matched})

    total_matches = sum(r["equal_a2dp_addend_count"] for r in reloc_sections)
    return {
        "schema": "op7t-hotdog-a2dp-relocations-v1",
        "elf_file_path_offset": offset,
        "elf_path_virtual_address": target_va,
        "elf_path_virtual_address_hex": hex(target_va),
        "containing_section_names": containing_sections,
        "relocation_sections": reloc_sections,
        "total_relocation_entries": parsed_relocs,
        "relocation_entries_with_path_equal_addend": total_matches,
        "relocation_matches_samples": matching_relocs,
        "aligned_raw_32bit_equal_value_count": len(candidate_offsets),
        "aligned_raw_32bit_equal_value_samples": candidate_samples,
        "status": ("A2DP_RELOCATION_CANDIDATES_FOUND" if total_matches
                   else "A2DP_ALIGNED_POINTER_VALUE_CANDIDATES_FOUND" if candidate_offsets
                   else "NO_SIMPLE_A2DP_POINTER_CANDIDATES"),
        "proves_instructions_reference_path": False,
        "proves_dlopen_receives_a2dp_path": False,
        "proves_runtime_loading": False,
        "elf_executed": False,
        "elf_extracted": False,
        "flash_ready": False,
        "limitations": "Equal REL/RELA addends and raw aligned words are candidate pointer values only; indirect PC-relative addressing and ARM/Thumb code paths are not decoded.",
    }


def inspect(path, archive_sha, elf_sha):
    path = Path(path)
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_ARCHIVE_BYTES:
        raise ProbeError("Missing or oversized ZIP")
    expected_digest(archive_sha, "archive")
    expected_digest(elf_sha, "ELF")
    if sha256_file(path) != archive_sha:
        raise ProbeError("ZIP SHA256 differs from pinned observation")
    elf = zip_audio(path)
    if hashlib.sha256(elf).hexdigest() != elf_sha:
        raise ProbeError("ELF SHA256 differs from pinned observation")
    result = parse_elf(elf)
    result["archive_sha256_verified"] = True
    result["elf_sha256_verified"] = True
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--expect-archive-sha256", required=True)
    parser.add_argument("--expect-elf-sha256", required=True)
    opts = parser.parse_args(argv)
    try:
        report = inspect(opts.archive, opts.expect_archive_sha256, opts.expect_elf_sha256)
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, struct.error) as exc:
        print(f"ELF relocation probe FAILED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
