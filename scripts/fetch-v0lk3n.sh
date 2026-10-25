#!/usr/bin/env bash
# Fetch a pinned V0lk3n LOS 23.2 *candidate* into its own ignored workspace.
# Neither the crDroid source nor the existing KernelSU worktrees are touched.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/config/v0lk3n.lock"
KERNEL="$ROOT/.work/v0lk3n-kernel"
WITH_SUBMODULES=0
case "${1:-}" in
  "") ;;
  --submodules) WITH_SUBMODULES=1 ;;
  *) echo "Usage: bash scripts/fetch-v0lk3n.sh [--submodules]" >&2; exit 2 ;;
esac
[[ "$V0LK3N_SHA" =~ ^[a-f0-9]{40}$ ]] || { echo "Invalid V0lk3n commit SHA" >&2; exit 2; }
[[ "$V0LK3N_URL" == "https://github.com/V0lk3n/nethunter_kernel_oneplus_sm8150.git" &&
   "$V0LK3N_REF" == "nethunter-lineage-23.2" &&
   "$V0LK3N_DEVICE" == "hotdog" &&
   "$V0LK3N_SOURCE_ANDROID" == 16 &&
   "$V0LK3N_TARGET_ANDROID" == 17 ]] || { echo "Unexpected V0lk3n source target" >&2; exit 2; }
mkdir -p "$ROOT/.work"
if [[ ! -e "$KERNEL" ]]; then
  git clone --filter=blob:none --single-branch --branch "$V0LK3N_REF" -- "$V0LK3N_URL" "$KERNEL"
fi
[[ -d "$KERNEL/.git" ]] || { echo "Missing candidate kernel Git tree" >&2; exit 2; }
[[ "$(git -C "$KERNEL" remote get-url origin)" == "$V0LK3N_URL" ]] ||
  { echo "Candidate source remote differs from pinned URL" >&2; exit 2; }
[[ -z "$(git -C "$KERNEL" status --porcelain)" ]] ||
  { echo "Candidate source tree is dirty: refusing checkout" >&2; exit 2; }
if ! git -C "$KERNEL" cat-file -e "$V0LK3N_SHA^{commit}" 2>/dev/null; then
  git -C "$KERNEL" fetch origin "$V0LK3N_REF"
fi
git -C "$KERNEL" checkout --detach "$V0LK3N_SHA"
[[ "$(git -C "$KERNEL" rev-parse HEAD)" == "$V0LK3N_SHA" ]] ||
  { echo "Candidate source SHA mismatch" >&2; exit 2; }
if (( WITH_SUBMODULES )); then
  # V0lk3n contains Kali builder and third-party Wi-Fi/CAN submodules.
  # This is opt-in to avoid fetching more unreviewed sources during triage.
  git -C "$KERNEL" submodule update --init --recursive
fi
echo "Pinned V0lk3n source: $V0LK3N_SHA"
echo "Base=LineageOS 23.2 / Android 16; target=crDroid 13 / Android 17 (NOT verified)"
echo "No boot image, no device changes, flash_ready=false"
