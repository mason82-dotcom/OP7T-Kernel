# OP7T-Kernel: crDroid 13 / Android 17 / Kali NetHunter

This repository is the **build and patch workspace** for the **OnePlus 7T Pro (`hotdog`)**. The upstream 1.5 GB kernel tree is fetched on demand, pinned to a fixed Git commit and **not mirrored** here.

**Status: experimental source scaffolding. NOT FLASHABLE.** No boot image, tested NetHunter injection patch, correctly signed rebuilt vendor modules or validated hardware build has been produced.

## Verified basis

- crDroid **v13.0 = Android 17**. **Android 13 was crDroid v9**, and using its old `13.0` AOSP branch here would be incorrect.
- Official kernel: [crdroidandroid/android_kernel_oneplus_sm8150 branch 17.0](https://github.com/crdroidandroid/android_kernel_oneplus_sm8150/tree/17.0).
- Lock: [config/upstream.lock](config/upstream.lock), SHA `1083c6c5906114c71b11a429898b111a1b1b8109` at time of project setup.
- Source Makefile: Linux 4.14.357.
- Device build specifies `vendor/sm8150-perf_defconfig` **plus** `vendor/oplus.config`; boot kernel name **`Image`**, not `Image.gz-dtb`.
- The base config **already includes** USB ConfigFS and HID; Qualcomm WLAN is a module with signature enforcement.
- Only `hotdog` is in scope; **not** `hotdogg`/5G McLaren.

## Profiles

| Profile | Purpose | Risk |
| --- | --- | --- |
| `baseline` | Build original 17.0 kernel + correct OPlus overlay | reference, still untested |
| `core` | Enable SYSVIPC / USB serial and ACM/ECM functions | experimental |
| `external` | Core + built-in ath9k_htc, carl9170, rtl8187, mt7601u, rt2800usb | experimental; adapter firmware and injection **not verified** |

Internal QCACLD monitor/injection is **not implemented**. Older NetHunter Android-13 or LineageOS driver trees must not be copied wholesale. The external profile includes drivers, **not injection patches**; monitor/injection availability must be verified for specific adapters.

## Build on Linux x86_64

    sudo apt-get install -y git make bc bison flex python3 build-essential \
      libelf-dev libssl-dev clang-14 lld-14 llvm-14 \
      gcc-aarch64-linux-gnu gcc-arm-linux-gnueabi

    bash scripts/fetch-source.sh
    CC=clang-14 LD=ld.lld-14 AR=llvm-ar-14 NM=llvm-nm-14 \
      OBJCOPY=llvm-objcopy-14 OBJDUMP=llvm-objdump-14 STRIP=llvm-strip-14 \
      bash scripts/build.sh baseline

Replace `baseline` with `core` or `external` to build other profiles. Clang 14 is an **initial experimental compiler selection**, not a proven exact crDroid ROM build toolchain. GitHub Actions runs lightweight syntax/config checks on pushes, an experimental **baseline kernel compilation on pull requests**, and offers manual workflow dispatch for the core/external profiles. Successful compilation alone does not establish flash/ROM compatibility.

Outputs are written to `.work/artifacts/<profile>/`: `Image`, module files, DTBs, `kernel.config`, compiler version, source SHA and `SHA256SUMS`. **None are a flashable ZIP or boot image.**

## Mandatory release gates

The **original** ROM boot image, active slot, original module signatures and firmware, boot header and DTB/DTBO must be validated from the actual installed build. Kernel module signatures matter: baseline `CONFIG_MODULE_SIG_FORCE=y` while OPlus enables `CONFIG_QCA_CLD_WLAN=m`. Do **not** disable module security enforcement to make an image appear compatible.

Read [flash safety and recovery](docs/FLASHING.md) first. No script changes the phone. No KernelSU/Magisk changes are made. Please use NetHunter features only in explicitly authorized testing.

Sources: [crDroid hotdog v13](https://www.crdroid.net/hotdog/13), [crDroid 17.0 board config](https://github.com/crdroidandroid/android_device_oneplus_sm8150-common/blob/17.0/BoardConfigCommon.mk), [Kali NetHunter kernel docs](https://www.kali.org/docs/nethunter/).
