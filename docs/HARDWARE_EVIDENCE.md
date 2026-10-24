# Hotdog hardware evidence ledger (read-only)

Last reconciled: **2026-10-24**. Repository target: **OnePlus 7T Pro `hotdog`**, Android 17 / crDroid 13. **No flash authorization**.

This file is the authoritative *project status of the evidence seen so far*, not a statement that uncollected original images or keys exist. The same ADB tests should **not** be requested again unless the device/ROM changes, an earlier observation is disputed, or a narrowly defined unanswered question requires a new observation. Follow the source comments for the actual user-provided results. Keep sensitive serials, full fingerprints, binaries and private keys out of this repository.

## A. Completed physical-device evidence (do not retest by default)

| ID | Evidence | Observed result | What the observation **does not** establish |
| --- | --- | --- | --- |
| DEV-01 | Device and OS read-only ADB inventory | `ro.product.device=OnePlus7TPro` (supported `hotdog` OEM alias); Android 17; crDroid release `13.0`; build display `v13.0-20261021` | Exact flashable original installed ROM archive identity |
| DEV-02 | Slot and running kernel | Slot `_b`; kernel `4.14.357-perf-g57037290bb57` | Kernel source-commit identity, correct A/B recovery/rollback |
| DEV-03 | WLAN runtime | `/proc/modules` reports `wlan` loaded, Live; `(C)` is staging-quality taint, **not** signature verification | The module file's binary identity or compatibility with the rebuilt kernel |
| DEV-04 | Privilege and SELinux | ADB shell `uid=2000`, domain `u:r:shell:s0`, SELinux Enforcing | Unprivileged access to protected vendor module inode metadata |
| DEV-05 | Vendor module layout | `/vendor/lib/modules` points to `/vendor_dlkm/lib/modules`; `/vendor_dlkm` mounted ext4 read-only | A verified partition image or cryptographic integrity proof |
| DEV-06 | Directory name visibility | Whitelisted names include `qca_cld3_wlan.ko`, `gspca_main.ko`, `modules.alias`, `modules.dep`, `modules.load`, `modules.softdep`; `ls -laZ` reports inaccessible inode metadata | The file's readability, hash, ELF integrity, signature, or ABI |
| DEV-07 | Exact-path and sysfs checks | `qca_cld3_wlan.ko` metadata access denied; `wlan.ko` absent *at that path*; `/sys/module/wlan/initstate` denied; `srcversion` absent | General module absence, unsigned code, signature failure, or SELinux policy cause |
| DEV-08 | Fingerprint caveat | Some build/vendor properties show Android 12 OnePlus OEM baseline identity | Identity of the running Android 17 system or the exact installed OTA |

References: [Device/ROM evidence](https://github.com/mason82-dotcom/OP7T-Kernel/issues/3#issuecomment-6383417323), [SELinux and loaded WLAN evidence](https://github.com/mason82-dotcom/OP7T-Kernel/issues/3#issuecomment-6383632627), [read-only vendor_dlkm directory evidence](https://github.com/mason82-dotcom/OP7T-Kernel/issues/3#issuecomment-6383673521).

## B. Completed build / test infrastructure

| ID | State | Evidence |
| --- | --- | --- |
| CI-01 | **PASS** | Pinned kernel `core` / `external` compilation and CI artifacts; raw ARM64 `Image` only, no flashable `boot.img` |
| CI-02 | **PASS for build-internal signing stage** | `modules_install` stages rebuilt signed `wlan.ko`; generated signing key stays outside published artifacts |
| CI-03 | **PASS for structural tooling only** | Offline boot.img v2 structural validator and synthetic tests; no actual installed boot.img is certified |
| CI-04 | **PASS for metadata tooling only** | `compare-rom-modules.py` supports `modinfo` metadata comparison and regression tests; no original ROM-module binary comparison is documented |
| CI-05 | **Merged** | [PR #9](https://github.com/mason82-dotcom/OP7T-Kernel/pull/9) read-only vendor_dlkm name evidence, after [PR #8](https://github.com/mason82-dotcom/OP7T-Kernel/pull/8) access diagnostics |
| CI-06 | **Draft, integration builds pending as of ledger update** | [PR #10](https://github.com/mason82-dotcom/OP7T-Kernel/pull/10) adds offline AArch64 ELF `__versions` / `Module.symvers` CRC triage; Python lint/tests passed, full PR core/external run was in progress |

A passing CI build establishes that a *newly built* signed module corresponds to a *newly built* kernel, **not** that the installed ROM trusts its signing certificate or its vendor module ABI.

## C. Unresolved gates: collect only NEW evidence

| Gate | Required evidence | Current status | Acceptance criterion |
| --- | --- | --- | --- |
| ROM-01 | Original `boot.img`, `dtbo.img`, `vendor_dlkm` / vendor images, extracted from a **proven matching installed ROM** or separately attested partition images, plus hashes and documented provenance | **UNKNOWN** | Explicit source-to-installed-build identity; matching calendar date or OEM fingerprint alone is insufficient |
| MOD-01 | Original `qca_cld3_wlan.ko` binary from ROM-01, original signature trailer metadata, rebuilt `wlan.ko` and matching build `Module.symvers` | **NOT YET EVIDENCED** | Compare `vermagic`, imported-symbol CRCs and signing metadata; report all unresolved dependencies |
| MOD-02 | Trusted module-signing certificate chain of the *actual booting kernel*, signatures on **all required** vendor modules, complete symbol ABI and firmware dependencies | **UNKNOWN / BLOCKING** | Trust and compatibility verified without reducing `CONFIG_MODULE_SIG_FORCE` or SELinux enforcement |
| BOOT-01 | Original boot header v2, DTB/DTBO, ramdisk, boot parameters, AVB/rollback and correct A/B layout | **UNKNOWN / BLOCKING** | Verified *offline* baseline repack and byte-identical or fully justified equivalence, without touching partitions |
| REC-01 | Recovery access, validated backups for both slots, tested restoration procedure | **NOT EVIDENCED / BLOCKING** | Documented recoverable device state before any live boot attempt |
| HW-01 | Owned-device boot and Wi-Fi, cellular, BT, cameras, USB, charging, standby and thermals | **NOT STARTED** | Recorded end-to-end test results **only after** ROM/MOD/BOOT/REC gates |

**Do not reinterpret `UNKNOWN` as `PASS` or `FAIL`.** The original reference OTA is tracked in `config/rom-reference.json` for offline identification only; it does not prove the installed partition images match.

## D. Next test, only after obtaining authentic original images

Do not rerun DEV-01 through DEV-08. Inspect the exact-ROM original `qca_cld3_wlan.ko` offline against the rebuilt module and `Module.symvers`, recording hashes/provenance outside Git:

```bash
python3 scripts/compare-rom-modules.py \
  --built /path/to/build/artifacts/core/modules/drivers/staging/qcacld-3.0/wlan.ko \
  --rom /path/to/verified-installed-rom/qca_cld3_wlan.ko
```

When PR #10 is merged, additionally use `scripts/audit-module-abi.py` with its `--symvers` option on matching build artifacts. **Even matching CRCs or a module-signature trailer are not a proof of runtime key trust, boot safety, complete ABI or authorization to flash.**

Review [issue #3](https://github.com/mason82-dotcom/OP7T-Kernel/issues/3) before changing any gate from UNKNOWN. **`flash_ready=false`**.
