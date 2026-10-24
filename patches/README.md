# QCACLD 3.0 WLAN patch catalog — OnePlus 7T Pro (`hotdog`)

**Repository reference**: `crdroidandroid/android_kernel_oneplus_sm8150`, branch `17.0`, pinned source commit `1083c6c5906114c71b11a429898b111a1b1b8109`.
Android 17 / crDroid 13; kernel Linux 4.14.357-derived.

## Patch A (P0): Passive monitor-VDEV safety

**Available as a candidate**, not applied to the build: [0001-monitor-vdev-null-and-error-guards.patch](qcacld-3.0/0001-monitor-vdev-null-and-error-guards.patch).

The original pinned driver contains:

- `dp_get_mon_vdev_from_pdev_wifi3`: uses `pdev->monitor_vdev->vdev_id` after guarding `pdev` but not `monitor_vdev`; a missing monitor VDEV can cause a null-pointer dereference.
- `hdd_enable_monitor_mode`: receives the VDEV ID as `uint8_t`, then checks `vdev_id < 0`, which can never be true. The CDP helpers encode `-EINVAL` in this unsigned return value. The patch checks that specific encoded sentinel and fails on missing SoC context.

Scope: two narrowly scoped source changes. No TX path, injection, regulatory overrides or firmware changes. A valid VDEV with numeric value equal to the encoded sentinel would be indistinguishable under the existing ABI; real hardware range and firmware behavior still require review.

**Read-only preflight**, only after obtaining the exact pinned source via `bash scripts/fetch-source.sh`:

```bash
python3 scripts/check-wlan-patches.py --kernel .work/kernel
```

The preflight checks the SHA lock, clean checkout, only the two allowed source paths, and `git apply --check`. It does NOT apply, compile or flash the patch. A successful preflight is only an applicability check.

Manual source-level review is still required. If explicitly applying the patch in an isolated throwaway checkout, compile an experimental profile and validate Wi-Fi station mode, scanning, association, suspend/resume, passive monitor capture, and regression behavior on an owned device **only after** the independent boot, module-key and ROM/ABI release gates are met. Never flash unverified builds.

## Additional proposed patch tracks (not yet ported)

| Priority | Candidate | Evidence required | Status |
| --- | --- | --- | --- |
| P0 | Exact ROM WLAN module ABI, signatures and `vendor_dlkm` placement | Original ROM hash, `__versions`, `Module.symvers`, firmware, signer trust | Existing offline tooling; runtime unknown |
| P1 | Passive internal monitor mode lifecycle/channel validation | cfg80211 advertise/registration, monitor-only mode switch, `cdp_set_monitor_mode`, Radiotap reception | Candidate A guards error paths; not compiled |
| P2 | USB WLAN compatibility for ath9k_htc, carl9170, rtl8187, rt2800usb, mt7601u | Adapter USB IDs, matched firmware, cross-compile, module signing, RF/regulatory behavior | Kernel config experimental; no driver backport |
| P3 | External RTL8812AU/MT7612U ports | Exact driver commit and license, Linux 4.14 and Clang compatibility, stable API, signed module | Not imported |
| Research | Internal QCACLD injection | Confirmed hardware/firmware TX support and lawful controlled test plan | Not implemented; no claim |

The pinned source already has `CONFIG_FEATURE_MONITOR_MODE_SUPPORT := y`, `NL80211_IFTYPE_MONITOR` and a passive receive handler. In `wlan_hdd_main.c`, the monitor netdev ops intentionally have no `ndo_start_xmit`; changing cfg80211 flags does not create a functional injection path. NetHunter documentation states QCACLD 3.0 is monitor-only. Therefore do not transplant generic `mac80211` injection patches into Qualcomm's offload datapath.

References: [Kali NetHunter WLAN adapter guidance](https://www.kali.org/docs/nethunter/wireless-cards/), [NetHunter kernel patch taxonomy](https://gitlab.com/kalilinux/nethunter/build-scripts/kali-nethunter-kernels/-/tree/main), [device community report with passive capture](https://github.com/althsec/nethunter-oneplus7tpro-los23.2).

**Review gates**: no production WLAN changes, no private keys in artifacts, no AVB/SELinux weakening, no flashable output, no device writes. `flash_ready=false`.
