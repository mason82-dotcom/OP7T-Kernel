#!/usr/bin/env python3
"""Verify a rebuilt hotdog WLAN module against its *own* Module.symvers.

Host-side proof of build self-consistency only. Comparing against this build's
own exports does not establish compatibility, key trust or code safety on the
physical installed ROM. No ADB, module loads, flashing, or uploads of binaries.
"""
import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
ROM_SHA = "57037290bb57caefd3c337db3511fca5751fb4ef"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
ABI_PATH = PROJECT / "scripts" / "audit-module-abi.py"
SPEC = importlib.util.spec_from_file_location("op7t_existing_abi_parser", ABI_PATH)
ABI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ABI)


class SelfCheckError(ValueError):
    pass


def safe_json(directory, filename, limit=1024 * 1024):
    path = directory / filename
    if (path.is_symlink() or not path.is_file() or
            not 0 < path.stat().st_size <= limit):
        raise SelfCheckError("Required bounded build attestation is absent")
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise SelfCheckError("Invalid bounded build attestation JSON") from exc
    if not isinstance(obj, dict):
        raise SelfCheckError("Build attestation must be a JSON object")
    return obj


def sha256_file(path):
    with path.open("rb") as stream:
        digest = hashlib.sha256()
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(data)
    return digest.hexdigest()


def require_wlan_report(artifacts, report, compiled):
    if (report.get("schema") != "op7t-kernel-artifact-report-v1" or
            report.get("device") != "hotdog" or
            report.get("upstream_commit") != ROM_SHA or
            report.get("profile") != "core" or
            report.get("module_signature_enforcement") is not True or
            report.get("module_debug_sections_verified") is not True or
            report.get("module_signature_load_blocked") is not False or
            report.get("flash_ready") is not False):
        raise SelfCheckError("Kernel artifact provenance/signature gates failed")
    if (compiled.get("schema") != "hotdog-wlan-icnss-compile-attestation-v4" or
            compiled.get("upstream_sha") != ROM_SHA or
            compiled.get("source_pin_role") != "observed_rom_release_source_candidate" or
            compiled.get("all_modified_translation_units_compiled") is not True or
            compiled.get("module_elf_audited") is not True or
            compiled.get("flash_ready") is not False or
            compiled.get("installed_rom_module_abi_verified") is not False or
            compiled.get("signer_trust_on_installed_rom_verified") is not False):
        raise SelfCheckError("Selected ROM-source compiler attestation gates failed")
    m = compiled.get("wlan_module")
    modules = report.get("modules")
    if not isinstance(m, dict) or not isinstance(modules, list):
        raise SelfCheckError("Missing signed WLAN module metadata")
    if report.get("wlan_module_count") != 1:
        raise SelfCheckError("Expected exactly one qualified WLAN module")
    name = m.get("module")
    if not isinstance(name, str):
        raise SelfCheckError("Missing recorded signed WLAN path")
    relative = Path(name)
    if (relative.is_absolute() or ".." in relative.parts or
            not name.startswith("modules/") or
            relative.name not in ("wlan.ko", "qca_cld3_wlan.ko")):
        raise SelfCheckError("Unsafe or unexpected WLAN module path")
    staged = artifacts / relative
    if (staged.is_symlink() or not staged.is_file() or
            staged.stat().st_size > ABI.MAX_MODULE):
        raise SelfCheckError("Signed kernel WLAN module is unavailable")
    audited = [entry for entry in modules if isinstance(entry, dict)
               and entry.get("path") == name]
    if len(audited) != 1:
        raise SelfCheckError("WLAN module not unique in artifact audit")
    meta = audited[0]
    actual_hash = sha256_file(staged)
    if (not HEX64.fullmatch(str(m.get("sha256", ""))) or
            actual_hash != m["sha256"] or
            meta.get("sha256") != actual_hash or
            meta.get("size_bytes") != staged.stat().st_size or
            meta.get("has_embedded_signature") is not True or
            meta.get("debug_sections") != [] or
            not meta.get("signature_key_id") or
            m.get("signed_and_stripped") is not True):
        raise SelfCheckError("Staged WLAN differs from signed/stripped attestation")
    rel = report.get("kernel_release")
    if (not isinstance(rel, str) or not rel or
            not isinstance(m.get("vermagic"), str) or
            m["vermagic"].split()[0] != rel):
        raise SelfCheckError("Staged WLAN vermagic is not the compiled kernel release")
    return staged, rel


