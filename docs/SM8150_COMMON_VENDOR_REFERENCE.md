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

### Real hotdog audio ELF dynamic results (Raspberry Pi, 2026-10-26)

The user ran `scripts/audit-hotdog-audio-elf.py` on the original
`proprietary_vendor_oneplus_hotdog-17.0.zip`, verifying the exact
local ZIP SHA-256
`c038a3ccab574795c496d043f4d735b920dbbbab279232229a80c94aa32a0078`
before parsing the single audio shared library in memory.

- Member: `proprietary/odm/lib/hw/audio.primary.msmnile.so`.
- Size: **810,136 bytes**; ELF SHA-256:
  `08a20a73c123c793d717f1b8e7078df1b9efb3853753fae7fac269d3a20a829f`.
- `ELFCLASS32`, little-endian, `EM_ARM`, `ET_DYN`; SONAME:
  `audio.primary.msmnile.so`.
- **24** `DT_NEEDED` entries were observed:
  `libbase.so`, `liblog.so`, `libcutils.so`, `libtinyalsa.so`,
  `libtinycompress.so`, `libaudioroute.so`, `libaudioutils.so`,
  `libexpat.so`, `libhidlbase.so`, `libprocessgroup.so`,
  `libutils.so`, `libaudio_log_utils.so`,
  `vendor.qti.hardware.audiohalext@1.0.so`,
  `android.hardware.sensors@1.0.so`, `libhardware.so`,
  `libhardware_legacy.so`, `libhidltransport.so`,
  `libhwbinder.so`, `libaudioEngineerTest.so`,
  `android.hardware.power@1.2.so`, `libc++.so`, `libc.so`,
  `libm.so` and `libdl.so`.
- Neither `/vendor/lib/liba2dpoffload.so` **nor**
  `/odm/lib/liba2dpoffload.so` occurs in the parsed `DT_NEEDED`
  array. `old_needed_present=false`, `new_needed_present=false`,
  `expected_dynamic_fixup_verified=false`.
- Status: **`EXPECTED_FULLPATH_NEEDED_NOT_OBSERVED`**.
- ELF was read directly into bounded memory from the ZIP;
  `elf_written_to_disk=false`, `elf_executed=false`.

**Technical interpretation:** The upstream `extract-files.py`
`replace_needed(old,new)` rule is *declared*, but no direct
`DT_NEEDED` dependency on either path is observable in this local
archive member. The rule may be vestigial/conditional, may have
applied to a different blob revision, or the library could be used
indirectly. **Do not claim that the fixup is missing or broken**
without additional provenance evidence, and **do not create or
patch** an ELF dependency merely to match the extraction script.

Next, read only this ELF's bounded ASCII string references and
the already downloaded common-vendor Blueprint/module list to
identify other audio dependencies (notably
`libaudioEngineerTest.so`) and potential indirect loading
hints. Raw string occurrences are not proof of dynamic loading.
Common vendor binary presence and full loader resolution remain
unverified; `flash_ready=false`.

### Direct audio dependencies with source-level common modules

The pinned common vendor `Android.bp` has independently been inspected
for actual names from the observed Audio HAL's `DT_NEEDED` list:

| Audio HAL `DT_NEEDED` | Pinned common module | `Android.bp` declared source |
| --- | --- | --- |
| `libaudioEngineerTest.so` | `libaudioEngineerTest` | `proprietary/odm/lib/libaudioEngineerTest.so` (32-bit ODM) |
| `libaudio_log_utils.so` | `libaudio_log_utils` | `proprietary/vendor/lib/libaudio_log_utils.so` (32-bit vendor) |
| `vendor.qti.hardware.audiohalext@1.0.so` | `vendor.qti.hardware.audiohalext@1.0` | `proprietary/vendor/lib/vendor.qti.hardware.audiohalext@1.0.so` (32-bit vendor) |

This gives a **more directly justified** static dependency
investigation than treating `liba2dpoffload_odm` as a proven direct
audio HAL dependency: `libaudioEngineerTest.so` is observed in the
actual ELF dynamic table and is declared by the pinned common
vendor source. These are name/source declarations only, not proof
that their binary blobs match this OTA, were installed on the device
or are resolved at runtime.

