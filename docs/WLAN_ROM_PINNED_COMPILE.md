# Isolated patched ICNSS WLAN build against observed hotdog ROM-source candidate

This draft extends the **passing parent kernel compile** (#27), **ROM source-only diff parity** (#34), and **softirq callback-context risk audit** (#35) to a real Clang-14 **host-only build** against the exact observed-ROM source candidate. No device is connected or modified.

| Attribute | Immutable evidence |
| --- | --- |
| Official upstream repository | `crdroidandroid/android_kernel_oneplus_sm8150` |
| Original project source lock | `1083c6c5906114c71b11a429898b111a1b1b8109` |
| Observed-ROM source candidate | `57037290bb57caefd3c337db3511fca5751fb4ef` |
| Observed ROM / OTA WLAN release reference | `4.14.357-perf-g57037290bb57` |
| Only applied RFC patch | `0002-qcacld-hotdog-icnss-monitor-rx-rfc.patch` |
| Selected module build | `core`, Clang/LLVM 14, explicit optional experiment |

## Host-side opt-in

On an authorized Linux x86_64 development machine with the normal Clang 14 cross-compiler prerequisites:

```sh
CC=clang-14 LD=ld.lld-14 AR=llvm-ar-14 NM=llvm-nm-14 \
OBJCOPY=llvm-objcopy-14 OBJDUMP=llvm-objdump-14 STRIP=llvm-strip-14 \
WLAN_PATCH_EXPERIMENT=1 WLAN_ROM_PIN_EXPERIMENT=1 \
bash scripts/build.sh core
```

A ROM-source experiment **requires both** variables and the `core` profile. The default (neither flag) continues to use the unchanged committed `config/upstream.lock`, the pristine original source and standard build outputs.

The experiment first pins and validates the original Git source, fetches exactly the child SHA, and executes the independent ROM source-parity gate (strict ancestry, exact charger-only delta, hashes for WLAN build inputs, checks against both revisions) **before** creating the disposable child worktree and applying only the ICNSS RX RFC. A failed gate blocks compilation.

The worktree is detached, temporary, and cleaned on exit. Output paths are isolated:

- `.work/out-wlan-rom-core` — compiler output with patched kernel Image and objects, local only
- `.work/module-stage-wlan-rom-core` — installation *staging on the build host*, never the host's system or phone
- `.work/artifacts/wlan-rom-core` — raw build artifacts plus bounded provenance and audit metadata, not flashable

The normal signed-and-stripped artifact audit is required, followed by an independent check of the actually compiled `wlan_hdd_tx_rx.o`, the signed `wlan.ko`, module SHA-256, kernel release and the ROM source-parity JSON. The signer is an **ephemeral CI build key**, and its presence is **not** evidence of trust by the installed ROM. Keys remain ignored in compiler outputs.

Only these metadata files are uploaded by the dedicated `wlan-rom-pinned-compile` CI job: `artifact-report.json`, `kernel.config`, `kernel.release`, `upstream-commit.txt`, `toolchain-report.json`, `wlan-patch-experiment.json` and `wlan-rom-source-parity.json`. No Image, DTB, WLAN module, full `Module.symvers`, private signing key, or flashable ZIP leaves the workflow.

## Interpretation and outstanding release blockers

A successful build establishes **successful local code generation from the observed-ROM source candidate**, with the reviewed RFC, under this Clang toolchain. It does **not** prove the compiler output matches the installed kernel binary or signed reference OTA WLAN module. The patched worktree also changes the `-dirty` build provenance. The generated module's release string and signer must **not** be mistaken for the original ROM's ABI or key chain.

The child upstream commit changes OPlus charger resume logic, so charging-safety review remains required even though WLAN source files are unchanged. Kernel `Module.symvers` CRCs, vendor firmware, exact active boot slot and ROM kernel binary, actual signing trust, callback softirq/BH/NAPI execution context, monitor-RX packet flow, normal Wi-Fi stability and injection all remain unverified.

Never flash this build, install the test `wlan.ko` on the phone, change AVB/module signing or merge the experiment automatically. **`flash_ready=false`.**
