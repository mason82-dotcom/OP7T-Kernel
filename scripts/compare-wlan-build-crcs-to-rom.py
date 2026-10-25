#!/usr/bin/env python3
"""Compare locally extracted original OTA WLAN ELF with CI-only rebuilt CRC map.

Never loads or flashes a module; CI CRC map is build evidence, not a trusted
signature or proof of installed-device kernel ABI/ROM provenance.
"""
import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROM_SHA = "57037290bb57caefd3c337db3511fca5751fb4ef"
HEX_SHA = re.compile(r"^[a-f0-9]{64}$")
HEX_CRC = re.compile(r"^0x[a-f0-9]{8}$")
MAX_SYMBOLS = 8192


def load_abi():
    spec = importlib.util.spec_from_file_location(
        "wlan_rom_crc_map_elf", ROOT / "scripts" / "audit-module-abi.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ABI = load_abi()


def bounded_json(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 1024 * 1024:
        raise ValueError("Missing, symlinked, empty or oversized JSON evidence")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Expected JSON object")
    return value


def sha256_file(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def digest_map(symbols):
    return hashlib.sha256(
        json.dumps(symbols, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    ).hexdigest()


def compare(original_module, expected_original_sha256, built_map_file, compiled_report_file, self_report_file):
    if not isinstance(expected_original_sha256, str) or not HEX_SHA.fullmatch(expected_original_sha256):
        raise ValueError("Original ELF requires a prior independent SHA-256")
    original_module = Path(original_module)
    if (original_module.name != "qca_cld3_wlan.ko" or original_module.is_symlink()
            or not original_module.is_file()
            or not 0 < original_module.stat().st_size <= ABI.MAX_MODULE):
        raise ValueError("Original qca_cld3_wlan.ko missing, symlinked or oversized")
    if sha256_file(original_module) != expected_original_sha256:
        raise ValueError("Original ELF differs from expected independently obtained SHA-256")

    built = bounded_json(built_map_file)
    compiled = bounded_json(compiled_report_file)
    selfcheck = bounded_json(self_report_file)
    values = built.get("imported_symbol_crcs")
    if (built.get("schema") != "hotdog-wlan-built-import-crc-map-v1"
            or built.get("device") != "hotdog"
            or built.get("kernel_source_sha") != ROM_SHA
            or built.get("validated_against_same_build_Module_symvers") is not True
            or built.get("compared_against_original_ROM_wlan_ELF") is not False
            or built.get("flash_ready") is not False
            or selfcheck.get("schema") != "hotdog-built-wlan-self-crc-v1"
            or selfcheck.get("kernel_source_sha") != ROM_SHA
            or selfcheck.get("built_kernel_module_self_consistency") is not True
            or selfcheck.get("missing_exported_symbol_count") != 0
            or selfcheck.get("mismatched_symbol_crc_count") != 0
            or selfcheck.get("flash_ready") is not False
            or compiled.get("schema") != "hotdog-wlan-icnss-compile-attestation-v4"
            or compiled.get("upstream_sha") != ROM_SHA
            or compiled.get("installed_rom_module_abi_verified") is not False
            or compiled.get("signer_trust_on_installed_rom_verified") is not False
            or compiled.get("flash_ready") is not False):
        raise ValueError("One or more mutually bound ROM-source CI attestations are invalid")
    wm = compiled.get("wlan_module")
    if (not isinstance(wm, dict)
            or not isinstance(wm.get("vermagic"), str)
            or not wm["vermagic"].strip()
            or wm.get("signed_and_stripped") is not True
            or not isinstance(built.get("kernel_release"), str)
            or not built["kernel_release"].strip()
            or type(built.get("imported_symbol_count")) is not int):
        raise ValueError("Compiled WLAN metadata is missing, unsigned or malformed")
    if (built.get("rebuilt_wlan_module_sha256") != selfcheck.get("wlan_module_sha256")
            or built.get("rebuilt_wlan_module_sha256") != wm.get("sha256")
            or built.get("rebuilt_Module_symvers_sha256") != selfcheck.get("built_Module_symvers_sha256")
            or built.get("kernel_release") != selfcheck.get("kernel_release")
            or built.get("installed_kernel_module_key_trust_verified") is not False
            or built.get("imported_symbol_count") != selfcheck.get("built_module_symbols_versioned")
            or built.get("imported_symbol_count") != selfcheck.get("matched_against_same_build_Module_symvers")
            or wm.get("vermagic", "").split(" ")[0] != built.get("kernel_release")
            or not HEX_SHA.fullmatch(str(built.get("rebuilt_wlan_module_sha256", "")))):
        raise ValueError("Build CRC export does not bind to supplied same-run CI evidence")
    if (not isinstance(values, dict) or not 0 < len(values) <= MAX_SYMBOLS
            or built.get("imported_symbol_count") != len(values)
            or not all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) and isinstance(value, str)
                       and HEX_CRC.fullmatch(value) for key, value in values.items())
            or digest_map(values) != built.get("imported_symbol_map_sha256")):
        raise ValueError("Untrusted or malformed built symbol CRC map")

    rom = ABI.inspect(original_module)
    originals = rom.get("versions")
    if (rom.get("sha256") != expected_original_sha256
            or not rom.get("signature", {}).get("trailer_present")
            or not rom.get("has_versions_section")
            or not isinstance(originals, dict) or not originals
            or not isinstance(rom.get("vermagic"), str)
            or not rom["vermagic"].strip()):
        raise ValueError("Original OTA WLAN ELF missing valid signed symbol versions or vermagic")
    built_symbols = {key: int(value, 16) for key, value in values.items()}
    common = set(built_symbols) & set(originals)
    mismatch = sorted(k for k in common if built_symbols[k] != originals[k])
    built_only = sorted(set(built_symbols) - set(originals))
    rom_only = sorted(set(originals) - set(built_symbols))
    release_mismatch = wm["vermagic"] != rom["vermagic"]
    blockers = []
    if mismatch:
        blockers.append("shared_symbol_crc_mismatch")
    if built_only or rom_only:
        blockers.append("versioned_symbol_set_mismatch")
    if release_mismatch:
        blockers.append("vermagic_mismatch")
    original_map = {key: f"0x{crc:08x}" for key, crc in sorted(originals.items())}
    return {
        "schema": "hotdog-wlan-rom-vs-rom-pinned-ci-crcs-v1",
        "device": "hotdog",
        "rom_source_sha": ROM_SHA,
        "original_wlan_sha256": rom["sha256"],
        "rebuilt_wlan_sha256": built["rebuilt_wlan_module_sha256"],
        "original_wlan_vermagic": rom["vermagic"],
        "rebuilt_wlan_vermagic": wm["vermagic"],
        "original_crc_map_sha256": digest_map(original_map),
        "rebuilt_crc_map_sha256": built["imported_symbol_map_sha256"],
        "original_symbol_count": len(originals),
        "rebuilt_symbol_count": len(built_symbols),
        "common_symbol_count": len(common),
        "matching_crc_count": len(common) - len(mismatch),
        "different_crc_count": len(mismatch),
        "different_crc_samples": mismatch[:20],
        "built_only_symbol_count": len(built_only),
        "original_only_symbol_count": len(rom_only),
        "blockers": blockers,
        "status": "KNOWN_ABI_MISMATCH" if blockers else "OFFLINE_SYMBOL_PARITY_ONLY",
        "installed_ROM_provenance_verified": False,
        "kernel_signing_trust_verified": False,
        "runtime_monitor_mode_verified": False,
        "flash_ready": False,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--original-rom-wlan", required=True, type=Path)
    p.add_argument("--original-rom-sha256", required=True)
    p.add_argument("--built-map", required=True, type=Path)
    p.add_argument("--compiled-report", required=True, type=Path)
    p.add_argument("--selfcheck-report", required=True, type=Path)
    args = p.parse_args(argv)
    try:
        result = compare(args.original_rom_wlan, args.original_rom_sha256,
                         args.built_map, args.compiled_report, args.selfcheck_report)
    except (ValueError, OSError, json.JSONDecodeError, ABI.AuditError) as exc:
        print("WLAN CRC ROM comparison BLOCKED: " + str(exc), file=sys.stderr)
        return 3
    print(json.dumps(result, indent=2, sort_keys=True))
    return 2 if result["blockers"] else 4  # No result is flash approval


if __name__ == "__main__":
    sys.exit(main())
