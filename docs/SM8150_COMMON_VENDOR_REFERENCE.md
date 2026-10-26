# OnePlus SM8150 common proprietary vendor reference (crDroid 13 / Android 17)

## Exact public repository and verified source tip

The official crDroid
[`android_device_oneplus_sm8150-common` `17.0` dependency list](https://github.com/crdroidandroid/android_device_oneplus_sm8150-common/blob/17.0/crdroid.dependencies)
requests `crdroidandroid/proprietary_vendor_oneplus_sm8150-common`
under `vendor/oneplus/sm8150-common`; it does **not** specify a
remote or a branch in that dependency entry.

Unlike the **hotdog-specific proprietary source** supplied from
GitLab, the **sm8150-common vendor source is public on GitHub**:

- Repo: `https://github.com/crdroidandroid/proprietary_vendor_oneplus_sm8150-common`
- Verified branch: **`17.0`** (also current GitHub default branch).
- Branch tip observed on 2026-10-26: **`6586000353465cc53b42189be056d5c037e14ef9`**.
- [Pinned source tree](https://github.com/crdroidandroid/proprietary_vendor_oneplus_sm8150-common/tree/6586000353465cc53b42189be056d5c037e14ef9).
- GitHub's recursive tree for that revision returned **`truncated=false`**, **1,102 tree entries** (of which **1,000 Git blobs**, totaling **524,843,573 bytes** according to the Git tree).
- `Android.bp` has **480,900 bytes** and includes approximately **679 top-level-looking module `name:` entries** (lexical count; not a validated Soong model).
- `sm8150-common-vendor.mk` has **57,495 bytes**; `BoardConfigVendor.mk` **50 bytes**.

Source-only pin and Git blob content hashes:
[`config/sm8150-common-vendor-reference.json`](../config/sm8150-common-vendor-reference.json).

**Version distinction:** The GitHub tree SHA is directly observed
and now pinned. It is **not proof** that this specific revision
generated the official 2026-10-21 OTA or matches currently installed
vendor partitions. The full proprietary source tree, device image,
signatures and executable payloads have **not** been copied into this
project or validated against the phone.

## Confirmed cross-tree audio dependency

The official
[`hotdog` extraction script](https://github.com/crdroidandroid/android_device_oneplus_hotdog/blob/17.0/extract-files.py)
imports `vendor/oneplus/sm8150-common` and performs a targeted
`DT_NEEDED` string fixup on the hotdog ODM
`odm/lib/hw/audio.primary.msmnile.so`: redirecting
`/vendor/lib/liba2dpoffload.so` to
`/odm/lib/liba2dpoffload.so`.

The pinned common vendor source's
[`Android.bp`](https://github.com/crdroidandroid/proprietary_vendor_oneplus_sm8150-common/blob/6586000353465cc53b42189be056d5c037e14ef9/Android.bp)
contains a **`cc_prebuilt_library_shared`** candidate:

| Property | Source observation |
| --- | --- |
| Module name | `liba2dpoffload_odm` |
| `stem` | `liba2dpoffload` |
| `srcs`, `android_arm` | `proprietary/odm/lib/liba2dpoffload.so` |
| `compile_multilib` | `"32"` |
| `device_specific` | `true` |
| `prefer` | `true` |

The pinned `sm8150-common-vendor.mk` explicitly lists
`liba2dpoffload_odm` among `PRODUCT_PACKAGES`.
This is a concrete source-level **cross-tree alignment** for the
hotdog audio HAL, not proof that a particular archived vendor
ELF already has that fixup applied, that Android's shared-library
dependency graph resolves, or that the installed device uses the
exact same blob.

The common `Android.bp` also declares namespace imports for
several distinct device/QCOM/OPLUS trees. Full Soong dependency
resolution is not yet proven, and its namespace references do not
mean those additional projects have been cloned.

The device common
[`common.mk`](https://github.com/crdroidandroid/android_device_oneplus_sm8150-common/blob/17.0/common.mk)
inherits `vendor/oneplus/sm8150-common/sm8150-common-vendor.mk`.

## Read-only source-only checkout on Raspberry Pi

To inspect only the three **public build-definition text files**
without downloading or storing any proprietary binary payloads:

```bash
(
  set -euo pipefail
  cd ~/Projekte/OP7T-Kernel-KSU-Review
  DIR="$PWD/.work/vendor-sm8150-common-17"
  mkdir -p "$DIR"

  SHA=6586000353465cc53b42189be056d5c037e14ef9
  RAW="https://raw.githubusercontent.com/crdroidandroid/proprietary_vendor_oneplus_sm8150-common/$SHA"

  for name in Android.bp sm8150-common-vendor.mk BoardConfigVendor.mk; do
    curl --fail --location --retry 2 --connect-timeout 20 \
      --output "$DIR/$name.partial" "$RAW/$name"
    mv "$DIR/$name.partial" "$DIR/$name"
  done

  # Git blob SHA-1 hashes are content-addressed checks against the
  # exact previously inspected commit. This checks the files downloaded
  # by curl, not provenance or authenticity of the entire ROM.
  test "$(git hash-object "$DIR/Android.bp")" = \
    b0405bf3d952d9e077955efb224a64262629471f
  test "$(git hash-object "$DIR/sm8150-common-vendor.mk")" = \
    f0f7837677547dfa7795a2555b0e3c02a0c0ad78
  test "$(git hash-object "$DIR/BoardConfigVendor.mk")" = \
    18ed0ae744b9de7e8c7f1b178416ab59ffa14791

  echo "COMMON_VENDOR_TEXT_PIN_OK"
  printf 'Expected audio package:\n'
  grep -n -F 'liba2dpoffload_odm' \
    "$DIR/Android.bp" "$DIR/sm8150-common-vendor.mk"
)
```

This does not read the phone and does not download the common
vendor's `proprietary/` contents. Do not recursively clone the
vendor repository just to verify three text files.

## Outstanding safety and completeness gates

- Independently establish the **2026-10-21 OTA's exact common vendor
  revision**, if documented; current branch tip is not necessarily
  historical release state.
- Verify the hotdog library's **actual archive ELF DT_NEEDED** fields
  with controlled read-only parsing if necessary, and check linked
  common vendor blobs from a trusted matching source. No dynamic
  loading or ELF modifications.
- Audit common `Android.bp` source rules and namespace imports
  without pretending a successful Soong build.
- Audit actual original `vendor_dlkm` module identity, signer trust,
  ABI and installed A/B slot independently. Lack of `.ko` in the
  hotdog-specific archive does not imply no kernel modules elsewhere.
- Never copy common or hotdog proprietary binary payloads into the
  public `mason82-dotcom/OP7T-Kernel` repository; do not flash radio
  images or alter AVB, SELinux or signature enforcement.

**`flash_ready=false`.**
