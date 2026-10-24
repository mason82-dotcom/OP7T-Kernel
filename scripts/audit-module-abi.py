#!/usr/bin/env python3
"""Offline, read-only ARM64 Linux 4.14 module symbol CRC comparison.

No ADB, network, root, ELF execution, extraction, module loading, or flashing.
Results are evidence, never release authorization.
"""
import argparse
import hashlib
import json
import re
import struct
import sys
from pathlib import Path

MAX_MODULE = 96 * 1024 * 1024
MAX_SYMVERS = 32 * 1024 * 1024
ELF_HEADER = struct.Struct("<16sHHIQQQIHHHHHH")
SECTION_HEADER = struct.Struct("<IIQQQQIIQQ")
VERSION_RECORD = struct.Struct("<Q56s")
SIGNATURE_MARKER = b"~Module signature appended~\n"
SYMBOL = re.compile(r"^[A-Za-z_.$][A-Za-z0-9_.$]*$")
SYMVERS_CRC = re.compile(r"^0x[0-9a-fA-F]{1,8}$")


class AuditError(ValueError):
    pass


def bounded_file(path: Path, limit: int) -> bytes:
    if not path.is_file() or path.stat().st_size == 0:
        raise AuditError("Input missing or empty")
    if path.stat().st_size > limit:
        raise AuditError("Input exceeds size limit")
    return path.read_bytes()


def section_data(blob: bytes) -> dict:
    if len(blob) < ELF_HEADER.size:
        raise AuditError("Truncated ELF header")
    (ident, etype, machine, version, _entry, _phoff, shoff, _flags,
     ehsize, _phentsize, _phnum, shentsize, shnum, names_index) = ELF_HEADER.unpack_from(blob)
    if ident[:4] != b"\x7fELF" or ident[4:7] != bytes((2, 1, 1)):
        raise AuditError("Expected little-endian 64-bit ELF")
    if etype != 1 or machine != 183 or version != 1 or ehsize != 64:
        raise AuditError("Expected relocatable AArch64 ELF")
    if shentsize != SECTION_HEADER.size or not (2 <= shnum <= 8192):
        raise AuditError("Unsupported ELF section table")
    if not (0 < names_index < shnum) or shoff < 64 or shoff + shnum * shentsize > len(blob):
        raise AuditError("Invalid ELF section table bounds")

    raw_sections = []
    for n in range(shnum):
        (name, section_type, _flags, _addr, offset, size, _link, _info,
         _align, _entsize) = SECTION_HEADER.unpack_from(blob, shoff + n * shentsize)
        if section_type != 8 and offset + size > len(blob):
            raise AuditError("Out-of-bounds ELF section")
        raw_sections.append((name, section_type, offset, size))
    _, ntype, name_offset, name_size = raw_sections[names_index]
    if ntype != 3:
        raise AuditError("Missing ELF section string table")
    table = blob[name_offset:name_offset + name_size]
    result = {}
    for name, section_type, offset, size in raw_sections:
        if name >= len(table):
            raise AuditError("Invalid ELF section name")
        end = table.find(b"\x00", name)
        if end < 0:
            raise AuditError("Unterminated ELF section name")
        try:
            decoded = table[name:end].decode("ascii")
        except UnicodeDecodeError as error:
            raise AuditError("Non-ASCII ELF section name") from error
        if decoded in (".modinfo", "__versions"):
            if decoded in result or section_type == 8:
                raise AuditError("Duplicate or invalid required section")
            result[decoded] = blob[offset:offset + size]
    return result


def parse_modinfo(raw: bytes) -> dict:
    items = {}
    for item in raw.split(b"\x00"):
        if b"=" not in item:
            continue
        k, v = item.split(b"=", 1)
        if k in (b"vermagic", b"name", b"depends"):
            key = k.decode("ascii")
            if key in items:
                raise AuditError("Duplicate module info key")
            value = v.decode("utf-8", errors="replace")
            if not value or len(value) > 1024:
                raise AuditError("Invalid module info value")
            items[key] = value
    if not items.get("vermagic"):
        raise AuditError("Missing ELF .modinfo vermagic")
    return items


def parse_versions(raw: bytes) -> dict:
    if not raw:
        return {}
    if len(raw) % VERSION_RECORD.size:
        raise AuditError("Malformed __versions record length")
    if len(raw) // VERSION_RECORD.size > 100000:
        raise AuditError("Too many __versions entries")
    result = {}
    for offset in range(0, len(raw), VERSION_RECORD.size):
        wide_crc, name_bytes = VERSION_RECORD.unpack_from(raw, offset)
        name_bytes = name_bytes.split(b"\x00", 1)[0]
        try:
            name = name_bytes.decode("ascii")
        except UnicodeDecodeError as error:
            raise AuditError("Invalid CRC symbol name encoding") from error
        if not SYMBOL.fullmatch(name) or name in result:
            raise AuditError("Invalid or duplicate CRC symbol name")
        result[name] = wide_crc & 0xffffffff
    return result


def signature_trailer(blob: bytes) -> dict:
    if not blob.endswith(SIGNATURE_MARKER):
        return {"trailer_present": False, "cryptographically_verified": False}
    pos = len(blob) - len(SIGNATURE_MARKER)
    if pos < 12:
        raise AuditError("Truncated module signature footer")
    fields = blob[pos - 12:pos]
    sig_length = int.from_bytes(fields[8:12], "big")
    if sig_length == 0 or sig_length > pos - 12:
        raise AuditError("Invalid module signature length")
    return {
        "trailer_present": True,
        "signature_bytes": sig_length,
        "pkcs7_id_type": fields[2],
        "cryptographically_verified": False,
    }


