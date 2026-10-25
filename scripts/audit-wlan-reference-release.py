#!/usr/bin/env python3
"""Read-only comparison of an actual CI metadata ZIP to a reference OTA release.

This never imports or executes a kernel binary or checks trusted keys. An exact
vermagic release match would still NOT prove installed-ROM module compatibility.
"""
import argparse
import hashlib
import json
import re
import stat
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROM_SHA = "57037290bb57caefd3c337db3511fca5751fb4ef"
PARENT_SHA = "1083c6c5906114c71b11a429898b111a1b1b8109"
SCHEMA = "hotdog-wlan-reference-release-gap-v1"
ALLOWED = frozenset((
    "artifact-report.json", "kernel.config", "kernel.release",
    "upstream-commit.txt", "toolchain-report.json",
    "wlan-patch-experiment.json", "wlan-rom-source-parity.json",
    "built-wlan-self-crc-report.json",
))
JSON_INPUTS = (
    "artifact-report.json", "wlan-patch-experiment.json",
    "wlan-rom-source-parity.json", "built-wlan-self-crc-report.json",
    "toolchain-report.json",
)
MAX_FILE = 1024 * 1024
MAX_ARCHIVE = 2 * 1024 * 1024
RELEASE = re.compile(r"^4\.14\.357-perf-g[0-9a-f]{12}(?:-dirty)?$")
SHA256 = re.compile(r"^[a-f0-9]{64}$")


class ReferenceGapError(ValueError):
    pass


def source_json(path, limit=MAX_FILE):
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size < limit:
        raise ReferenceGapError("Pinned source reference missing or invalid")
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise ReferenceGapError("Pinned source reference JSON unreadable") from exc
    if not isinstance(obj, dict):
        raise ReferenceGapError("Pinned source reference must be an object")
    return obj


def reference(project=ROOT):
    project = Path(project)
    rom = source_json(project / "config/rom-reference.json")
    release = source_json(project / "config/wlan-rom-reference-release.json")
    if (rom.get("schema") != "op7t-crdroid-ota-reference-v1"
            or rom.get("device") != "hotdog"
            or rom.get("android_major") != 17
            or rom.get("crdroid_major") != 13
            or release.get("schema") != "hotdog-wlan-reference-release-v1"
            or release.get("device") != "hotdog"
            or release.get("rom_reference_manifest") != "config/rom-reference.json"
            or release.get("rom_reference_zip_sha256") != rom.get("sha256")
            or release.get("rom_reference_release_date") != rom.get("release_date")
            or release.get("reference_ota_wlan_module") != "qca_cld3_wlan.ko"
            or release.get("observed_rom_source_sha") != ROM_SHA
            or release.get("observed_reference_wlan_vermagic_release")
               != "4.14.357-perf-g57037290bb57"
            or release.get("installed_rom_binary_identity_verified") is not False
            or release.get("reference_ota_module_signing_key_trust_verified") is not False
            or release.get("flash_ready") is not False
            or not SHA256.fullmatch(str(rom.get("sha256", "")))):
        raise ReferenceGapError("Unapproved or inconsistent reference OTA provenance")
    return release