The earlier 15/15 source-chain result refers only to **source build
definitions**. It does not conflict with the absence of an A2DP
`DT_NEEDED` in the actual archived HAL.

### Real Audio HAL ASCII-string probe and narrowed A2DP hypothesis (Raspberry Pi, 2026-10-26)

The user scanned the **already SHA-verified** 810,136-byte archived
`audio.primary.msmnile.so` in memory for selected exact byte
sequences, without extracting or executing the member:

| Raw byte substring | Observed occurrences |
| --- | ---: |
| `liba2dpoffload` | **1** |
| `/odm/lib/` | **1** |
| `/vendor/lib/` | **24** |
| `dlopen` | **3** |
| `android_dlopen_ext` | **0** |
| `dlsym` | **33** |
| `libaudioEngineerTest` | **1** |

**Critical distinction:** Neither old nor new A2DP path was in the
parsed 24 `DT_NEEDED` entries, **but `liba2dpoffload` occurs
somewhere else in the ELF**. Combined with the sole `/odm/lib/`
substring this raises (but does not confirm) a possible embedded
`/odm/lib/liba2dpoffload.so` string used for `dlopen` or
other runtime logic. `dlopen`/`dlsym` substring counts can occur in
import/export symbols and do not demonstrate an actual runtime call.

To determine exact byte offsets and, where bounded and printable,
whole NUL-delimited ASCII strings, the new
[`scripts/audit-hotdog-audio-strings.py`](../scripts/audit-hotdog-audio-strings.py)
only reads the single ZIP ELF into memory and compares both
known local SHA-256 digests. It never modifies/extracts ELF binaries.

```bash
(
  set -euo pipefail
  cd ~/Projekte/OP7T-Kernel-KSU-Review
  BRANCH=experiment/hotdog-aosp-clang-r596125
  REF="refs/remotes/origin/${BRANCH}"
  DIR="$PWD/.work/vendor-hotdog-17"

  git fetch origin "+refs/heads/${BRANCH}:${REF}"
  git show "${REF}:scripts/audit-hotdog-audio-strings.py" \
    > "$DIR/audit-audio-strings.py.partial"
  mv "$DIR/audit-audio-strings.py.partial" "$DIR/audit-audio-strings.py"

  python3 "$DIR/audit-audio-strings.py" \
    "$DIR/proprietary_vendor_oneplus_hotdog-17.0.zip" \
    --expect-archive-sha256 c038a3ccab574795c496d043f4d735b920dbbbab279232229a80c94aa32a0078 \
    --expect-elf-sha256 08a20a73c123c793d717f1b8e7078df1b9efb3853753fae7fac269d3a20a829f \
    | tee "$DIR/audio-strings-audit.json"
)
```

The probe distinguishes the precise
`/odm/lib/liba2dpoffload.so` and legacy
`/vendor/lib/liba2dpoffload.so` byte patterns from
substring counts, returning bounded ASCII samples and file offsets.
It does **not** prove call sites, actual `dlopen` execution,
linker namespace compatibility, matching common-vendor ELF contents
or installed-ROM identity. **`flash_ready=false`.**

### Confirmed exact embedded A2DP ODM path (Raspberry Pi, 2026-10-26)

The user reran a bounded in-memory string scan of the exact hotdog
ZIP SHA-256 `c038a3ccab574795c496d043f4d735b920dbbbab279232229a80c94aa32a0078`
and the original 810,136-byte Audio HAL ELF SHA-256
`08a20a73c123c793d717f1b8e7078df1b9efb3853753fae7fac269d3a20a829f`.
Both checks **passed**, and no ELF was extracted, written or executed.

| ELF raw substring | Confirmed locations / interpretation |
| --- | --- |
| `/odm/lib/liba2dpoffload.so` | **Exactly one full NUL-delimited printable string** at **ELF file offset 91,471** (hex **`0x1654f`**) |
| `liba2dpoffload` | Exactly one, within the same full ODM string |
| `/vendor/lib/liba2dpoffload.so` | **0** occurrences |
| `dlopen` | 3 substrings: import-looking `dlopen` at 41,151; `%s: dlopen failed` at 122,935; `%s: failed to dlopen VNDK_FWK_LIB %s` at 184,740 |
| `dlsym` | 33 substrings; includes `dlsym` at 41,158 and several diagnostic messages |
| `/vendor/lib/` | 24 string occurrences, often referencing other sound libraries |
| `libaudioEngineerTest` | 1 substring, full string `libaudioEngineerTest.so` at file offset 65,147 |

