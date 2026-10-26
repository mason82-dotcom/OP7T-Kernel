#!/usr/bin/env python3
"""Read-only ARM32 ELF relocation imports for dlopen/dlsym.

Reads one SHA256-pinned ELF member in bounded memory from local hotdog vendor
ZIP. Parses ELF32 SHT_DYNSYM and REL/RELA symbol-indexed relocations. Reports
imported-function relocation slots, NOT call sites, PLT stubs, control flow,
runtime behavior or A2DP string uses. No blob extraction or execution.
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
EXPECTED_ZIP_SHA = "c038a3ccab574795c496d043f4d735b920dbbbab279232229a80c94aa32a0078"
EXPECTED_ELF_SHA = "08a20a73c123c793d717f1b8e7078df1b9efb3853753fae7fac269d3a20a829f"
WATCH = ("dlopen", "dlsym", "android_dlopen_ext")
MAX_ARCHIVE = 8 * 1024**3
MAX_ELF = 8 * 1024**2
MAX_ENTRIES = 100000
MAX_SECTIONS = 8192
MAX_RELOCATIONS = 200000
MAX_SYMBOLS = 100000
MAX_DYNSTR = 4 * 1024**2
MAX_SAMPLES = 16


class ImportRelocationError(ValueError):
    pass


def bounded(data, offset, size, label):
    if offset < 0 or size < 0 or offset > len(data) or size > len(data) - offset:
        raise ImportRelocationError("Out-of-bounds " + label)
    return data[offset:offset + size]


def sha_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as reader:
        for chunk in iter(lambda: reader.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def checked_zip(path):
    path = Path(path)
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_ARCHIVE:
        raise ImportRelocationError("Missing or oversized ZIP")
    if sha_file(path) != EXPECTED_ZIP_SHA:
        raise ImportRelocationError("ZIP SHA256 does not match pinned source")
    with zipfile.ZipFile(path) as z:
        entries = z.infolist()
        if not 0 < len(entries) <= MAX_ENTRIES:
            raise ImportRelocationError("ZIP member count out of bounds")
        roots = set()
        matches = []
        for entry in entries:
            n = entry.filename
            if (not n or n.startswith("/") or "\\" in n or "\x00" in n
                    or len(n) > 1024):
                raise ImportRelocationError("Unsafe ZIP member")
            parts = n.rstrip("/").split("/")
            if any(p in ("", ".", "..") for p in parts):
                raise ImportRelocationError("Unsafe ZIP path")
            roots.add(parts[0])
            if n == ZIP_ROOT + MEMBER and not entry.is_dir():
                matches.append(entry)
        if roots != {ZIP_ROOT[:-1]} or len(matches) != 1:
            raise ImportRelocationError("Unexpected ZIP root or audio ELF")
        item = matches[0]
        if not 52 <= item.file_size <= MAX_ELF:
            raise ImportRelocationError("Unexpected ELF size")
        with z.open(item) as stream:
            data = stream.read(MAX_ELF + 1)
        if len(data) != item.file_size:
            raise ImportRelocationError("Truncated or oversized ELF member")
    if hashlib.sha256(data).hexdigest() != EXPECTED_ELF_SHA:
        raise ImportRelocationError("ELF SHA256 does not match pinned source")
    return data


def cstring(data, offset):
    if not 0 <= offset < len(data):
        raise ImportRelocationError("Invalid ELF string offset")
    end = data.find(b"\0", offset, min(len(data), offset + 257))
    if end < 0:
        raise ImportRelocationError("Unterminated/oversized ELF string")
    name = data[offset:end]
    if any(not 32 <= c <= 126 for c in name):
        raise ImportRelocationError("Non-printable ELF symbol/section string")
    return name.decode("ascii")


def inspect_elf(data):
    if len(data) < 52 or data[:7] != b"\x7fELF\x01\x01\x01":
        raise ImportRelocationError("Expected ELF32 little-endian")
    fields = struct.unpack_from("<HHIIIIIHHHHHH", data, 16)
    (etype, machine, version, _, _, shoff, _, ehsize, _, _, shentsize,
     shnum, shstrndx) = fields
    if etype != 3 or machine != 40 or version != 1 or ehsize < 52:
        raise ImportRelocationError("Expected ARM ELF32 ET_DYN")
    if not shoff or shentsize < 40 or not 0 < shnum <= MAX_SECTIONS or shstrndx >= shnum:
        raise ImportRelocationError("Section headers required for exact symbol relocation resolution")
    bounded(data, shoff, shnum * shentsize, "section header table")
    rows = [struct.unpack_from("<IIIIIIIIII", data, shoff + i * shentsize)
            for i in range(shnum)]
    shstr = rows[shstrndx]
    if shstr[1] != 3 or shstr[5] > MAX_DYNSTR:
        raise ImportRelocationError("Invalid section-name string table")
    shstrdata = bounded(data, shstr[4], shstr[5], "section name strings")
    sections = []
    for i, row in enumerate(rows):
        name, typ, flags, addr, offset, size, link, info, align, entsize = row
        if name >= len(shstrdata):
            raise ImportRelocationError("Section-name index out of range")
        textname = cstring(shstrdata, name)
        if typ != 8 and size:
            bounded(data, offset, size, "section body")
        sections.append({"name": textname, "type": typ, "offset": offset,
                         "size": size, "link": link, "entsize": entsize})

    symbols = {}
    dynsym_sections = set()
    for idx, section in enumerate(sections):
        if section["type"] != 11:
            continue
        link = section["link"]
        size, esize = section["size"], section["entsize"]
        if link >= len(sections) or sections[link]["type"] != 3 or (
            esize < 16 or not esize or size % esize or size // esize > MAX_SYMBOLS
        ):
            raise ImportRelocationError("Invalid dynsym layout")
        linked = sections[link]
        if linked["size"] > MAX_DYNSTR:
            raise ImportRelocationError("Oversized dynamic symbol string table")
        strings = bounded(data, linked["offset"], linked["size"], "dynstr")
        syms = []
        for i in range(size // esize):
            st_name, _, _, _, _, st_shndx = struct.unpack_from(
                "<IIIBBH", data, section["offset"] + i * esize
            )
            if st_name >= len(strings):
                raise ImportRelocationError("Dynsym string offset out of bounds")
            syms.append({"name": cstring(strings, st_name),
                         "is_undefined": st_shndx == 0})
        symbols[idx] = syms
        dynsym_sections.add(idx)

    if not dynsym_sections:
        raise ImportRelocationError("No SHT_DYNSYM found")
    observed = {name: {"undefined_dynsym_count": 0,
                       "relocation_entry_count": 0,
                       "relocation_samples": []} for name in WATCH}
    for symbol_table in symbols.values():
        for sym in symbol_table:
            if sym["name"] in observed and sym["is_undefined"]:
                observed[sym["name"]]["undefined_dynsym_count"] += 1

    scanned = 0
    scanned_sections = []
    for section in sections:
        typ = section["type"]
        if typ not in (9, 4):  # SHT_REL, SHT_RELA
            continue
        esize = section["entsize"]
        minimum = 8 if typ == 9 else 12
        size = section["size"]
        if esize < minimum or not esize or size % esize:
            raise ImportRelocationError("Invalid REL/RELA entry size")
        count = size // esize
        scanned += count
        if scanned > MAX_RELOCATIONS:
            raise ImportRelocationError("Too many relocation entries")
        scanned_sections.append({"section": section["name"], "entries": count})
        symbol_table = symbols.get(section["link"])
        if symbol_table is None:
            # Other relocation sections may use non-dynamic symbol tables.
            continue
        for i in range(count):
            loc = section["offset"] + i * esize
            r_offset, r_info = struct.unpack_from("<II", data, loc)
            symindex = r_info >> 8
            rtype = r_info & 255
            if symindex >= len(symbol_table):
                raise ImportRelocationError("Relocation dynsym index out of range")
            sym = symbol_table[symindex]
            if sym["name"] not in observed:
                continue
            slot = observed[sym["name"]]
            slot["relocation_entry_count"] += 1
            if len(slot["relocation_samples"]) < MAX_SAMPLES:
                slot["relocation_samples"].append({
                    "section": section["name"],
                    "relocation_offset_vaddr_hex": hex(r_offset),
                    "relocation_type_id": rtype,
                    "dynsym_index": symindex,
                    "undefined_symbol": sym["is_undefined"],
                })
    return {
        "schema": "op7t-hotdog-audio-import-relocations-v1",
        "scope": "ELF32_SHT_DYNSYM_and_REL_RELA_metadata_only",
        "relocation_sections_examined": scanned_sections,
        "total_relocation_entries_examined": scanned,
        "loader_imports": observed,
        "status": "IMPORT_RELOCATION_METADATA_RECORDED",
        "proves_plt_stub_address": False,
        "proves_dlopen_called_from_audio_hal": False,
        "proves_a2dp_path_argument_passed_to_dlopen": False,
        "proves_runtime_a2dp_loading": False,
        "elf_executed": False,
        "elf_extracted_to_disk": False,
        "flash_ready": False,
        "limitations": "Relocation slots are ELF link-time vaddrs, not disassembled PLT stub or call sites. No ARM/Thumb dataflow or device runtime examined.",
    }


def inspect(path):
    r = inspect_elf(checked_zip(path))
    r["zip_sha256_verified"] = True
    r["elf_sha256_verified"] = True
    return r


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("archive", type=Path)
    opts = p.parse_args(argv)
    try:
        report = inspect(opts.archive)
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile,
            struct.error) as exc:
        print(f"ELF import relocation audit FAILED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
