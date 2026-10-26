# Experimental crDroid 13 / hotdog baseline with Android Clang 22

## Scope and preservation

This **experimental, non-flashable** comparison is based on
`experiment/hotdog-rom-release-source-pin`, not the default branch.
It builds the untouched crDroid 13 / Android 17 kernel (no NetHunter or
KernelSU patch) at `57037290bb57caefd3c337db3511fca5751fb4ef`.

Workflow: `.github/workflows/hotdog-aosp-clang22-baseline.yml`.
It runs **only by manual dispatch** on
`experiment/hotdog-aosp-clang-r596125`; documentation commits do not
start a new costly kernel build. It is separate from the Clang-14
`nethunter-kernel.yml` workflow.

## Reproducible compiler input

- Repository: `https://android.googlesource.com/platform/prebuilts/clang/host/linux-x86`
- Immutable repository commit: `29182889399818f97baa65ea238c80e8117981eb`
- Sparse prebuilt directory: `clang-r596125`
- Expected `clang --version`: Android Clang 22.0.2, `based on r596125`
- Expected `ld.lld --version`: LLD 22.0.2

The CI job rejects a mismatched compiler version, wrong source pin, and
missing tools. It records compiler and linker hashes via
`scripts/audit-toolchain.py`. An AOSP-prebuilt layout match is **not**
cryptographic proof that it is the exact compiler used for the official
ROM, and does not confer flash-readiness.

The build deliberately preserves its true CI build user, host and
timestamp, rather than imitating the official OTA release. This lets
us separate toolchain effects from build-environment differences.

## Established offline reference evidence (October 26, 2026)

Reference OTA: `crDroidAndroid-17.0-20261021-hotdog-v13.0.zip`.
The original kernel from its `boot.img` is 48,713,752 bytes, SHA-256
`d0e941cde7e7cd0b0e13838dc30506c448450e8e1238c40a1da2cc9b8b7b3571`.
The earlier Clang-14 baseline is 48,715,792 bytes, SHA-256
`21d0651587c7bc79a8b68bf4f360e47c235988118d461b24d01a54be3756a274`.

The embedded original and Clang-14 configurations agree on all 5,007
CONFIG entries. The WLAN and GSPCA module imported symbol-version CRCs
agree with the reference OTA: 394/394 and 65/65, respectively. The
first nonheader Image difference is offset 2048; differences spread
through 47 one-MiB ranges. The original kernel reports Clang 22.0.2
and LLD 22.0.2, whereas the Clang-14 baseline reports Ubuntu 14.0.0.

These observations concern the **reference OTA**, not independently
attested contents of the phone's active installed partitions.

## Inspect new workflow results

Open the workflow run in GitHub Actions or use:

```bash
gh run list --repo mason82-dotcom/OP7T-Kernel \
  --workflow hotdog-aosp-clang22-baseline.yml \
  --branch experiment/hotdog-aosp-clang-r596125 --limit 5
```

If successful, download the `hotdog-aosp22-unverified-baseline-<commit>`
artifact to a **new** directory, then verify its included `SHA256SUMS`.
Do not replace the existing Clang-14 baseline or any original OTA file.
The artifact includes a raw ARM64 `Image`, configuration, unsigned
build metadata, DTBs, signed **new-build** modules, and a toolchain
provenance report. The toolchain's **private generated signing key is
not archived**.

Compare the new kernel with the original locally using
`scripts/audit-bootimg.py`, the resulting `sections.kernel.sha256`
and `sha256sum` of the artifact `Image`. A different hash is
expected unless all relevant compiler/linker choices, build identity,
time, signing artifacts and other influences match. Do not change
kernel configuration to force equality.

## Safety gates

`CONFIG_MODULE_SIG_FORCE=y` remains enabled. The generated CI
module-signing key differs from the reference OTA's key.
Matching source/configuration and symbol CRCs does not prove that the
device trusts any newly signed module, nor AVB, DTB/DTBO compatibility,
active-slot identity or bootability. The workflow deliberately does
not pack a boot image, flash the device, bypass module signature
enforcement or set `flash_ready=true`.

## Completed first Clang-22 CI baseline (2026-10-26)