**The ELF contains the complete expected ODM A2DP path.**
The earlier direct dependency analysis remains simultaneously valid:
**neither** the legacy vendor nor the ODM A2DP path appears in its
24 `DT_NEEDED` names. A statically embedded, NUL-terminated path
is compatible with runtime dynamic loading (e.g. `dlopen`), but
the string's presence and nearby unrelated diagnostics do **not**
prove a particular call site, execution path or whether loading
succeeds. Also, this does **not** show that an ELF `DT_NEEDED`
fixup was applied: it may have been intended for another source
revision or been conditional/no-op for this blob.

Next classify the ELF string's loadable segment, file section and
virtual address and distinguish true `dlopen`/`dlsym` undefined
dynamic symbols from plain text. This is still weaker than an ARM
code-reference or runtime loader trace.

**`flash_ready=false`**.

### ELF A2DP string segment and `dlopen` import probe

The [`audit-hotdog-elf-path-segment.py`](../scripts/audit-hotdog-elf-path-segment.py)
script checks the same ZIP and ELF against their recorded SHA-256
digests, maps the unique full NUL-delimited ODM A2DP string at ELF
file offset **91,471 (`0x1654f`)** to any file-backed `PT_LOAD`
segment and section header, and checks whether `dlopen`, `dlsym`
or `android_dlopen_ext` are **undefined `SHT_DYNSYM`
imports**. On a stripped/unavailable section table, symbol-import
status stays **unknown** instead of being reported absent.

Read-only Raspberry Pi command (no blob export or execution):

```bash
(
  set -euo pipefail
  cd ~/Projekte/OP7T-Kernel-KSU-Review
  BRANCH=experiment/hotdog-aosp-clang-r596125
  REF="refs/remotes/origin/${BRANCH}"
  DIR="$PWD/.work/vendor-hotdog-17"
  git fetch origin "+refs/heads/${BRANCH}:${REF}"
  git show "${REF}:scripts/audit-hotdog-elf-path-segment.py" \
    > "$DIR/audit-elf-segment.py.partial"
  mv "$DIR/audit-elf-segment.py.partial" "$DIR/audit-elf-segment.py"

  python3 "$DIR/audit-elf-segment.py" \
    "$DIR/proprietary_vendor_oneplus_hotdog-17.0.zip" \
    --expect-archive-sha256 c038a3ccab574795c496d043f4d735b920dbbbab279232229a80c94aa32a0078 \
    --expect-elf-sha256 08a20a73c123c793d717f1b8e7078df1b9efb3853753fae7fac269d3a20a829f \
    | tee "$DIR/audio-elf-segment-audit.json"
)
```

`path_file_offset` is the **offset within the ELF member**, not
the overall ZIP offset. `virtual_address` is the ELF **link-time**
virtual address, not a runtime ASLR address. Even a `dlopen`
import plus the A2DP string in `.rodata` would **not** establish
an actual ARM instruction reference, a `dlopen` call with the A2DP
path, or a successfully loaded common-vendor library. No firmware
is modified; `flash_ready=false`.

### ELF path mapping and imported linker symbols (Pi, 2026-10-26)

The user ran `scripts/audit-hotdog-elf-path-segment.py` on the
exact locally verified ZIP and Audio HAL ELF (both SHA-256 checks
passed). The reported A2DP string mapping and imported symbols:

