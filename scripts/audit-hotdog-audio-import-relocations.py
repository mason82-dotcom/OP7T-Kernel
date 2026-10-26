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



def _arm_rotate_immediate(word):
    """Decode 32-bit ARM immediate with right rotate; no instruction execution."""
    imm = word & 0xff
    shift = ((word >> 8) & 0xf) * 2
    return ((imm >> shift) | (imm << (32 - shift))) & 0xffffffff if shift else imm


def _arm_add_ip(word, expected_base):
    # 32-bit ARM DP immediate: ADD ip,pc,#imm or ADD ip,ip,#imm.
    if ((word >> 25) & 7) != 1:
        return None
    if ((word >> 21) & 15) != 4 or ((word >> 20) & 1) != 0:
        return None
    if ((word >> 16) & 15) != expected_base or ((word >> 12) & 15) != 12:
        return None
    if ((word >> 28) & 15) == 15:
        return None
    return _arm_rotate_immediate(word)


def _arm_ldr_pc_ip(word):
    # ARM single-word LDR pc,[ip,#immediate] with pre-indexed addressing.
    if ((word >> 26) & 3) != 1 or ((word >> 25) & 1) != 0:
        return None
    if ((word >> 24) & 1) != 1 or ((word >> 22) & 1) != 0:
        return None
    if ((word >> 20) & 1) != 1:
        return None
    if ((word >> 16) & 15) != 12 or ((word >> 12) & 15) != 15:
        return None
    if ((word >> 28) & 15) == 15:
        return None
    displacement = word & 0xfff
    return displacement if ((word >> 23) & 1) else -displacement


def inspect_arm_plt_entry(data, plt_header, relocation_index, relocation_slot):
    """Validate a 16-byte PLT candidate by decoding 3 ARM opcodes.

    Does not map caller xrefs or prove the corresponding dlopen function is
    invoked. If any instruction deviates, report unverified, not a match.
    """
    start = plt_header["address"] + 32 + 16 * relocation_index
    end = plt_header["address"] + plt_header["size"]
    output = {
        "candidate_entry_vaddr_hex": hex(start),
        "assumed_entry_size_bytes": 16,
        "assumed_reserved_header_bytes": 32,
        "candidate_bounded_by_plt": start >= plt_header["address"] and start + 16 <= end,
        "arm32_three_instruction_pattern": False,
        "computed_got_slot_hex": None,
        "computed_got_matches_relocation_slot": False,
        "call_site_verified": False,
        "a2dp_argument_verified": False,
    }
    if not output["candidate_bounded_by_plt"]:
        return output
    file_off = plt_header["offset"] + start - plt_header["address"]
    bounded(data, file_off, 16, "ARM PLT candidate")
    first, second, third = struct.unpack_from("<III", data, file_off)
    a = _arm_add_ip(first, 15)
    b = _arm_add_ip(second, 12)
    c = _arm_ldr_pc_ip(third)
    if a is None or b is None or c is None:
        return output
    output["arm32_three_instruction_pattern"] = True
    target = (start + 8 + a + b + c) & 0xffffffff
    output["computed_got_slot_hex"] = hex(target)
    output["computed_got_matches_relocation_slot"] = target == relocation_slot
    return output


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
                         "size": size, "link": link, "entsize": entsize,
                         "address": addr, "flags": flags})

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

    # Section-header bounds only. PLT stub offsets must not be inferred
    # from relocation ordinal without architecture-specific validation.
    plt_sections = [{
        "name": entry["name"],
        "file_offset_hex": hex(entry["offset"]),
        "vaddr_hex": hex(entry["address"]),
        "size_bytes": entry["size"],
        "executable_flag": bool(entry["flags"] & 0x4),
    } for entry in sections if entry["name"] in (".plt", ".iplt", ".plt.got")]
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
                    "relocation_entry_index": i,
                    "relocation_offset_vaddr_hex": hex(r_offset),
                    "relocation_type_id": rtype,
                    "relocation_type_name": "R_ARM_JUMP_SLOT" if rtype == 22 else None,
                    "dynsym_index": symindex,
                    "undefined_symbol": sym["is_undefined"],
                })
    # This layout is only a candidate until the 3 ARM32 instructions are
    # decoded and their resulting GOT address equals the relocation slot.
    plt_candidates = {}
    plt = [sec for sec in sections if sec["name"] == ".plt"
           and sec["type"] == 1 and (sec["flags"] & 4)]
    relplt = [sec for sec in sections if sec["name"] == ".rel.plt"
              and sec["type"] == 9]
    exact_layout = (
        len(plt) == 1 and len(relplt) == 1
        and plt[0]["size"] == 32 + (relplt[0]["size"] // 8) * 16
        and relplt[0]["entsize"] == 8
    )
    if exact_layout:
        for import_name, record in observed.items():
            for sample in record["relocation_samples"]:
                if sample["section"] != ".rel.plt" or sample["relocation_type_id"] != 22:
                    continue
                plt_candidates[import_name] = inspect_arm_plt_entry(
                    data, plt[0], sample["relocation_entry_index"],
                    int(sample["relocation_offset_vaddr_hex"], 16)
                )
    return {
        "schema": "op7t-hotdog-audio-import-relocations-v2",
        "plt_32_plus_16_per_relplt_entry_layout_observed": exact_layout,
        "verified_arm_plt_candidates": plt_candidates,
        "scope": "ELF32_SHT_DYNSYM_and_REL_RELA_metadata_only",
        "relocation_sections_examined": scanned_sections,
        "plt_section_headers": plt_sections,
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
        "limitations": "Only a decoded three-instruction ARM PLT sequence whose GOT address equals its R_ARM_JUMP_SLOT is marked mapped; candidates alone never prove caller references or that the A2DP path is passed to dlopen.",
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
