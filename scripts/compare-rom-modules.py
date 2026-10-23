#!/usr/bin/env python3
"""Read-only comparison of a built kernel module with the original ROM module.

Matching metadata never proves that the installed kernel trusts a signing key.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

FIELDS = ("name", "vermagic", "signer", "sig_key", "sig_hashalgo")


def inspect(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"Missing or empty module: {path}")
    data = {"filename": path.name, "size_bytes": path.stat().st_size}
    for field in FIELDS:
        try:
            p = subprocess.run(
                ["modinfo", "-F", field, str(path)],
                check=True, text=True, capture_output=True, timeout=15,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            raise ValueError(f"modinfo failed for {path.name} ({field}): {error}") from error
        data[field] = p.stdout.strip() or None
    if not data["name"] or not data["vermagic"]:
        raise ValueError(f"Incomplete module metadata: {path.name}")
    return data


def compare(built: dict, rom: dict) -> dict:
    issues = []
    unknowns = []
    if built.get("name") != rom.get("name"):
        issues.append("module names differ")
    if built.get("vermagic") != rom.get("vermagic"):
        issues.append("vermagic strings differ")
    for side, data in (("built", built), ("rom", rom)):
        if not data.get("signer") or not data.get("sig_key"):
            unknowns.append(f"{side}: signer and/or signature key unavailable")
    if not unknowns:
        if built["sig_key"] != rom["sig_key"]:
            issues.append("module signature key identifiers differ")
        if built.get("sig_hashalgo") != rom.get("sig_hashalgo"):
            issues.append("signature hash algorithms differ")
    status = "known_metadata_mismatch" if issues else "needs_live_trust_and_abi_review"
    return {
        "schema": "op7t-built-vs-rom-module-v1",
        "built": built,
        "rom": rom,
        "metadata_mismatches": issues,
        "metadata_unknowns": unknowns,
        "status": status,
        "installed_kernel_key_trust_verified": False,
        "kernel_symbol_abi_verified": False,
        "boot_image_compatible": False,
        "flash_ready": False,
        "limitations": [
            "Verity, vendor_dlkm placement, module dependencies, VINTF and runtime firmware not inspected",
            "Equal signer / sig_key does not prove trust by the booting kernel",
            "Comparing a ZIP's modules does not prove that ZIP matches the installed build",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--built", required=True, type=Path, help="rebuilt wlan.ko")
    parser.add_argument("--rom", required=True, type=Path, help="original wlan.ko from exact ROM")
    args = parser.parse_args()
    try:
        outcome = compare(inspect(args.built), inspect(args.rom))
    except ValueError as error:
        print(f"Module comparison FAILED: {error}", file=sys.stderr)
        return 3
    print(json.dumps(outcome, indent=2, sort_keys=True))
    return 2 if outcome["metadata_mismatches"] else 0


if __name__ == "__main__":
    sys.exit(main())
