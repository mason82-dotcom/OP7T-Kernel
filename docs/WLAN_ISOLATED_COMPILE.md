# Experimental isolated QCACLD-3.0 compile for hotdog

This deliberately extends [WLAN patch qualification](WLAN_PATCH_QUALIFICATION.md) into a **separate source-compiled kernel test**, without installing anything on the phone. Target: OnePlus 7T Pro, crDroid 13 / Android 17, source `1083c6c5906114c71b11a429898b111a1b1b8109`.

## Opt-in command

On Linux x86_64 with the same Clang/LLVM prerequisites used in the normal build:

```sh
CC=clang-14 LD=ld.lld-14 AR=llvm-ar-14 NM=llvm-nm-14 \
OBJCOPY=llvm-objcopy-14 OBJDUMP=llvm-objdump-14 STRIP=llvm-strip-14 \
WLAN_PATCH_EXPERIMENT=1 bash scripts/build.sh core
```

Never execute this command on the phone. It creates only **host-side experimental build outputs**.

### Isolation and gates

1. Reuse the pinned *clean* original checkout only for reference.
2. Run `scripts/qualify-wlan-patches.py` read-only. Refuse if the source lock or patch scopes differ.
3. Create a new detached disposable Git worktree, apply only the two reviewed patch files and check **exactly three allowed modified driver paths**.
4. Compile with the regular `core` kernel profile in a separate `.work/out-wlan-core` tree, stage modules in `.work/module-stage-wlan-core` and run the **same signed-and-stripped ELF artifact audit** as the regular build, then verify nonempty compiler objects for all three modified translation units (`dp_main.o`, `wlan_hdd_rx_monitor.o`, `wlan_hdd_tx_rx.o`).
5. Write artifacts only under `.work/artifacts/wlan-core`, with a supplementary `wlan-patch-experiment.json` containing patch and compiler-object SHA-256 hashes, the audited signed WLAN module hash and signer metadata, and explicitly false ROM-trust/readiness fields.
6. Always remove the disposable source worktree on process exit, even after a failed compile. The pristine pinned original checkout and normal build profiles are not patched.

The separate GitHub Actions `wlan-isolated-compile` job is restricted to the development branch and requires successful read-only patch qualification. Its artifact upload contains **only bounded metadata**, no raw Image, DTBs, kernel module, signing private key or flashable ZIP. Production kernel compilation continues using untouched sources.

## Interpretation

Passing this build proves only that the two optional patches compile into the pinned kernel under the experimental CI toolchain and pass the local signed/stripped-module metadata checks. It does **not** establish monitor RX correctness or which callback runs on hotdog, packet injection support, trust by the installed ROM kernel, module symbol CRC parity, vendor firmware compatibility, DTBO/boot image parity, AVB state or hardware stability.

Physical runtime validation must precede any installation investigation. **No flashing or boot slot changes. `flash_ready=false`.**

The independent `scripts/audit-wlan-compile.py` checks all three compiled C objects, one on-disk signed/stripped WLAN module, SHA-256, exact module vermagic, and the pinned previous artifact report. Missing code-generation evidence is a **failed build**, not a presumed success. This does not establish that the code is executed by hotdog firmware.
