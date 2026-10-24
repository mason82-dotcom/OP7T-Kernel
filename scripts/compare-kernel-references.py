#!/usr/bin/env python3
"""Compare pinned crDroid and LineageOS hotdog kernel build *inputs* offline.

No ADB, flashing, network, source modification or kernel execution.
Raw Kconfig requests are not a resolved .config or a verified module ABI.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_MANIFEST = Path(__file__).resolve().parents[1] / "config" / "kernel-alternatives.json"
FILES = (
    "Makefile",
    "arch/arm64/configs/vendor/sm8150-perf_defconfig",
    "arch/arm64/configs/vendor/oplus.config",
    "drivers/staging/qcacld-3.0/Kconfig",
)
CRITICAL = (
    "CONFIG_LOCALVERSION", "CONFIG_MODULES", "CONFIG_MODVERSIONS",
    "CONFIG_MODULE_SIG", "CONFIG_MODULE_SIG_FORCE", "CONFIG_MODULE_SIG_ALL",
    "CONFIG_QCA_CLD_WLAN", "CONFIG_CFG80211",
)


class ReferenceError(ValueError):
    pass


def git(tree: Path, *args: str) -> str:
    try:
        response = subprocess.run(
            ["git", "-C", str(tree), *args], check=False, capture_output=True,
            text=True, timeout=25, encoding="utf-8", errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ReferenceError("Local git verification unavailable") from exc
    if response.returncode or len(response.stdout) > 20000:
        raise ReferenceError("Git reference verification failed")
    return response.stdout.strip()


def get_text(root: Path, relative: str) -> str:
    path = root / relative
    if not path.is_file() or path.stat().st_size > 2_000_000:
        raise ReferenceError("Missing or oversized pinned source file: " + relative)
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeError as exc:
        raise ReferenceError("Invalid source text encoding: " + relative) from exc


def parse_makefile(text: str) -> dict:
    properties = {}
    for field in ("VERSION", "PATCHLEVEL", "SUBLEVEL", "EXTRAVERSION"):
        matches = re.findall(r"^" + field + r"\s*=\s*(.*?)\s*$", text, re.MULTILINE)
        if len(matches) != 1:
            raise ReferenceError("Expected unique Makefile kernel " + field)
        properties[field] = matches[0]
    if not all(properties[k].isdigit() for k in ("VERSION", "PATCHLEVEL", "SUBLEVEL")):
        raise ReferenceError("Invalid kernel version fields")
    if not re.fullmatch(r"[-A-Za-z0-9._+]*", properties["EXTRAVERSION"]):
        raise ReferenceError("Invalid kernel EXTRAVERSION")
    return {
        "version": ".".join(properties[k] for k in ("VERSION", "PATCHLEVEL", "SUBLEVEL")),
        "extraversion": properties["EXTRAVERSION"],
    }


def config_entries(text: str, label: str) -> dict:
    values = {}
    for line in text.splitlines():
        enabled = re.fullmatch(r"(CONFIG_[A-Z0-9_]+)=(.*)", line)
        disabled = re.fullmatch(r"# (CONFIG_[A-Z0-9_]+) is not set", line)
        if not (enabled or disabled):
            continue
        name, value = (
            (enabled.group(1), enabled.group(2)) if enabled
            else (disabled.group(1), "n")
        )
        if name in values:
            raise ReferenceError("Duplicate requested Kconfig symbol in " + label)
        values[name] = value
    return values


def local_snapshot(root: Path, expected_sha: str) -> dict:
    if not re.fullmatch(r"[a-f0-9]{40}", expected_sha):
        raise ReferenceError("Invalid pinned source SHA")
    if git(root, "rev-parse", "HEAD") != expected_sha:
        raise ReferenceError("Source checkout HEAD differs from pinned SHA")
    if git(root, "status", "--porcelain", "--untracked-files=no"):
        raise ReferenceError("Pinned kernel checkout has tracked local changes")
    contents = {name: get_text(root, name) for name in FILES}
    base = config_entries(contents[FILES[1]], "defconfig")
    overlay = config_entries(contents[FILES[2]], "oplus.config")
    requested = dict(base)
    requested.update(overlay)
    mk = parse_makefile(contents["Makefile"])
    return {
        "source_sha": expected_sha,
        "kernel_makefile": mk,
        "source_sha256": {
            name: hashlib.sha256(contents[name].encode("utf-8")).hexdigest()
            for name in FILES
        },
        "base_config_symbol_count": len(base),
        "oplus_config_symbol_count": len(overlay),
        "requested_symbol_count": len(requested),
        "requested": requested,
        "overlay": overlay,
        "qcacld_kconfig_exists": "config QCA_CLD_WLAN" in contents[FILES[3]],
    }


def compare(manifest: dict, cr: dict, lo: dict) -> dict:
    if manifest.get("schema") != "op7t-kernel-reference-comparison-v1":
        raise ReferenceError("Wrong comparison manifest schema")
    if manifest.get("android_major") != 17 or manifest.get("flash_ready") is not False:
        raise ReferenceError("Unsafe manifest target or readiness")
    delta = [
        {"symbol": key, "crdroid_requested": cr["requested"].get(key),
         "lineage_requested": lo["requested"].get(key)}
        for key in sorted(set(cr["requested"]) | set(lo["requested"]))
        if cr["requested"].get(key) != lo["requested"].get(key)
    ]
    safety = []
    if cr["kernel_makefile"] != lo["kernel_makefile"]:
        safety.append("makefile_kernel_version_or_suffix_differs")
    if lo["overlay"].get("CONFIG_MODULE_SIG") == "n":
        safety.append("lineage_oplus_overlay_explicitly_disables_module_signing")
    if not cr["qcacld_kconfig_exists"] or not lo["qcacld_kconfig_exists"]:
        safety.append("qcacld_kconfig_missing_in_one_reference")
    for key in ("CONFIG_QCA_CLD_WLAN", "CONFIG_MODVERSIONS", "CONFIG_MODULE_SIG_FORCE"):
        if cr["requested"].get(key) != lo["requested"].get(key):
            safety.append("requested_" + key + "_differs")
    return {
        "schema": manifest["schema"],
        "target": manifest.get("target"),
        "source_pins": {
            "crdroid": cr["source_sha"],
            "lineage": lo["source_sha"],
        },
        "makefiles": {
            "crdroid": cr["kernel_makefile"],
            "lineage": lo["kernel_makefile"],
        },
        "config_differences_count": len(delta),
        "critical_requested_symbols": {
            key: {"crdroid": cr["requested"].get(key), "lineage": lo["requested"].get(key),
                  "lineage_oplus_overlay": lo["overlay"].get(key)}
            for key in CRITICAL
        },
        "requested_differences": delta[:250],
        "differences_truncated": len(delta) > 250,
        "source_sha256": {
            "crdroid": cr["source_sha256"],
            "lineage": lo["source_sha256"],
        },
        "manual_review_flags": sorted(set(safety)),
        "requested_kconfig_is_resolved_config": False,
        "effective_kernel_config_verified": False,
        "full_kernel_source_diff_performed": False,
        "module_signatures_or_abi_verified": False,
        "lineage_android17_boot_compatibility_verified": False,
        "installed_crdroid_rom_compatibility_verified": False,
        "flash_ready": False,
        "status": "source_configuration_reference_only",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--crdroid-tree", type=Path, required=True)
    parser.add_argument("--lineage-tree", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args(argv)
    try:
        manifest = json.loads(get_text(args.manifest.parent, args.manifest.name))
        cr = local_snapshot(args.crdroid_tree, manifest["primary"]["sha"])
        lo = local_snapshot(args.lineage_tree, manifest["alternative"]["sha"])
        report = compare(manifest, cr, lo)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except (ReferenceError, KeyError, TypeError, OSError, ValueError) as exc:
        print(f"Reference comparison FAILED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
