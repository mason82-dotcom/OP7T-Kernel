# Safety gate: NOT YET FLASHABLE

The output is a raw kernel payload and unsigned/rebuilt module set, **not** a functional boot image or certified NetHunter kernel. No script in this project flashes a device.

## Exact installed device and ROM

A read-only version and slot check is provided:

    bash scripts/device-audit.sh

For troubleshooting, the equivalent commands can be executed individually:

    adb shell getprop ro.product.device
    adb shell getprop ro.build.version.release
    adb shell getprop ro.build.fingerprint
    adb shell getprop ro.boot.slot_suffix
    adb shell uname -a

Only proceed later if device is `hotdog` and Android is 17; do not use this for `hotdogg` 5G McLaren. Confirm the exact installed crDroid build and kernel commit before packaging.

## Boot configuration verified against 17.0 device tree

* `BOARD_BOOT_HEADER_VERSION := 2`
* `BOARD_KERNEL_IMAGE_NAME := Image`
* `BOARD_KERNEL_SEPARATED_DTBO := true`
* `BOARD_INCLUDE_DTB_IN_BOOTIMG := true`
* `BOARD_RAMDISK_USE_LZ4 := true`
* `TARGET_KERNEL_CONFIG := vendor/sm8150-perf_defconfig vendor/oplus.config`

Any packaging must preserve the **exact** installed ROM's boot image metadata, DTB/DTBO and ramdisk. Android 17 does not imply a modern GKI vendor_boot layout for this 2019-launched device.

## Major blocker: kernel modules

The vendor overlay sets `CONFIG_QCA_CLD_WLAN=m`; the base defconfig sets `CONFIG_MODULE_SIG_FORCE=y`. Existing ROM `wlan.ko` or `vendor_dlkm` modules can refuse to load after a rebuilt kernel due to signatures, vermagic or ABI. Do not disable signature enforcement just to bypass this check. A verified compatible and correctly signed module deployment plan is a separate release requirement.

## Build-to-ROM provenance lock

`config/rom-reference.json` records the public crDroid 13 `hotdog` OTA package released on **2026-10-21** and its published SHA-256. This is a **reference**, not proof that a connected phone is running that exact build. A downloaded ROM ZIP can be verified offline with:

    python3 scripts/verify-rom-zip.py crDroidAndroid-17.0-20261021-hotdog-v13.0.zip

Only the exact installed build's original boot/DTBO and vendor modules can serve as compatibility references for any boot image packaging. The checksum verification script does not extract, patch or flash the ZIP.

## Additional build artifact audit

The generated `artifact-report.json` records the Image header, source SHA, DTBs, module hashes, vermagic, signer identity, signature key ID and algorithm. It verifies **build-internal** module release consistency and requires the Qualcomm WLAN module. The optional `Module.symvers` and `System.map` are retained for detailed local investigation. **Even signed modules may fail to load** if the certificate is not trusted by the exact running kernel. A successful audit is a raw-build check, not a flash certification. `flash_ready` is always `false`.

## Read-only original ROM module comparison

With the exact installed ROM's original `wlan.ko` available locally, run `scripts/compare-rom-modules.py` with `--built` and `--rom` paths. Compare `vermagic` and signer/key identifiers; mismatches are blockers, matching values are **not approval**. The script neither extracts the installed ROM nor writes to the device. Check the *actual* trusted module certificates and symbol ABI separately before image packaging.

## Required tests before any real flash

1. Compile and compare `baseline`, `core` and (optionally) `external` on an isolated builder; inspect all failures.
2. Back up **both slots** and retain complete ROM/recovery image and hashes. Verify fastboot/recovery access and correct slot.
3. Review and validate the boot image packager separately on extracted image data before writing.
4. Boot/rollback proof on actual device, followed by Wi-Fi, mobile data, Bluetooth, camera, USB, suspend, charging and thermal tests.
5. Test own authorized USB-WLAN and HID hardware in a controlled lab.
6. Port internal QCACLD monitor mode and injection **only** in a separate review after the stable reference.

Do not flash either slot or alter AVB, SELinux or thermal protections as part of CI. Do not wipe userdata to fix a kernel-only bootloop.
