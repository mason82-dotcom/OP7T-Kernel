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

## Raspberry Pi: successful pinned text download (2026-10-26)

The user successfully downloaded all three common-vendor **build
text files** using the pinned GitHub commit SHA and verified their
exact Git blob hashes against
[`config/sm8150-common-vendor-reference.json`](../config/sm8150-common-vendor-reference.json):

- `Android.bp`: `b0405bf3d952d9e077955efb224a64262629471f`
- `sm8150-common-vendor.mk`: `f0f7837677547dfa7795a2555b0e3c02a0c0ad78`
- `BoardConfigVendor.mk`: `18ed0ae744b9de7e8c7f1b178416ab59ffa14791`

Pi output was **`COMMON_VENDOR_TEXT_PIN_OK`**, followed by source
observations `Android.bp:16175` and
`sm8150-common-vendor.mk:769` for
`liba2dpoffload_odm`. No common-vendor proprietary
`proprietary/` files were downloaded in this operation.

### Read-only hotdog/common ODM audio cross-tree check

The next, standalone
[`scripts/audit-hotdog-common-audio.py`](../scripts/audit-hotdog-common-audio.py)
audit connects the archived **hotdog** audio `cc_prebuilt_library_shared`
module metadata with the **common** `liba2dpoffload_odm`
module and `PRODUCT_PACKAGES` entry. It rejects common build
text files that do not match their pinned Git hashes and optionally
compares the hotdog ZIP against the user-observed SHA-256. It checks
filenames and expected lexical properties only, never reads or
executes proprietary ELF bytes.

```bash
(
  set -euo pipefail
  cd ~/Projekte/OP7T-Kernel-KSU-Review

  BRANCH=experiment/hotdog-aosp-clang-r596125
  REF="refs/remotes/origin/${BRANCH}"
  HOTDOG="$PWD/.work/vendor-hotdog-17"
  COMMON="$PWD/.work/vendor-sm8150-common-17"

  git fetch origin "+refs/heads/${BRANCH}:${REF}"

  git show "${REF}:scripts/audit-hotdog-common-audio.py" \
    > "$COMMON/audit-audio.py.partial"
  mv "$COMMON/audit-audio.py.partial" "$COMMON/audit-audio.py"

  git show "${REF}:config/sm8150-common-vendor-reference.json" \
    > "$COMMON/source-reference.json.partial"
  mv "$COMMON/source-reference.json.partial" "$COMMON/source-reference.json"

  python3 "$COMMON/audit-audio.py" \
    --hotdog-zip "$HOTDOG/proprietary_vendor_oneplus_hotdog-17.0.zip" \
    --common-dir "$COMMON" \
    --reference "$COMMON/source-reference.json" \
    --expect-hotdog-sha256 c038a3ccab574795c496d043f4d735b920dbbbab279232229a80c94aa32a0078 \
    | tee "$COMMON/audio-cross-tree-audit.json"
)
```

The audit reports `checks` and
`STATIC_AUDIO_SOURCE_CHAIN_ALIGNS` only if the pinned text inputs,
hotdog ZIP hash, module names, expected 32-bit/audio install
properties, module package references and literal hotdog ZIP source
filename all meet the exact assertions.

**Interpretation constraint:** The common vendor module's `srcs`
is checked as a literal source *declaration*, not as a downloaded
common-vendor ELF file. The new `liba2dpoffload` binary is not
present in this text-only workspace, so its actual content, fixup
and `DT_NEEDED` linkage remain explicitly unverified. The
standalone kernel build is unchanged. `flash_ready=false`.

## Pi-side cross-tree audio chain: 15/15 verified (2026-10-26)

The user ran `scripts/audit-hotdog-common-audio.py` with the
existing hotdog ZIP and exact common-vendor build text revision
`6586000353465cc53b42189be056d5c037e14ef9`.

