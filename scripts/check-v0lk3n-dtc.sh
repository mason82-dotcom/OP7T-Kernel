#!/usr/bin/env bash
# Verify the selected external DTC supports unresolved overlay targets and emits fixups.
# This is a compiler capability check, NOT verification of the device's real DTBO.
set -Eeuo pipefail

DTC_BIN="${DTC_EXT:-dtc}"
command -v "$DTC_BIN" >/dev/null || {
  echo "V0lk3n overlay compiler missing: $DTC_BIN" >&2
  exit 2
}
command -v fdtget >/dev/null || {
  echo "V0lk3n overlay verification requires fdtget" >&2
  exit 2
}
TMP="$(mktemp -d)"
trap 'rm -rf -- "$TMP"' EXIT

# Linux's old in-tree DTC fails on this unresolved &label root-node
# reference even with -@. The selected compiler MUST emit a base fixup.
cat > "$TMP/external-target.dts" <<'DTS'
/dts-v1/;
/plugin/;

/ {
    compatible = "op7t,v0lk3n-overlay-preflight";
};

&missing_kernel_base_label {
    status = "okay";
};
DTS

"$DTC_BIN" -@ -I dts -O dtb -o "$TMP/external-target.dtbo" "$TMP/external-target.dts"
test -s "$TMP/external-target.dtbo"
FIXUP="$(fdtget -t s "$TMP/external-target.dtbo" /__fixups__ missing_kernel_base_label)"
[[ "$FIXUP" == *"/fragment@"* && "$FIXUP" == *":target:0"* ]] || {
  echo "V0lk3n DTC gate: missing valid external-target fixup" >&2
  exit 2
}
"$DTC_BIN" --version
echo "V0lk3n DTC external label preflight: PASS (not a real device-tree validation)"
echo "flash_ready=false"
