#!/usr/bin/env python3
"""Offline preflight for the pinned hotdog QCACLD WLAN patch candidate."""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SHA = "1083c6c5906114c71b11a429898b111a1b1b8109"
ROOT = Path(__file__).resolve().parents[1]
BASE = Path("drivers/staging/qcacld-3.0")


def inspect_source(source):
    paths = {
        "config": BASE / "configs/default_defconfig",
        "kbuild": BASE / "Kbuild",
        "rx": BASE / "core/hdd/src/wlan_hdd_rx_monitor.c",
    }
    sources = {}
    for field, relative in paths.items():
        item = source / relative
        if not item.is_file() or item.is_symlink() or not (0 < item.stat().st_size <= 8 * 1024 * 1024):
            raise ValueError("Missing/invalid pinned WLAN source: " + field)
        sources[field] = item.read_text(encoding="utf-8")
    match = re.findall(r"^\s*CONFIG_FEATURE_MONITOR_MODE_SUPPORT\s*:?=\s*([yn])\s*$",
                       sources["config"], re.MULTILINE)
    if len(match) != 1:
        raise ValueError("Ambiguous monitor mode config")
    return {
        "schema": "hotdog-qcacld-monitor-patch-candidates-v1",
        "kernel_source_sha": SHA,
        "monitor_enabled_in_default_profile": match[0] == "y",
        "kimocoder_patch_redundant": match[0] == "y",
        "rx_netif_rx_ni_call_count": sources["rx"].count("rxstat = netif_rx_ni(skb);"),
        "rx_netif_rx_call_count": sources["rx"].count("rxstat = netif_rx(skb);"),
        "rx_object_in_kbuild": "wlan_hdd_rx_monitor.o" in sources["kbuild"],
        "lithium_gate_in_kbuild": "CONFIG_LITHIUM" in sources["kbuild"],
        "packet_capture_gate_in_kbuild": "CONFIG_WLAN_FEATURE_PKT_CAPTURE" in sources["kbuild"],
        "rx_rfc_anchor_matches": sources["rx"].count("rxstat = netif_rx_ni(skb);") == 1,
        "patch_applied": False,
        "runtime_monitor_verified": False,
        "packet_injection_verified": False,
        "flash_ready": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, default=ROOT / ".work/kernel")
    args = p.parse_args()
    try:
        rev = subprocess.run(["git", "-C", str(args.source), "rev-parse", "HEAD"],
                             capture_output=True, check=True, text=True, timeout=10)
        if rev.stdout.strip() != SHA:
            raise ValueError("Source SHA differs from pinned upstream")
        report = inspect_source(args.source)
    except (OSError, UnicodeError, ValueError, subprocess.SubprocessError) as exc:
        print("WLAN patch preflight FAILED: " + str(exc), file=sys.stderr)
        return 3
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["rx_rfc_anchor_matches"] else 2


if __name__ == "__main__":
    sys.exit(main())
