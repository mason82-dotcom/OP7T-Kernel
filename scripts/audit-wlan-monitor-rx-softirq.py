#!/usr/bin/env python3
"""Read-only hotdog monitor-RX callback and kernel softirq semantics audit.

The result is a *review blocker*, never proof that the RFC is safe or that
monitor mode works. No kernel patching, devices or compilation.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

PIN = "1083c6c5906114c71b11a429898b111a1b1b8109"
WLAN_PATH = "drivers/staging/qcacld-3.0/core/hdd/src/wlan_hdd_tx_rx.c"
DEV_PATH = "net/core/dev.c"
KBUILD_PATH = "drivers/staging/qcacld-3.0/Kbuild"
PROFILE_PATH = "drivers/staging/qcacld-3.0/configs/default_defconfig"
PATCH_PATH = "patches/candidates/0002-qcacld-hotdog-icnss-monitor-rx-rfc.patch"
ROOT = Path(__file__).resolve().parents[1]


class ContextAuditError(ValueError):
    pass


def require_once(text, pattern, reason):
    hits = list(re.finditer(pattern, text, re.MULTILINE | re.DOTALL))
    if len(hits) != 1:
        raise ContextAuditError(reason)
    return hits[0]


def c_function(source, function):
    # Require exactly one C definition, not a comment, declaration or call.
    hit = require_once(
        source,
        r"^[ \t]*(?:static[ \t]+)?(?:QDF_STATUS|int)"
        r"[ \t]+" + re.escape(function) +
        r"[ \t]*\([^;{}]*\)[ \t\n]*\{",
        "Missing or ambiguous function definition: " + function,
    )
    left = hit.end() - 1
    depth = 0
    for i in range(left, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[left:i + 1]
    raise ContextAuditError("Incomplete C function: " + function)


def check_rfc_patch(patch):
    if not patch or len(patch.encode("utf-8")) > 65536:
        raise ContextAuditError("Invalid or oversized monitor RFC patch")
    if patch.count("diff --git ") != 1 or patch.count("\n@@ ") != 1:
        raise ContextAuditError("RFC patch changed structure or file count")
    needle = "diff --git a/" + WLAN_PATH + " b/" + WLAN_PATH
    if needle not in patch or patch.count(needle) != 1:
        raise ContextAuditError("RFC does not exclusively target ICNSS RX source")
    minus = [x[1:].strip() for x in patch.splitlines()
             if x.startswith("-") and not x.startswith("---")]
    plus = [x[1:].strip() for x in patch.splitlines()
            if x.startswith("+") and not x.startswith("+++")]
    if minus != ["* Scheduling rx sirq", "rxstat = netif_rx_ni(skb);"]:
        raise ContextAuditError("Unexpected RFC removal scope")
    if plus != ["* Same backlog path; avoid _ni BH handling",
                "rxstat = netif_rx(skb);"]:
        raise ContextAuditError("Unexpected RFC added code or comment")


def inspect_sources(wlan, dev, kbuild, profile, patch):
    cb = c_function(wlan, "hdd_mon_rx_packet_cbk")
    capture = c_function(wlan, "hdd_set_pktcapture_cb")
    monitor = c_function(wlan, "hdd_set_mon_rx_cb")
    ordinary = c_function(dev, "netif_rx")
    immediate = c_function(dev, "netif_rx_ni")

    if cb.count("rxstat = netif_rx(skb);") != 1 or cb.count(
            "rxstat = netif_rx_ni(skb);") != 1:
        raise ContextAuditError("Callback skb-chain dispatch changed")
    if not re.search(
        r"if[ \t]*\([ \t]*skb->next[ \t]*\)[ \t]*\{"
        r"[^}]*rxstat[ \t]*=[ \t]*netif_rx\(skb\);[ \t]*\}"
        r"[ \t]*else[ \t]*\{[^}]*"
        r"rxstat[ \t]*=[ \t]*netif_rx_ni\(skb\);",
        cb, re.DOTALL,
    ):
        raise ContextAuditError("Original final-SKB immediate-drain branch changed")
    if ("Scheduling rx sirq" not in cb or
            "skb_next = skb->next;" not in cb or
            "qdf_net_buf_debug_release_skb(skb);" not in cb):
        raise ContextAuditError("Callback queue/lifetime logic differs")
    if "cdp_register_pktcapture_cb" not in capture or (
            "hdd_mon_rx_packet_cbk" not in capture):
        raise ContextAuditError("Packet-capture registration changed")
    if ("txrx_ops.rx.rx = hdd_mon_rx_packet_cbk;" not in monitor or
            "cdp_vdev_register(" not in monitor):
        raise ContextAuditError("Monitor vdev callback registration changed")
    if not re.search(r"#ifdef[ \t]+WLAN_FEATURE_PKT_CAPTURE[\s\S]*?"
                     r"\bint[ \t]+hdd_set_pktcapture_cb\(", wlan):
        raise ContextAuditError("Capture callback compile guard not located")
    if not re.search(r"#ifdef[ \t]+FEATURE_MONITOR_MODE_SUPPORT[\s\S]*?"
                     r"\bint[ \t]+hdd_set_mon_rx_cb\(", wlan):
        raise ContextAuditError("Monitor callback compile guard not located")
    if "return netif_rx_internal(skb);" not in ordinary:
        raise ContextAuditError("netif_rx() kernel semantics changed")
    if ("netif_rx_internal(skb);" not in immediate or
            "local_softirq_pending()" not in immediate or
            "do_softirq();" not in immediate or
            "preempt_disable();" not in immediate or
            "preempt_enable();" not in immediate):
        raise ContextAuditError("netif_rx_ni() kernel softirq semantics changed")
    if "do_softirq(" in ordinary or "local_softirq_pending(" in ordinary:
        raise ContextAuditError("netif_rx() also performs immediate softirq drain")
    if not re.search(r"ifeq[ \t]*\(\$\(CONFIG_LITHIUM\),[ \t]*y\)"
                     r"[\s\S]*?HDD_OBJS[ \t]*\+=[ \t]*\$\(HDD_SRC_DIR\)/wlan_hdd_rx_monitor.o",
                     kbuild):
        raise ContextAuditError("Inactive LITHIUM monitor object guard changed")
    if not re.search(r"\$\(HDD_SRC_DIR\)/wlan_hdd_tx_rx.o", kbuild):
        raise ContextAuditError("ICNSS RX callback object not in Kbuild")
    if not re.search(r"ifeq[ \t]*\(\$\(CONFIG_ICNSS\),[ \t]*y\)"
                     r"[ \t\n]*CONFIG_HELIUMPLUS[ \t]*:=[ \t]*y", profile):
        raise ContextAuditError("Selected ICNSS/HELIUMPLUS profile changed")
    check_rfc_patch(patch)
    return {
        "schema": "hotdog-monitor-rx-softirq-source-audit-v1",
        "pinned_kernel_source": PIN,
        "selected_rx_object": "drivers/staging/qcacld-3.0/core/hdd/src/wlan_hdd_tx_rx.o",
        "driver_family": "ICNSS_HELIUMPLUS",
        "registration_sites": [
            "hdd_set_mon_rx_cb: cdp_vdev_register",
            "hdd_set_pktcapture_cb: cdp_register_pktcapture_cb (conditional)",
        ],
        "original_last_skb_uses_netif_rx_ni": True,
        "kernel_netif_rx_ni_explicitly_drains_pending_softirq": True,
        "kernel_netif_rx_has_no_explicit_immediate_softirq_drain": True,
        "rfc_changes_last_skb_immediate_softirq_drain": True,
        "rfc_modifies_only_rx_backlog_call": True,
        "caller_cpu_context_verified": False,
        "caller_bh_and_napi_state_verified": False,
        "rfc_behavioral_equivalence_verified": False,
        "passive_monitor_runtime_verified": False,
        "packet_injection_verified": False,
        "rom_module_abi_verified": False,
        "flash_ready": False,
        "status": "STATIC_ONLY_SEMANTIC_CHANGE_REQUIRES_CALLER_CONTEXT",
        "next_required_evidence": [
            "prove ICNSS monitor RX callback invocation context without device mutation",
            "establish softirq/BH/NAPI scheduling invariants before any patch promotion",
            "verify complete exact ROM kernel and module ABI independently",
        ],
    }


def checked_git(kernel, *args):
    try:
        return subprocess.run(
            ["git", "-C", str(kernel), *args], check=True,
            capture_output=True, text=True, timeout=20,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        raise ContextAuditError("Pinned source Git verification failed") from None


def audit(kernel, project=ROOT):
    kernel = Path(kernel).resolve(strict=True)
    project = Path(project).resolve(strict=True)
    if checked_git(kernel, "rev-parse", "HEAD") != PIN:
        raise ContextAuditError("Not the immutable pinned hotdog kernel source")
    if checked_git(kernel, "status", "--porcelain"):
        raise ContextAuditError("Original source checkout was modified")
    board = (kernel / "arch/arm64/configs/vendor/sm8150-perf_defconfig").read_text(
        encoding="utf-8"
    )
    oplus = (kernel / "arch/arm64/configs/vendor/oplus.config").read_text(
        encoding="utf-8"
    )
    if not re.search(r"^CONFIG_ICNSS=y$", board, re.MULTILINE):
        raise ContextAuditError("Pinned hotdog defconfig no longer selects ICNSS")
    if (not re.search(r"^CONFIG_QCA_CLD_WLAN=m$", oplus, re.MULTILINE) or
            not re.search(r'^CONFIG_QCA_CLD_WLAN_PROFILE="default"$',
                          oplus, re.MULTILINE)):
        raise ContextAuditError("Pinned hotdog vendor WLAN build profile changed")
    original = project / PATCH_PATH
    if original.is_symlink() or not original.is_file():
        raise ContextAuditError("Missing or linked approved RFC patch")
    files = {}
    for name in (WLAN_PATH, DEV_PATH, KBUILD_PATH, PROFILE_PATH):
        item = kernel / name
        if not item.is_file() or item.is_symlink():
            raise ContextAuditError("Pinned kernel source input unavailable")
        files[name] = item.read_text(encoding="utf-8")
    patch = original.read_text(encoding="utf-8")
    report = inspect_sources(
        files[WLAN_PATH], files[DEV_PATH], files[KBUILD_PATH],
        files[PROFILE_PATH], patch,
    )
    report["source_sha256"] = {
        name: hashlib.sha256(content.encode("utf-8")).hexdigest()
        for name, content in files.items()
    }
    report["rfc_patch_sha256"] = hashlib.sha256(patch.encode("utf-8")).hexdigest()
    report["original_checkout_verified_clean_and_pinned"] = True
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit(args.kernel)
    except (OSError, UnicodeError, ContextAuditError) as e:
        print("RX SOFTIRQ STATIC AUDIT BLOCKED: " + str(e), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
,
                          oplus, re.MULTILINE)):
        raise ContextAuditError("Pinned hotdog vendor WLAN build profile changed")
    original = project / PATCH_PATH
    if original.is_symlink() or not original.is_file():
        raise ContextAuditError("Missing or linked approved RFC patch")
    files = {}
    for name in (WLAN_PATH, DEV_PATH, KBUILD_PATH, PROFILE_PATH):
        item = kernel / name
        if not item.is_file() or item.is_symlink():
            raise ContextAuditError("Pinned kernel source input unavailable")
        files[name] = item.read_text(encoding="utf-8")
    patch = original.read_text(encoding="utf-8")
    report = inspect_sources(
        files[WLAN_PATH], files[DEV_PATH], files[KBUILD_PATH],
        files[PROFILE_PATH], patch,
    )
    report["source_sha256"] = {
        name: hashlib.sha256(content.encode("utf-8")).hexdigest()
        for name, content in files.items()
    }
    report["rfc_patch_sha256"] = hashlib.sha256(patch.encode("utf-8")).hexdigest()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit(args.kernel)
    except (OSError, UnicodeError, ContextAuditError) as e:
        print("RX SOFTIRQ STATIC AUDIT BLOCKED: " + str(e), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
