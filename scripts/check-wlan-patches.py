#!/usr/bin/env python3
"""Read-only compatibility preflight for a pinned optional QCACLD monitor patch.

This NEVER applies the patch, builds a module, accesses ADB, or flashes a device.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
LOCK = PROJECT / "config/upstream.lock"
PATCH = PROJECT / "patches/qcacld-3.0/0001-monitor-vdev-null-and-error-guards.patch"
ALLOWED = {
    "drivers/staging/qca-wifi-host-cmn/dp/wifi3.0/dp_main.c",
    "drivers/staging/qcacld-3.0/core/hdd/src/wlan_hdd_rx_monitor.c",
}

class PreflightError(ValueError):
    pass


def expected_commit(lock=LOCK):
    text = Path(lock).read_text(encoding="utf-8")
    sha = re.findall(r"^UPSTREAM_SHA=([a-f0-9]{40})$", text, flags=re.M)
    if len(sha) != 1:
        raise PreflightError("Source SHA lock missing or ambiguous")
    return sha[0]


def validate_patch(path=PATCH):
    p = Path(path)
    payload = p.read_bytes()
    if not payload or len(payload) > 32 * 1024:
        raise PreflightError("Unexpected patch size")
    text = payload.decode("utf-8")
    entries = re.findall(r"^diff --git a/(\S+) b/(\S+)$", text, flags=re.M)
    if (len(entries) != len(ALLOWED) or
            {left for left, right in entries if left == right} != ALLOWED or
            any(left != right for left, right in entries)):
        raise PreflightError("Patch changes unexpected source paths")
    if not text.endswith("\n"):
        raise PreflightError("Patch must end in a newline")
    return hashlib.sha256(payload).hexdigest()


def invoke_git(*args):
    try:
        result = subprocess.run(["git", *map(str, args)],
                                capture_output=True, text=True, check=False, timeout=60)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        raise PreflightError("Cannot inspect pinned checkout") from e
    if result.returncode != 0:
        raise PreflightError("Read-only Git preflight failed")
    return result.stdout.strip()


def check(kernel, patch=PATCH, lock=LOCK):
    kernel = Path(kernel).resolve(strict=True)
    if not kernel.is_dir() or not (kernel / ".git").exists():
        raise PreflightError("Pinned kernel Git checkout is required")
    locked = expected_commit(lock)
    patch_hash = validate_patch(patch)
    head = invoke_git("-C", kernel, "rev-parse", "--verify", "HEAD")
    if head != locked:
        raise PreflightError("Checked-out kernel commit differs from upstream.lock")
    if invoke_git("-C", kernel, "status", "--porcelain"):
        raise PreflightError("Kernel checkout must be clean")
    invoke_git("-C", kernel, "apply", "--check", Path(patch).resolve(strict=True))
    return {
        "schema": "hotdog-qcacld-monitor-safety-preflight-v1",
        "upstream_commit": locked,
        "patch_sha256": patch_hash,
        "files_checked": len(ALLOWED),
        "patch_applicable_to_clean_source": True,
        "patch_applied": False,
        "patch_compiled": False,
        "monitor_mode_runtime_verified": False,
        "packet_injection_enabled": False,
        "flash_ready": False,
        "status": "CONTEXT_CHECK_ONLY",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--kernel", type=Path, default=PROJECT / ".work/kernel")
    args = p.parse_args()
    try:
        report = check(args.kernel)
    except (PreflightError, OSError, UnicodeError) as e:
        print("WLAN patch preflight blocked: " + str(e), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