def read_ci_zip(path):
    path = Path(path)
    if (path.is_symlink() or not path.is_file() or
            not 0 < path.stat().st_size <= MAX_ARCHIVE):
        raise ReferenceGapError("Metadata ZIP missing or exceeds strict size bound")
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            names = [item.filename for item in members]
            if set(names) != ALLOWED or len(names) != len(ALLOWED):
                raise ReferenceGapError("Unexpected, duplicate or absent CI metadata files")
            for item in members:
                mode = (item.external_attr >> 16) & 0xFFFF
                if (item.flag_bits & 1 or item.is_dir() or
                        (mode and stat.S_IFMT(mode) not in (0, stat.S_IFREG)) or
                        not 0 < item.file_size < MAX_FILE or
                        item.compress_size <= 0):
                    raise ReferenceGapError("Unsafe or oversized CI artifact member")
            data = {item.filename: archive.read(item) for item in members}
    except (OSError, zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
        raise ReferenceGapError("Cannot decode bounded CI metadata ZIP") from exc
    parsed = {}
    for name in JSON_INPUTS:
        try:
            parsed[name] = json.loads(data[name].decode("utf-8"))
        except (ValueError, UnicodeError) as exc:
            raise ReferenceGapError("Malformed CI metadata record: " + name) from exc
        if not isinstance(parsed[name], dict):
            raise ReferenceGapError("CI metadata record must be an object")
    for name in ("kernel.release", "upstream-commit.txt"):
        try:
            value = data[name].decode("ascii").strip()
        except UnicodeError as exc:
            raise ReferenceGapError("Invalid commit/kernel text encoding") from exc
        if not value or len(value) > 128:
            raise ReferenceGapError("Invalid commit/kernel text length")
        parsed[name] = value
    try:
        parsed["kernel.config"] = data["kernel.config"].decode("utf-8")
    except UnicodeError as exc:
        raise ReferenceGapError("Invalid Kconfig encoding") from exc
    parsed["ci_artifact_zip_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return parsed


def require_false(obj, keys, label):
    for key in keys:
        if obj.get(key) is not False:
            raise ReferenceGapError(label + " improperly claims verified compatibility: " + key)


def analyze(ci, ref):
    artifact = ci["artifact-report.json"]
    experiment = ci["wlan-patch-experiment.json"]
    parity = ci["wlan-rom-source-parity.json"]
    crc = ci["built-wlan-self-crc-report.json"]
    tools = ci["toolchain-report.json"]

    if (artifact.get("schema") != "op7t-kernel-artifact-report-v1"
            or artifact.get("device") != "hotdog"
            or artifact.get("profile") != "core"
            or artifact.get("upstream_commit") != ROM_SHA
            or artifact.get("module_signature_enforcement") is not True
            or artifact.get("module_debug_sections_verified") is not True
            or artifact.get("wlan_module_count") != 1
            or artifact.get("module_count") != 2
            or artifact.get("signed_module_count") != 2
            or ci["upstream-commit.txt"] != ROM_SHA
            or artifact.get("kernel_release") != ci["kernel.release"]
            or experiment.get("upstream_sha") != ROM_SHA
            or experiment.get("schema") != "hotdog-wlan-icnss-compile-attestation-v4"
            or experiment.get("source_pin_role") != "observed_rom_release_source_candidate"
            or experiment.get("all_modified_translation_units_compiled") is not True
            or experiment.get("module_elf_audited") is not True
            or parity.get("schema") != "hotdog-wlan-rom-source-parity-v1"
            or parity.get("source_equivalence_verified") is not True
            or parity.get("parent_sha") != PARENT_SHA
            or parity.get("rom_source_sha") != ROM_SHA
            or crc.get("schema") != "hotdog-built-wlan-self-crc-v1"
            or crc.get("kernel_source_sha") != ROM_SHA
            or crc.get("kernel_release") != ci["kernel.release"]
            or crc.get("built_kernel_module_self_consistency") is not True
            or crc.get("mismatched_symbol_crc_count") != 0
            or crc.get("missing_exported_symbol_count") != 0
            or tools.get("schema") != "op7t-toolchain-provenance-v1"
            or tools.get("official_rom_build_toolchain_verified") is not False):
        raise ReferenceGapError("Required current CI source, toolchain or CRC evidence missing")

    require_false(artifact, ("flash_ready", "hardware_verified",
                            "rom_module_key_trust_verified"), "Artifact")
    require_false(experiment, ("flash_ready", "installed_rom_module_abi_verified",
                               "signer_trust_on_installed_rom_verified",
                               "rfc_behavioral_equivalence_verified"), "Compile")
    require_false(parity, ("flash_ready", "rom_module_abi_verified",
                           "rom_signing_key_trust_verified"), "Source parity")
    require_false(crc, ("flash_ready", "compared_against_actual_ROM_Module_symvers",
                        "actual_ROM_kernel_binary_identity_verified",
                        "installed_kernel_signing_trust_verified"), "Self CRC")

    count = crc.get("built_module_symbols_versioned")
    if (not isinstance(count, int) or isinstance(count, bool) or count <= 0):
        raise ReferenceGapError("Invalid internal module symbol CRC coverage")
    # Existing v1 uses an underscore for the field, not a dot.
    if crc.get("matched_against_same_build_Module_symvers") != count:
        raise ReferenceGapError("Self-CRC imported symbol count mismatch")

    wlan = experiment.get("wlan_module")
    modules = artifact.get("modules")
    if not isinstance(wlan, dict) or not isinstance(modules, list):
        raise ReferenceGapError("Signed WLAN metadata missing")
    signed = [m for m in modules if isinstance(m, dict)
              and m.get("path") == wlan.get("module")]
    if len(signed) != 1:
        raise ReferenceGapError("Signed WLAN module not uniquely identified")
    module = signed[0]
    if (module.get("path") != "modules/drivers/staging/qcacld-3.0/wlan.ko"
            or not isinstance(module.get("vermagic"), str)
            or module.get("vermagic") != wlan.get("vermagic")
            or module.get("sha256") != wlan.get("sha256")
            or crc.get("wlan_module_sha256") != wlan.get("sha256")
            or not SHA256.fullmatch(str(wlan.get("sha256", "")))
            or module.get("size_bytes") != wlan.get("size_bytes")
            or not module.get("has_embedded_signature")
            or not wlan.get("signed_and_stripped")
            or module.get("signature_key_id") != wlan.get("signature_key_id")
            or not module.get("signer")
            or module.get("signer") != wlan.get("signer")):
        raise ReferenceGapError("WLAN signer, file hash or module source is inconsistent")

    release = ci["kernel.release"]
    built_vermagic = wlan["vermagic"]
    if not RELEASE.fullmatch(release) or built_vermagic.split()[0] != release:
        raise ReferenceGapError("Unsupported or inconsistent compiled kernel release")
    for name in ("CONFIG_MODVERSIONS=y", "CONFIG_MODULE_SIG_FORCE=y",
                 "CONFIG_QCA_CLD_WLAN=m"):
        if name not in ci["kernel.config"].splitlines():
            raise ReferenceGapError("Required module security Kconfig absent: " + name)

    reference_release = ref["observed_reference_wlan_vermagic_release"]
    different = release != reference_release
    known = ["reference_ota_wlan_vermagic_release_mismatch"] if different else []
    unknown = [
        "reference_ota_wlan_ELF_not_compared",
        "installed_kernel_exported_symbol_CRCs_not_compared",
        "installed_kernel_module_signing_key_trust_unverified",
        "installed_ROM_and_reference_OTA_binary_identity_unverified",
        "patched_monitor_rx_callback_execution_context_unverified",
        "original_ROM_compiler_and_kernel_binary_not_matched",
    ]
    return {
        "schema": SCHEMA,
        "device": "hotdog",
        "ci_artifact_zip_sha256": ci["ci_artifact_zip_sha256"],
        "reference_ota_zip_sha256": ref["rom_reference_zip_sha256"],
        "reference_ota_module": ref["reference_ota_wlan_module"],
        "reference_wlan_release": reference_release,
        "rebuilt_wlan_release": release,
        "rebuilt_wlan_vermagic": built_vermagic,
        "rebuilt_wlan_sha256": wlan["sha256"],
        "internally_matched_symbol_crc_count": count,
        "internally_mismatched_symbol_crc_count": 0,
        "known_compatibility_blockers": known,
        "remaining_verification_requirements": unknown,
        "status": ("BLOCKED_REFERENCE_OTA_VERMAGIC_MISMATCH" if different
                   else "BLOCKED_UNVERIFIED_ROM_ABI_AND_KEY_TRUST"),
        "installed_ROM_binary_identity_verified": False,
        "reference_OTA_wlan_abi_verified": False,
        "installed_kernel_module_signing_key_trust_verified": False,
        "complete_vendor_kernel_abi_verified": False,
        "wifi_hardware_runtime_verified": False,
        "patch_behavioral_equivalence_verified": False,
        "flash_ready": False,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ci-metadata-zip", required=True, type=Path)
    p.add_argument("--project", type=Path, default=ROOT)
    p.add_argument("--strict", action="store_true",
                   help="Return nonzero if any release compatibility blocker remains")
    args = p.parse_args(argv)
    try:
        outcome = analyze(read_ci_zip(args.ci_metadata_zip), reference(args.project))
    except (ReferenceGapError, OSError) as exc:
        print("REFERENCE RELEASE AUDIT BLOCKED: " + str(exc), file=sys.stderr)
        return 3
    print(json.dumps(outcome, indent=2, sort_keys=True))
    if args.strict and (outcome["known_compatibility_blockers"]
                        or outcome["remaining_verification_requirements"]):
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