| Observation | User-observed result |
| --- | --- |
| Full `/odm/lib/liba2dpoffload.so` | `0x1654f`, 91,471 bytes into the ELF |
| Section | **`.rodata`**, index **12**, file range `[80080, 218412)`, `sh_addr=80080` |
| `PT_LOAD` | file start `0`, read-only `R` |
| Link-time ELF virtual address | **`0x1654f`**, not an actual ASLR load address |
| `dlopen` | **1** `SHT_DYNSYM` symbol, **1 undefined import** |
| `dlsym` | **1** `SHT_DYNSYM` symbol, **1 undefined import** |
| `android_dlopen_ext` | **0** dynamic name matches |
| Probe status | `PATH_MAPPED_AND_DLOPEN_IMPORT_OBSERVED` |
| ELF executed / extracted | **false / false** |
| Runtime path argument or successful loading proven | **false** |
| Kernel release | `flash_ready=false` |

These observations strengthen the **dynamic A2DP loading
hypothesis**. Both the complete A2DP ODM path and the presence
of undefined `dlopen`/`dlsym` dynamic symbols are independently
present in the same ELF. Crucially they do **not** yet show any
ARM/Thumb instruction that references the path, passes it to
`dlopen`, or executes at runtime. A future read-only ARM reference
audit should carefully distinguish relocations/literal-pointer
candidates from validated instruction-level cross-references.
Do not modify the audio library to force any `DT_NEEDED` entry.

### Read-only A2DP ELF relocation and pointer candidates

The next offline tool,
[`scripts/audit-hotdog-a2dp-relocations.py`](../scripts/audit-hotdog-a2dp-relocations.py),
checks the existing ZIP and audio ELF SHA-256, then reads the
single audio ELF in bounded memory. It uses ELF32 program/section
headers to map the **complete NUL-delimited A2DP string**
`/odm/lib/liba2dpoffload.so` (previously at `0x1654f`) to a
file-backed virtual address. It then scans:

- **4-byte-aligned raw ELF words** whose little-endian value equals
  that virtual address. These are **candidate** literal pointer values,
  not confirmed usable pointers or ARM/Thumb instructions.
- `SHT_REL` and `SHT_RELA` entries whose recorded addend equals
  the same A2DP virtual address. For `SHT_REL`, the implicit addend
  is only read when the relocation slot maps unambiguously into
  file-backed `PT_LOAD` data. It reports the numeric relocation
  type and symbol index, without guessing linkage semantics.

```bash
(
  set -euo pipefail
  cd ~/Projekte/OP7T-Kernel-KSU-Review
  BRANCH=experiment/hotdog-aosp-clang-r596125
  REF="refs/remotes/origin/${BRANCH}"
  DIR="$PWD/.work/vendor-hotdog-17"

  git fetch origin "+refs/heads/${BRANCH}:${REF}"
  git show "${REF}:scripts/audit-hotdog-a2dp-relocations.py" \
    > "$DIR/audit-a2dp-relocs.py.partial"
  mv "$DIR/audit-a2dp-relocs.py.partial" "$DIR/audit-a2dp-relocs.py"

  python3 "$DIR/audit-a2dp-relocs.py" \
    "$DIR/proprietary_vendor_oneplus_hotdog-17.0.zip" \
    --expect-archive-sha256 c038a3ccab574795c496d043f4d735b920dbbbab279232229a80c94aa32a0078 \
    --expect-elf-sha256 08a20a73c123c793d717f1b8e7078df1b9efb3853753fae7fac269d3a20a829f \
    | tee "$DIR/a2dp-relocations-audit.json"
)
```

A matching relocation or 32-bit word is **not** a proven
instruction-level code reference and certainly not confirmation
that `dlopen` receives the string. Conversely, zero exact
pointer candidates cannot exclude PC-relative ARM/Thumb address
construction or indirect references. No binary data are written
or executed. Do not flash or patch the HAL; **`flash_ready=false`**.

### Real ZIP relocation result: no simple A2DP pointer candidates

The user ran `scripts/audit-hotdog-a2dp-relocations.py` against the
same verified hotdog ZIP / original ELF. Confirmed:

| ELF relocation/word observation | Result |
| --- | --- |
| `elf_file_path_offset` | **91,471**, `0x1654f` |
| `elf_path_virtual_address` | **91,471**, `0x1654f` |
| ELF section | `.rodata` |
| Relocation section observed | `.rel.plt` |
| Relocation entries examined | **944** |
| Entries with addend exactly equal to the path VA | **0** |
| Aligned raw 32-bit words equal to path VA | **0** |
| Status | **`NO_SIMPLE_A2DP_POINTER_CANDIDATES`** |
| ELF executed or extracted | **false** |

