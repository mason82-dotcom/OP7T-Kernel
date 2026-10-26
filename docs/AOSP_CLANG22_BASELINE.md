# Experimental crDroid 13 / hotdog baseline with Android Clang 22

## Scope and preservation

This **experimental, non-flashable** comparison is based on
`experiment/hotdog-rom-release-source-pin`, not the default branch.
It builds the untouched crDroid 13 / Android 17 kernel (no NetHunter or
KernelSU patch) at `57037290bb57caefd3c337db3511fca5751fb4ef`.

Workflow: `.github/workflows/hotdog-aosp-clang22-baseline.yml`.
It runs on pushes to `experiment/hotdog-aosp-clang-r596125` and by
manual dispatch on that branch. It is separate from the Clang-14
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
