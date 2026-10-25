#!/usr/bin/env python3
"""Compare actual local rebuilt WLAN ELF and independently obtained original ROM WLAN ELF.

Read-only. This compares supplied byte sequences and self-built Module.symvers;
it does NOT prove the source of the claimed ROM module, trusted kernel keys,
installed ROM identity, module loadability or runtime safety. Never flashes.
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
SHA = re.compile(r"^[0-9a-f]{64}$")
WLAN_PATH = "modules/drivers/staging/qcacld-3.0/wlan.ko"
EXPECTED_REFERENCE_BASENAME = "qca_cld3_wlan.ko"


def import_script(module_name, name):
    p = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(module_name, p)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ABI = import_script("hotdog_local_arm64_elf", "audit-module-abi.py")
MODULES = import_script("hotdog_module_modinfo_compare", "compare-rom-modules.py")
SELF = import_script("hotdog_local_signed_module_crc", "audit-wlan-built-crcs.py")


class PairAuditError(ValueError):
    pass


def bounded_regular(path, limit):
    """Prevent final symlink, missing/empty/oversized files and path traversal."""
    path = Path(path)
    if (path.is_symlink() or not path.is_file() or
            not 0 < path.stat().st_size <= limit):
        raise PairAuditError("ELF or symbol file absent, symlinked or over limit")
    return path


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def examine(artifacts, reference_module, reference_module_sha256):
    if not isinstance(reference_module_sha256, str) or not SHA.fullmatch(reference_module_sha256):
        raise PairAuditError("Expected original module digest must be a 64-character SHA-256")
    artifacts = Path(artifacts)
    if artifacts.is_symlink() or not artifacts.is_dir():
        raise PairAuditError("Rebuilt artifact directory invalid")
    # Refuse symlinks in any locally staged path component, not just wlan.ko.
    for rel in (
        "modules",
        "modules/drivers",
        "modules/drivers/staging",
        "modules/drivers/staging/qcacld-3.0",
    ):
        if (artifacts / rel).is_symlink():
            raise PairAuditError("Symlink in rebuilt module staging path")

    report = SELF.check(artifacts)
    if (report.get("schema") != "hotdog-built-wlan-self-crc-v1"
            or report.get("kernel_source_sha") != ROM_SHA
            or report.get("flash_ready") is not False
            or report.get("built_kernel_module_self_consistency") is not True
            or report.get("installed_kernel_signing_trust_verified") is not False):
        raise PairAuditError("Existing signed WLAN/CRC build gate did not pass")

    built = bounded_regular(artifacts / WLAN_PATH, ABI.MAX_MODULE)
    symvers_file = bounded_regular(artifacts / "Module.symvers", ABI.MAX_SYMVERS)
    reference = bounded_regular(Path(reference_module), ABI.MAX_MODULE)
    if reference.name != EXPECTED_REFERENCE_BASENAME:
        raise PairAuditError("Expected exact original ROM WLAN module name")
    if built.resolve() == reference.resolve():
        raise PairAuditError("Cannot compare a module to itself")
    if sha256_file(built) != report["wlan_module_sha256"]:
        raise PairAuditError("Built WLAN module no longer matches self-CRC attestation")
    if sha256_file(symvers_file) != report["built_Module_symvers_sha256"]:
        raise PairAuditError("Built Module.symvers differs from self-CRC attestation")
    original_sha = sha256_file(reference)
    if original_sha != reference_module_sha256:
        raise PairAuditError("Original ROM module mismatches independently supplied SHA-256")

    try:
        built_elf = ABI.inspect(built)
        rom_elf = ABI.inspect(reference)
        symvers = ABI.parse_symvers(symvers_file)
    except (ABI.AuditError, OSError) as exc:
        raise PairAuditError("Unable to inspect one or both AArch64 ELF module binaries") from exc
    for obj in (built_elf, rom_elf):
        if not obj["signature"]["trailer_present"]:
            raise PairAuditError("An unsigned module cannot pass this signed ROM pair audit")
        if not obj["has_versions_section"] or not obj["versions"]:
            raise PairAuditError("Required AArch64 kernel symbol __versions missing")
    if built_elf["sha256"] != report["wlan_module_sha256"]:
        raise PairAuditError("Built WLAN ELF SHA-256 differs from signed attestation")
    # Requires modinfo/kmod locally. Key identifiers are NOT cryptographic trust.
    try:
        built_info = MODULES.inspect(built)
        rom_info = MODULES.inspect(reference)
    except (ValueError, OSError) as exc:
        raise PairAuditError("Unable to inspect module signing/metadata with modinfo") from exc
    if (built_info.get("vermagic") != built_elf["vermagic"] or
            rom_info.get("vermagic") != rom_elf["vermagic"]):
        raise PairAuditError("ELF .modinfo and kmod metadata disagree")
    build_audit = SELF.safe_json(artifacts, "artifact-report.json")
    compiled_audit = SELF.safe_json(artifacts, "wlan-patch-experiment.json")
    recorded = compiled_audit["wlan_module"]
    if (built_info.get("signer") != recorded["signer"] or
            built_info.get("sig_key") != recorded["signature_key_id"] or
            built_info.get("vermagic") != recorded["vermagic"]):
        raise PairAuditError("Signed rebuilt WLAN metadata mismatches build attestation")
    if build_audit.get("kernel_release") != report["kernel_release"]:
        raise PairAuditError("Rebuilt kernel release differs from independent build audit")
    # Only compare byte content and symbol records of the provided ELF pair.
    abi = ABI.compare(built_elf, rom_elf, symvers)
    module_metadata = MODULES.compare(built_info, rom_info)
    known = sorted(set(abi["blockers"] + module_metadata["metadata_mismatches"]))
    unknown = sorted(set(abi["unknowns"] + module_metadata["metadata_unknowns"] + [
        "original_ROM_module_digest_supplied_by_operator_provenance_unverified",
        "reference_OTA_module_identity_not_cryptographically_attested",
        "installed_kernel_module_key_trust_not_verified",
        "installed_ROM_boot_partition_and_vendor_dlkm_not_verified",
        "runtime_monitor_rx_softirq_and_firmware_behavior_not_verified",
    ]))
    # Expected module may not have the same kernel release even when both
    # have valid arm64/vermagic fields. Do NOT silently normalize -dirty.
    return {
        "schema": "hotdog-wlan-original-elf-pair-audit-v1",
        "device": "hotdog",
        "rom_source_candidate_sha": ROM_SHA,
        "built_wlan_module_sha256": built_elf["sha256"],
        "provided_original_wlan_module_sha256": rom_elf["sha256"],
        "operator_supplied_original_module_digest_matches": True,
        "operator_supplied_digest_proves_ota_provenance": False,
        "built_kernel_release": report["kernel_release"],
        "rebuilt_wlan_vermagic": built_elf["vermagic"],
        "provided_original_wlan_vermagic": rom_elf["vermagic"],
        "rebuilt_module_signature_key_id": built_info.get("sig_key"),
        "provided_original_module_signature_key_id": rom_info.get("sig_key"),
        "shared_symbol_crc_count": abi["shared_versioned_symbol_count"],
        "mismatched_shared_symbol_crc_count": abi["different_symbol_crc_count"],
        "rom_only_versioned_symbol_count": abi["rom_only_symbol_count"],
        "built_only_versioned_symbol_count": abi["built_only_symbol_count"],
        "original_symbols_missing_from_built_symvers": abi["rom_symbols_not_in_built_symvers_count"],
        "original_symbols_mismatching_built_symvers": abi["rom_symbol_mismatches_built_symvers_count"],
        "known_compatibility_blockers": known,
        "unknown_verification_requirements": unknown,
        "status": ("KNOWN_ELF_MODULE_ABI_OR_SIGNER_MISMATCH" if known else
                   "NO_OBSERVED_ELF_MISMATCH_BUT_ROM_TRUST_UNVERIFIED"),
        "original_rom_module_provenance_independently_verified": False,
        "installed_kernel_abi_verified": False,
        "installed_kernel_module_signing_trust_verified": False,
        "module_signature_cryptographically_verified": False,
        "complete_vendor_kernel_abi_verified": False,
        "monitor_rx_runtime_verified": False,
        "flash_ready": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--built-artifacts", type=Path, required=True)
    parser.add_argument("--original-rom-wlan", type=Path, required=True)
    parser.add_argument("--original-rom-sha256", type=str, required=True,
                        help="Expected SHA-256 obtained INDEPENDENTLY from verified OTA extraction")
    parser.add_argument("--strict", action="store_true",
                        help="Exit nonzero while any mismatch or verification unknown remains")
    args = parser.parse_args(argv)
    try:
        result = examine(args.built_artifacts, args.original_rom_wlan,
                         args.original_rom_sha256)
    except (PairAuditError, ABI.AuditError, OSError, KeyError, TypeError) as exc:
        print("OFFLINE WLAN BINARY PAIR AUDIT BLOCKED: " + str(exc), file=sys.stderr)
        return 3
    print(json.dumps(result, sort_keys=True, indent=2))
    if result["known_compatibility_blockers"]:
        return 2
    if args.strict and result["unknown_verification_requirements"]:
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
