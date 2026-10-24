#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/config/upstream.lock"
PROFILE="${1:-baseline}"
case "$PROFILE" in baseline|core|external|kernelsu) ;; *) echo "Usage: $0 {baseline|core|external|kernelsu}" >&2; exit 2 ;; esac
KERNEL="$ROOT/.work/kernel"
OUT="$ROOT/.work/out-$PROFILE"
ART="$ROOT/.work/artifacts/$PROFILE"
DEF="$KERNEL/arch/arm64/configs/vendor/sm8150-perf_defconfig"
OPLUS="$KERNEL/arch/arm64/configs/vendor/oplus.config"
CC_BIN="${CC:-clang}"
LD_BIN="${LD:-ld.lld}"
AR_BIN="${AR:-llvm-ar}"
NM_BIN="${NM:-llvm-nm}"
OBJCOPY_BIN="${OBJCOPY:-llvm-objcopy}"
OBJDUMP_BIN="${OBJDUMP:-llvm-objdump}"
STRIP_BIN="${STRIP:-llvm-strip}"
CROSS64="${CROSS_COMPILE:-aarch64-linux-gnu-}"
CROSS32="${CROSS_COMPILE_ARM32:-arm-linux-gnueabi-}"
JOBS="${JOBS:-2}"

# Old Qualcomm Kbuild invokes LLVM utilities by their UNSUFFIXED names
# (llvm-nm / llvm-ar), even if command-line NM/AR are version-suffixed.
# Resolve tools from the SAME LLVM installation as the selected clang.
# Ubuntu clang-14 installs these under /usr/lib/llvm-14/bin.
if [[ -n "${LLVM_TOOLCHAIN_BIN:-}" ]]; then
  [[ -d "$LLVM_TOOLCHAIN_BIN" ]] || { echo "LLVM_TOOLCHAIN_BIN directory missing" >&2; exit 2; }
  export PATH="$LLVM_TOOLCHAIN_BIN:$PATH"
elif [[ "$CC_BIN" =~ ^clang-([0-9]+)$ ]]; then
  llvm_dir="/usr/lib/llvm-${BASH_REMATCH[1]}/bin"
  if [[ -d "$llvm_dir" ]]; then export PATH="$llvm_dir:$PATH"; fi
fi
for unsuffixed in llvm-nm llvm-ar llvm-objcopy llvm-objdump llvm-strip; do
  command -v "$unsuffixed" >/dev/null || {
    echo "Kbuild requires $unsuffixed on PATH (set LLVM_TOOLCHAIN_BIN)" >&2
    exit 2
  }
done
echo "LLVM utility path: $(command -v llvm-nm)"

[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] || { echo "Linux x86_64 build host required" >&2; exit 2; }
for command_name in make git python3 sha256sum readelf "$CC_BIN" "$LD_BIN" "$AR_BIN" "$NM_BIN" "$OBJCOPY_BIN" "$OBJDUMP_BIN" "$STRIP_BIN"; do
  command -v "$command_name" >/dev/null || { echo "Missing build tool: $command_name" >&2; exit 2; }
done
bash "$ROOT/scripts/fetch-source.sh"
if [[ "$PROFILE" == kernelsu ]]; then
  KERNEL="$(bash "$ROOT/scripts/prepare-kernelsu-next.sh")"
fi
DEF="$KERNEL/arch/arm64/configs/vendor/sm8150-perf_defconfig"
OPLUS="$KERNEL/arch/arm64/configs/vendor/oplus.config"
test -s "$DEF" && test -s "$OPLUS"
rm -rf "$OUT" "$ART"
mkdir -p "$OUT" "$ART"
# Toolchain provenance is evidence, NOT proof of installed-ROM compiler parity.
python3 "$ROOT/scripts/audit-toolchain.py" --clang "$CC_BIN" --ld "$LD_BIN" \
  --output "$ART/toolchain-report.json"
export ARCH=arm64 SUBARCH=arm64
export KBUILD_BUILD_USER=op7t-kernel KBUILD_BUILD_HOST=buildhost
export SOURCE_DATE_EPOCH="$(git -C "$KERNEL" show -s --format=%ct HEAD)"
export KBUILD_BUILD_TIMESTAMP="$(date -u -d "@$SOURCE_DATE_EPOCH" '+%a %b %d %H:%M:%S UTC %Y')"

KARGS=(O="$OUT" ARCH=arm64 CC="$CC_BIN" LD="$LD_BIN" AR="$AR_BIN" NM="$NM_BIN"
  OBJCOPY="$OBJCOPY_BIN" OBJDUMP="$OBJDUMP_BIN" STRIP="$STRIP_BIN"
  CROSS_COMPILE="$CROSS64" CROSS_COMPILE_ARM32="$CROSS32")

make -C "$KERNEL" "${KARGS[@]}" vendor/sm8150-perf_defconfig
FRAGMENTS=()
if [[ "$PROFILE" != baseline ]]; then FRAGMENTS+=("$ROOT/config/nethunter-core.fragment"); fi
if [[ "$PROFILE" == external ]]; then FRAGMENTS+=("$ROOT/config/nethunter-external.fragment"); fi
if [[ "$PROFILE" == kernelsu ]]; then FRAGMENTS+=("$ROOT/config/kernelsu-next.fragment"); fi

