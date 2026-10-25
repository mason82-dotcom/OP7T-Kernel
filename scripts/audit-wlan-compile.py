#!/usr/bin/env python3
"""Fail-closed provenance gate for a host-only patched QCACLD compilation.

Reads a prior signed/stripped module audit and checks the actual compiler
objects for all patched C translation units. Never installs kernel modules.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

PIN = "1083c6c5906114c71b11a429898b111a1b1b8109"
ROOT = Path(__file__).resolve().parents[1]
# Only this ICNSS/HELIUMPLUS object is compiled by the pinned hotdog config.
# The source-applicable VDEV/LITHIUM candidate is NOT compiled or selected.
PATCHES = (
    "patches/candidates/0002-qcacld-hotdog-icnss-monitor-rx-rfc.patch",
)
INACTIVE_LITHIUM_PATCH = (
    "patches/qcacld-3.0/0001-monitor-vdev-null-and-error-guards.patch"
)
EXPECTED_OBJECTS = (
    "drivers/staging/qcacld-3.0/core/hdd/src/wlan_hdd_tx_rx.o",
)
ELF_HASH = re.compile(r"^[a-f0-9]{64}$")


class AttestationError(ValueError):
    pass


def sha256_file(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def compiled_objects(out):
    """Require nonempty .o for the selected ICNSS C translation unit."""
    out = Path(out)
    found = []
    for relative in EXPECTED_OBJECTS:
        path = out / relative
        if path.is_symlink() or not path.is_file() or path.stat().st_size < 128:
            raise AttestationError("Patched translation unit not compiled: " + relative)
        found.append({
            "object": relative,
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        })
    return found


def wlan_module_metadata(artifacts, report, expected_sha=PIN):
    if report.get("schema") != "op7t-kernel-artifact-report-v1":
        raise AttestationError("Unknown artifact report schema")
    if report.get("device") != "hotdog" or report.get("upstream_commit") != expected_sha:
        raise AttestationError("Artifact report target/source mismatch")
    if report.get("profile") != "core":
        raise AttestationError("Only experimental core profile is supported")
    if (report.get("module_signature_enforcement") is not True or
            report.get("module_debug_sections_verified") is not True or
            report.get("module_signature_load_blocked") is not False or
            report.get("flash_ready") is not False):
        raise AttestationError("Signed/stripped or no-flash artifact gates failed")
    config = report.get("final_config")
    if not isinstance(config, dict) or config.get("CONFIG_QCA_CLD_WLAN") != "m":
        raise AttestationError("QCACLD not compiled as a module")
    modules = report.get("modules")
    if not isinstance(modules, list) or not modules:
        raise AttestationError("Missing audited kernel modules")
    wlan = [
        m for m in modules
        if isinstance(m, dict) and
        Path(str(m.get("path", ""))).name in ("wlan.ko", "qca_cld3_wlan.ko")
    ]
    if len(wlan) != 1 or report.get("wlan_module_count") != 1:
        raise AttestationError("Exactly one audited Qualcomm WLAN module required")
    m = wlan[0]
    rel = Path(str(m["path"]))
    if (rel.is_absolute() or ".." in rel.parts or not rel.parts or
            rel.parts[0] != "modules" or rel.suffix != ".ko"):
        raise AttestationError("Unsafe module path in report")
    file = artifacts / rel
    if not file.is_file() or file.is_symlink():
        raise AttestationError("Staged signed WLAN module missing")
    if not ELF_HASH.fullmatch(str(m.get("sha256", ""))) or sha256_file(file) != m["sha256"]:
        raise AttestationError("WLAN module hash differs from audited artifact")
    if file.stat().st_size != m.get("size_bytes"):
        raise AttestationError("WLAN module size changed")
    if not (m.get("has_embedded_signature") is True and
            isinstance(m.get("signer"), str) and m["signer"] and
            isinstance(m.get("signature_key_id"), str) and m["signature_key_id"] and
            m.get("debug_sections") == []):
        raise AttestationError("WLAN module is not signed and stripped")
    release = report.get("kernel_release")
    if not isinstance(release, str) or not release:
        raise AttestationError("Missing kernel release")
    if not isinstance(m.get("vermagic"), str) or m["vermagic"].split()[0] != release:
        raise AttestationError("WLAN module vermagic mismatch")
    return {
        "module": str(rel),
        "size_bytes": file.stat().st_size,
        "sha256": m["sha256"],
        "vermagic": m["vermagic"],
        "signer": m["signer"],
        "signature_key_id": m["signature_key_id"],
        "signed_and_stripped": True,
        "trusted_by_installed_rom": False,
    }


def attest(out, artifacts, project=ROOT, expected_sha=PIN):
    out, artifacts, project = (Path(p).resolve(strict=True)
                               for p in (out, artifacts, project))
    if expected_sha != PIN:
        raise AttestationError("Unapproved source SHA")
    if not out.is_dir() or not artifacts.is_dir():
        raise AttestationError("Expected separated build and artifact directories")
    try:
        data = json.loads((artifacts / "artifact-report.json").read_text(encoding="utf-8"))
    except (ValueError, OSError, UnicodeError) as exc:
        raise AttestationError("Cannot read successful signed-module audit") from exc
    wlan = wlan_module_metadata(artifacts, data, expected_sha)
    objects = compiled_objects(out)
    patches = []
    for rel in PATCHES:
        path = project / rel
        if path.is_symlink() or not path.is_file():
            raise AttestationError("Unapproved or missing patch")
        patches.append({"path": rel, "sha256": sha256_file(path)})
    return {
        "schema": "hotdog-wlan-icnss-compile-attestation-v3",
        "selected_driver_family": "ICNSS_HELIUMPLUS",
        "inactive_lithium_patch": {"path": INACTIVE_LITHIUM_PATCH,
            "applied": False, "compiled": False,
            "reason": "CONFIG_LITHIUM objects excluded by pinned hotdog build"},
        "upstream_sha": PIN,
        "profile": "core",
        "patches": patches,
        "compiled_modified_translation_units": objects,
        "all_modified_translation_units_compiled": True,
        "wlan_module": wlan,
        "module_elf_audited": True,
        "rom_kernel_symbol_crc_compatible": False,
        "installed_rom_module_abi_verified": False,
        "signer_trust_on_installed_rom_verified": False,
        "monitor_mode_runtime_verified": False,
        "packet_injection_verified": False,
        "wifi_hardware_tested": False,
        "flash_ready": False,
        "status": "EXPERIMENTAL_HOST_COMPILE_UNVERIFIED_ROM",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--artifacts", type=Path, required=True)
    p.add_argument("--expected-sha", default=PIN)
    args = p.parse_args()
    try:
        report = attest(args.out, args.artifacts, expected_sha=args.expected_sha)
        target = args.artifacts / "wlan-patch-experiment.json"
        with target.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, sort_keys=True)
            stream.write("\n")
        print("Isolated WLAN compile: selected ICNSS RX object and signed/stripped wlan.ko verified; flash_ready=false")
        return 0
    except (AttestationError, OSError, UnicodeError) as e:
        print("WLAN COMPILE ATTESTATION BLOCKED: " + str(e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
