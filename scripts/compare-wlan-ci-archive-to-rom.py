#!/usr/bin/env python3
"""Validate an exact CI metadata ZIP and compare its WLAN CRC map with a local OTA ELF.

Read-only on a host. No module execution, ADB, extraction of arbitrary ZIP paths,
key trust, ROM provenance or flashing. All legitimate outcomes remain nonzero.
"""
import argparse
import hashlib
import importlib.util
import json
import re
import stat
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROM_SHA = "57037290bb57caefd3c337db3511fca5751fb4ef"
HEX_SHA = re.compile(r"^[a-f0-9]{64}$")
ALLOWED = frozenset((
    "kernel.config", "upstream-commit.txt", "artifact-report.json",
    "kernel.release", "toolchain-report.json", "wlan-patch-experiment.json",
    "wlan-rom-source-parity.json", "built-wlan-self-crc-report.json",
    "built-wlan-import-crcs.json",
))
EVIDENCE = (
    "built-wlan-import-crcs.json", "wlan-patch-experiment.json",
    "built-wlan-self-crc-report.json",
)
MAX_ZIP_SIZE = 2 * 1024 * 1024
MAX_MEMBER = 1024 * 1024
MAX_TOTAL = 3 * 1024 * 1024


class ArchiveAuditError(ValueError):
    pass


