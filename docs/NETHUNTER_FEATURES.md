# Kali NetHunter feature matrix — OnePlus 7T Pro

**Scope:** `hotdog`, crDroid 13 / Android 17, pinned Linux 4.14.357-derived source. A configured or compiled feature is **not** automatically available on the running handset. Nothing in this table is authorized for flashing. See [release safety](FLASHING.md).

| Feature | Mainline preparation | Not yet demonstrated |
| --- | --- | --- |
| USB `HID-4` / ConfigFS | Upstream USB ConfigFS HID already enabled | User-space gadget setup, real USB host enumeration, SELinux/roles |
| USB Arsenal | Existing NCM/RNDIS/HID; `core` requests ACM/ECM | NetHunter userspace, role switching and compatible host modes |
| Bluetooth `BT_RFCOMM` | `core` requests RFCOMM and TTY options | Runtime BT classic and tool integration |
| External `ATH9K_HTC` | `external` requests selected in-tree USB Wi-Fi drivers | USB IDs, firmware, power, monitor and TX function per adapter |
| External `CARL9170` / `RTL8187` / `MT7601U` / `RT2800USB` | `external` requests available in-tree drivers | Exact adapter functionality; **no injection patch guarantee** |
| Internal Qualcomm `QCACLD` | `qcacld-3.0` present; WLAN built as a kernel module | Matching installed ROM signature, ABI, runtime monitor mode |
| Internal packet injection | **No accepted production patch** | Firmware support, safety, hardware RX/TX validation |
| RTL8812AU / MT7612U | **Not bundled** | Dedicated verified backport, configuration, signing and hardware tests |

Feature taxonomy: [Kali NetHunter kernel registry](https://gitlab.com/kalilinux/nethunter/build-scripts/kali-nethunter-kernels/-/tree/main).

## External firmware is separate

An in-tree driver does **not** ship the adapter firmware. Match chipset, USB ID and firmware path before testing:

| Driver | Example chipset / firmware |
| --- | --- |
| `ath9k_htc` | AR9271 / AR7010; `htc_9271.fw` / `htc_7010.fw` |
| `carl9170` | AR9170; `carl9170-1.fw` |
| `mt7601u` | MT7601U; `mt7601u.bin` |
| `rtl8187` | RTL8187 family; depends on revision |
| `rt2800usb` | RT2x00 family; inspect the actual chipset |

Firmware is not bundled. Validate licensing, provenance and exact ROM lookup locations before adding any dependency. A powered USB-C OTG hub may be required by adapter current consumption.

## Internal QCACLD research is not a release feature

Monitor-VDEV and ICNSS RX experiments are recorded in **draft / stacked pull requests** (e.g. [qualification #26](https://github.com/mason82-dotcom/OP7T-Kernel/pull/26), [compile experiment #27](https://github.com/mason82-dotcom/OP7T-Kernel/pull/27), [source parity #34](https://github.com/mason82-dotcom/OP7T-Kernel/pull/34), [callback-context blocker #35](https://github.com/mason82-dotcom/OP7T-Kernel/pull/35)). **Their patches must not be represented as merged or hardware validated.** They require exact-source applicability, caller-context/locking review, version-specific ABI checks, isolated compilation and owned-hardware testing. Generic patches from another phone/Android release are not transferable.

A separate [LineageOS 23.2 community port](https://github.com/althsec/nethunter-oneplus7tpro-los23.2) mentions passive monitor support on `hotdog`, but it does **not** validate passive monitoring or packet injection for this pinned crDroid 13 build.

## Hardware acceptance

Only **after** all [ROM/module/boot/recovery release gates](FLASHING.md) are passed, establish stable boot and essential phone functions, then test USB HID/Arsenal, Bluetooth and specific external adapters on owned devices/networks. Record firmware IDs, adapter USB IDs, runtime logs, interface capabilities, reconnect/suspend and authorized RX/TX test results with repeatable procedures. Internal injection remains unimplemented until a separate reviewed and evidence-backed change is merged.

Candidate source changes follow [patch staging policy](../patches/README.md). Build commands are maintained **only** in [BUILD.md](BUILD.md).