Run [40305770114](https://github.com/mason82-dotcom/OP7T-Kernel/actions/runs/40305770114)
on revision `e75e73fe9a59099f54ccbe0812a380a09e0096b0` completed **successfully**.
The pinned AOSP prebuilt printed compiler ID `15071444`,
`clang version 22.0.2`, LLD `22.0.2` and LLVM revision
`de03d430485c884861198b25459851f429cbdbad`. The test job passed
100 Python tests. The kernel release is
`4.14.357-perf-g57037290bb57`.

**Observed from the CI log:**
- New `Image` size: **48,713,752 bytes** — exactly the same size as the
  kernel extracted from the reference OTA.
- New `Image` SHA-256:
  `808acbfaa5a110466c9a020735b1664a3e1a71ac1fd56835b519a9d7e3e3e3b1`.
- Reference OTA `Image` SHA-256:
  `d0e941cde7e7cd0b0e13838dc30506c448450e8e1238c40a1da2cc9b8b7b3571`.
- The previous Clang-14 2,040-byte size mismatch is eliminated.
  **Byte-for-byte identity is still false.**
- The CI verified its own artifact `SHA256SUMS`. Independent Pi-side
  comparison against original modules and original `Image` is pending.

Artifacts uploaded:
- `hotdog-aosp22-report-40305770114`
- `hotdog-aosp22-unverified-baseline-e75e73fe9a59099f54ccbe0812a380a09e0096b0`

**No release gate has changed.** The original device's installed
partition provenance, signing-key trust, DTBO/AVB dependencies, and
bootability are still unknown. `flash_ready=false`; never flash this
raw `Image` or mix its new-build modules with the installed ROM.

## Completed Raspberry Pi reference comparison (2026-10-26)

The user downloaded the complete artifact from run `40305770114` into
`.work/baseline-aosp22-40305770114` and checked its `SHA256SUMS`.
Its `upstream-commit.txt` and `kernel.release` report the pinned
source and release.

**Original OTA `boot.img` kernel versus the Clang-22 artifact:**

| Verification | Result |
| --- | --- |
| Reference OTA Image size | 48,713,752 bytes |
| Clang-22 Image size | 48,713,752 bytes, exact size match |
| Reference OTA Image SHA-256 | `d0e941cde7e7cd0b0e13838dc30506c448450e8e1238c40a1da2cc9b8b7b3571` |
| Clang-22 Image SHA-256 | `808acbfaa5a110466c9a020735b1664a3e1a71ac1fd56835b519a9d7e3e3e3b1` |
| First different Image byte | 2076 (decimal, `0x81c`), after ARM64 header |
| Embedded reference vs Clang-22 kernel CONFIG entries | 5007/5007 identical |
| Reference WLAN `qca_cld3_wlan.ko` vs rebuilt `wlan.ko` imported symbol CRCs | 394/394 match, zero missing, zero blockers |
| Reference `gspca_main.ko` vs rebuilt `gspca_main.ko` imported symbol CRCs | 65/65 match, zero missing, zero blockers |
| `scripts/audit-module-abi.py --fail-on-unknown` | Exit 0 for both module comparisons |
| Final verdict | `abi_and_trust_not_proven`; `flash_ready=false` |

This closes the earlier **pending Pi-side module comparison**, but not the
signing, AVB/DTBO, active installed-slot evidence, firmware dependency,
unversioned export, or actual bootability gates. The raw `Image` is
not a signed / verified `boot.img`. Identical image **size** and imported
symbol-version CRCs must not be represented as binary identity or safe
kernel replacement.

### Next evidence isolation

Inspect the unchanged official and rebuilt `Image` binaries to
characterize differing-byte counts, ranges, `linux_banner` metadata,
embedded build identity, and module signer metadata. Avoid attributing all
remaining differences to the build timestamp before examining actual code
and other build-dependent data. Do not modify the source configuration or
the reference partition images in pursuit of hash equality.

## Bytewise kernel image evidence (Raspberry Pi, 2026-10-26)

The local binary scan confirmed the same length (48,713,752 bytes) but
**11,016,552 different bytes (22.6149%)** between the extracted original
OTA kernel and the AOSP Clang-22 rebuild, across 10,066 4-KiB blocks and
45 distinct one-MiB regions. The first differing byte was offset 2076.
Most differences were in MiB regions 25–34, where some regions had
nearly every byte differ.

The original kernel build banner:
`build-user@build-host`, `Wed Oct 21 11:17:11 MSK 2026`.
Clang-22 rebuild banner:
`op7t-kernel@buildhost`, `Mon Oct 19 16:51:17 UTC 2026`.
Both banners identify **the same Android Clang 22.0.2 / LLD 22.0.2
prebuilt revision**. However the actual embedded `IKCFG_ST` starts at
offset 35,122,456 in the reference versus 35,065,112 in the rebuild,
a displacement of 57,344 bytes.

**Interpretation caution:** The 22.6149% byte difference is not an
estimate of the percentage of machine instructions changed. The images
may have relocated blocks; a position-by-position comparison reports
those bytes as different even when the content is identical elsewhere.
Conversely the same file size and matching symbol CRCs are not proof of
instruction equivalence. The next offline test should search for
shifted identical byte blocks around key regions before attributing
the divergence to timestamps, signing, linking or compile flags.

No signing or boot safety gate is relaxed. `flash_ready=false`.

## Relocation-anchor sampling (Raspberry Pi, 2026-10-26)

A read-only 128-byte anchor probe with 256-KiB stride and a ±256-KiB
local search window against the rebuilt Clang-22 `Image` found:

| Original Image region | Unique anchors at same position | Unique moved anchors | Not found | Ambiguous |
| --- | ---: | ---: | ---: | ---: |
| 0–8 MiB | 19 | 0 | 13 | 0 |
| 8–16 MiB | 21 | 0 | 11 | 0 |
| 16–24 MiB | 16 | 0 | 15 | 1 |
| 24–32 MiB | 1 | 4 | 23 | 0 |
| 32–40 MiB | 1 | 9 | 10 | 1 |
| 40–48 MiB (last partial region) | 6 | 0 | 5 | 0 |

Examples of negative shifts in the 24–40 MiB interval include
−11,776, −11,280, −17,023, −22,307, −29,697, −33,018,
−37,897, −49,961, −55,637, and −57,216 bytes.
The −57,216-byte shift was observed for four different anchors.
The `IKCFG_ST` header independently shifted by −57,344 bytes.
These are **not identical offsets** and cannot be conflated.

**Assessment:** At least some content in the middle of the raw Image
appears to be relocated, while several sampled byte sequences in the
first 24 MiB and after 40 MiB remain at their original positions.
There is no uniform global file shift. The probe is *sparse and
bounded*; a missing 128-byte anchor may reflect changes in its content
or a shift outside the ±256-KiB window, not necessarily different code.
The 22.6149% byte mismatch is not a claim that this percentage of
machine instructions differs.

Next isolate the embedded `IKCFG_ST` gzip member (position, compressed
length, decompressed exact-byte hash, gzip-header mtime), then locate
the unchanged compressed member after relocation. Compare build banner
separately from compile/layout differences; avoid assuming that the
two different generated module-signing certificates are trusted by
the actual device. No flashing, repacking, or new build required.

`flash_ready=false`.

## Embedded IKCONFIG gzip analysis (Raspberry Pi, 2026-10-26)

The user inspected the bounded `IKCFG_ST` ... `IKCFG_ED`
section in the verified reference OTA kernel and the CI AOSP Clang-22
kernel.

| Property | Original reference OTA | Rebuilt AOSP Clang 22 |
| --- | ---: | ---: |
| IKCONFIG start | 35,122,456 | 35,065,112 |
| IKCONFIG end (exclusive) | 35,158,937 | 35,101,676 |
| gzip member length | 36,465 | 36,548 |
| decompressed byte length | 163,567 | 163,567 |
| gzip header mtime | 0 | 0 |
| uncompressed SHA-256 | `9dcf7bdd77569401c448ac7b23425350693d217be96744cbb70da8a7dff50b86` | same |
| compressed SHA-256 | `d1f73a41111879f15541904ca51bb049aec5eec1f17caa7f480c7cecb58eb151` | `dc334c19cf550b56fe44e9586fae5c565b387427295b1fc640ba18141e325ed1` |

The CI `kernel.config` is also byte-identical to the decompressed
embedded CI config, and the uncompressed reference OTA and CI config
blobs are **exactly byte-identical**, not just equivalent on 5007
configuration keys.

The IKCONFIG start displacement is −57,344 bytes, while the end
displacement is −57,261 bytes due to the rebuilt gzip stream being 83
bytes larger. Do not attribute the 57,344-byte layout displacement to
the 83-byte gzip size change, and do not infer code equivalence from
identical configuration.

The source at kernel commit
`57037290bb57caefd3c337db3511fca5751fb4ef`
generates `kernel/config_data.gz` via the Makefile gzip recipe in
`scripts/Makefile.lib`: `gzip -n -f -9`. Both members have mtime 0.
The next offline investigation compares member gzip headers/trailers,
the raw DEFLATE payload and a local `gzip -n -9` recompression,
**without** rewriting the original OTA, altering toolchains or
changing kernel configuration.

The two Images are not byte-identical. `flash_ready=false`.

## Exact IKCONFIG GZIP decomposition (Raspberry Pi, 2026-10-26)

Both embedded IKCONFIG gzip streams have identical 10-byte headers
(`1f8b0800000000000203`), `mtime=0`, `XFL=2`,
`OS=3`. Their 8-byte trailers are also byte-identical,
meaning the CRC32 and ISIZE of the decoded content agree.
The sole difference inside the gzip streams is the compressed
**DEFLATE payload**:

- Original reference OTA: 36,465 bytes;
  SHA-256 `d1f73a41111879f15541904ca51bb049aec5eec1f17caa7f480c7cecb58eb151`.
- New CI Clang-22 build: 36,548 bytes;
  SHA-256 `dc334c19cf550b56fe44e9586fae5c565b387427295b1fc640ba18141e325ed1`.
- Decompressed configuration from both: 163,567 bytes,
  SHA-256 `9dcf7bdd77569401c448ac7b23425350693d217be96744cbb70da8a7dff50b86`.
- Locally running GNU gzip **1.13** with `gzip -n -f -9` on
  that exact 163,567-byte config reproduces the **entire rebuilt CI
  gzip stream byte-for-byte**, not the original reference stream.

This identifies the local gzip 1.13 output as an exact match to the CI
gzip payload. It **does not prove that CI itself used gzip 1.13**;
different compressor versions may produce identical bytes. The
reference OTA's compressor implementation/version remains unproven.
The 83-byte difference in gzip member length alone cannot account for
the 57,344-byte IKCONFIG section displacement in the overall kernel.

Suggested next step: test candidate GNU gzip versions in isolated
**compression-only** probes and compare the entire member SHA-256.
Do not modify the official kernel sources or try to force matching
kernel hash by replacing signed or embedded bytes. The original
installed-device trust and flash gates remain unverified;
`flash_ready=false`.

## Clang-22 System.map section boundaries (Raspberry Pi, 2026-10-26)

The user read the rebuilt kernel's `System.map` relative to `_text`:

| Symbol | Offset | Approximate MiB |
| --- | ---: | ---: |
| `_stext` | 2,048 | 0.002 |
| `_etext` / `__start_rodata` | 26,738,688 | 25.500 |
| `__end_rodata` | 38,883,328 | 37.082 |
| `__init_begin` | 39,321,600 | 37.500 |
| `__init_end` / `_sdata` | 45,613,056 | 43.500 |
| `_edata` / `__bss_start` | 48,715,776 | 46.459 |
| `__bss_stop` | 56,573,496 | 53.953 |
| `_end` | 56,598,528 | 53.977 |

The byte-mismatch hotspot in the **26–34 MiB** window is therefore
primarily within the rebuilt kernel's **read-only data**, rather than
predominantly within its `.text`. Numerous `__func__.*.llvm.*`
symbols around 32.7 MiB are further evidence of compiler-generated
read-only constants / metadata. A shifted member in the read-only
region is a plausible contributor to bytewise differences, not proof
of code identity or runtime compatibility.

Important bounds: the raw ARM64 `Image` has only **48,713,752**
bytes, whereas `_edata` maps to offset **48,715,776**, 2,024 bytes
past the end of the file. Do **not** assume every virtual
`System.map` address is an accessible raw `Image` byte. Clip any
sectionwise comparison to available file bytes, and treat BSS and
symbol-to-file-address mapping separately.

The next offline diagnostic should compute per-section differing-byte
counts and check relocated, high-entropy read-only anchors within
those mapped, bounded file regions; no further kernel compile is
required to gather this evidence. `flash_ready=false`.
