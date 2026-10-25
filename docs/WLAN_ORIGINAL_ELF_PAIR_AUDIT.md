# Offline audit: original ROM WLAN ELF versus locally rebuilt hotdog WLAN ELF

This draft extends the green [#39 reference-release gap audit](https://github.com/mason82-dotcom/OP7T-Kernel/pull/39) to **actual ELF bytes** when a user independently supplies BOTH a locally built kernel module and the original ROM module. It never calls ADB/fastboot, loads a module, flashes or modifies a phone.

## Why the previous CI metadata is insufficient

Successful [#38 CI](https://github.com/mason82-dotcom/OP7T-Kernel/actions/runs/40154311077) produced a signed, stripped `wlan.ko` and verified **394/394** of its imported symbol CRCs against the **same build**. Its metadata archive contains **no actual .ko** and **no full Module.symvers** by design. It cannot compare a reference OTA ELF against a CI ELF or verify installed-kernel key trust.

The experimental signed module has `4.14.357-perf-g57037290bb57-dirty` as its vermagic release, whereas the separately observed original reference OTA `qca_cld3_wlan.ko` uses `4.14.357-perf-g57037290bb57`. A direct offline comparison of the existing exact artifacts will therefore report **vermagic mismatch**. Do not alter the version suffix to masquerade as the ROM or disable signature verification.

## Required inputs

1. Run the approved host-only ROM-source experiment locally on an x86_64 build host. This creates `.work/artifacts/wlan-rom-core/modules/drivers/staging/qcacld-3.0/wlan.ko` and its exact generated `Module.symvers` and JSON provenance. The build can use a **different ephemeral signing key than GitHub Actions**, so its resulting `wlan.ko` SHA-256 need not equal the published CI hash. The audit instead ties the module to the attestations from **that same local build**.
2. Independently obtain `qca_cld3_wlan.ko` from the official, verified reference OTA's read-only `vendor_dlkm` extraction or a separately authenticated source. The pinned reference OTA manifest is `config/rom-reference.json`. Provide an **independently established expected SHA-256** for that module. Merely computing a SHA-256 of an unknown module and supplying it back as the expected hash **does not prove OTA provenance**.
3. Install local host `kmod` (for `modinfo`), Python 3 and required compiler utilities from the main build workflow. No root privileges, device connection or internet access are needed to run the audit.

## Offline comparison

```bash
python3 scripts/audit-wlan-original-elf-pair.py \
  --built-artifacts .work/artifacts/wlan-rom-core \
  --original-rom-wlan /verified/rom-extraction/qca_cld3_wlan.ko \
  --original-rom-sha256 EXPECTED_REFERENCE_MODULE_SHA256 \
  --strict > wlan-original-vs-local-report.json
```

The strict mode reports a nonzero status until every mismatch/uncertainty is cleared; it **does not** grant flash approval. Exit codes: `2` known ELF/signer/CRC mismatch; `3` missing, unsafe, inconsistent, unsigned or unreadable input; `4` unresolved uncertainty without known mismatch; `0` only means the comparison ran without a detected blocker when strict mode is omitted.

## Safety gates and conclusions

The wrapper calls the existing `audit-wlan-built-crcs.py` first to require an exact source pin, one signed and stripped rebuilt WLAN module, a locally matching SHA-256/size, a signature trailer, the recorded temporary signing identity and CRC match against its own `Module.symvers`. It then checks both supplied ARM64 ELF `.modinfo` and `__versions` sections, compares symbol CRCs and checks `modinfo`-reported signer, `sig_key` and `vermagic`. File size bounds, expected original basename and no symlinks are enforced. Only aggregate counts, bounded discrepancy names and the two file SHA-256 hashes leave the script; it does not publish the ELF binaries.

Unknowns remain even if *every* supplied field matches: the original module's provenance is operator-supplied, the running device may have different OTA/boot/vendor partitions, a module-signature trailer/key ID does not establish cryptographic trust by the running kernel, firmware/vendor interfaces may differ, and the monitor-RX callback's softirq/NAPI behavior is untested on-device. `flash_ready=false` always. No forced module insertions, signing bypass, AVB changes, flashable builds, production merges or hardware enablement.
