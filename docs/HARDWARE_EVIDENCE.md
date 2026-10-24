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
| CI-04 | **PASS for offline reference-module metadata only** | The verified *reference OTA* yielded `qca_cld3_wlan.ko` and offline `modinfo` values. Comparison against rebuilt modules identifies a `vermagic` / signer-key mismatch; no installed-partition or full symbol-CRC attestation |
| CI-05 | **Merged** | [PR #9](https://github.com/mason82-dotcom/OP7T-Kernel/pull/9) read-only vendor_dlkm name evidence, after [PR #8](https://github.com/mason82-dotcom/OP7T-Kernel/pull/8) access diagnostics |
| CI-06 | **MERGED and CI PASS** | [PR #21](https://github.com/mason82-dotcom/OP7T-Kernel/pull/21) integrates the AArch64 ELF `__versions` / `Module.symvers` and dependency audit plus Clang toolchain provenance. [Lint, core and external CI](https://github.com/mason82-dotcom/OP7T-Kernel/actions/runs/40133399716) all passed; original installed-module ABI remains unverified |
| CI-07 | **MERGED and CI PASS** | [PR #13](https://github.com/mason82-dotcom/OP7T-Kernel/pull/13) removes debug sections via Kbuild **before** module signing and enforces final ELF section/signature checks; [PR #14](https://github.com/mason82-dotcom/OP7T-Kernel/pull/14) documents the official crDroid build reference |
| CI-08 | **PASS for one build's internal CRC consistency only** | The complete [experimental core artifact from run 40125985800](https://github.com/mason82-dotcom/OP7T-Kernel/actions/runs/40125985800) has 33 present checksum-verified members. The two uploaded modules match it byte for byte. All 394 `wlan.ko` and 65 `gspca_main.ko` imported CRC records agree with that same build's `Module.symvers`. The original ROM modules were not compared in this check. |
 
### Build artifacts versus the original reference-OTA WLAN module

The operator already extracted the reference OTA's `vendor_dlkm.img` and identified `qca_cld3_wlan.ko`; **do not request another basic ADB inventory**. [Original offline findings](https://github.com/mason82-dotcom/OP7T-Kernel/issues/3#issuecomment-6387373827). The extracted module was from a cryptographically checked *reference ZIP*, **not** from a proven matching installed partition.

| Evidence | Reference OTA module | Rebuilt Core | Rebuilt External |
| --- | --- | --- | --- |
| Module bytes | 14,982,321 | 14,997,801 | 14,998,641 |
| Kernel release used in `vermagic` | `4.14.357-perf-g57037290bb57` | `4.14.357-perf-g1083c6c59061` | `4.14.357-perf-g1083c6c59061` |
| Module signing key ID prefix | `5C:B6:0B:B2` | `06:B3:1C:C7` | `0A:69:07:87` |
| Runtime kernel key trust | Unknown | Unknown | Unknown |
| Proven installed-ROM matching | No | No | No |

The two rebuilt modules are signed with **different autogenerated keys**, so do not exchange `.ko` files or kernel images across separate builds. `modinfo` and signed-module **metadata** do not establish PKCS#7 verification, original partition identity, compatibility of referenced symbols, or runtime success. The CI-report ZIPs contain only JSON/config/kernelrelease metadata; the module files were **not** included. [Release blocker and current checks](https://github.com/mason82-dotcom/OP7T-Kernel/issues/3).

A separately downloaded **manual raw** `core` artifact from run 40125985800 does contain both signed modules and `Module.symvers`; its signing key ID begins `32:1A:C3:9C`. It is a distinct build from the Core and External columns above. Its rebuilt `vermagic` is `4.14.357-perf-g1083c6c59061`, so the known reference-OTA `g57037290bb57` mismatch remains. Its internal CRC agreement cannot close MOD-01 or MOD-02 without a proven installed-ROM original and a direct original-versus-rebuilt comparison.

A passing CI build establishes that a *newly built* signed module corresponds to a *newly built* kernel, **not** that the installed ROM trusts its signing certificate or its vendor module ABI.

## C. Unresolved gates: collect only NEW evidence

| Gate | Required evidence | Current status | Acceptance criterion |
| --- | --- | --- | --- |
| ROM-01 | Original `boot.img`, `dtbo.img`, `vendor_dlkm` / vendor images, extracted from a **proven matching installed ROM** or separately attested partition images, plus hashes and documented provenance | **UNKNOWN** | Explicit source-to-installed-build identity; matching calendar date or OEM fingerprint alone is insufficient |
| MOD-01 | Original `qca_cld3_wlan.ko` binary from a *proven installed ROM*, original signature trailer metadata, matching rebuilt `wlan.ko` and `Module.symvers` | **REFERENCE OTA MODULE INSPECTED; INSTALLED MATCH AND FULL CRC AUDIT OPEN** | Reference OTA `vermagic` and key ID differ from rebuilt modules; provenance plus imported-symbol CRCs and load dependency review still required |
| MOD-02 | Trusted module-signing certificate chain of the *actual booting kernel*, signatures on **all required** vendor modules, complete symbol ABI and firmware dependencies | **UNKNOWN / BLOCKING** | Trust and compatibility verified without reducing `CONFIG_MODULE_SIG_FORCE` or SELinux enforcement |
| BOOT-01 | Original boot header v2, DTB/DTBO, ramdisk, boot parameters, AVB/rollback and correct A/B layout | **UNKNOWN / BLOCKING** | Verified *offline* baseline repack and byte-identical or fully justified equivalence, without touching partitions |
| REC-01 | Recovery access, validated backups for both slots, tested restoration procedure | **NOT EVIDENCED / BLOCKING** | Documented recoverable device state before any live boot attempt |
| HW-01 | Owned-device boot and Wi-Fi, cellular, BT, cameras, USB, charging, standby and thermals | **NOT STARTED** | Recorded end-to-end test results **only after** ROM/MOD/BOOT/REC gates |

**Do not reinterpret `UNKNOWN` as `PASS` or `FAIL`.** The original reference OTA is tracked in `config/rom-reference.json` for offline identification only; it does not prove the installed partition images match.

## D. Next NEW evidence: confirm installed image, then compare original modules

Do not rerun DEV-01 through DEV-08. The reference-ROM module was already extracted and inspected offline; what remains is to **prove it matches the installed device's partition** and compare it against actual rebuilt module ELF files and matching `Module.symvers`. Record hashes and provenance locally, outside Git:

```bash
python3 scripts/compare-rom-modules.py \
  --built /path/to/build/artifacts/core/modules/drivers/staging/qcacld-3.0/wlan.ko \
  --rom /path/to/verified-installed-rom/qca_cld3_wlan.ko
```

The merged `scripts/audit-module-abi.py` additionally accepts `--symvers` and `--fail-on-unknown` on matching build artifacts. **No comparison based on complete real binaries has yet been certified in this ledger.** **Even matching CRCs or a module-signature trailer are not a proof of runtime key trust, boot safety, complete ABI or authorization to flash.**

Review [issue #3](https://github.com/mason82-dotcom/OP7T-Kernel/issues/3) before changing any gate from UNKNOWN. **`flash_ready=false`**.
