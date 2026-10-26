# crDroid 13 / Android 17 proprietary hotdog vendor reference

## Upstream dependency

The [official hotdog device dependency list](https://github.com/crdroidandroid/android_device_oneplus_hotdog/blob/17.0/crdroid.dependencies)
specifies:

- `crdroidandroid/proprietary_vendor_oneplus_hotdog`
- remote: **`crdroid-gitlab`**
- branch: **`17.0`**
- full-ROM target path: **`vendor/oneplus/hotdog`**

Upstream GitLab source:
`https://gitlab.com/crdroidandroid/proprietary_vendor_oneplus_hotdog`

User-provided ZIP archive endpoint:
`https://gitlab.com/crdroidandroid/proprietary_vendor_oneplus_hotdog/-/archive/17.0/proprietary_vendor_oneplus_hotdog-17.0.zip?ref_type=heads`

This path is the **device-specific vendor tree**, not the
`crdroidandroid/proprietary_vendor_oneplus_sm8150-common` dependency
used by the common chipset tree. They are distinct sources.
The [hotdog BoardConfig](https://github.com/crdroidandroid/android_device_oneplus_hotdog/blob/17.0/BoardConfig.mk)
uses `include vendor/oneplus/hotdog/BoardConfigVendor.mk`, and
[device.mk](https://github.com/crdroidandroid/android_device_oneplus_hotdog/blob/17.0/device.mk)
inherits `vendor/oneplus/hotdog/hotdog-vendor.mk`.

**Purpose:** optional evidence of the ROM's proprietary vendor inputs.
It is not a patch series for the standalone kernel and does not make
the CI kernel match the exact installed ROM. Do not copy or commit
proprietary blobs to this public repository.

### Source provenance limitation

The branch `17.0` is moving. Its user-provided ZIP URL does not pin a
specific Git commit and has **not** been accessible for download from
this assistant's runtime. Therefore there is **no verified archive
contents, archive hash, source commit, license grant, vendor module
identity or installed-device match** at this point.

GitLab's own documentation warns that generated archive file SHA-256
checksums may change for the same repository content. An archive SHA
proves byte integrity against a separately known hash, not Git commit
identity. For source pinning, record and independently verify a full
40-character commit SHA (and a signed tag or commit signature when
available) and retrieve that specific revision for the *full ROM*
workspace. Do not confuse vendor source tree revisions with kernel
source SHA `57037290bb57caefd3c337db3511fca5751fb4ef`.

Reference-only metadata: [`config/hotdog-vendor-reference.json`](../config/hotdog-vendor-reference.json).
The `source_commit_sha` remains `null` until independently verified.

## Raspberry Pi: download and inspect without extracting

The commands below create files **only inside ignored `.work`** and
are separate from all kernel builds. The URL is supplied directly by
the user; download success cannot be asserted in advance.

```bash
(
  set -euo pipefail
  cd ~/Projekte/OP7T-Kernel-KSU-Review

  BRANCH=experiment/hotdog-aosp-clang-r596125
  git fetch origin "+refs/heads/${BRANCH}:refs/remotes/origin/${BRANCH}"
  REF="refs/remotes/origin/${BRANCH}"
  git cat-file -e "${REF}^{commit}"

  DIR="$PWD/.work/vendor-hotdog-17"
  mkdir -p "$DIR"

  # Write temp files first. A failing git show must never leave empty tools.
  git show "${REF}:scripts/inspect-hotdog-vendor-zip.py" \
    > "$DIR/inspect-hotdog-vendor-zip.py.partial"
  mv "$DIR/inspect-hotdog-vendor-zip.py.partial" \
     "$DIR/inspect-hotdog-vendor-zip.py"
  git show "${REF}:config/hotdog-vendor-reference.json" \
    > "$DIR/hotdog-vendor-reference.json.partial"
  mv "$DIR/hotdog-vendor-reference.json.partial" \
     "$DIR/hotdog-vendor-reference.json"

  ARCHIVE="$DIR/proprietary_vendor_oneplus_hotdog-17.0.zip"
  URL='https://gitlab.com/crdroidandroid/proprietary_vendor_oneplus_hotdog/-/archive/17.0/proprietary_vendor_oneplus_hotdog-17.0.zip?ref_type=heads'

  if test ! -s "$ARCHIVE"; then
    curl --fail --location --retry 2 --connect-timeout 20 \
      --output "$ARCHIVE.partial" "$URL"
    mv "$ARCHIVE.partial" "$ARCHIVE"
  else
    echo "Reuse existing ZIP: $ARCHIVE"
  fi

  python3 "$DIR/inspect-hotdog-vendor-zip.py" \
    --reference "$DIR/hotdog-vendor-reference.json" \
    "$ARCHIVE" | tee "$DIR/inventory.json"
)
```

If a trusted SHA-256 for the **exact ZIP bytes** is known, supply
`--expect-sha256 64hexcharacters` to the inspector. Otherwise it still
calculates the local archive's SHA-256 but correctly sets
`expected_sha256_verified=false`.

The inspector:
- **never extracts or loads** proprietary binaries;
- checks names for traversal, duplicate members and suspicious wrapper;
- bounds member counts, member sizes and total reported size;
- identifies `BoardConfigVendor.mk`, `hotdog-vendor.mk`,
  module name samples and aggregate file groups;
- rejects missing expected makefiles with nonzero status; and
- always returns `flash_ready=false`, and never declares the
  GitLab source revision, signatures or installed-ROM identity verified.

This is **ZIP-directory inventory only**; it does not decompress and
cryptographically verify every contained blob. The file list could
include Git LFS pointers or other missing payloads, and link targets
must not be followed automatically.


## Verified Pi-side metadata inventory — 2026-10-26

The user reported a successful download and local run of
`scripts/inspect-hotdog-vendor-zip.py`. The earlier `git fetch`
problem was repaired with an explicit remote-tracking refspec.

| Local ZIP metadata | Observed value |
| --- | --- |
| ZIP name | `proprietary_vendor_oneplus_hotdog-17.0.zip` |
| ZIP byte length | `114977497` |
| Local ZIP SHA-256 | `c038a3ccab574795c496d043f4d735b920dbbbab279232229a80c94aa32a0078` |
| GitLab root | `proprietary_vendor_oneplus_hotdog-17.0` |
| Total ZIP file entries | **788** |
| Sum of declared uncompressed file sizes | **463065937 bytes** |
| `proprietary/` entries | **764** |
| `radio/` entries | **19** |
| Repository-root files | **5** |
| Symlinks detected via ZIP Unix metadata | **0** |
| `.ko` filenames found | **0** |
| `BoardConfigVendor.mk` | Present |
| `hotdog-vendor.mk` | Present |
| Inspector status | `VENDOR_ZIP_METADATA_ONLY` |

This **user-observed local file digest** identifies that snapshot and
does not authenticate the source against a trusted upstream signed
commit, nor independently verify every compressed blob's CRC/data.
The source commit, matching `sm8150-common` vendor snapshot and
installed-partition identities are still unverified. No `.ko`
in this **hotdog-specific** ZIP does not imply `sm8150-common`,
`vendor_dlkm` or the shipped ROM contains no kernel modules.
Those module audits remain separately grounded in the reference OTA.

The next offline audit should inspect only `BoardConfigVendor.mk`
and `hotdog-vendor.mk` as bounded text directly from this ZIP to
identify included Android makefiles, package lists, copy rules and
dependencies; do not extract or execute the vendor tree.
**`flash_ready=false`.**


### Targeted vendor Makefile analysis (no unpacking)

After completing the ZIP directory inventory, fetch the **read-only,
bounded Makefile** inspector into the ignored local workspace and
inspect only the two build-definition text members:

```bash
(
  set -euo pipefail
  cd ~/Projekte/OP7T-Kernel-KSU-Review
  BRANCH=experiment/hotdog-aosp-clang-r596125
  REF="refs/remotes/origin/$BRANCH"
  git fetch origin "+refs/heads/${BRANCH}:${REF}"
  DIR="$PWD/.work/vendor-hotdog-17"
  mkdir -p "$DIR"
  git show "${REF}:scripts/inspect-hotdog-vendor-makefiles.py" \
    > "$DIR/inspect-makefiles.py.partial"
  mv "$DIR/inspect-makefiles.py.partial" "$DIR/inspect-makefiles.py"

  python3 "$DIR/inspect-makefiles.py" \
    "$DIR/proprietary_vendor_oneplus_hotdog-17.0.zip" \
    | tee "$DIR/makefiles-audit.json"
)
```

The audit validates the ZIP wrapper and paths, checks that
`BoardConfigVendor.mk` and `hotdog-vendor.mk` each exist exactly
once, reads no more than **512 KiB** from either, rejects binary data
and symlink entries, and reports at most **70 selected directive
lines per file**. The complete vendor tree is **never extracted,
interpreted as executable code, built or published**. The resulting
log represents selected *textual* Makefile observations, not
expanded Android Make dependencies and not a full firmware
compatibility analysis. Missing `.ko` in this archive does not
exclude modules in the distinct common vendor tree or in OTA
`vendor_dlkm`.


### Verify PRODUCT_COPY_FILES sources against the downloaded ZIP

The 2026-10-26 local Makefile read returned:
- BoardConfigVendor.mk: **319 bytes**, **24 lines**, and **zero lines**
  matching the previous heuristic filter. This does **not** prove
  the file is empty or has no active instructions; the dedicated
  copyfile audit now prints up to 40 active (non-comment) lines.
- hotdog-vendor.mk: **116,834 bytes**, **774 lines**, **761 heuristic
  matching lines**; previous 70-line sample showed
  `PRODUCT_COPY_FILES` referencing ODM ACDB, sensors, Wi-Fi config,
  camera calibration and firmware. The 761 matched physical lines
  are **not** 761 independently checked source-to-destination rules.

Use the new **static, read-only** cross-check to count literal
`PRODUCT_COPY_FILES` mappings, test their source filenames against
the ZIP directory, identify duplicate destination strings, and
distinguish Make-generated/dynamic references from missing files.

```bash
(
  set -euo pipefail
  cd ~/Projekte/OP7T-Kernel-KSU-Review
  BRANCH="experiment/hotdog-aosp-clang-r596125"
  REF="refs/remotes/origin/${BRANCH}"
  git fetch origin "+refs/heads/${BRANCH}:${REF}"
  DIR="$PWD/.work/vendor-hotdog-17"
  mkdir -p "$DIR"
  git show "${REF}:scripts/audit-hotdog-vendor-copyfiles.py" \
    > "$DIR/audit-copyfiles.py.partial"
  mv "$DIR/audit-copyfiles.py.partial" "$DIR/audit-copyfiles.py"

  python3 "$DIR/audit-copyfiles.py" \
    "$DIR/proprietary_vendor_oneplus_hotdog-17.0.zip" \
    | tee "$DIR/copyfiles-audit.json"
)
```

Interpretation:
- `local_source_rules_found_in_zip`: number of *literal*
  `vendor/oneplus/hotdog/...` source references whose relative ZIP
  names exist. Membership does **not** verify contents.
- `local_source_rules_missing_in_zip`: unresolved literal paths
  *within this hotdog-specific ZIP*, not necessarily absent from all
  Android build trees.
- `duplicate_destination_count`: identical destination *text
  strings*, not expanded / normalized Android partition paths.
- `nonliteral_or_unparsed_rule_count`: dynamic Make expressions or
  syntax the static parser deliberately does not evaluate.
- `zip_proprietary_and_radio_files_not_in_literal_copy_rules`: may
  be legitimate firmware/radio resources handled elsewhere.
- `boardconfig_active_lines`: textual non-comment observations,
  **never evaluated as build commands**.

The auditor does not extract or execute blobs, evaluate Make variables,
verify compressed member CRCs, infer proprietary licenses or attest
the ROM running on a device. Treat its status as a *limited build
manifest audit*, never a kernel-ABI or bootability verdict.
`flash_ready=false`.


## Completed static copyfile inventory (Raspberry Pi, 2026-10-26)

User's locally downloaded archive `proprietary_vendor_oneplus_hotdog-17.0.zip`
at 114,977,497 bytes, SHA-256
`c038a3ccab574795c496d043f4d735b920dbbbab279232229a80c94aa32a0078`,
was successfully processed with `scripts/audit-hotdog-vendor-copyfiles.py`.

| Static ZIP/Makefile observation | User-confirmed result |
| --- | ---: |
| `PRODUCT_COPY_FILES` literal entries | **759** |
| Local-source paths found among ZIP filenames | **759** |
| Local-source paths absent | **0** |
| Duplicate destination texts | **0** |
| External sources / unparsed rules | **0 / 0** |
| Additional `PRODUCT_PACKAGES` tokens | **5** |
| ZIP proprietary/radio payload names | **783** |
| Payload filenames not in direct copy rules | **24** |
| Status | `STATIC_COPY_REFERENCES_RESOLVE` |

The five package names are `audio.primary.msmnile_odm`,
`com.qti.sensor.imx471`, `com.qti.sensor.imx481`,
`com.qti.sensor.imx586`, and `com.qti.sensor.s5k3m5`.
The 24 unreferenced ZIP names sample includes five audio/camera
shared libraries plus 19 `radio/*.img` images. The active
`BoardConfigVendor.mk` contains one `AB_OTA_PARTITIONS +=`
definition naming 19 radio-related partitions (including `LOGO`,
`abl`, `modem`, `dsp`, `xbl` and `xbl_config`).

**Evidence precision:** Zero missing *literal path names* means
the static generated copyfile manifest is internally consistent.
It does not guarantee decompressed file contents, correct
`Android.bp`/`Android.mk` module definitions, product packaging,
Radio/firmware compatibility, partition mapping, executable/runtime
behavior, signer trust or installed ROM identity. Neither the
`radio/*.img` payloads nor original `vendor_dlkm` modules are
safe to flash or replace without separate release gates.

### Additional filename-only parity fields

The static auditor also checks the `AB_OTA_PARTITIONS` token names
against `radio/<name>.img` ZIP entries **using exact filenames**,
and lists possible library files whose basenames match the
`PRODUCT_PACKAGES` entries (accepting a suffix `_odm` for candidate
matching). These checks require no binary extraction and do not
prove Android Make/Soong build module resolution.

To rerun the expanded audit using the existing ZIP and an explicit
remote-tracking ref:

```bash
(
  set -euo pipefail
  cd ~/Projekte/OP7T-Kernel-KSU-Review
  BRANCH=experiment/hotdog-aosp-clang-r596125
  REF="refs/remotes/origin/${BRANCH}"
  git fetch origin "+refs/heads/${BRANCH}:${REF}"
  DIR="$PWD/.work/vendor-hotdog-17"
  git show "${REF}:scripts/audit-hotdog-vendor-copyfiles.py" \
    > "$DIR/audit-copyfiles.py.partial"
  mv "$DIR/audit-copyfiles.py.partial" "$DIR/audit-copyfiles.py"

  python3 "$DIR/audit-copyfiles.py" \
    "$DIR/proprietary_vendor_oneplus_hotdog-17.0.zip" \
    | tee "$DIR/copyfiles-audit.json"
)
```

Check `radio_partition_filename_alignment`,
`ab_ota_partitions_without_radio_image`,
`radio_images_without_ab_ota_partition`, and
`package_library_basename_candidates`. These are static
**filename alignment** checks only; the actual 19/19 and 5/5
results must come from running the updated auditor on the
user's ZIP, not from extrapolating its earlier partial inventory.
`flash_ready=false`.

## Confirmed radio, copyfile and package filename alignment (Raspberry Pi, 2026-10-26)

The user reran the expanded static audit of the **previously downloaded**
114,977,497-byte vendor ZIP (local SHA-256
`c038a3ccab574795c496d043f4d735b920dbbbab279232229a80c94aa32a0078`).

| File/makefile alignment | Confirmed observation |
| --- | --- |
| `PRODUCT_COPY_FILES` source names resolving inside ZIP | **759/759** |
| Missing copy sources | **0** |
| Duplicate destination strings | **0** |
| Unparsed copy tokens | **0** |
| BoardConfig `AB_OTA_PARTITIONS` tokens | **19** |
| Unique corresponding `radio/<partition>.img` names | **19/19** |
| Unmatched board radio partition/image names | **0/0** |
| `PRODUCT_PACKAGES` tokens | **5** |
| Candidate shared-library basenames in ZIP | **5/5** |
| Archive `proprietary/` and `radio/` files not direct copied | **24: five candidate .so files and 19 radio images** |
| Inspector | `STATIC_COPY_REFERENCES_RESOLVE` / `STATIC_NAMES_MATCH` |
| `flash_ready` | `false` |

The 19 names are `LOGO`, `abl`, `aop`, `bluetooth`,
`cmnlib`, `cmnlib64`, `devcfg`, `dsp`, `hyp`,
`imagefv`, `keymaster`, `modem`, `multiimgoem`,
`qupfw`, `storsec`, `tz`, `uefisecapp`, `xbl`, and
`xbl_config`. These are **firmware/bootloader-sensitive** images.
Filename matching is not permission to flash or replace them.

Five exact candidate matches (filenames only):

| Product package | ZIP path candidate |
| --- | --- |
| `audio.primary.msmnile_odm` | `proprietary/odm/lib/hw/audio.primary.msmnile.so` |
| `com.qti.sensor.imx471` | `proprietary/odm/lib64/camera/com.qti.sensor.imx471.so` |
| `com.qti.sensor.imx481` | `proprietary/odm/lib64/camera/com.qti.sensor.imx481.so` |
| `com.qti.sensor.imx586` | `proprietary/odm/lib64/camera/com.qti.sensor.imx586.so` |
| `com.qti.sensor.s5k3m5` | `proprietary/odm/lib64/camera/com.qti.sensor.s5k3m5.so` |

The [official device extract-files.py](https://github.com/crdroidandroid/android_device_oneplus_hotdog/blob/17.0/extract-files.py)
declares `namespace_imports=['vendor/oneplus/sm8150-common']` and
applies an ODM audio ELF `DT_NEEDED` fixup to
`odm/lib/hw/audio.primary.msmnile.so`.
This **separate common-vendor tree** is therefore relevant to any
actual full-ROM build, alongside the `hotdog` tree. The canonical
device `Android.bp` itself contains `soong_namespace {}`.

**Outstanding checks:** verify the generated vendor
`Android.bp`/`Android.mk` definitions for the five
`PRODUCT_PACKAGES` names; the correct `sm8150-common` source
commit and its own payload; firmware identities against the actual
installed ROM; file integrity beyond ZIP directory entries; and
kernel module signer/ABI runtime compatibility. Static matches do
not imply a bit-reproducible OTA nor release-safe kernel.
`flash_ready=false`.

### Scan the generated vendor module names (additional offline gate)

The hotdog-specific ZIP's static manifest contains five
`PRODUCT_PACKAGES` tokens whose `.so` basename candidates were all
observed on the Raspberry Pi. To check whether their **module name
tokens** are also present in the generated vendor `Android.bp` or
`Android.mk`, use the read-only and bounded
[`scripts/audit-hotdog-vendor-soong-names.py`](../scripts/audit-hotdog-vendor-soong-names.py).
The script reads only `hotdog-vendor.mk`, `Android.bp` and
`Android.mk` at the ZIP root, if present; it neither unpacks the ZIP
nor evaluates Android build files.

```bash
(
  set -euo pipefail
  cd ~/Projekte/OP7T-Kernel-KSU-Review

  BRANCH=experiment/hotdog-aosp-clang-r596125
  REF="refs/remotes/origin/${BRANCH}"
  DIR="$PWD/.work/vendor-hotdog-17"

  git fetch origin "+refs/heads/${BRANCH}:${REF}"
  git show "${REF}:scripts/audit-hotdog-vendor-soong-names.py" \
    > "$DIR/audit-soong.py.partial"
  mv "$DIR/audit-soong.py.partial" "$DIR/audit-soong.py"

  python3 "$DIR/audit-soong.py" \
    "$DIR/proprietary_vendor_oneplus_hotdog-17.0.zip" \
    | tee "$DIR/soong-name-audit.json"
)
```

The report shows `product_package_name_candidates`, the presence
of top-level `Android.bp`/`Android.mk`, and the count of missing
module *name tokens*. A lexical name match is **not** proof that
the Blueprint file defines a valid module of the correct type, has
correct `srcs` or `shared_libs`, resolves dependencies, passes
Soong validation, or matches the binaries installed on the device.
Missing names may indicate generated artifacts stored elsewhere;
do not create fabricated module declarations to silence the audit.

The official
[hotdog extraction script](https://github.com/crdroidandroid/android_device_oneplus_hotdog/blob/17.0/extract-files.py)
references the distinct `vendor/oneplus/sm8150-common`
namespace and includes an audio ODM `DT_NEEDED` rewrite. Neither
is validated by this lexical check.

**No vendor firmware or module is authorized for flashing.**
`flash_ready=false`.

## Subsequent compatibility analysis (not automatic)

1. Obtain a verifiable **source revision** for the hotdog ZIP, and
   separately the `sm8150-common` vendor revision required by the ROM.
2. Review the vendor Android makefiles and proprietary dependencies,
   not their executable contents, against the official `hotdog`
   device tree. Any local extraction should go to a separate ignored
   workspace, with strict path and symlink checks.
3. Inventory any `vendor_dlkm` module references; compare actual
   module files to the **proven matching** reference OTA using metadata,
   signatures and symbol ABI, not filename coincidence.
4. Keep kernel signature enforcement, AVB, SELinux, module loading paths
   and the original OTA's A/B partition contract unchanged.

Our Clang-22 `Image` / original kernel and module audit remains
separate. The actual installed-ROM identity and module signer trust
have not been established. **`flash_ready=false`.**
