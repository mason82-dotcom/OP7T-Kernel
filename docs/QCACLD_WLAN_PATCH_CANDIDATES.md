# QCACLD-3.0 WLAN patch candidates — hotdog / crDroid v13 / Android 17

**Research only. No candidate is wired into `scripts/build.sh` or applied to the pinned source.**

Source reference: `crdroidandroid/android_kernel_oneplus_sm8150`, revision
`1083c6c5906114c71b11a429898b111a1b1b8109` (Linux 4.14.357).

## Priority and disposition

| Priority | Candidate | Evidence at pinned source | Recommendation |
| --- | --- | --- | --- |
| P0 | [kimocoder monitor enable](https://github.com/kimocoder/qualcomm_android_monitor_mode/blob/master/files/enable_monitor_mode.patch) | `qcacld-3.0/configs/default_defconfig:875` already says `CONFIG_FEATURE_MONITOR_MODE_SUPPORT := y` | **Do not apply: redundant** |
| P1 | [local RFC monitor RX final-SKB fix](../patches/candidates/0001-qcacld-monitor-rx-netif-rx-rfc.patch) | `core/hdd/src/wlan_hdd_rx_monitor.c:85` calls `netif_rx_ni(skb)`; preceding SKBs use `netif_rx(skb)` | Review on isolated build only; verify callback context first |
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

## Safe next gates

1. Confirm pinned source SHA and the exact matching source anchors using
   `scripts/audit-wlan-patch-candidates.py`; it never applies the patch.
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
