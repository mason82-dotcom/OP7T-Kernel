# NetHunter features and hardware acceptance

**Target**: OnePlus 7T Pro (`hotdog`), crDroid 13 / Android 17, Linux 4.14.357-derived kernel, pinned SHA from `config/upstream.lock`.

**Everything is experimental until built and tested on the exact ROM.** There are no tested NetHunter patch files in `patches/`. Do not advertise USB Arsenal, monitor mode or injection as working based on this document.

| Kali feature | Current kernel preparation | Requires hardware acceptance |
| --- | --- | --- |
| `HID-4` | Existing `USB_CONFIGFS_F_HID=y` and `USB_CONFIGFS=y` | Android USB functions, USB Arsenal, owned host enumeration |
| USB Arsenal modes | Existing NCM, RNDIS, HID; core adds ACM and ECM | User-space USB gadget setup, SELinux, role switching |
| `BT_RFCOMM` | Core requests `BT_RFCOMM=y`, `BT_RFCOMM_TTY=y` | BT classic and NetHunter tools; not internal BT patch |
| `ATH9K_HTC` | Experimental external profile requests in-tree driver | Match USB ID, firmware, power, monitor and injection in owned lab |
| `QCACLD` | Stock Qualcomm `qcacld-3.0` remains in source, configured as module | Matching signed `wlan.ko`, firmware, supported monitor mode, no injection assumption |
| `Injection` | **Not implemented** as a code patch | Per-chipset TX tests with permission; no capability claims |
| RTL8812AU / MT7612U | **Not included** (no compatible driver backport validated) | Separate version-specific driver port and load/signature review |

Official source for NetHunter's feature taxonomy: https://gitlab.com/kalilinux/nethunter/build-scripts/kali-nethunter-kernels/-/tree/main

## Firmware notes for external USB Wi-Fi (not bundled)

These are chipset families, not universal device guarantees:

* Atheros `ath9k_htc`: AR9271/AR7010 family, `htc_9271.fw` / `htc_7010.fw` for matching chipsets
* `carl9170`: AR9170 family, `carl9170-1.fw`
* `mt7601u`: MT7601U family, `mt7601u.bin`
* `rtl8187`: RTL8187 family (device revision must be checked)
* `rt2800usb`: RT2x00 family; firmware filenames depend on actual chipset

Firmware is **not supplied** by building a kernel. Verify licensing, versions, /vendor firmware lookup and read-only binding information before adding files. Use a powered USB-C OTG hub if current draw is too high, rather than modifying power management safeguards.

## Internal Wi-Fi research

The kernel includes `drivers/staging/qcacld-3.0`, but Android QCA data paths are not interchangeable with mac80211. A generic injection patch from a different phone or Linux version must not be cherry-picked. Investigate `wlan_hdd_cfg80211`, monitor-vdev handling, TX path, firmware offload limitations, and driver ABI in **a separate reviewed PR**.

A community hardware report on `hotdog` with **LineageOS 23.2 / Android 16** documents internal passive monitor mode working while internal packet injection does not work. This is useful feasibility evidence, **not a validation for crDroid 13 / Android 17**:
https://github.com/althsec/nethunter-oneplus7tpro-los23.2

## Acceptance tests (all on owned hardware)

1. Source SHA and actual ROM fingerprint must be recorded. Run `bash scripts/device-audit.sh`.
2. Build `baseline` then `core` then `external`; compare `kernel.config` and `artifact-report.json`.
3. Check `wlan.ko` modinfo `vermagic`, signer, matching ROM public key and load errors. Presence of a signature is not proof of trust.
4. Verify cellular, internal WLAN, Bluetooth, camera, boot, sleep, battery drain and thermals before NetHunter features.
5. Use an owned host PC to confirm the HID keyboard/mouse USB gadgets enumerate via NetHunter USB Arsenal. USB-config Kconfig support alone is insufficient.
6. For external Wi-Fi, verify adapter USB ID, firmware, `iw phy` monitor support, association/reconnect and optional TX tests on a network the operator controls.
7. Capture module load failures, kernel logs, USB enumeration failures and recovery steps in a hardware-test report.

No flashing or automated changes to device boot slots, module signature enforcement, AVB, SELinux or vendor firmware are part of this project.
