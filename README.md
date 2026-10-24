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
      libelf-dev libssl-dev kmod clang-14 lld-14 llvm-14 \
      gcc-aarch64-linux-gnu gcc-arm-linux-gnueabi

    bash scripts/fetch-source.sh
    CC=clang-14 LD=ld.lld-14 AR=llvm-ar-14 NM=llvm-nm-14 \
      OBJCOPY=llvm-objcopy-14 OBJDUMP=llvm-objdump-14 STRIP=llvm-strip-14 \
      bash scripts/build.sh baseline

For quick, non-compiling Kconfig dependency validation use `CONFIG_ONLY=1 bash scripts/build.sh core` (or `external`). This generates only a verified `kernel.config`, not a kernel. The previous baseline **fully compiled successfully** in [Actions run 39975157488](https://github.com/mason82-dotcom/OP7T-Kernel/actions/runs/39975157488), producing 20 DTBs and 2 UNSIGNED modules. PR CI now compiles `core` and `external` independently, while manual workflow runs can select any one profile. Replace `baseline` with `core` or `external` to build other profiles. Clang 14 is an **initial experimental compiler selection**, not a proven exact crDroid ROM build toolchain. GitHub Actions runs lightweight syntax/config checks on pushes, experimental **core/external full kernel compilations** on pull requests, and manual builds of the baseline/core/external profiles. To limit public CI artifact size, pull requests upload JSON+config build attestations, not whole module trees. Manually dispatched runs may upload raw experimental binaries. Successful compilation alone does not establish flash/ROM compatibility.

Outputs are written to `.work/artifacts/<profile>/`: `Image`, module files, DTBs, `kernel.config`, compiler version, source SHA, `artifact-report.json` and `SHA256SUMS`. **None are a flashable ZIP or boot image.**

## Read-only device compatibility check

With USB debugging enabled and adb available, run `bash scripts/device-audit.sh` (or `bash scripts/device-audit.sh --serial <ADB_SERIAL>` for multiple devices). It prints device codename, Android/ROM version, kernel, ROM fingerprint and active slot. It rejects non-`hotdog`/non-Android-17 devices and **never modifies the phone**. This does not determine module signature or boot image compatibility.

LLVM toolchain note: older Qualcomm Kbuild may invoke unsuffixed `llvm-nm` and `llvm-ar`, even if `AR=llvm-ar-14` and `NM=llvm-nm-14` were specified. `scripts/build.sh` now prepends `/usr/lib/llvm-14/bin` when using `clang-14`, or accepts `LLVM_TOOLCHAIN_BIN` explicitly.

## Read-only installed-ROM module inventory

On the Android 17 / crDroid 13 **hotdog**, run `bash scripts/device-module-audit.sh` (optionally with `--serial ADB_SERIAL`). It performs the existing strict device preflight, prints the public build and vendor fingerprints, Android security patch information and available `wlan.ko` module filenames/hash values from normal ADB-readable locations. This uses **no root or write operations**; missing filenames mean only that the paths were not visible, not that the WLAN driver does not exist. It cannot verify kernel key trust, module ABI or flash compatibility.

## Artifact compatibility audit

At the end of a successful kernel build `scripts/audit-artifacts.py` checks the raw ARM64 Image magic, all DTBs, the pinned source commit, expected Kconfig safety constraints, and the presence of rebuilt kernel modules. It records each module's `modinfo` vermagic, signer, signature key ID, algorithm and hashes in `artifact-report.json`, verifies that all captured modules match the just-built `kernel.release` and requires an actual Qualcomm `wlan.ko` (or `qca_cld3_wlan.ko`). `Module.symvers`, `modules.order` and `System.map` are retained when generated for offline ABI investigation. It cannot assert trusted keys for the installed ROM; the report's `flash_ready` remains `false` by design. A missing module signer is recorded, **not** worked around. Any failure prevents publication of seemingly complete build artifacts.

On build failure, GitHub Actions uploads only the last 2,500 lines of a build log and the relevant `.config` files for diagnosis. It explicitly avoids exporting the working tree or any generated module-signing private keys. **These checks cannot establish compatibility with the installed ROM**.

## Critical module signing blocker

The earlier baseline generated **2 unsigned modules** because `make modules` was followed by raw copying: in this Linux 4.14 tree, automatic module signatures are applied at **`make modules_install`**. This experimental follow-up now stages that installation under `.work/module-stage-<profile>` and requires a generated signing key and signed `wlan.ko`. The matching kernel image is necessary for its generated certificate to be trusted; **this still does not certify the installed ROM**, its other vendor modules or any boot image. The artifact audit now records `module_signature_load_blocked=true` and module paths. Kernel signing must be resolved against the actual installed ROM's trusted certificates and vendor modules, **without disabling enforcement or publishing signing secrets**. These outputs are not for flashing.

### Secure module staging

`scripts/build.sh` now requires `CONFIG_MODULE_SIG_ALL=y`, stages modules through Kbuild's `modules_install` into a temporary directory, and copies **only staged modules** into `artifacts/<profile>/modules`. The public build-certificate SHA-256 is recorded in `signing-cert.sha256`; generated private key `certs/signing_key.pem` stays exclusively in ignored `.work/out-<profile>`, never in CI-uploaded artifacts. The artifact audit runs in `--require-signed` mode and rejects unsigned modules or WLAN modules without a signing key ID. Signing success must be proven by CI.

## NetHunter feature assessment

The USB HID ConfigFS functionality is **already enabled** in the pinned kernel. The `core` profile additionally requests RFCOMM and RFCOMM TTY for Bluetooth Arsenal and CDC ACM/ECM. Use `external` for the experimental in-tree USB Wi-Fi drivers. No code patch for Qualcomm internal monitor/injection has been merged.

The official NetHunter kernel registry distinguishes `HID-4`, `BT_RFCOMM`, `QCACLD`, `ATH9K_HTC` and `Injection` features. Enabling Kconfig symbols **alone** does not justify advertising these as working. See [feature validation and driver research](docs/NETHUNTER_FEATURES.md).

## Offline WLAN module comparison (read-only)

Once the original `wlan.ko` has been extracted from the **exact installed ROM**, compare it with the rebuilt module:

    python3 scripts/compare-rom-modules.py \
      --built .work/artifacts/baseline/modules/drivers/staging/qcacld-3.0/wlan.ko \
      --rom /path/to/extracted-exact-rom/wlan.ko

The script compares module name, complete `vermagic`, signer, signature key ID and hash algorithm. A mismatch is a blocker; matching values still **do not prove kernel key trust, ABI compatibility, device bootability or NetHunter readiness**. It never writes to or modifies the phone.

## Offline original boot image header audit

For an **original** `boot.img` from the exact installed `hotdog` ROM, run `python3 scripts/audit-bootimg.py /path/to/original-boot.img`. Optionally add `--expect-sha256 <known_hash>` to verify its original fingerprint. The script checks the AOSP boot header v2, 4096-byte pages, raw ARM64 kernel, required ramdisk and embedded FDT/DTB, section offsets and truncation. It emits JSON **only to stdout**, never extracts/patches/flashes. It does not verify AVB, DTBO partition, installed-ROM provenance, runtime module keys or hardware bootability; `flash_ready` remains false. Header layout is from [AOSP android17-release bootimg.h](https://android.googlesource.com/platform/system/tools/mkbootimg/+/refs/heads/android17-release/include/bootimg/bootimg.h).

## Mandatory release gates

The **original** ROM boot image, active slot, original module signatures and firmware, boot header and DTB/DTBO must be validated from the actual installed build. Kernel module signatures matter: baseline `CONFIG_MODULE_SIG_FORCE=y` while OPlus enables `CONFIG_QCA_CLD_WLAN=m`. Do **not** disable module security enforcement to make an image appear compatible.

Read [flash safety and recovery](docs/FLASHING.md) first. No script changes the phone. No KernelSU/Magisk changes are made. Please use NetHunter features only in explicitly authorized testing.

Sources: [crDroid hotdog v13](https://www.crdroid.net/hotdog/13), [crDroid 17.0 board config](https://github.com/crdroidandroid/android_device_oneplus_sm8150-common/blob/17.0/BoardConfigCommon.mk), [Kali NetHunter kernel docs](https://www.kali.org/docs/nethunter/).
