#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/config/upstream.lock"
KERNEL="$ROOT/.work/kernel"
[[ "$UPSTREAM_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "Invalid SHA" >&2; exit 2; }
[[ "$DEVICE" == hotdog && "$ROM_ANDROID" == 17 ]] || { echo "Wrong target" >&2; exit 2; }
mkdir -p "$ROOT/.work"
if [[ ! -e "$KERNEL" ]]; then
  git clone --filter=blob:none --single-branch --branch "$UPSTREAM_REF" "$UPSTREAM_URL" "$KERNEL"
fi
[[ -d "$KERNEL/.git" ]] || { echo "Not a Git kernel tree" >&2; exit 2; }
[[ -z "$(git -C "$KERNEL" status --porcelain)" ]] || { echo "Dirty source tree" >&2; exit 2; }
if ! git -C "$KERNEL" cat-file -e "$UPSTREAM_SHA^{commit}" 2>/dev/null; then
  git -C "$KERNEL" fetch origin "$UPSTREAM_REF"
fi
if ! git -C "$KERNEL" cat-file -e "$UPSTREAM_SHA^{commit}" 2>/dev/null; then
  # A historical exact commit can remain retrievable after branch HEAD moves.
  # Never silently substitute the moving branch tip for the locked SHA.
  git -C "$KERNEL" fetch origin "$UPSTREAM_SHA"
fi
git -C "$KERNEL" cat-file -e "$UPSTREAM_SHA^{commit}" || { echo "Pinned commit unavailable" >&2; exit 2; }
git -C "$KERNEL" checkout --detach "$UPSTREAM_SHA"
[[ "$(git -C "$KERNEL" rev-parse HEAD)" == "$UPSTREAM_SHA" ]] || exit 2
echo "Pinned crDroid 13 Android 17 source: $UPSTREAM_SHA"
