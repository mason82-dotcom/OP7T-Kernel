#!/usr/bin/env bash
# Apply reviewed source compile fixes to the pinned V0lk3n candidate.
# A successful patch application does NOT attest ABI, DTBO or device readiness.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/config/v0lk3n.lock"
KERNEL="$ROOT/.work/v0lk3n-kernel"
PATCH="$ROOT/patches/v0lk3n-build-compile-preflight.patch"

[[ "$V0LK3N_SHA" =~ ^[a-f0-9]{40}$ ]] || exit 2
[[ "$(git -C "$KERNEL" rev-parse HEAD)" == "$V0LK3N_SHA" ]] || {
  echo "Pinned V0lk3n candidate SHA not found" >&2
  exit 2
}
test -s "$PATCH"
# The source was verified before enabling submodules by fetch-v0lk3n.sh.
# Never patch an already-modified source or an unreviewed additional file.
if [[ -n "$(git -C "$KERNEL" status --porcelain)" ]]; then
  echo "V0lk3n source worktree is dirty; refusing patch to avoid overwrite" >&2
  exit 2
fi
git -C "$KERNEL" apply --check "$PATCH"
git -C "$KERNEL" apply "$PATCH"
git -C "$KERNEL" diff --check
git -C "$KERNEL" apply --reverse --check "$PATCH"
mapfile -t MODIFIED < <(git -C "$KERNEL" diff --name-only)
if [[ "${#MODIFIED[@]}" != 4 ||
      "${MODIFIED[0]}" != "arch/arm64/boot/dts/18821/sm8150-mtp-overlay.dts" ||
      "${MODIFIED[1]}" != "drivers/staging/qcacld-3.0/Kbuild" ||
      "${MODIFIED[2]}" != "drivers/staging/qcacld-3.0/core/hdd/src/wlan_hdd_inject_security.c" ||
      "${MODIFIED[3]}" != "scripts/Makefile.lib" ]]; then
  echo "Unexpected V0lk3n modifications after applying pinned compile patch" >&2
  exit 2
fi
echo "V0lk3n source compile preflight patch applied (NOT validated by compiler yet)"
sha256sum "$PATCH"
echo "flash_ready=false"