# Device BoardConfigCommon.mk specifies base config followed by vendor/oplus.config.
(
  cd "$KERNEL"
  ./scripts/kconfig/merge_config.sh -m -O "$OUT" "$DEF" "$OPLUS" "${FRAGMENTS[@]}"
)
make -C "$KERNEL" "${KARGS[@]}" olddefconfig
VERIFY=(--config "$OUT/.config")
for fragment in "${FRAGMENTS[@]}"; do VERIFY+=(--fragment "$fragment"); done
python3 "$ROOT/scripts/verify-config.py" "${VERIFY[@]}"
if [[ "$PROFILE" == kernelsu ]]; then
  git -C "$ROOT/.work/kernelsu-next" rev-parse HEAD > "$ART/kernelsu-next-commit.txt"
fi

# Fast configuration-only acceptance path; never emits an Image, DTBs or modules.
case "${CONFIG_ONLY:-0}" in
  0) ;;
  1)
    mkdir -p "$ART"
    cp "$OUT/.config" "$ART/kernel.config"
    git -C "$KERNEL" rev-parse HEAD > "$ART/upstream-commit.txt"
    echo "CONFIG_ONLY PASSED for $PROFILE; no kernel built or flashable artifacts"
    exit 0
    ;;
  *) echo "CONFIG_ONLY accepts only 0 or 1" >&2; exit 2 ;;
esac

# BoardConfigCommon.mk: BOARD_KERNEL_IMAGE_NAME := Image
make -C "$KERNEL" "${KARGS[@]}" -j"$JOBS" Image dtbs modules
IMAGE="$OUT/arch/arm64/boot/Image"
test -s "$IMAGE" || { echo "No arm64 Image produced" >&2; exit 1; }
cp "$IMAGE" "$ART/Image"
cp "$OUT/.config" "$ART/kernel.config"
git -C "$KERNEL" rev-parse HEAD > "$ART/upstream-commit.txt"
"$CC_BIN" --version > "$ART/compiler.txt"
make -s -C "$KERNEL" "${KARGS[@]}" kernelrelease > "$ART/kernel.release"
for metadata in Module.symvers modules.order System.map; do
  if [[ -s "$OUT/$metadata" ]]; then cp "$OUT/$metadata" "$ART/$metadata"; fi
done

# The vendor kernel signs modules on modules_install, NOT on 'make modules'.
# Stage only within .work; never install kernel modules into the host OS.
# Private keys remain in the ignored build output, never in archived artifacts.
if ! grep -qx 'CONFIG_MODULE_SIG_ALL=y' "$OUT/.config" ||
   ! grep -qx 'CONFIG_MODULE_SIG_KEY="certs/signing_key.pem"' "$OUT/.config"; then
  echo "Signing gate: CONFIG_MODULE_SIG_ALL=y with the autogenerated build key is required" >&2
  exit 1
fi
STAGE="$ROOT/.work/module-stage-$PROFILE"
rm -rf -- "$STAGE"
mkdir -p "$STAGE"
# Kbuild order in scripts/Makefile.modinst: copy -> strip-debug -> sign.
# Never strip modules after they have been signed; preserve the staged signature.
make -C "$KERNEL" "${KARGS[@]}" INSTALL_MOD_PATH="$STAGE" INSTALL_MOD_STRIP=1 DEPMOD=true modules_install

RELEASE="$(cat "$ART/kernel.release")"
STAGED_KERNEL="$STAGE/lib/modules/$RELEASE/kernel"
[[ -d "$STAGED_KERNEL" ]] || { echo "No staged kernel modules: $STAGED_KERNEL" >&2; exit 1; }
count=0
while IFS= read -r -d '' module; do
  relative="${module#"$STAGED_KERNEL/"}"
  install -D -m 0644 "$module" "$ART/modules/$relative"
  count=$((count + 1))
done < <(find "$STAGED_KERNEL" -type f -name '*.ko' -print0)
(( count > 0 )) || { echo "No signed .ko files staged" >&2; exit 1; }
# Export only the DER public certificate. Never copy certs/signing_key.pem.
PUBCERT="$OUT/certs/signing_key.x509"
[[ -s "$PUBCERT" ]] || { echo "Missing autogenerated public signing certificate" >&2; exit 1; }
install -m 0644 "$PUBCERT" "$ART/signing-cert.x509"
sha256sum "$PUBCERT" | awk '{print $1}' > "$ART/signing-cert.sha256"
[[ ! -e "$ART/modules/certs/signing_key.pem" ]] || exit 1
while IFS= read -r -d '' dtb; do
  relative="${dtb#"$OUT/"}"
  install -D -m 0644 "$dtb" "$ART/dtbs/$relative"
done < <(find "$OUT/arch/arm64/boot/dts" -type f -name '*.dtb' -print0)

python3 "$ROOT/scripts/audit-artifacts.py" "$ART" --expected-sha "$UPSTREAM_SHA" --profile "$PROFILE" --require-signed --require-stripped
mapfile -d '' -t SIGNED_MODULES < <(find "$ART/modules" -type f -name '*.ko' -print0 | sort -z)
python3 "$ROOT/scripts/verify-build-module-cms.py" \
  --certificate "$ART/signing-cert.x509" \
  --fingerprint "$ART/signing-cert.sha256" \
  "${SIGNED_MODULES[@]}" > "$ART/build-module-cms.json"
(
  cd "$ART"
  find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 -r sha256sum > SHA256SUMS
)
echo "Created experimental raw artifacts: $ART"
echo "Not a boot.img; do not flash. See docs/FLASHING.md"
