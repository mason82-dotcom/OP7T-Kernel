# QCACLD-3.0 WLAN patch candidates — hotdog / crDroid v13 / Android 17

**Research only. No candidate is wired into `scripts/build.sh` or applied to the pinned source.**

Source reference: `crdroidandroid/android_kernel_oneplus_sm8150`, revision
`1083c6c5906114c71b11a429898b111a1b1b8109` (Linux 4.14.357).

## Priority and disposition

| Priority | Candidate | Evidence at pinned source | Recommendation |
| --- | --- | --- | --- |
| P0 | [kimocoder monitor enable](https://github.com/kimocoder/qualcomm_android_monitor_mode/blob/master/files/enable_monitor_mode.patch) | `qcacld-3.0/configs/default_defconfig:875` already says `CONFIG_FEATURE_MONITOR_MODE_SUPPORT := y` | **Do not apply: redundant** |
| P1a | [hotdog ICNSS RX callback RFC](../patches/candidates/0002-qcacld-hotdog-icnss-monitor-rx-rfc.patch) | **Actual hotdog configuration** has `CONFIG_ICNSS=y` and `CONFIG_QCA_CLD_WLAN=m`; `hdd_mon_rx_packet_cbk()` in `wlan_hdd_tx_rx.c:1451` uses `netif_rx_ni(skb)` | Prefer for scoped review; not applied or proven safe |
| P1b | [Lithium/QCA6xxx monitor RX RFC](../patches/candidates/0001-qcacld-monitor-rx-netif-rx-rfc.patch) | `wlan_hdd_rx_monitor.c:85` also calls `netif_rx_ni(skb)`, but `wlan_hdd_rx_monitor.h` gates the callback to `QCA_WIFI_QCA6290/6390/6490/6750`; these guards are **not proven active** on hotdog's ICNSS path | Keep as reference only; not the primary hotdog candidate |
| P2 | Qualcomm packet-capture feature wiring | Pinned `Kbuild` contains `CONFIG_WLAN_FEATURE_PKT_CAPTURE`, `CONFIG_LITHIUM`, `FEATURE_MONITOR_MODE_SUPPORT` branches | Investigate effective feature flags, actual firmware and chipset before changes |
| P3 | [Re4son SM8150 NetHunter Android 10](https://github.com/Re4son/android_kernel_oneplus_sm8150_draco/tree/nethunter-10.0) | Similar Qualcomm SoC family, different branch, ROM and firmware | Compare specific source code only; no wholesale port |
| P4 | [Loukious Xiaomi SM8150 injection commit](https://github.com/Loukious/android_kernel_xiaomi_sm8150/commit/18c57c61ecd8f02de778e36db6be9b41167a8825) | Changes ~40 files including `wlan_hdd_frame_inject.c` and TX datapath | **Defer**: substantial security/firmware/ABI and integration uncertainty |
| P5 | External USB adapters | Already requested experimental `ath9k_htc`, `carl9170`, `rtl8187`, `mt7601u`, `rt2800usb` | Prefer actual adapter and firmware tests; no in-kernel injection claim |

## Confirmed source findings

- `arch/arm64/configs/vendor/oplus.config` selects
  `CONFIG_QCA_CLD_WLAN=m` and `CONFIG_QCA_CLD_WLAN_PROFILE="default"`.
- The upstream QCACLD default profile already enables monitor-mode support,
  but runtime RX, cfg80211, firmware ring/capture support and signed-module
  ABI compatibility remain unverified on the installed crDroid ROM.
- The local RFC changes only `netif_rx_ni(skb)` to `netif_rx(skb)` for
  the final packet. This is a **hypothesis**, not an established fix; the
  correct RX API depends on NAPI/softirq/process context. Do not change
  `IFF_UP` or private `__LINK_STATE_START` flags to hide failures.
- A separate [hotdog LineageOS 23.2 Android 16 NetHunter project](https://github.com/althsec/nethunter-oneplus7tpro-los23.2)
  describes passive monitor-mode support without confirmed internal injection.
  It does **not** validate Android 17.

## Correct receive path for the actual hotdog build

Further inspection of the *pinned* `vendor/sm8150-perf_defconfig` found
`CONFIG_ICNSS=y`, rather than a proven QCA6290/6390/6490/6750
(`CONFIG_LITHIUM`) configuration. The corresponding
`vendor/oplus.config` selects QCACLD as a module with the `default` profile.
The `wlan_hdd_rx_monitor.h` helper is guarded by QCA6xxx chip macros and
falls back to stubs without them.

More relevant for **hotdog** is the monitor callback in
`core/hdd/src/wlan_hdd_tx_rx.c`:
`hdd_mon_rx_packet_cbk()` (line 1401), which is selected through
`hdd_set_mon_rx_cb()`. Its final SKB currently takes the
`netif_rx_ni()` path (line 1451). Candidate `0002` changes only the final
SKB to `netif_rx()`, aligning with its earlier-frame backlog path. This is
**not an established bug fix**: whether `netif_rx_ni()` is unsuitable depends
on the actual invocation context, backlog scheduling and monitor interface
state; there is no Android 17 device demonstration yet. No synthetic
`IFF_UP`, `__LINK_STATE_START`, packet capture forcing or TX injection is
included.

The revised offline source auditor now checks both callback paths and checks
`git apply --check` of candidate `0002` against the **locked upstream
SHA**. The command never modifies the source:

```bash
bash scripts/fetch-source.sh
python3 scripts/audit-wlan-patch-candidates.py --source .work/kernel
```

A successful source preflight only establishes that the RFC patch *would
apply*. To consider patching the kernel, reviewers must establish callback
context and capture output on the original unpatched build first. This source
RFC is **never applied automatically**.

## Safe next gates

1. Confirm pinned source SHA, device-specific ICNSS callback, and `git apply --check`
   using `scripts/audit-wlan-patch-candidates.py`; it never applies the patch.
2. Verify current build and `qcacld-3.0` effective compile defines.
3. Before any attempt to apply the RFC, instrument or inspect the monitor RX
   callback execution context and confirm why reception is failing.
4. Build as a separate `wlan.ko`, preserve signed/stripped module
   validation, then compare module version CRCs using
   `scripts/audit-module-abi.py`.
5. Require matching installed ROM, vendor firmware, signing trust, power
   management, connection stability and a read-only device baseline.

No change to AVB, SELinux, kernel signature enforcement, boot slot or firmware.
`flash_ready=false` at every stage.
