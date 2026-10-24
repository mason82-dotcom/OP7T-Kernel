# OP7T-Kernel: crDroid 13 / Android 17 / Kali NetHunter

This repository is the **build and patch workspace** for the **OnePlus 7T Pro (`hotdog`)**. The upstream 1.5 GB kernel tree is fetched on demand, pinned to a fixed Git commit and **not mirrored** here.

**Status: experimental source scaffolding. NOT FLASHABLE.** No boot image, tested NetHunter injection patch, correctly signed rebuilt vendor modules or validated hardware build has been produced.

> Build reference: [crDroid 13 / Android 17 source and kernel alignment](docs/CRDROID_17_BUILD_REFERENCE.md). The official manifest/`brunch` instructions are for full ROM builds; this project remains standalone and **not flashable**.

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

## Official crDroid 17.0 toolchain selection vs experimental CI

The pinned source snapshot of `crdroidandroid/android_vendor_crdroid` at commit `9e09ebeb03fc3e744b679401b9655f780b6b0af4` selects release `cp2a` and the AOSP prebuilt `clang-r596125`. The inspected OnePlus `hotdog` and `sm8150-common` configs do not override `TARGET_KERNEL_CLANG_VERSION`. Our GitHub Actions still use **experimental Clang 14**. We do **not** know which exact compiler built the original October 21 ROM. The build emits a bounded `toolchain-report.json` using [audit-toolchain.py](scripts/audit-toolchain.py), but a matching version or directory name can never prove bit-for-bit identity, ABI compatibility, or trusted signatures.

## Build on Linux x86_64

    sudo apt-get install -y git make bc bison flex python3 build-essential \
      libelf-dev libssl-dev binutils kmod clang-14 lld-14 llvm-14 \
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

### Strip debug information before signing

The previous unstripped `core` report measured a **916,922,321-byte** `wlan.ko`, compared with a **14,982,321-byte** `qca_cld3_wlan.ko` extracted from the verified *reference* OTA. This size discrepancy suggests substantial debug sections but does **not** prove that stripping alone resolves the size/ABI problem. `scripts/build.sh` now passes `INSTALL_MOD_STRIP=1` to the kernel's staged `modules_install`. The pinned upstream `scripts/Makefile.modinst` orders **copy -> strip (`--strip-debug`) -> sign**, so no signed `.ko` is edited afterward.