This is a **negative result for two narrow pointer representations
only**. `.rel.plt` typically relates to dynamic binding stubs,
and it is not a complete catalog of program-data address references.
ARM/Thumb PC-relative address construction, arithmetic, register
bases, GOT indirections, and branch-dependent code may still reference
the string. No claims about lack of runtime loading are justified.

### Optional in-memory ARM disassembly text hints

[`scripts/audit-hotdog-a2dp-llvm-objdump.py`](../scripts/audit-hotdog-a2dp-llvm-objdump.py)
checks both original SHA-256s, feeds only the bounded Audio HAL ELF
bytes into `llvm-objdump` **via standard input**, and extracts only
a limited number of lines mentioning the *exact string virtual
address* `0x1654f` or loader symbols `dlopen` / `dlsym`.
No binary is written to disk or executed as a program. The
disassembly tool itself runs locally to inspect the data.

```bash
(
  set -euo pipefail
  cd ~/Projekte/OP7T-Kernel-KSU-Review
  BRANCH=experiment/hotdog-aosp-clang-r596125
  REF="refs/remotes/origin/${BRANCH}"
  DIR="$PWD/.work/vendor-hotdog-17"

  git fetch origin "+refs/heads/${BRANCH}:${REF}"
  git show "${REF}:scripts/audit-hotdog-a2dp-llvm-objdump.py" \
    > "$DIR/audit-llvm-text.py.partial"
  mv "$DIR/audit-llvm-text.py.partial" "$DIR/audit-llvm-text.py"

  command -v llvm-objdump || true

  python3 "$DIR/audit-llvm-text.py" \
    "$DIR/proprietary_vendor_oneplus_hotdog-17.0.zip" \
    | tee "$DIR/a2dp-llvm-text-audit.json"
)
```

If `llvm-objdump` is unavailable, the script returns
`LLVM_OBJDUMP_NOT_INSTALLED`, without changing the system or
installing packages. Do not confuse it with a run-time loader failure.

Even if a disassembly line mentions `0x1654f`, this parser treats
the line as **a candidate for review**, not an instruction-level
def-use chain; and an absent text hit cannot rule out PIC/GOT or
multi-instruction ARM/Thumb address formation. A correct `dlopen`
call-argument proof needs verified basic blocks, register dataflow
and symbolic call-target attribution.

**`flash_ready=false`**. No OTA partition, module, ELF or kernel
has been patched.

### Pi result: llvm-objdump missing; fallback now checks versioned LLVM and GNU ARM tools

The user's first `audit-hotdog-a2dp-llvm-objdump.py` run
returned `LLVM_OBJDUMP_NOT_INSTALLED`; both original SHA-256 checks
passed and the ELF was not executed or extracted. **This was an
analysis-tool availability issue**, not an ELF failure or negative
disassembly result.

The audit script now discovers existing binaries in order:
`llvm-objdump`, `llvm-objdump-22` through
`llvm-objdump-16` (including Debian 13's usual
`llvm-objdump-19`), then native ARM cross tools such as
`arm-linux-gnueabi-objdump`,
`arm-linux-gnueabihf-objdump` and
`arm-none-eabi-objdump`. It **does not install packages**.

LLVM receives ELF bytes on standard input using `-`, supported by
the official LLVM object-dumper interface. ARM GNU objdump expects a
filename; on Linux the script therefore creates an anonymous
`memfd` (RAM-backed descriptor) and passes it via
`/proc/self/fd/<fd>` to the child process. It does not create a
named or persistent extracted ELF on the filesystem. Tool binary
execution is limited to the disassembler, **not** the untrusted ELF.

Use the existing tool and original local ZIP:

