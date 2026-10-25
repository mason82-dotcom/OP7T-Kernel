# Host-built WLAN ELF ↔ same-build Module.symvers CRC self-check

**Research-only addition, stacked on draft ROM-source compiler experiment #36.** It is not an installed-ROM ABI check, signature trust check, firmware check, or flash approval.

The observed-ROM-source candidate `57037290bb57caefd3c337db3511fca5751fb4ef` selects `CONFIG_MODVERSIONS=y` in the vendor defconfig. A successful ROM-source compile generates a signed, stripped `wlan.ko` and its own `Module.symvers`. We can check internal agreement between those two **from the same new build** without revealing kernel binaries or claiming they will load on the physical phone.

## Required evidence and blocking conditions

`scripts/audit-wlan-built-crcs.py` inspects only the local experimental artifact directory:

- The bounded `artifact-report.json` must attest the exact ROM-source SHA, `hotdog`, `core`, enforced module signing, stripped modules, and `flash_ready=false`.
- The prior `wlan-patch-experiment.json` must attest a successful selected ICNSS RX compilation with the correct SHA, one signed WLAN module and all ROM/flash compatibility flags false.
- The module is read from the *recorded* safe relative path inside the artifact staging directory, not an arbitrary path. Its SHA-256 and size must match the previous module audit.
- An existing offline AArch64 ELF parser checks `__versions` symbol CRC records and the module signature trailer; signature presence is **not** cryptographic verification.
- Every versioned imported symbol in the rebuilt WLAN ELF must resolve with an identical CRC in that build's own `Module.symvers`. Missing or differing records, absent symbols, unparseable ELF, symlinked inputs or untrustworthy reports **fail closed**.
- A bounded `built-wlan-self-crc-report.json` records module and symvers digests, counts, and explicit false ROM/trust/runtime flags. Original `Module.symvers`, signing keys, ELF and kernel images remain **local only**, never uploaded.

This test runs after module signing and the existing strict compile audit, before `SHA256SUMS` is finalized.

A local test following the authorized, opt-in build:

```sh
python3 scripts/audit-wlan-built-crcs.py \
  --artifacts .work/artifacts/wlan-rom-core
```

It refuses to overwrite a previous report. No device is connected or changed.

## Critical interpretation

Even a perfect **self-built** CRC match cannot establish equivalence with the official reference OTA's `qca_cld3_wlan.ko` or the running kernel. The installed original image, its own symbol export CRCs and trusted signing certificates must be independently verified with evidence from the exact phone/build; generated ephemeral signing keys remain untrusted. The callback's softirq/BH/NAPI safety, charging-source changes, normal Wi-Fi functionality and passive monitor operation are also unverified.

**`compared_against_actual_ROM_Module.symvers=false`, `installed_kernel_signing_trust_verified=false`, `flash_ready=false`.** No kernel/module deployment, AVB changes, signature bypass, flash packages or automatic merges.
