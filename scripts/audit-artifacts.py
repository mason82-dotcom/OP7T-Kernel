#!/usr/bin/env python3
"""Inspect raw kernel build artifacts. Never declares images flashable."""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ARM64_IMAGE_MAGIC = b"ARM\x64"
SHA = re.compile(r"^[a-f0-9]{40}$")
CONFIG_KEYS = (
    "CONFIG_QCA_CLD_WLAN",
    "CONFIG_MODULE_SIG_FORCE",
    "CONFIG_USB_GADGET",
    "CONFIG_USB_CONFIGFS",
    "CONFIG_USB_CONFIGFS_F_HID",
    "CONFIG_ATH9K_HTC",
    "CONFIG_CARL9170",
    "CONFIG_RTL8187",
    "CONFIG_MT7601U",
    "CONFIG_RT2800USB",
)


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def kernel_config_values(path):
    config = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("CONFIG_") and "=" in line:
            name, value = line.split("=", 1)
            config[name] = value
        elif line.startswith("# CONFIG_") and line.endswith(" is not set"):
            config[line[2:-11]] = "n"
    return {key: config.get(key, "not present") for key in CONFIG_KEYS}


def module_metadata(path, relative):
    def field(name):
        try:
            result = subprocess.run(
                ["modinfo", "-F", name, str(path)],
                check=True, capture_output=True, text=True, timeout=15,
            )
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise ValueError(f"Cannot inspect module {relative}: {exc}") from exc
        return result.stdout.strip()

    signer = field("signer")
    vermagic = field("vermagic")
    if not vermagic:
        raise ValueError(f"Module {relative} has no vermagic")
    return {
        "path": relative,
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "vermagic": vermagic,
        "signer": signer if signer else None,
        "signature_key_id": field("sig_key") or None,
        "signature_hash_algorithm": field("sig_hashalgo") or None,
        "has_embedded_signature": bool(signer),
        # Presence of signature != ROM key trust: no trust claims here.
    }


def collect(root, expected_sha, profile):
    image = root / "Image"
    if not image.is_file():
        raise ValueError("Missing raw arm64 Image")
    if image.stat().st_size < 64:
        raise ValueError("Image too short for arm64 header")
    with image.open("rb") as handle:
        handle.seek(0x38)
        if handle.read(4) != ARM64_IMAGE_MAGIC:
            raise ValueError("Image is not recognized as an arm64 raw Image")
    config_path = root / "kernel.config"
    if not config_path.is_file():
        raise ValueError("Missing final kernel.config")
    cfg = kernel_config_values(config_path)
    for name, expected in (
        ("CONFIG_MODULE_SIG_FORCE", "y"),
        ("CONFIG_QCA_CLD_WLAN", "m"),
        ("CONFIG_USB_CONFIGFS_F_HID", "y"),
    ):
        if cfg.get(name) != expected:
            raise ValueError(f"{name}={cfg.get(name)}; expected {expected}")
    commit_path = root / "upstream-commit.txt"
    if not commit_path.is_file():
        raise ValueError("Missing upstream-commit.txt")
    commit = commit_path.read_text(encoding="utf-8").strip()
    if not SHA.fullmatch(commit) or commit != expected_sha:
        raise ValueError(f"Kernel source mismatch: {commit}")
    dtbs = sorted((root / "dtbs").rglob("*.dtb"))
    modules = sorted((root / "modules").rglob("*.ko"))
    if not dtbs:
        raise ValueError("No DTBs captured; packaging must be blocked")
    if not modules:
        raise ValueError("No kernel modules captured; cannot audit vendor WLAN")
    release_file = root / "kernel.release"
    if not release_file.is_file():
        raise ValueError("Missing kernel.release")
    release = release_file.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"[a-zA-Z0-9._+\\-]+", release):
        raise ValueError("Invalid kernel.release")
    module_details = [module_metadata(path, str(path.relative_to(root))) for path in modules]
    incompatible = [
        m["path"] for m in module_details
        if m["vermagic"].split()[0] != release
    ]
    if incompatible:
        raise ValueError(f"Built module vermagic does not match {release}: {incompatible[:10]}")
    wlan = [m for m in module_details if Path(m["path"]).name in {"wlan.ko", "qca_cld3_wlan.ko"}]
    if not wlan:
        raise ValueError("CONFIG_QCA_CLD_WLAN=m but no built Qualcomm WLAN module found")
    unsigned = [m["path"] for m in module_details if not m["has_embedded_signature"]]
    signature_load_blocked = cfg["CONFIG_MODULE_SIG_FORCE"] == "y" and bool(unsigned)
    return {
        "schema": "op7t-kernel-artifact-report-v1",
        "device": "hotdog",
        "rom": "crDroid 13 / Android 17",
        "profile": profile,
        "upstream_commit": commit,
        "kernel_release": release,
        "build_module_vermagic_match": True,
        "image": {"path": "Image", "size_bytes": image.stat().st_size, "sha256": sha256_file(image)},
        "final_config": cfg,
        "dtb_count": len(dtbs),
        "dtbs": [{"path": str(p.relative_to(root)), "sha256": sha256_file(p)} for p in dtbs],
        "module_count": len(modules),
        "signed_module_count": sum(m["has_embedded_signature"] for m in module_details),
        "unsigned_modules": unsigned,
        "module_signature_enforcement": cfg["CONFIG_MODULE_SIG_FORCE"] == "y",
        "module_signature_load_blocked": signature_load_blocked,
        "module_runtime_compatibility": (
            "blocked_unsigned_modules" if signature_load_blocked
            else "unverified_rom_key_trust_and_abi"
        ),
        "wlan_module_count": len(wlan),
        "modules": module_details,
        "rom_module_key_trust_verified": False,
        "hardware_verified": False,
        "boot_image_verified": False,
        "flash_ready": False,
        "status": "RAW_ARTIFACT_ONLY_UNVERIFIED",
        "warnings": (
            (["UNSIGNED MODULE(S) with CONFIG_MODULE_SIG_FORCE=y: kernel rejects unsigned modules; do not flash"]
             if signature_load_blocked else [])
            + [
            "Module signer and vermagic cannot establish ABI or trusted-key compatibility with the installed ROM",
            "DTBs are not yet matched with the exact installed ROM boot image",
            "Never flash Image, DTBs or modules from this report directly",
            ]
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact_dir", type=Path)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--profile", choices=("baseline", "core", "external"), required=True)
    args = parser.parse_args()
    try:
        if not SHA.fullmatch(args.expected_sha):
            raise ValueError("Expected upstream SHA must contain exactly 40 lowercase hex digits")
        artifact_dir = args.artifact_dir.resolve(strict=True)
        report = collect(artifact_dir, args.expected_sha, args.profile)
        output = artifact_dir / "artifact-report.json"
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Raw artifact audit: {report['module_count']} modules, {report['signed_module_count']} signed, {report['dtb_count']} DTBs")
        print("Release state: RAW_ARTIFACT_ONLY_UNVERIFIED; flash_ready=false")
        return 0
    except (OSError, ValueError) as exc:
        print(f"Artifact audit FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