```bash
(
  set -euo pipefail
  cd ~/Projekte/OP7T-Kernel-KSU-Review
  BRANCH=experiment/hotdog-aosp-clang-r596125
  REF="refs/remotes/origin/${BRANCH}"
  DIR="$PWD/.work/vendor-hotdog-17"

  git fetch origin "+refs/heads/${BRANCH}:${REF}"
  git show "${REF}:scripts/audit-hotdog-a2dp-llvm-objdump.py" \
    > "$DIR/audit-llvm-text.py.partial"
  mv "$DIR/audit-llvm-text.py.partial" "$DIR/audit-llvm-text.py"

  python3 "$DIR/audit-llvm-text.py" \
    "$DIR/proprietary_vendor_oneplus_hotdog-17.0.zip" \
    | tee "$DIR/a2dp-disassembly-audit.json"
)
```

Check `selected_tool_name`, `selected_tool_flavor` and
`disassembly.status`. If no listed tools exist, the status is
`NO_ARM_DISASSEMBLER_AVAILABLE`. **Do not treat missing tools
or zero textual references as evidence of no A2DP code path.**

To investigate available **Debian** packages without changing the Pi:

```bash
apt-cache policy llvm-19 binutils-arm-linux-gnueabi
```

No `sudo`, `apt install`, changes to repositories, code modifications,
OTA partition writes or kernel rebuilds are part of the audit.
`flash_ready=false`.

### GNU ARM disassembly: 127,841 instruction lines, zero simple text hits

On the Raspberry Pi the version-aware probe detected
**`arm-linux-gnueabi-objdump`** and successfully ran against the
original SHA-256-verified ZIP and Audio HAL using an anonymous
RAM descriptor (no extraction or ELF execution).

| Actual Pi finding | Value |
| --- | --- |
| `selected_tool_flavor` | `gnu-arm` |
| `selected_tool_name` | `arm-linux-gnueabi-objdump` |
| `instruction_lines_parsed` | **127,841** |
| `a2dp_exact_address_text_hit_count` | **0** |
| `loader_symbol_text_hit_count` | **0** |
| `candidate_lines` | `[]` |
| Disassembler status | `DISASSEMBLY_TEXT_CANDIDATES_RECORDED` |
| Hash checks | ZIP **true**, ELF **true** |
| Binary executed/extracted | **false / false** |

These are **zero textual hits in the disassembled instructions**,
not a determination that no ARM/Thumb code uses the A2DP string.
Imports in `SHT_DYNSYM`, `.rel.plt` and indirect PLT/GOT call
paths need not appear as the literal text `dlopen` or `0x1654f`
in the particular GNU disassembly format used.

The new independent
[`scripts/audit-hotdog-audio-import-relocations.py`](../scripts/audit-hotdog-audio-import-relocations.py)
checks the original pinned ZIP+ELF SHA-256, then inspects
`SHT_DYNSYM` and symbol-indexed `SHT_REL`/`SHT_RELA` entries
for **`dlopen`**, **`dlsym`** and
**`android_dlopen_ext`**. It reports the relocation slot's
ELF virtual address, relocation type number, and dynamic symbol
index, without guessing PLT stub addresses, call sites, or the A2DP
string argument. Only one small ELF is read directly from ZIP into
bounded memory; binary content is never executed or persisted.

```bash
(
  set -euo pipefail
  cd ~/Projekte/OP7T-Kernel-KSU-Review
  BRANCH="experiment/hotdog-aosp-clang-r596125"
  REF="refs/remotes/origin/${BRANCH}"
  DIR="$PWD/.work/vendor-hotdog-17"

  git fetch origin "+refs/heads/${BRANCH}:${REF}"
  git show "${REF}:scripts/audit-hotdog-audio-import-relocations.py" \
    > "$DIR/audit-import-relocations.py.tmp"
  mv "$DIR/audit-import-relocations.py.tmp" \
    "$DIR/audit-import-relocations.py"

  python3 "$DIR/audit-import-relocations.py" \
    "$DIR/proprietary_vendor_oneplus_hotdog-17.0.zip" \
    | tee "$DIR/audio-import-relocations-audit.json"
)
```

Interpret `loader_imports.dlopen.relocation_samples` as **relocation
slot metadata** only. Even a confirmed `R_ARM_JUMP_SLOT`
relocation is not a proof of an invoked function, let alone
that `/odm/lib/liba2dpoffload.so` is passed as its argument.
`flash_ready=false`.

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
