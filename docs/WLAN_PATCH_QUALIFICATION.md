# QCACLD-3.0 monitor RX and VDEV patch qualification — hotdog

**Review-only status:** two candidate patches are stored, neither is applied by the kernel build. Target: OnePlus 7T Pro (hotdog), crDroid 13 / Android 17, pinned source commit 1083c6c5906114c71b11a429898b111a1b1b8109.

## What is qualified

| Candidate | Origin | Scope | Remaining evidence |
| --- | --- | --- | --- |
| Monitor VDEV safety | [PR #18](https://github.com/mason82-dotcom/OP7T-Kernel/pull/18) | Guard missing DP monitor VDEV / SoC and check unsigned error sentinel correctly | Compile and firmware/runtime/hardware validation |
| Hotdog ICNSS monitor RX | [PR #23](https://github.com/mason82-dotcom/OP7T-Kernel/pull/23) | Change last monitor SKB from netif_rx_ni() to netif_rx() in hdd_mon_rx_packet_cbk() | **Prove callback execution context first**, then isolated compile and passive RX measurements |

In the pinned kernel, CONFIG_ICNSS=y and the QCACLD default profile is selected as a signed module. CONFIG_FEATURE_MONITOR_MODE_SUPPORT is already y; the historical kimocoder one-line enable patch is redundant. The alternate wlan_hdd_rx_monitor.c RX callback has other QCA/Lithium gates and must not be assumed to carry the hotdog receive path.

## Read-only test procedure

From this repository root on a supported Linux development host:

    bash scripts/fetch-source.sh
    python3 -m unittest discover -s tests -v
    python3 scripts/qualify-wlan-patches.py --kernel .work/kernel

The final command verifies the exact upstream SHA, pristine source checkout, hotdog-specific driver flags and callback signatures. It rejects patches touching files outside a hardcoded allowlist and runs a **combined git apply --check**, detecting conflicting patch contexts without applying or modifying the source.

GitHub Actions performs this check in a separate PR job. Existing core/external CI builds continue to use the **unmodified** source. A passing patch-context check is not an experimental patched-module compile.

## Acceptance gates for future experimental kernel work

1. Confirm which monitor RX callback runs and its NAPI / softirq / process context. Using netif_rx() instead of netif_rx_ni() is a hypothesis, not a proven correction.
2. If indicated by measurement, test the two candidates in a disposable source tree and compile both kernel profiles with preserved strip-before-sign and integrity checks.
3. Compare kernel and module ABI, original installed crDroid ROM modules, certificate trust and vendor WLAN firmware compatibility. Signature presence alone is not key trust.
4. Verify passive frame capture, normal Wi-Fi association/reconnect, suspend/resume, battery/thermal effects and regulatory operation on owned hardware.

These candidates **do not enable 802.11 packet injection** and do not grant monitor capabilities through Kconfig alone. Never force IFF_UP or private netdevice state bits to mask a broken monitor interface. No ADB writes, reflashing, AVB changes, SELinux bypass, vendor firmware edits or reduced CONFIG_MODULE_SIG_FORCE enforcement are authorized by this PR.

**flash_ready=false**
