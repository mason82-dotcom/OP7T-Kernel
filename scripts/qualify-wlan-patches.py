#!/usr/bin/env python3
"""Check two optional QCACLD patches against exact hotdog sources, read only."""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIN = "1083c6c5906114c71b11a429898b111a1b1b8109"
CANDIDATES = (
    ("monitor-vdev-safety",
     "patches/qcacld-3.0/0001-monitor-vdev-null-and-error-guards.patch",
     frozenset({
         "drivers/staging/qca-wifi-host-cmn/dp/wifi3.0/dp_main.c",
         "drivers/staging/qcacld-3.0/core/hdd/src/wlan_hdd_rx_monitor.c",
     })),
    ("hotdog-icnss-monitor-rx",
     "patches/candidates/0002-qcacld-hotdog-icnss-monitor-rx-rfc.patch",
     frozenset({"drivers/staging/qcacld-3.0/core/hdd/src/wlan_hdd_tx_rx.c"})),
)
SOURCE = {
    "defconfig": "arch/arm64/configs/vendor/sm8150-perf_defconfig",
    "oplus": "arch/arm64/configs/vendor/oplus.config",
    "profile": "drivers/staging/qcacld-3.0/configs/default_defconfig",
    "icnss_rx": "drivers/staging/qcacld-3.0/core/hdd/src/wlan_hdd_tx_rx.c",
    "lithium_rx": "drivers/staging/qcacld-3.0/core/hdd/src/wlan_hdd_rx_monitor.c",
    "dp": "drivers/staging/qca-wifi-host-cmn/dp/wifi3.0/dp_main.c",
}


class GateError(ValueError):
    pass


def validate_patch(path, allowed):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise GateError("Patch missing or symlinked")
    binary = path.read_bytes()
    if not 0 < len(binary) <= 32768 or b"\x00" in binary:
        raise GateError("Patch is empty, binary or oversized")
    content = binary.decode("utf-8")
    if not content.endswith("\n") or "\r" in content:
        raise GateError("Invalid line endings")
    for forbidden in ("GIT binary patch", "Binary files ", "new file mode ",
                      "deleted file mode ", "rename from ", "rename to ",
                      "copy from ", "copy to ", "old mode ", "new mode "):
        if forbidden in content:
            raise GateError("Forbidden patch operation")
    headers = re.findall(r"^diff --git a/(\S+) b/(\S+)$", content, re.M)
    before = re.findall(r"^--- a/(\S+)$", content, re.M)
    after = re.findall(r"^\+\+\+ b/(\S+)$", content, re.M)
    if (len(headers) != len(allowed) or
            len(set(headers)) != len(headers) or
            any(a != b for a, b in headers) or
            {a for a, b in headers} != allowed or
            len(before) != len(allowed) or set(before) != allowed or
            len(after) != len(allowed) or set(after) != allowed or
            not re.search(r"^@@ -\d+", content, re.M)):
        raise GateError("Patch changed unapproved source paths")
    added = "\n".join(l[1:] for l in content.splitlines()
                      if l.startswith("+") and not l.startswith("+++"))
    if re.search(r"(?i)CONFIG_MODULE_SIG|CONFIG_SECURITY_SELINUX|"
                 r"CONFIG_WLAN_DEBUG_CRASH_INJECT|fastboot|"
                 r"frame_inject|packet_injection|disable_avb", added):
        raise GateError("Security/TX scope expanded outside review")
    return hashlib.sha256(binary).hexdigest()


