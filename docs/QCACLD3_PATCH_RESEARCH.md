# QCACLD-3.0 WLAN patches for OnePlus 7T Pro (hotdog)

## Decision

**Offer an experimental, opt-in, source-only port; do not auto-apply the entire
NetHunter kernel or advertise internal packet injection as working.**

### Authoritative and directly relevant references

1. **Kali 2026.2**: https://www.kali.org/blog/kali-linux-2026-2-release/
   documents the newer QCACLD-3 injection work.
2. **Kali's device registry**: https://nethunter.kali.org/kernels includes the
   OnePlus 7/7 Pro/7T/7T Pro family, **LineageOS 23.2 (Android 16)**,
   with `Internal Monitor` and `QCACLD-3 Injection` capability tags.
   This registry classification is not a hardware test of our ROM.
3. **Pinned source candidate**:
   https://github.com/V0lk3n/nethunter_kernel_oneplus_sm8150/commit/2ea326d095d723b62c896160a1810f0c95bcc5bb
   from 2026-06-20, importing QCACLD-3.0 injection support into the
   OnePlus 7 SM8150 kernel. Parent:
   `3434121b9dbfa58b82c321ee313ddabb202093e3`.
4. **Reference for upstream implementation**:
   https://github.com/kimocoder/android_kernel_oneplus_avicii/commit/8eb5de1047e7bf069cb4de38c3a35489b35df189
   (larger cross-kernel patch with newer-kernel compatibility shims).
5. **Other SM8150 port**:
   https://github.com/Loukious/android_kernel_xiaomi_sm8150/commit/18c57c61ecd8f02de778e36db6be9b41167a8825
   (TX descriptors / WMA injection path changes).
6. **Conflicting field evidence**:
   https://github.com/althsec/nethunter-oneplus7tpro-los23.2/blob/main/GUIDE.md
   reports successful **passive internal monitor mode** but says internal
   injection is not functional on its tested 7T Pro LineageOS 23.2 setup.
   Therefore do not upgrade registry feature tags to confirmed behavior.

### Pinned target comparison

- Target **crDroid 13 / Android 17**, `hotdog`, 4.14.357 source:
  `crdroidandroid/android_kernel_oneplus_sm8150`,
  commit `1083c6c5906114c71b11a429898b111a1b1b8109`.
- Existing `drivers/staging/qcacld-3.0/configs/default_defconfig` **already**
  sets `CONFIG_FEATURE_MONITOR_MODE_SUPPORT := y`. Kconfig changes alone
  do not implement monitor RX, TX injection, WMA or firmware support.
- Candidate adds `CONFIG_FEATURE_FRAME_INJECTION_SUPPORT := y` and
  previously absent files such as `wlan_hdd_frame_inject.c` and
  `wma_frame_inject.c`; it also hooks Kbuild, HDD, WMA, DP TX and the
  monitor RX path.
- The candidate commit changes **45 paths**: **43 driver paths** plus
  `.gitmodules` and `kali-nethunter-kernel-builder`. The latter two
  must never enter our kernel patch.
- Existing host build uses Clang 14 experimentally; upstream crDroid 17.0
  source selects `clang-r596125`. Source, module ABI, signing and exact
  installed ROM provenance remain gates.

### Prioritized subseries

| Stage | Contents | Gate |
|---|---|---|
| P0 — review | Pin patch ancestry and 43-file whitelist; read-only `git apply --check` against **exact source SHA** | All paths validated, no implicit driver replacement |
| P1 — monitor | Review and port only monitor RX, channel and radiotap paths; preserve stock STA/AP behavior | Build, passive tests, reboot/reconnect, regulatory checks |
| P2 — injection | Port coherent Kbuild+HDD+DP/WMA TX and frame validation/security subseries behind **off-by-default feature flag** | Target build and isolated owned-lab TX tests; independent driver/firmware review |
| P3 — compatibility | Compare `Module.symvers`, `vermagic`, signing trust, `vendor_dlkm`, kernel firmware behavior against exact installed ROM | No flash approval until all independent gates pass |

The P1/P2 split is conceptual until code-level dependencies have been
identified and verified; splitting this large commit incorrectly can break
the driver. A clean `git apply --check` proves only that textual patch
contexts match, *not* that it compiles or works. A failed check is expected
when the baseline drifts; manual review is required, never `git apply -3`
or forcing hunks.

### Read-only patch preflight (Linux or WSL2)

Obtain the patch from the reviewed, immutable upstream commit:

```bash
curl -fL --proto '=https' --proto-redir '=https' --max-time 90 \
  https://github.com/V0lk3n/nethunter_kernel_oneplus_sm8150/commit/2ea326d095d723b62c896160a1810f0c95bcc5bb.patch \
  -o /tmp/op7t-qcacld3-candidate.patch

# Source must have been fetched from config/upstream.lock beforehand:
bash scripts/fetch-source.sh
python3 scripts/qcacld3-patch-preflight.py \
  --patch /tmp/op7t-qcacld3-candidate.patch \
  --kernel .work/kernel \
  --output .work/qcacld3-preflight.json
```

The script rejects unexpected paths/modes, detects dirty or unpinned target
source, and invokes **only `git apply --check`**. It filters the two
non-driver entries for the Git context check. It does not install, stage or
compile a patch; it does not execute code inside the patch. Use `--strict`
to return exit 4 when contexts conflict. Re-running with the same
`--output` fails rather than overwriting previous evidence.

**No automatic source patching, ADB, module loading, boot.img creation,
fastboot, AVB bypass, signature bypass or flashable output.**
`flash_ready=false` remains mandatory.