def import_comparator():
    spec = importlib.util.spec_from_file_location(
        "hotdog_ci_zip_crc_comparator", ROOT / "scripts" / "compare-wlan-build-crcs-to-rom.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


COMP = import_comparator()


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_zip(path, expected_sha256):
    path = Path(path)
    if not isinstance(expected_sha256, str) or not HEX_SHA.fullmatch(expected_sha256):
        raise ArchiveAuditError("A pre-recorded SHA-256 of the CI ZIP is required")
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_ZIP_SIZE:
        raise ArchiveAuditError("CI ZIP missing, linked, empty or oversized")
    actual_sha = sha256_file(path)
    if actual_sha != expected_sha256:
        raise ArchiveAuditError("CI ZIP SHA-256 differs from independently recorded value")
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if len(members) != len(ALLOWED) or {m.filename for m in members} != ALLOWED:
                raise ArchiveAuditError("Unexpected, duplicate or absent CI ZIP member")
            if sum(m.file_size for m in members) > MAX_TOTAL:
                raise ArchiveAuditError("CI ZIP uncompressed total exceeds limit")
            for m in members:
                mode = (m.external_attr >> 16) & 0xffff
                if (m.flag_bits & 1 or m.is_dir() or
                        (mode and stat.S_IFMT(mode) not in (0, stat.S_IFREG)) or
                        m.file_size <= 0 or m.file_size > MAX_MEMBER or
                        m.compress_size <= 0):
                    raise ArchiveAuditError("Unsafe or oversized CI ZIP member")
            data = {m.filename: archive.read(m) for m in members}
    except (OSError, zipfile.BadZipFile, RuntimeError, NotImplementedError,
            EOFError, ValueError) as exc:
        if isinstance(exc, ArchiveAuditError):
            raise
        raise ArchiveAuditError("CI ZIP integrity or decoding failed") from exc

    try:
        records = {name: json.loads(data[name].decode("utf-8")) for name in (
            "artifact-report.json", "wlan-patch-experiment.json",
            "built-wlan-self-crc-report.json", "built-wlan-import-crcs.json",
        )}
        release = data["kernel.release"].decode("ascii").strip()
        upstream = data["upstream-commit.txt"].decode("ascii").strip()
    except (ValueError, UnicodeError) as exc:
        raise ArchiveAuditError("Malformed CI ZIP metadata") from exc
    if not all(isinstance(r, dict) for r in records.values()):
        raise ArchiveAuditError("CI ZIP metadata records must be objects")
    report = records["artifact-report.json"]
    compiled = records["wlan-patch-experiment.json"]
    selfcheck = records["built-wlan-self-crc-report.json"]
    crc = records["built-wlan-import-crcs.json"]
    wlan = compiled.get("wlan_module")
    modules = report.get("modules")
    if (not isinstance(wlan, dict) or not isinstance(modules, list)
            or len(release) > 128 or not release
            or upstream != ROM_SHA
            or report.get("schema") != "op7t-kernel-artifact-report-v1"
            or report.get("device") != "hotdog"
            or report.get("profile") != "core"
            or report.get("upstream_commit") != ROM_SHA
            or report.get("module_signature_enforcement") is not True
            or report.get("flash_ready") is not False
            or report.get("kernel_release") != release
            or compiled.get("schema") != "hotdog-wlan-icnss-compile-attestation-v4"
            or compiled.get("upstream_sha") != ROM_SHA
            or compiled.get("flash_ready") is not False
            or selfcheck.get("kernel_release") != release
            or selfcheck.get("built_kernel_module_self_consistency") is not True
            or selfcheck.get("flash_ready") is not False
            or crc.get("kernel_release") != release
            or crc.get("flash_ready") is not False
            or not isinstance(wlan.get("vermagic"), str)
            or wlan["vermagic"].split(" ")[0] != release
            or not isinstance(wlan.get("sha256"), str)
            or not HEX_SHA.fullmatch(wlan["sha256"])
            or not any(
                isinstance(m, dict) and
                m.get("path") == "modules/drivers/staging/qcacld-3.0/wlan.ko" and
                m.get("sha256") == wlan["sha256"] and
                m.get("has_embedded_signature") is True
                for m in modules
            )):
        raise ArchiveAuditError("CI ZIP release, module signing or source attestations conflict")
    return data, actual_sha


def compare_archive(ci_zip, ci_zip_sha256, original, original_sha256, original_map_sha256):
    if not isinstance(original_map_sha256, str) or not HEX_SHA.fullmatch(original_map_sha256):
        raise ArchiveAuditError("A separately recorded original OTA CRC map digest is required")
    members, verified_sha = validate_zip(ci_zip, ci_zip_sha256)
    with tempfile.TemporaryDirectory(prefix="op7t-wlan-metadata-") as directory:
        root = Path(directory)
        for name in EVIDENCE:
            (root / name).write_bytes(members[name])
        result = COMP.compare(
            Path(original), original_sha256,
            root / EVIDENCE[0], root / EVIDENCE[1], root / EVIDENCE[2],
        )
    if result.get("original_crc_map_sha256") != original_map_sha256:
        raise ArchiveAuditError("Original OTA ELF map differs from independently documented CRC map")
    if result.get("flash_ready") is not False:
        raise ArchiveAuditError("Comparator unexpectedly claimed flash eligibility")
    result["ci_artifact_zip_sha256"] = verified_sha
    result["ci_metadata_archive_verified_against_operator_digest"] = True
    result["installed_ROM_provenance_verified"] = False
    result["flash_ready"] = False
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ci-zip", type=Path, required=True)
    parser.add_argument("--ci-zip-sha256", required=True)
    parser.add_argument("--original-rom-wlan", type=Path, required=True)
    parser.add_argument("--original-rom-sha256", required=True)
    parser.add_argument("--original-rom-crc-map-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        result = compare_archive(
            args.ci_zip, args.ci_zip_sha256, args.original_rom_wlan,
            args.original_rom_sha256, args.original_rom_crc_map_sha256,
        )
    except (ArchiveAuditError, ValueError, OSError, TypeError, KeyError,
            json.JSONDecodeError, COMP.ABI.AuditError) as exc:
        print("WLAN ZIP/ROM CRC comparison BLOCKED: " + str(exc), file=sys.stderr)
        return 3
    print(json.dumps(result, indent=2, sort_keys=True))
    return 2 if result["blockers"] else 4  # Never installation approval.


if __name__ == "__main__":
    sys.exit(main())
