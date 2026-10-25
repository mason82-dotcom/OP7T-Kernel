# Read-only evidence and offline inspection tools

Use these commands to obtain bounded evidence without writing to the device. **No listed script is a flashing utility.** The existing [hardware evidence ledger](HARDWARE_EVIDENCE.md) contains completed observations; do not rerun them by default. Do not publish raw device serials, private signing material, full sensitive fingerprints or original proprietary images.

## Connected device (ADB, authorized USB debugging)

| Purpose | Command | Interpretation |
| --- | --- | --- |
| Minimal compatibility guard | `bash scripts/device-audit.sh` | Checks target/version/slot; read-only |
| Module/ROM inventory | `bash scripts/device-module-audit.sh` | Shows accessible WLAN paths/fingerprints; permission-denied ≠ absent |
| Cross-platform structured evidence | `python3 scripts/device-evidence.py --output hotdog-device-evidence.json` | Local JSON, create-only output; Windows equivalent uses `py -3` |

Run from the repository root. The Bash scripts accept `--serial ADB_SERIAL` and the Python script accepts `--serial ADB_SERIAL` when more than one device is attached. Python 3 and Android Platform Tools must be on PATH. The Python check recognizes `hotdog` and the OEM property alias `OnePlus7TPro`, rejects `hotdogg` / `OnePlus7TProNR` and Android versions other than 17.

For the crDroid 17.0 upstream, `ro.crdroid.version=17.0` describes the Android platform while `ro.crdroid.build.version=13.0` identifies the crDroid version. Android-12 OEM/vendor fingerprints **alone** do not prove installed-ROM identity. The Python inventory distinguishes WLAN directory-entry visibility, stat/readability, and loaded-module names; `Permission denied` is **not absence**. It cannot prove certificate trust or vendor-module ABI.

## Offline reference OTA

The OTA pinned in [`config/rom-reference.json`](../config/rom-reference.json) is a **reference only**. For a locally obtained matching ZIP:

~~~bash
python3 scripts/verify-rom-zip.py /path/to/crDroidAndroid-17.0-20261021-hotdog-v13.0.zip
python3 scripts/inspect-ota-payload.py /path/to/crDroidAndroid-17.0-20261021-hotdog-v13.0.zip
~~~

The first checks the configured archive identity/checksum; the second reads the bounded CrAU A/B payload v2 partition *manifest*, not extracted partitions. Neither command proves that the ZIP was installed, cryptographically validates every payload partition, or writes to a phone. Delta payloads can omit unchanged partitions.

## Offline module inspection

After separately obtaining modules from a **proven matching installed ROM** and a specific kernel-build output:

~~~bash
python3 scripts/compare-rom-modules.py \
  --built .work/artifacts/core/modules/drivers/staging/qcacld-3.0/wlan.ko \
  --rom /path/to/exact-installed-rom/qca_cld3_wlan.ko

python3 scripts/audit-module-abi.py \
  --built .work/artifacts/core/modules/drivers/staging/qcacld-3.0/wlan.ko \
  --rom /path/to/exact-installed-rom/qca_cld3_wlan.ko \
  --symvers .work/artifacts/core/Module.symvers \
  --fail-on-unknown
~~~

Check the actual built file locations first. `compare-rom-modules.py` compares identity metadata; `audit-module-abi.py` checks ELF, import CRCs, dependencies and known uncertainty. See the [ABI audit guide](MODULE_ABI_AUDIT.md) for exit codes and limitations. Matching hashes/CRCs, `vermagic` or visible signature trailers never establishes full kernel ABI, signing-key trust or bootability.

## Artifact ZIP intake

~~~bash
python3 scripts/inspect-artifact-zip.py /path/to/files.zip
python3 scripts/inspect-artifact-zip.py /path/to/files.zip --require-complete
~~~

The tool verifies present members using the supplied `SHA256SUMS` and artifact manifest and identifies entries missing from partial exports. Completeness and checksums do **not** authenticate GitHub Actions provenance or imply installed-ROM module compatibility. Historical partial/core-artifact findings belong in the [evidence ledger](HARDWARE_EVIDENCE.md), not in this commands page.

## Original boot image (offline only)

~~~bash
python3 scripts/audit-bootimg.py /path/to/original-boot.img \
  --expect-sha256 <known-original-sha256>
~~~

Checks original Android boot-header v2 layout, raw ARM64 kernel, ramdisk, FDT/DTB bounds and SHA-256; emits JSON without extraction, repacking or flashing. This does **not** inspect AVB trust, separate DTBO compatibility, active-slot provenance, vendor-module loading or device boot. Review the [upstream board assumptions](CRDROID_17_BUILD_REFERENCE.md) and [release gates](FLASHING.md) before interpreting results.

## Interpretation rule

All outputs are **inspection evidence**, never an automatic release sign-off. Unknown or inaccessible material stays **UNKNOWN**. In particular, a locally verifiable build-generated public certificate cannot establish the current installed kernel's certificate trust. The authoritative status of each missing fact is in [HARDWARE_EVIDENCE.md](HARDWARE_EVIDENCE.md).
