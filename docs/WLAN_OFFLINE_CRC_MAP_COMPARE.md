# Offline CRC parity: verified OTA original vs ROM-source CI rebuild

## What the physical Pi has confirmed (2026-10-25)

- Device reports `OnePlus7TPro`, Android 17, crDroid 13.0 (`v13.0-20261021`), kernel `4.14.357-perf-g57037290bb57`, slot `_b`, verified boot `green`.
- Official reference ZIP `crDroidAndroid-17.0-20261021-hotdog-v13.0.zip` matched its pinned SHA-256 `423be5133cb09c88e1dab741ddf77a7e545121c6cf8381d50b4a93c431857834`. It contained an update_engine payload with `vendor_dlkm`. A read-only extraction from its ext filesystem produced `qca_cld3_wlan.ko` SHA-256 `be1a5db188d53d0510df9ad320a31aaf2c1b92662cab7dac4810513477d25924`.
- The original OTA module has **394 imported versioned symbols**. Local canonical map SHA-256 `c45d949ad0cfb368620f6178cbb334c51566932da961862785f8374ce86d7ed4`.
- A local comparison report for rebuilt `wlan.ko` **built from old source 1083c6c59061**, SHA-256 `ccb74c7a56eb2c9b2c5942f949854c020bd03de4d6541245c64fc4f9ef4e1257`, had 394 common symbol names, 185 differing CRCs, 209 matching CRCs and a kernel version mismatch. This does **not** evaluate the later `57037290bb57` experiment.
- GitHub Actions runs `40154311077` and `40153310822` compiled using the observed ROM *source* candidate `57037290bb57`, but **uploaded metadata only**, not the original built ELF, generated `Module.symvers` or all individual CRCs. Their 394/394 counts were *same-build* checks, not against original OTA binary.

## New CI output

On this branch only, the existing disposable `WLAN_ROM_PIN_EXPERIMENT=1 WLAN_PATCH_EXPERIMENT=1` CI job runs on Linux x86_64 with Clang 14. After `scripts/audit-wlan-built-crcs.py` checks the signed ELF against its own `Module.symvers`, `scripts/export-wlan-build-crcs.py` adds `built-wlan-import-crcs.json` to the metadata-only Actions artifact. It contains the **name/CRC pairs** and a canonical SHA-256 tied to the same run's WLAN module SHA, release and selfcheck. No kernel images, module ELF bytes, Module.symvers or signing keys are published by this new job.

This is *only* an import-symbol comparison. It does not prove the original OTA module matches a booted kernel's exports, test monitor RX runtime scheduling, verify original signer against a trusted kernel certificate or establish flash eligibility.

## Pi 5 commands after CI succeeds

```bash
cd ~/Projekte/OP7T-Kernel-PR40-Test
git fetch --no-tags origin research/hotdog-wlan-offline-crc-map-compare
git switch --detach FETCH_HEAD

mkdir -p .work/ci-rom-pinned-crcs
gh run download RUN_ID --repo mason82-dotcom/OP7T-Kernel \
  --name hotdog-wlan-rom-source-compile-RUN_ID \
  --dir .work/ci-rom-pinned-crcs

set -o pipefail
python3 scripts/compare-wlan-build-crcs-to-rom.py \
  --original-rom-wlan .work/device-evidence/qca_cld3_wlan.ko \
  --original-rom-sha256 be1a5db188d53d0510df9ad320a31aaf2c1b92662cab7dac4810513477d25924 \
  --built-map .work/ci-rom-pinned-crcs/built-wlan-import-crcs.json \
  --compiled-report .work/ci-rom-pinned-crcs/wlan-patch-experiment.json \
  --selfcheck-report .work/ci-rom-pinned-crcs/built-wlan-self-crc-report.json \
  | tee .work/device-evidence/rom-vs-pinned-build-crcs.json
printf 'ABI report exit: %s\n' "${PIPESTATUS[0]}"
```

Replace `RUN_ID` with the **successful new branch job's** workflow run ID, not an older baseline run. `2` means known mismatch, `3` means invalid/unbound/missing evidence, `4` means no detected symbol blocker but unknown real-world compatibility remains. Never flash or force-load based on any of these results.

The previously exported `original-wlan-crcs.json` remains local. The tool reparses the original ELF and requires the independently recorded SHA to avoid silently using an unrelated CRC JSON file. Original OTA provenance and physically installed partitions still require independent device/binary attestation.
