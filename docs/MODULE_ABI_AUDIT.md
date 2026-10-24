# Read-only ARM64 module ABI evidence — hotdog / crDroid 13

This audit compares **recompiled kernel modules** with the **original modules**
from the **exact installed** OnePlus 7T Pro (`hotdog`) crDroid 13 / Android 17
ROM. The tool uses Python 3 standard library only, never runs an ELF file,
opens ADB, changes a partition or flashes the device.

The script is derived from the earlier [PR #10](https://github.com/mason82-dotcom/OP7T-Kernel/pull/10),
rebased conceptually onto current `main` and hardened for dependency drift,
malformed high CRC bits and optional strict reporting. [PR #13](https://github.com/mason82-dotcom/OP7T-Kernel/pull/13)
separately addresses stripping module debug sections **before** signing;
the changes are independent and should not be conflated with ABI parity.

## What is actually checked

- AArch64 `ELF64`, little-endian, relocatable (`ET_REL`) structure and bounds.
- `.modinfo` kernel release / `vermagic`, optional module name, `depends`.
- Imported kernel symbol CRCs in `__versions`, using the Linux 4.14 AArch64
  `struct modversion_info` layout (8-byte unsigned long + 56-byte name).
- CRC disagreements on the set of common imports, and, if provided,
  mismatches between the original module's imports and the rebuilt
  `Module.symvers`.
- Presence and length of an appended module signature trailer **only**.
  This is *not* signature verification or proof of trust.
- SHA-256 and file size for traceability (not compatibility).

Modules may legitimately have different sets of imported symbols after an
implementation change. Changes in module dependencies are flagged for review,
not silently treated as compatible. Matching CRCs do **not** establish kernel
ABI compatibility: symbol type changes, KABI/private structures, firmware,
kernel config, runtime dependencies, module key trust and exact ROM provenance
remain open.

## Inputs

Use the signed, **stripped** `wlan.ko` and `gspca_main.ko` from the same
successful kernel-build profile, plus the corresponding
`.work/artifacts/<profile>/Module.symvers` when generated. Confirm the
actual staged module relative paths within that build output rather than
assuming fixed directories.

Original `qca_cld3_wlan.ko` and `gspca_main.ko` must be extracted from a
provenance-verified `vendor_dlkm.img` or the actual connected device's
verified partition. A matching filename, stock kernel release or dated OTA
ZIP **does not prove the ZIP was installed on the phone**.

Example after independently obtaining the original and built modules:

```bash
python3 scripts/audit-module-abi.py \
  --built /path/to/rebuilt/wlan.ko \
  --rom /path/to/exact-installed/vendor_dlkm/qca_cld3_wlan.ko \
  --symvers /path/to/rebuilt/Module.symvers \
  --fail-on-unknown > wlan-abi-review.json

python3 scripts/audit-module-abi.py \
  --built /path/to/rebuilt/gspca_main.ko \
  --rom /path/to/exact-installed/vendor_dlkm/gspca_main.ko \
  --symvers /path/to/rebuilt/Module.symvers \
  --fail-on-unknown > gspca-abi-review.json
```

Run with `python3 -m unittest discover -s tests -v` for synthetic fixture
coverage; **these fixtures cannot replace testing real signed modules**.

## Exit codes and report semantics

| Exit | Meaning |
| --- | --- |
| 0 | Offline comparison ran without known CRC/vermagic blockers (not a compatibility approval) |
| 2 | Known CRC or metadata mismatch, stop |
| 3 | Malformed or inaccessible input, stop |
| 4 | `--fail-on-unknown`: at least one unresolved uncertainty, stop |

The report always sets
`module_signature_cryptographically_verified=false`,
`installed_kernel_module_key_trust_verified=false`,
`full_kernel_vendor_abi_verified=false`,
`exact_installed_rom_provenance_verified=false` and `flash_ready=false`.

Do not disable module signature enforcement, AVB or SELinux to force a pass.
No boot image, flashable ZIP, partition write, recovery action or
USB/WLAN injection claims are produced.