The artifact audit now calls `readelf -W -S` on **the final signed staged modules** and refuses publication if debug sections are present, section inspection fails, or existing `modinfo` signer/key-ID checks fail. It records `module_strip_debug_required`, `module_debug_sections_verified` and `modules_with_debug_sections` in `artifact-report.json`. The real stripped size still needs a successful CI run, and no partition-fit, original-ROM ABI, signer trust, installed-image identity or flash compatibility can be claimed. `flash_ready=false` remains enforced. [Module install order](https://github.com/crdroidandroid/android_kernel_oneplus_sm8150/blob/17.0/scripts/Makefile.modinst).


## NetHunter feature assessment

The USB HID ConfigFS functionality is **already enabled** in the pinned kernel. The `core` profile additionally requests RFCOMM and RFCOMM TTY for Bluetooth Arsenal and CDC ACM/ECM. Use `external` for the experimental in-tree USB Wi-Fi drivers. No code patch for Qualcomm internal monitor/injection has been merged.

The official NetHunter kernel registry distinguishes `HID-4`, `BT_RFCOMM`, `QCACLD`, `ATH9K_HTC` and `Injection` features. Enabling Kconfig symbols **alone** does not justify advertising these as working. See [feature validation and driver research](docs/NETHUNTER_FEATURES.md).

## Windows / Linux / macOS device evidence (Python)

On Windows PowerShell (Python 3 and Android Platform Tools/ADB on PATH), from the repository root:

    py -3 scripts/device-evidence.py --output hotdog-device-evidence.json

On Linux / Raspberry Pi:

    python3 scripts/device-evidence.py --output hotdog-device-evidence.json

**crDroid property mapping verified from [vendor/lineage/config/version.mk, branch 17.0](https://github.com/crdroidandroid/android_vendor_crdroid/blob/17.0/config/version.mk):** `ro.crdroid.version=17.0` is the Android platform tag; `ro.crdroid.build.version=13.0` is the actual crDroid release. The audit now records both plus the display build property. An Android-12 OnePlus fingerprint may reflect the required legacy firmware baseline or property masking, so it is **not** proof of the running crDroid image. Use `--serial YOUR_ADB_SERIAL` only with multiple ADB devices. The read-only guard accepts canonical `hotdog` and the OEM fingerprint alias `OnePlus7TPro` (both seen in the [LineageOS hotdog device specification](https://github.com/LineageOS/android_device_oneplus_hotdog/blob/lineage-23.2/lineage_hotdog.mk)); it still rejects `hotdogg`, `OnePlus7TProNR` and Android versions other than 17. Matching a device string alone does **not** establish exact hardware/ROM image compatibility. The script collects build/vendor fingerprints, slot, security patches, kernel release and ADB-readable Qualcomm WLAN paths and hashes. It makes **read-only ADB calls** without root or Bash and saves a local report once (never overwrites it). Missing WLAN paths are inconclusive. Share the JSON only if comfortable sharing ROM/device metadata; it does not include a signing key, private modules or a device serial. The report always sets `flash_ready=false` and cannot determine trusted certificates or symbol ABI.

### Vendor-DLKM directory enumeration without inode access

The physical hotdog's `/vendor_dlkm` is mounted read-only and shows `qca_cld3_wlan.ko`, `gspca_main.ko` and the `modules.*` manifest names via `ls -laZ`, although each file's inode metadata is blocked (`-?????????`). The Python evidence script now performs a separate, fixed `adb shell ls -1 /vendor_dlkm/lib/modules` directory-name inventory, records **only seven allowlisted names**, and explicitly marks inode metadata, binary content, signer and symbol ABI as unverified. Merely seeing the directory entry does **not** prove the file is accessible, well-formed, signed, or the currently loaded module. The system remains unmodified.

### WLAN file-access diagnostic

The Python device report also probes the exact device-tree module alias `qca_cld3_wlan.ko`, the original `wlan.ko`, both vendor/vendor_dlkm paths, and two kernel sysfs fields. Each fixed ADB read-only probe returns only `metadata_visible`, `readable`, `permission_denied`, `not_found_in_this_path` or `unknown_error`; it never collects raw sysfs values. A `Permission denied` result is **not** module absence. The device-tree init script specifies `insmod /vendor/lib/modules/qca_cld3_wlan.ko`, and on tested devices `/vendor/lib/modules` may be a symlink to `/vendor_dlkm/lib/modules`. No module key, ABI or boot compatibility is certified.

## Offline OTA partition inventory (no extraction)

After checking a local OTA ZIP against the pinned reference via `scripts/verify-rom-zip.py`, inspect its **CrAU A/B payload v2 manifest**:

    python3 scripts/verify-rom-zip.py /path/to/crDroidAndroid-17.0-20261021-hotdog-v13.0.zip
    python3 scripts/inspect-ota-payload.py /path/to/crDroidAndroid-17.0-20261021-hotdog-v13.0.zip

The second command reads only a bounded protobuf manifest at the start of `payload.bin`, returning the OTA's *listed* `boot`, `dtbo`, `vendor`, `vendor_dlkm` and VBMeta partitions. It does **not** extract or hash partitions, cryptographically verify the payload signature, prove the ZIP was installed, or change the phone. Delta/partial OTA payloads may omit unchanged partitions: absent names are inconclusive. `flash_ready` remains false.

## Offline WLAN module comparison (read-only)

Once the original `wlan.ko` has been extracted from the **exact installed ROM**, compare it with the rebuilt module:

    python3 scripts/compare-rom-modules.py \
      --built .work/artifacts/baseline/modules/drivers/staging/qcacld-3.0/wlan.ko \
      --rom /path/to/extracted-exact-rom/wlan.ko

The script compares module name, complete `vermagic`, signer, signature key ID and hash algorithm. A mismatch is a blocker; matching values still **do not prove kernel key trust, ABI compatibility, device bootability or NetHunter readiness**. It never writes to or modifies the phone.

## Offline ARM64 module ABI triage

[Read-only ABI audit](docs/MODULE_ABI_AUDIT.md) checks `__versions` symbol CRCs, `.modinfo`, dependencies and signature trailer presence in the built and exact-ROM `wlan.ko` / `qca_cld3_wlan.ko` and `gspca_main.ko`. Supplying `Module.symvers` improves coverage but does not prove ABI or signature trust. `--fail-on-unknown` distinguishes unresolved evidence from a passing comparison. Build outputs, signed or unsigned, remain **NOT FLASHABLE**.

## Offline original boot image header audit

For an **original** `boot.img` from the exact installed `hotdog` ROM, run `python3 scripts/audit-bootimg.py /path/to/original-boot.img`. Optionally add `--expect-sha256 <known_hash>` to verify its original fingerprint. The script checks the AOSP boot header v2, 4096-byte pages, raw ARM64 kernel, required ramdisk and embedded FDT/DTB, section offsets and truncation. It emits JSON **only to stdout**, never extracts/patches/flashes. It does not verify AVB, DTBO partition, installed-ROM provenance, runtime module keys or hardware bootability; `flash_ready` remains false. Header layout is from [AOSP android17-release bootimg.h](https://android.googlesource.com/platform/system/tools/mkbootimg/+/refs/heads/android17-release/include/bootimg/bootimg.h).

## Mandatory release gates

The **original** ROM boot image, active slot, original module signatures and firmware, boot header and DTB/DTBO must be validated from the actual installed build. Kernel module signatures matter: baseline `CONFIG_MODULE_SIG_FORCE=y` while OPlus enables `CONFIG_QCA_CLD_WLAN=m`. Do **not** disable module security enforcement to make an image appear compatible.

Read [flash safety and recovery](docs/FLASHING.md) first. No script changes the phone. No KernelSU/Magisk changes are made. Please use NetHunter features only in explicitly authorized testing.

Sources: [crDroid hotdog v13](https://www.crdroid.net/hotdog/13), [crDroid 17.0 board config](https://github.com/crdroidandroid/android_device_oneplus_sm8150-common/blob/17.0/BoardConfigCommon.mk), [Kali NetHunter kernel docs](https://www.kali.org/docs/nethunter/).
