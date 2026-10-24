#!/usr/bin/env bash
# Prepare a separate source worktree: the original pinned source stays clean.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/config/upstream.lock"
source "$ROOT/config/kernelsu-next.lock"
SOURCE="$ROOT/.work/kernel"
KERNEL="$ROOT/.work/kernel-ksu"
KSU="$ROOT/.work/kernelsu-next"
KSU_PATCHED="$ROOT/.work/kernelsu-next-hotdog"
COMPAT_PATCH="$ROOT/patches/kernelsu-next-seccomp-4.14.patch"
[[ "$KSU_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo 'Invalid KernelSU-Next SHA' >&2; exit 2; }
[[ "$(git -C "$SOURCE" rev-parse HEAD)" == "$UPSTREAM_SHA" ]] || { echo 'Wrong kernel source' >&2; exit 2; }
if [[ ! -e "$KSU" ]]; then
  git clone --filter=blob:none --single-branch --branch "$KSU_REF" "$KSU_URL" "$KSU" >&2
fi
[[ -d "$KSU/.git" && -z "$(git -C "$KSU" status --porcelain)" ]] || { echo 'Dirty KernelSU-Next source' >&2; exit 2; }
if ! git -C "$KSU" cat-file -e "$KSU_SHA^{commit}" 2>/dev/null; then
  git -C "$KSU" fetch origin "$KSU_REF" >&2
fi
git -C "$KSU" checkout --detach "$KSU_SHA" >&2
[[ "$(git -C "$KSU" rev-parse HEAD)" == "$KSU_SHA" ]] || exit 2
if [[ ! -e "$KSU_PATCHED" ]]; then
  git -C "$KSU" worktree add --detach "$KSU_PATCHED" "$KSU_SHA" >&2
  git -C "$KSU_PATCHED" apply --check "$COMPAT_PATCH"
  git -C "$KSU_PATCHED" apply "$COMPAT_PATCH"
fi
[[ "$(git -C "$KSU_PATCHED" rev-parse HEAD)" == "$KSU_SHA" ]] || { echo 'Wrong patched KernelSU-Next source' >&2; exit 2; }
[[ "$(git -C "$KSU_PATCHED" status --porcelain)" == ' M kernel/core_hook.c' ]] || { echo 'Unexpected KernelSU-Next source changes' >&2; exit 2; }
git -C "$KSU_PATCHED" apply --reverse --check "$COMPAT_PATCH"
if [[ ! -e "$KERNEL" ]]; then
  git -C "$SOURCE" worktree add --detach "$KERNEL" "$UPSTREAM_SHA" >&2
fi
[[ "$(git -C "$KERNEL" rev-parse HEAD)" == "$UPSTREAM_SHA" ]] || { echo 'Wrong KernelSU kernel worktree' >&2; exit 2; }
[[ ! -e "$KERNEL/drivers/kernelsu" || -L "$KERNEL/drivers/kernelsu" ]] || { echo 'Unexpected drivers/kernelsu' >&2; exit 2; }
ln -sfn "$(realpath --relative-to="$KERNEL/drivers" "$KSU_PATCHED/kernel")" "$KERNEL/drivers/kernelsu"
grep -qFx 'obj-$(CONFIG_KSU) += kernelsu/' "$KERNEL/drivers/Makefile" || printf '\n%s\n' 'obj-$(CONFIG_KSU) += kernelsu/' >> "$KERNEL/drivers/Makefile"
grep -qFx 'source "drivers/kernelsu/Kconfig"' "$KERNEL/drivers/Kconfig" || printf '\n%s\n' 'source "drivers/kernelsu/Kconfig"' >> "$KERNEL/drivers/Kconfig"
[[ -s "$KERNEL/drivers/kernelsu/Kconfig" ]] || exit 2
echo "KernelSU-Next $KSU_SHA at $KERNEL" >&2
printf '%s\n' "$KERNEL"