def inspect_source(root):
    content = {}
    for name, relative in SOURCE.items():
        p = root / relative
        if p.is_symlink() or not p.is_file() or not (0 < p.stat().st_size < 2**21):
            raise GateError("Pinned source missing or invalid: " + name)
        content[name] = p.read_text(encoding="utf-8")
    def unique(pattern, key):
        return len(re.findall(pattern, content[key], re.M)) == 1
    icnss = unique(r"^CONFIG_ICNSS=y$", "defconfig")
    module = unique(r"^CONFIG_QCA_CLD_WLAN=m$", "oplus")
    profile = unique(r'^CONFIG_QCA_CLD_WLAN_PROFILE="default"$', "oplus")
    monitor = unique(r"^CONFIG_FEATURE_MONITOR_MODE_SUPPORT\s*:?=\s*y$", "profile")
    callback = re.search(r"^static QDF_STATUS hdd_mon_rx_packet_cbk\(.*?^\}\n#endif",
                         content["icnss_rx"], re.S | re.M)
    rx = callback.group(0) if callback else ""
    rx_ok = (bool(callback) and rx.count("rxstat = netif_rx(skb);") == 1 and
             rx.count("rxstat = netif_rx_ni(skb);") == 1)
    # Other DP functions legitimately have the same generic !pdev guard.
    # Inspect only the monitor getter, and reject zero/ambiguous definitions.
    mon_vdev_defs = re.findall(
        r"^static uint8_t dp_get_mon_vdev_from_pdev_wifi3\(.*?^\}",
        content["dp"], re.MULTILINE | re.DOTALL,
    )
    mon_vdev_body = mon_vdev_defs[0] if len(mon_vdev_defs) == 1 else ""
    safety_ok = (
        len(mon_vdev_defs) == 1 and
        mon_vdev_body.count("if (qdf_unlikely(!pdev))") == 1 and
        mon_vdev_body.count("return pdev->monitor_vdev->vdev_id;") == 1 and
        content["lithium_rx"].count("if (vdev_id < 0)") == 1 and
        content["lithium_rx"].count("cdp_get_mon_vdev_from_pdev(") == 1)
    return {
        "hotdog_icnss_configured": icnss,
        "qcacld_module_selected": module,
        "default_profile_selected": profile,
        "monitor_flag_already_enabled": monitor,
        "legacy_callback_anchor_matched": rx_ok,
        "vdev_safety_anchor_matched": safety_ok,
        "eligible": all((icnss, module, profile, monitor, rx_ok, safety_ok)),
    }


def git(kernel, *args):
    try:
        proc = subprocess.run(["git", "-C", str(kernel), *map(str, args)],
                              capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise GateError("Git unavailable") from e
    if proc.returncode:
        raise GateError("Git preflight failed at: " + args[0])
    return proc.stdout.strip()


def qualify(kernel, project=ROOT):
    kernel = Path(kernel).resolve(strict=True)
    project = Path(project).resolve(strict=True)
    lock = (project / "config/upstream.lock").read_text(encoding="utf-8")
    if re.findall(r"^UPSTREAM_SHA=([0-9a-f]{40})$", lock, re.M) != [PIN]:
        raise GateError("Upstream lock differs from this review")
    if not (kernel / ".git").exists() or git(kernel, "rev-parse", "HEAD") != PIN:
        raise GateError("Kernel SHA does not match pinned source")
    if git(kernel, "status", "--porcelain"):
        raise GateError("Kernel tree must be clean")
    source = inspect_source(kernel)
    if not source["eligible"]:
        raise GateError("Hotdog compile flags or callback anchors changed")
    paths = []
    patches = []
    for name, relative, allowed in CANDIDATES:
        candidate = project / relative
        digest = validate_patch(candidate, allowed)
        paths.append(candidate.resolve(strict=True))
        patches.append({"id": name, "path": relative, "sha256": digest,
                        "affected_files": len(allowed), "review_only": True})
    # One combined check also detects conflicts between the two candidate patches.
    git(kernel, "apply", "--check", *paths)
    if git(kernel, "status", "--porcelain"):
        raise GateError("Source unexpectedly changed during check")
    return {
        "schema": "hotdog-wlan-rfc-preflight-v1",
        "source_sha": PIN,
        "source_eligibility": source,
        "patches": patches,
        "combined_patch_context_check": True,
        "patch_applied": False,
        "patched_modules_compiled": False,
        "installed_rom_abi_verified": False,
        "signing_key_trust_verified": False,
        "runtime_monitor_verified": False,
        "packet_injection_verified": False,
        "flash_ready": False,
        "status": "READ_ONLY_CONTEXT_CHECK_ONLY",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--kernel", type=Path, default=ROOT / ".work/kernel")
    p.add_argument("--output", type=Path, help="Optional new file, never overwrite")
    args = p.parse_args()
    try:
        result = qualify(args.kernel)
        payload = json.dumps(result, sort_keys=True, indent=2) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as f:
                f.write(payload)
        print(payload, end="")
        return 0
    except (GateError, OSError, UnicodeError, subprocess.SubprocessError) as e:
        print("WLAN patch preflight BLOCKED: " + str(e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