def check(artifacts):
    original = Path(artifacts)
    if original.is_symlink() or not original.is_dir():
        raise SelfCheckError("Artifact directory absent or linked")
    artifacts = original.resolve(strict=True)
    report = safe_json(artifacts, "artifact-report.json")
    compiled = safe_json(artifacts, "wlan-patch-experiment.json")
    signed_wlan, release = require_wlan_report(artifacts, report, compiled)
    symvers_path = artifacts / "Module.symvers"
    if symvers_path.is_symlink() or not symvers_path.is_file():
        raise SelfCheckError("Compiled Module.symvers not staged locally")
    try:
        symvers = ABI.parse_symvers(symvers_path)
        module = ABI.inspect(signed_wlan)
    except (ABI.AuditError, OSError) as error:
        raise SelfCheckError("Cannot parse signed WLAN ELF/CRC evidence") from error
    if module["sha256"] != sha256_file(signed_wlan):
        raise SelfCheckError("WLAN ELF content hash changed during audit")
    if module["vermagic"].split()[0] != release:
        raise SelfCheckError("WLAN ELF release differs from audited kernel")
    if not module["signature"]["trailer_present"]:
        raise SelfCheckError("WLAN ELF signature trailer missing")
    versions = module["versions"]
    if not module["has_versions_section"] or not isinstance(versions, dict) or not versions:
        raise SelfCheckError("WLAN has no imported symbol CRCs despite MODVERSIONS")
    missing = sorted(set(versions) - set(symvers))
    mismatch = sorted(k for k in versions if k in symvers and versions[k] != symvers[k])
    if missing or mismatch:
        raise SelfCheckError(
            "Self-built Module.symvers lacks imported symbols or CRC parity: "
            + str(len(missing)) + " unresolved, " + str(len(mismatch)) + " mismatched"
        )
    return {
        "schema": "hotdog-built-wlan-self-crc-v1",
        "kernel_source_sha": ROM_SHA,
        "kernel_release": release,
        "wlan_module_sha256": module["sha256"],
        "built_module_symbols_versioned": len(versions),
        "matched_against_same_build_Module_symvers": len(versions),
        "missing_exported_symbol_count": 0,
        "mismatched_symbol_crc_count": 0,
        "built_Module_symvers_sha256": sha256_file(symvers_path),
        "built_kernel_module_self_consistency": True,
        "compared_against_actual_ROM_Module_symvers": False,
        "actual_ROM_kernel_binary_identity_verified": False,
        "reference_OTA_WLAN_ELF_abi_verified": False,
        "installed_kernel_signing_trust_verified": False,
        "signature_cryptographically_verified": False,
        "rx_callback_runtime_safety_verified": False,
        "flash_ready": False,
        "status": "BUILT_ARTIFACTS_INTERNALLY_CONSISTENT_ROM_UNVERIFIED",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = check(args.artifacts)
        filename = args.artifacts / "built-wlan-self-crc-report.json"
        if filename.is_symlink() or filename.exists():
            raise SelfCheckError("Self-CRC report already exists")
        with filename.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, sort_keys=True)
            stream.write("\n")
    except (OSError, UnicodeError, ValueError, SelfCheckError) as exc:
        print("BUILT WLAN SELF CRC AUDIT BLOCKED: " + str(exc), file=sys.stderr)
        return 2
    print("Built WLAN ELF CRCs match its own Module.symvers; installed ROM NOT verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
