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
