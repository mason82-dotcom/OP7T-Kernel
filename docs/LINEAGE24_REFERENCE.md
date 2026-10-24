# LineageOS 24.0: second Android 17 kernel source reference

**Scope:** OnePlus 7T Pro `hotdog`, not `hotdogg`; comparison only. **Do not flash this source, modules or boot images onto the installed crDroid 13 device.**

## Pinned upstreams (verified 2026-10-24)

| Parameter | crDroid 13 (currently built) | LineageOS 24.0 (alternative) |
| --- | --- | --- |
| Kernel repo | [crDroid SM8150](https://github.com/crdroidandroid/android_kernel_oneplus_sm8150/tree/17.0) | [LineageOS SM8150](https://github.com/LineageOS/android_kernel_oneplus_sm8150/tree/lineage-24.0) |
| Fixed commit | `1083c6c5906114c71b11a429898b111a1b1b8109` | `9f007fac27dce21d29d8230753b71d5634b8a00e` |
| Makefile | Linux 4.14.357 | Linux 4.14.357**-openela** |
| Base `CONFIG_MODULE_SIG` / `CONFIG_MODULE_SIG_FORCE` | Both `y` | Both `y` |
| OPlus overlay `CONFIG_MODULE_SIG` | Not explicitly changed | **Explicitly disabled** (`# CONFIG_MODULE_SIG is not set`) |
| `CONFIG_MODVERSIONS` / `CONFIG_QCA_CLD_WLAN` | `y` / `m` | `y` / `m` |

BoardConfigCommon.mk in both current Android-17 device trees defines **boot header v2**, **4096-byte pages**, raw `Image`, embedded DTB, separated DTBO and LZ4 ramdisk. Same board flags **do not** prove identical physical boot images, trusted module keys, signer identity, symbol ABI or runtime firmware behavior.

### High-priority divergences

1. **Kernel version suffix:** `EXTRAVERSION=-openela` on the LineageOS branch. The nominal kernel release can differ even with the same 4.14.357 patch level; `CONFIG_LOCALVERSION`, resolved config, localversion scripts and build metadata also matter. Never reuse crDroid `wlan.ko` on a Lineage kernel on this observation alone.
2. **Module signing:** the LineageOS OPlus fragment **requests disabling `CONFIG_MODULE_SIG`** even though the base defconfig requests it enabled with enforcement. Actual merged/olddefconfig output must be inspected. Do **not** remove enforcement or copy that overlay's disable line into our primary kernel merely to satisfy tests. Our primary `config/upstream.lock` and module-signing pipeline remain unchanged.
3. **Actual vendor WLAN module:** the installed crDroid kernel has a live `wlan` module and directory entry `qca_cld3_wlan.ko` in read-only vendor_dlkm. File bytes, trusted certificate and ABI are **not** authenticated by these source checks; prior device evidence remains in [HARDWARE_EVIDENCE.md](HARDWARE_EVIDENCE.md).
4. **NetHunter features:** reuse only reviewed, independently validated changes. Upstream branch presence, config requests and full kernel builds do not establish injection/HID/USB compatibility.

## Reproduce source-input comparison offline

No device connection is involved. From the repository root on Linux (with `git` and Python 3):

```bash
# Existing crDroid checkout at .work/kernel may already exist:
bash scripts/fetch-source.sh

git clone --filter=blob:none --single-branch --branch lineage-24.0 \
  https://github.com/LineageOS/android_kernel_oneplus_sm8150.git \
  .work/lineage24-reference
git -C .work/lineage24-reference checkout --detach \
  9f007fac27dce21d29d8230753b71d5634b8a00e

python3 scripts/compare-kernel-references.py \
  --crdroid-tree .work/kernel \
  --lineage-tree .work/lineage24-reference
```

The comparator first verifies both Git HEADs against `config/kernel-alternatives.json` and rejects locally modified tracked source files. It outputs JSON with Makefile differences, source-file SHA-256 hashes, explicit Kconfig requests and flagged high-risk deltas. **It does not build either source, run Kconfig's `olddefconfig`, parse all transitive kernel dependencies, compare actual modules or validate the device.** All readiness flags remain false.

## Development decision

**Retain crDroid 17.0 as the sole production-target build baseline.** LineageOS 24.0 is a **second upstream audit/reference**, not an interchangeable kernel image and not a replacement signing strategy. No automatic cherry-picks, boot-image creation, AVB changes or flashing.

Next only after the offline source audit: compare *resolved* `.config` and built `kernelrelease` outputs for each pinned source in isolated build directories and perform an authorized original-ROM `qca_cld3_wlan.ko` ABI/signature review. Treat any mismatch as a blocker; matching metadata remains insufficient to authorize flashing.