| Check category | User-confirmed result |
| --- | --- |
| Pinned common build file Git blob hash checks | Passed |
| Hotdog ZIP SHA256 matching prior local archive fingerprint | Passed |
| Hotdog audio module uniquely defined / package listed | Passed |
| Hotdog 32-bit, ODM device-specific, `hw` install path, output stem | Passed |
| Hotdog audio source path in ZIP and Soong `srcs` | Passed |
| Common audio module uniquely defined / package listed | Passed |
| Common 32-bit, device-specific, output stem, source declaration | Passed |
| Individual static assertions | **15 / 15** |
| `status` | **`STATIC_AUDIO_SOURCE_CHAIN_ALIGNS`** |
| `common_vendor_blob_file_existence_verified` | `false` |
| `elf_dt_needed_verified` | `false` |
| `cross_tree_soong_resolution_verified` | `false` |
| `installed_rom_compatibility_verified` | `false` |
| `flash_ready` | **`false`** |

The verified *source-code* declaration of the device extraction
fixup redirects the hotdog Audio HAL's `DT_NEEDED` entry from
`/vendor/lib/liba2dpoffload.so` to
`/odm/lib/liba2dpoffload.so`. The audit did **not** inspect actual
ELF dynamic tags. Never infer that the fixup is present on disk
merely because Android.bp and Make names align.

Next verify the existing hotdog ZIP's one audio ELF dynamic table
**read-only and without extracting it**, using a bounded,
data-only ELF metadata parser. No common proprietary binaries have
been downloaded, and ROM/Kernel runtime compatibility is still unknown.

### Direct ELF32 `DT_NEEDED` evidence — pending real ZIP probe

The new
[`scripts/audit-hotdog-audio-elf.py`](../scripts/audit-hotdog-audio-elf.py)
reads only **one selected** existing ZIP member
`proprietary/odm/lib/hw/audio.primary.msmnile.so` into bounded
memory, never writes or executes it. It validates the 32-bit ARM ELF
header and parses program-header `PT_DYNAMIC` entries for
`DT_STRTAB`, `DT_STRSZ`, `DT_NEEDED` and optional `DT_SONAME`.
It verifies the user's archived ZIP's SHA-256 before any content read,
if supplied.

Possible results:
- `EXPECTED_ODM_NEEDED_PATH_PRESENT`: `/odm/lib/liba2dpoffload.so`
  appears in dynamic dependencies without the legacy `/vendor/lib/`
  path.
- `LEGACY_VENDOR_NEEDED_PATH_PRESENT`: only the original
  `/vendor/lib/liba2dpoffload.so` is present; repository-level fixup
  is **not shown applied** to this ZIP member.
- `BOTH_LEGACY_AND_ODM_NEEDED_PATHS` or
  `EXPECTED_FULLPATH_NEEDED_NOT_OBSERVED`: ambiguous or
  different actual dependency names. Do not guess the result.

Run on Raspberry Pi, without downloading or unpacking the ELF:

```bash
(
  set -euo pipefail
  cd ~/Projekte/OP7T-Kernel-KSU-Review

  BRANCH=experiment/hotdog-aosp-clang-r596125
  REF="refs/remotes/origin/${BRANCH}"
  DIR="$PWD/.work/vendor-hotdog-17"

  git fetch origin "+refs/heads/${BRANCH}:${REF}"
  git show "${REF}:scripts/audit-hotdog-audio-elf.py" \
    > "$DIR/audit-audio-elf.py.partial"
  mv "$DIR/audit-audio-elf.py.partial" "$DIR/audit-audio-elf.py"

  python3 "$DIR/audit-audio-elf.py" \
    "$DIR/proprietary_vendor_oneplus_hotdog-17.0.zip" \
    --expect-archive-sha256 c038a3ccab574795c496d043f4d735b920dbbbab279232229a80c94aa32a0078 \
    | tee "$DIR/audio-elf-dynamic-audit.json"
)
```

The `elf_sha256` describes the ELF bytes observed in the ZIP, not a
trusted signature; the list of required libraries is not proof that
they can all be resolved at runtime. This narrow metadata read does
**not** touch common-vendor proprietary ELF contents, install
anything, disable verification or change the kernel. **`flash_ready=false`.**

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
