#!/usr/bin/env bash
# Read-only ADB vendor module inventory. Never roots, flashes or writes to device.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ADB=(adb)
if (( $# == 2 )) && [[ "$1" == --serial && -n "$2" ]]; then
  ADB+=(-s "$2")
elif (( $# != 0 )); then
  echo "Usage: $0 [--serial ADB_SERIAL]" >&2
  exit 2
fi

bash "$ROOT/scripts/device-audit.sh" "$@"

getprop() { "${ADB[@]}" shell getprop "$1" | tr -d '\r'; }
printf 'Vendor fingerprint: %s\n' "$(getprop ro.vendor.build.fingerprint)"
printf 'Security patch: %s\n' "$(getprop ro.build.version.security_patch)"
printf 'Vendor patch: %s\n' "$(getprop ro.vendor.build.security_patch)"
printf 'Verified boot: %s\n' "$(getprop ro.boot.verifiedbootstate)"

REMOTE='
visible=0
wireless=0
for dir in /vendor/lib/modules /vendor_dlkm/lib/modules /odm/lib/modules /system/lib/modules; do
  [ -d "$dir" ] || continue
  printf "MODULE_DIRECTORY %s\n" "$dir"
  for module in "$dir"/*.ko "$dir"/*/*.ko; do
    [ -f "$module" ] || continue
    visible=$((visible+1))
    printf "MODULE_PATH %s\n" "$module"
    case "$module" in
      */wlan.ko|*/qca_cld3_wlan.ko)
        wireless=$((wireless+1))
        if [ -r "$module" ] && command -v sha256sum >/dev/null 2>&1; then
          sha256sum "$module" | while IFS= read -r line; do
            printf "WLAN_MODULE_SHA256 %s\n" "$line"
          done
        else
          printf "WLAN_MODULE_HASH_UNAVAILABLE %s\n" "$module"
        fi
        ;;
    esac
  done
done
printf "VISIBLE_MODULE_COUNT %s\n" "$visible"
printf "VISIBLE_WLAN_MODULE_COUNT %s\n" "$wireless"
if [ "$wireless" -eq 0 ]; then printf "WLAN_MODULE_UNKNOWN (ADB-visible paths only)\n"; fi
if [ -r /proc/modules ]; then
  while IFS= read -r line; do
    case "$line" in
      wlan\ *|qca_cld3_wlan\ *) printf "LOADED_WLAN %s\n" "$line" ;;
    esac
  done </proc/modules
else
  printf "LOADED_WLAN_UNKNOWN (/proc/modules unreadable)\n"
fi
'
"${ADB[@]}" shell "$REMOTE" | tr -d '\r'
printf '%s\n' 'Exact ROM trust/ABI cannot be proven using this inventory.'
printf '%s\n' 'Read-only inventory completed; flash_ready=false.'
