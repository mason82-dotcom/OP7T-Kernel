# crDroid 13 / Android 17 source and board reference

## Scope and decision

The [official crDroid Android 17.0 README](https://github.com/crdroidandroid/android/blob/17.0/README.mkdn) describes a **complete Android ROM** workflow. This repository intentionally uses an **independent, pinned kernel-only build**. The upstream crDroid **v13** release targets **Android 17** (branch `17.0`), **not Android 13**. The only device in scope is OnePlus 7T Pro `hotdog`, not `hotdogg`.

Official source references in authority order:

1. [crDroid manifest/ROM source, `17.0`](https://github.com/crdroidandroid/android/tree/17.0).
2. [OnePlus SM8150 board settings, `17.0`](https://github.com/crdroidandroid/android_device_oneplus_sm8150-common/blob/17.0/BoardConfigCommon.mk).
3. [Official OnePlus SM8150 kernel, `17.0`](https://github.com/crdroidandroid/android_kernel_oneplus_sm8150/tree/17.0); reproducible working pin: [`config/upstream.lock`](../config/upstream.lock).
4. The **actual installed device's original partitions and kernel/module identities**, which supersede assumptions drawn from a reference ZIP for compatibility decisions.

## BoardConfig invariants

| Setting | Required interpretation |
| --- | --- |
| `TARGET_KERNEL_SOURCE := kernel/oneplus/sm8150` | Kernel project corresponding to the official source |
| `TARGET_KERNEL_CONFIG := vendor/sm8150-perf_defconfig vendor/oplus.config` | Apply base defconfig **and** OPlus overlay in that order |
| `BOARD_KERNEL_IMAGE_NAME := Image` | Raw ARM64 `Image`, not `Image.gz-dtb` or `boot.img` |
| `BOARD_BOOT_HEADER_VERSION := 2`; `BOARD_KERNEL_PAGESIZE := 4096` | Validate original boot header and offsets |
| `BOARD_INCLUDE_DTB_IN_BOOTIMG := true` | Original boot image includes an appropriate DTB |
| `BOARD_KERNEL_SEPARATED_DTBO := true` | Separate matching DTBO partition |
| `BOARD_RAMDISK_USE_LZ4 := true` | Preserve installed ROM ramdisk format |
| `TARGET_MODULE_ALIASES += wlan.ko:qca_cld3_wlan.ko` | Kernel WLAN filename may differ from vendor-module alias |
| `BOARD_AVB_ENABLE := true` | Do not bypass the verified-boot policy |

These are **source-level observations**, not acceptance of output images. On this legacy 2019-era handset Android 17 does not automatically imply a modern GKI `vendor_boot` packaging layout.

## Source-level compiler selection versus experiment

The pinned [crDroid vendor snapshot `9e09ebeb03fc3e744b679401b9655f780b6b0af4`](https://github.com/crdroidandroid/android_vendor_crdroid/tree/9e09ebeb03fc3e744b679401b9655f780b6b0af4), referenced by [`config/toolchain-reference.json`](../config/toolchain-reference.json), selects:

- `vars/aosp_target_release` → `cp2a`.
- `tools/get_clang_version.py` reads `release/flag_values/cp2a/RELEASE_BUILD_CLANG_VERSION.textproto`.
- That source-level release selection reports AOSP prebuilt `clang-r596125`.
- `build/envsetup.sh` exports the selection; `config/BoardConfigKernel.mk` uses it unless `TARGET_KERNEL_CLANG_VERSION` overrides the default.
- No override was observed in the inspected hotdog / SM8150-common BoardConfig revisions.

This evidence **does not prove** the compiler actually used for the 2026-10-21 OTA, binary identity or ABI equivalence. The checked-in [CI workflow](../.github/workflows/nethunter-kernel.yml) still selects **Clang 14** experimentally. `scripts/audit-toolchain.py` captures bounded provenance, not equivalence certification.

## Build workflows must not be conflated

**Normal project build:** use [BUILD.md](BUILD.md), which fetches a pinned kernel commit and compiles standalone kernel/module artifacts. There is no `brunch` dependency.

**Optional full-ROM reference environment** (large storage, RAM and bandwidth; separate checkout):

~~~bash
mkdir -p ~/crDroid && cd ~/crDroid
repo init -u https://github.com/crdroidandroid/android.git -b 17.0 --git-lfs --no-clone-bundle
repo sync -c
. build/envsetup.sh
# Only after checking hotdog device/vendor trees and their dependencies:
brunch hotdog
~~~

The official instructions are a moving manifest unless its resolved revisions are recorded. A successful `brunch` does not demonstrate compatibility of this repository's experimental NetHunter kernel with the installed ROM. Do not claim byte-reproducibility without matching manifest SHAs, build flags, compiler, device/vendor trees and artifacts.

For evidence already collected and unresolved installed-ROM source drift see [HARDWARE_EVIDENCE.md](HARDWARE_EVIDENCE.md). For safety gates see [FLASHING.md](FLASHING.md).
