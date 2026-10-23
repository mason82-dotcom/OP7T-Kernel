#!/usr/bin/env bash
# Read-only preflight for OnePlus 7T Pro (hotdog) / crDroid 13.
# Never writes, roots, reboots, unlocks or flashes the phone.
set -Eeuo pipefail
command -v adb >/dev/null || { echo "adb executable not found" >&2; exit 2; }
ADB=(adb)
if [[ "${1:-}" == --serial && -n "${2:-}" && $# -eq 2 ]]; then
  ADB+=( -s "$2" )
elif (( $# != 0 )); then
  echo "Usage: $0 [--serial ADB_SERIAL]" >&2; exit 2
fi
"${ADB[@]}" get-state | grep -qx device || { echo "ADB device not authorized / online" >&2; exit 2; }
getprop() { "${ADB[@]}" shell getprop "$1" | tr -d '\r'; }
device="$(getprop ro.product.device)"
release="$(getprop ro.build.version.release)"
fingerprint="$(getprop ro.build.fingerprint)"
slot="$(getprop ro.boot.slot_suffix)"
crdroid="$(getprop ro.crdroid.version)"
printf 'Device:          %s\n' "$device"
printf 'Android release: %s\n' "$release"
printf 'crDroid version: %s\n' "${crdroid:-<not exposed>}"
printf 'ROM fingerprint: %s\n' "$fingerprint"
printf 'Active A/B slot: %s\n' "${slot:-<unknown>}"
printf 'Kernel release:  %s\n' "$("${ADB[@]}" shell uname -r | tr -d '\r')"
if [[ "$device" != hotdog ]]; then
  echo "STOP: device is not the OnePlus 7T Pro hotdog (do not use for hotdogg)" >&2
  exit 3
fi
if [[ "$release" != 17 ]]; then
  echo "STOP: this project's source tree targets Android 17 / crDroid 13" >&2
  exit 3
fi
if [[ "$crdroid" != 13* ]]; then
  echo "WARNING: crDroid v13 cannot be validated from ro.crdroid.version."
  echo "Confirm the exact installed crDroid build from About Phone."
fi
if [[ "$slot" != _a && "$slot" != _b ]]; then
  echo "WARNING: A/B boot slot could not be verified."
fi
echo "Read-only compatibility inspection completed. This is NOT permission to flash."
