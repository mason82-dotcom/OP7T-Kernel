#!/usr/bin/env python3
"""Export the ROM-pinned *rebuilt* WLAN import CRC map as bounded CI evidence.

Only runs after the existing signed/stripped WLAN module and same-build
Module.symvers self-consistency gate. No binaries, keys, or device files
leave the runner. This map is not a live-device kernel ABI attestation.
"""
import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROM_SHA = "57037290bb57caefd3c337db3511fca5751fb4ef"
WLAN_REL = "modules/drivers/staging/qcacld-3.0/wlan.ko"
SAFE_SYMBOL = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
MAX_SYMBOLS = 8192


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SELF = load("wlan_crc_export_self", "audit-wlan-built-crcs.py")
ABI = load("wlan_crc_export_elf", "audit-module-abi.py")


def canonical_map_digest(symbols):
    return hashlib.sha256(
        json.dumps(symbols, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    ).hexdigest()


def generate(artifacts):
    artifacts = Path(artifacts)
    selfcheck = SELF.check(artifacts)
    if (selfcheck.get("schema") != "hotdog-built-wlan-self-crc-v1"
            or selfcheck.get("kernel_source_sha") != ROM_SHA
            or selfcheck.get("built_kernel_module_self_consistency") is not True
            or selfcheck.get("flash_ready") is not False):
        raise ValueError("ROM-source signed WLAN self-check not approved")
    elf_path = artifacts / WLAN_REL
    if elf_path.is_symlink() or not elf_path.is_file() or not 0 < elf_path.stat().st_size <= ABI.MAX_MODULE:
        raise ValueError("Signed rebuilt WLAN ELF absent or unsafe")
    result = ABI.inspect(elf_path)
    crc = result.get("versions")
    if (result.get("sha256") != selfcheck["wlan_module_sha256"]
            or not result.get("signature", {}).get("trailer_present")
            or not result.get("has_versions_section")
            or not isinstance(crc, dict)
            or not 0 < len(crc) <= MAX_SYMBOLS
            or not all(isinstance(k, str) and SAFE_SYMBOL.fullmatch(k)
                       and type(v) is int and 0 <= v <= 0xffffffff
                       for k, v in crc.items())):
        raise ValueError("Signed ROM-source WLAN ELF imported CRC data invalid")
    symbols = {name: f"0x{crc[name]:08x}" for name in sorted(crc)}
    return {
        "schema": "hotdog-wlan-built-import-crc-map-v1",
        "device": "hotdog",
        "kernel_source_sha": ROM_SHA,
        "kernel_release": selfcheck["kernel_release"],
        "rebuilt_wlan_module_sha256": result["sha256"],
        "rebuilt_Module_symvers_sha256": selfcheck["built_Module_symvers_sha256"],
        "validated_against_same_build_Module_symvers": True,
        "imported_symbol_count": len(symbols),
        "imported_symbol_map_sha256": canonical_map_digest(symbols),
        "imported_symbol_crcs": symbols,
        "compared_against_original_ROM_wlan_ELF": False,
        "installed_kernel_module_key_trust_verified": False,
        "flash_ready": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", required=True, type=Path)
    args = parser.parse_args(argv)
    out = args.artifacts / "built-wlan-import-crcs.json"
    try:
        result = generate(args.artifacts)
        if out.is_symlink() or out.exists():
            raise ValueError("CRC export already exists; refusing to overwrite")
        with out.open("x", encoding="utf-8") as handle:
            json.dump(result, handle, sort_keys=True, indent=2)
            handle.write("\n")
    except (ValueError, OSError, ABI.AuditError, SELF.SelfCheckError) as exc:
        print("WLAN CRC map export BLOCKED: " + str(exc), file=sys.stderr)
        return 2
    print(f"Validated {result['imported_symbol_count']} rebuilt WLAN CRCs; host-only, flash_ready=false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