def inspect(path: Path) -> dict:
    blob = bounded_file(path, MAX_MODULE)
    sections = section_data(blob)
    if ".modinfo" not in sections:
        raise AuditError("No .modinfo section")
    details = parse_modinfo(sections[".modinfo"])
    versions = parse_versions(sections["__versions"]) if "__versions" in sections else None
    return {
        "filename": path.name,
        "sha256": hashlib.sha256(blob).hexdigest(),
        "size_bytes": len(blob),
        "module_name": details.get("name"),
        "vermagic": details["vermagic"],
        "module_dependencies": details.get("depends"),
        "has_versions_section": versions is not None,
        "symbol_crc_count": len(versions) if versions is not None else 0,
        "versions": versions,
        "signature": signature_trailer(blob),
    }


def parse_symvers(path: Path) -> dict:
    raw = bounded_file(path, MAX_SYMVERS)
    symbols = {}
    for line in raw.decode("utf-8", errors="replace").splitlines():
        parts = line.split()
        if len(parts) < 3 or not SYMVERS_CRC.fullmatch(parts[0]) or not SYMBOL.fullmatch(parts[1]):
            raise AuditError("Invalid Module.symvers record")
        crc = int(parts[0], 16)
        if parts[1] in symbols and symbols[parts[1]] != crc:
            raise AuditError("Conflicting CRCs in Module.symvers")
        symbols[parts[1]] = crc
    if not symbols:
        raise AuditError("No Module.symvers records")
    return symbols


def compare(built: dict, rom: dict, symvers=None) -> dict:
    left, right = built["versions"], rom["versions"]
    unknowns = []
    blockers = []
    if built["vermagic"] != rom["vermagic"]:
        blockers.append("vermagic_mismatch")
    if built["module_name"] and rom["module_name"] and built["module_name"] != rom["module_name"]:
        blockers.append("module_name_mismatch")
    if left is None or right is None:
        unknowns.append("one_or_both_modules_lack___versions")
        common = set()
    else:
        common = set(left).intersection(right)
        if not common:
            unknowns.append("no_common_versioned_symbols")
    mismatched = sorted(name for name in common if left[name] != right[name])
    if mismatched:
        blockers.append("shared_symbol_crc_mismatch")
    symvers_checked = 0
    symvers_missing = 0
    symvers_bad = []
    if symvers is not None and right is not None:
        for name, crc in right.items():
            if name not in symvers:
                symvers_missing += 1
            else:
                symvers_checked += 1
                if symvers[name] != crc:
                    symvers_bad.append(name)
        if symvers_bad:
            blockers.append("rom_symbol_crc_differs_from_built_Module.symvers")
        if not symvers_checked:
            unknowns.append("no_rom_symbols_resolved_in_built_Module.symvers")
        if symvers_missing:
            unknowns.append("rom_symbols_missing_from_built_Module.symvers")
    elif symvers is None:
        unknowns.append("built_Module.symvers_not_supplied")
    else:
        unknowns.append("rom_lacks_versioned_symbol_dependencies")
    if not built["signature"]["trailer_present"]:
        unknowns.append("built_module_has_no_signature_trailer")
    if not rom["signature"]["trailer_present"]:
        unknowns.append("rom_module_has_no_signature_trailer")

    def summary(record):
        return {key: record[key] for key in (
            "filename", "sha256", "size_bytes", "module_name", "vermagic",
            "module_dependencies", "has_versions_section", "symbol_crc_count", "signature"
        )}

    return {
        "schema": "op7t-offline-elf-symbol-crc-v1",
        "built": summary(built),
        "rom": summary(rom),
        "shared_versioned_symbol_count": len(common),
        "different_symbol_crc_count": len(mismatched),
        "different_symbol_crc_samples": mismatched[:20],
        "built_only_symbol_count": len(set(left or {}) - set(right or {})),
        "rom_only_symbol_count": len(set(right or {}) - set(left or {})),
        "rom_symbol_matches_built_symvers_count": symvers_checked - len(symvers_bad),
        "rom_symbol_mismatches_built_symvers_count": len(symvers_bad),
        "rom_symbol_mismatch_samples": sorted(symvers_bad)[:20],
        "rom_symbols_not_in_built_symvers_count": symvers_missing,
        "blockers": sorted(set(blockers)),
        "unknowns": sorted(set(unknowns)),
        "status": "known_metadata_or_symbol_crc_mismatch" if blockers else "abi_and_trust_not_proven",
        "module_signature_cryptographically_verified": False,
        "installed_kernel_module_key_trust_verified": False,
        "full_kernel_vendor_abi_verified": False,
        "exact_installed_rom_provenance_verified": False,
        "flash_ready": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--built", type=Path, required=True, help="rebuilt signed WLAN .ko")
    parser.add_argument("--rom", type=Path, required=True, help="original WLAN .ko from exact installed ROM")
    parser.add_argument("--symvers", type=Path, help="matching rebuilt kernel Module.symvers")
    args = parser.parse_args(argv)
    try:
        result = compare(inspect(args.built), inspect(args.rom),
                         parse_symvers(args.symvers) if args.symvers else None)
    except (AuditError, OSError) as error:
        print(f"Offline ABI audit FAILED: {error}", file=sys.stderr)
        return 3
    print(json.dumps(result, indent=2, sort_keys=True))
    return 2 if result["blockers"] else 0


if __name__ == "__main__":
    sys.exit(main())
