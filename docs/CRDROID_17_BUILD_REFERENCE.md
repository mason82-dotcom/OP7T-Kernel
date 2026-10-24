# crDroid 13 / Android 17 build-reference alignment (hotdog)

## Decision

Use the [official crDroid source/build README](https://github.com/crdroidandroid/android/blob/17.0/README.mkdn) **as the ROM build reference** for the OnePlus 7T Pro (`hotdog`). Keep this repository a **separate, pinned kernel and module build**, rather than copying or syncing the entire Android tree just to rebuild a kernel.

The official README's `repo init`, `repo sync`, `. build/envsetup.sh`, and `brunch hotdog` workflow targets a **full crDroid ROM**. It does **not** replace this repository's `scripts/fetch-source.sh` / `scripts/build.sh` workflow, nor does a successful `brunch` establish NetHunter kernel safety. Do not run `brunch hotdog` without independently checking that the hotdog device/vendor/kernel trees are present and compatible.

## Authoritative references, in order

1. [crDroid Android manifest, branch 17.0](https://github.com/crdroidandroid/android/tree/17.0) — Android 17-based platform and general ROM build flow.
2. [OnePlus SM8150 common BoardConfig, branch 17.0](https://github.com/crdroidandroid/android_device_oneplus_sm8150-common/blob/17.0/BoardConfigCommon.mk) — kernel image, defconfig overlays, boot parameters, WLAN module alias, DTB/DTBO and AVB expectations.
3. [Official SM8150 kernel, branch 17.0](https://github.com/crdroidandroid/android_kernel_oneplus_sm8150/tree/17.0) — source tree. Our *reproducible* checkout is the exact SHA in [config/upstream.lock](../config/upstream.lock), not a moving branch HEAD.
4. **Exact installed device + ROM evidence** — determines what can actually boot and what module signing keys or vendor ABI will be accepted. A publicly downloaded OTA ZIP is only a candidate reference until installed-ROM identity is proven.

Version terminology: **crDroid 13 = Android 17; upstream branch `17.0`**. It does not mean Android 13 or crDroid branch `13.0`. Limit scope to OnePlus 7T Pro `hotdog` (not `hotdogg`).

## BoardConfig invariants to verify before packaging

| Official board setting | Required interpretation |
| --- | --- |
| `TARGET_KERNEL_SOURCE := kernel/oneplus/sm8150` | Official kernel source; our standalone build checks out its pinned equivalent |
| `TARGET_KERNEL_CONFIG := vendor/sm8150-perf_defconfig vendor/oplus.config` | Apply **both**, in that order, before verified NetHunter Kconfig fragments |
| `BOARD_KERNEL_IMAGE_NAME := Image` | Build a **raw ARM64 Image**, not a boot.img and not an assumed Image.gz-dtb |
| `BOARD_BOOT_HEADER_VERSION := 2`, `BOARD_KERNEL_PAGESIZE := 4096` | Verify original boot header and offsets, do not infer packaging from Android major version |
| `BOARD_INCLUDE_DTB_IN_BOOTIMG := true` | Preserve correct boot-image DTB from the exact ROM |
| `BOARD_KERNEL_SEPARATED_DTBO := true` | Treat DTBO as its own ROM-specific partition artifact |
| `BOARD_RAMDISK_USE_LZ4 := true` | Preserve installed-ROM ramdisk/compression |
| `TARGET_MODULE_ALIASES += wlan.ko:qca_cld3_wlan.ko` | Preserve ROM-expected WLAN naming and loading paths |
| `BOARD_AVB_ENABLE := true` | Do not change verified-boot policy as a shortcut |

These configuration values are source-tree observations, **not evidence of compatibility of any generated artifacts**.

## Build workflow — default: standalone kernel

Run on an isolated **Linux x86_64** build host (native or a correctly configured WSL2 Linux filesystem; not inside a Windows-mounted NTFS workspace). Select the exact toolchain deliberately; Clang 14 is the project's current experimental choice, **not yet proven bit-identical to the official ROM builder**.

```bash
git clone https://github.com/mason82-dotcom/OP7T-Kernel.git
cd OP7T-Kernel
bash scripts/fetch-source.sh
CONFIG_ONLY=1 bash scripts/build.sh baseline
CONFIG_ONLY=1 bash scripts/build.sh core
CONFIG_ONLY=1 bash scripts/build.sh external
# After Kconfig gates and host toolchain prerequisites pass:
CC=clang-14 LD=ld.lld-14 AR=llvm-ar-14 NM=llvm-nm-14 \
  OBJCOPY=llvm-objcopy-14 OBJDUMP=llvm-objdump-14 STRIP=llvm-strip-14 \
  bash scripts/build.sh baseline
```

Full compiling and staging remain in the existing scripts; `CONFIG_ONLY=1` does **not** produce a kernel. All raw build outputs remain experimental and **not flashable**. Do not publish private module-signing keys.

### Optional full-ROM reference workspace — NOT the default path

Only when toolchain/build-rule parity requires inspecting or compiling a full ROM, on a host with substantial disk, RAM and download capacity:

```bash
mkdir -p ~/crDroid && cd ~/crDroid
repo init -u https://github.com/crdroidandroid/android.git -b 17.0 --git-lfs --no-clone-bundle
repo sync -c
. build/envsetup.sh
# Only after verifying hotdog-specific device/vendor projects and dependencies:
brunch hotdog
```

Keep this separate from OP7T-Kernel. Record the resolved manifest revision and the precise device/kernel/vendor project SHAs. `repo sync -c` saves some work but may still download a **very large** source tree. Never imply full-ROM reproducibility from an unpinned moving manifest.

## Release blockers / acceptance order

- [x] Match crDroid branch 17.0, device codename hotdog, pinned kernel source, base defconfig and OPlus overlay in this repository.
- [x] Provide build-time read-only kernel/module inventory and a non-flashable artifact report.
- [ ] Reproduce an official ROM-equivalent **toolchain** and check kernel configuration / generated artifacts against the exact ROM.
- [ ] Prove on-device installed-ROM identity and firmware baseline; reference OTA verification **alone** is insufficient.
- [ ] Extract original `boot.img`, DTB/DTBO and vendor modules from the **matching** installed build; verify headers/hashes and provenance.
- [ ] Compare `qca_cld3_wlan.ko` / `wlan.ko`, `gspca_main.ko`, all dependent vendor modules, `vermagic`, `Module.symvers`, exported symbols, trust chains and module-loading paths.
- [ ] Validate staged signatures are generated and would be trusted by the actual running kernel. **Do not disable `CONFIG_MODULE_SIG_FORCE`, SELinux or AVB to bypass failures.**
- [ ] Validate a deterministic original-boot repacking process **offline**, retaining ROM ramdisk, header parameters, DTB/DTBO relationships and rollback material. No implicit boot image generation or flashing.
- [ ] Test recovery/rollback and baseline functionality on physical hardware **only after gates pass**.
- [ ] Validate NetHunter `core` / `external` features per physical adapter and authorized test; Wi-Fi injection/monitor mode cannot be inferred from Kconfig alone.

Current status: **`flash_ready=false`**. The reference aligns the project architecture; it does not change that decision.

Related: [main README](../README.md), [flashing safety](FLASHING.md), [NetHunter features](NETHUNTER_FEATURES.md).
