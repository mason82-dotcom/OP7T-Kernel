#!/usr/bin/env python3
"""Cross-platform, strictly read-only ADB evidence for the hotdog kernel project.

Runs on Windows, macOS and Linux without bash, root or phone-side writes.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SCHEMA = "op7t-hotdog-device-evidence-v1"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SERIAL = re.compile(r"^[a-zA-Z0-9._:\[\]-]{1,128}$")
SAFE_REMOTE_PATH = re.compile(
    r"^/(?:vendor|vendor_dlkm|odm|system)/lib/modules/(?:[A-Za-z0-9_.+-]+/)?(?:wlan|qca_cld3_wlan)\.ko$"
)
PROPERTIES = {
    "device": "ro.product.device",
    "android_release": "ro.build.version.release",
    "rom_fingerprint": "ro.build.fingerprint",
    # This property is Android platform 17.0, NOT the crDroid v13 release.
    "crdroid_version": "ro.crdroid.version",
    "crdroid_build_version": "ro.crdroid.build.version",
    "crdroid_display_version": "ro.crdroid.display.version",
    "system_fingerprint": "ro.system.build.fingerprint",
    "active_slot": "ro.boot.slot_suffix",
    "vendor_fingerprint": "ro.vendor.build.fingerprint",
    "security_patch": "ro.build.version.security_patch",
    "vendor_security_patch": "ro.vendor.build.security_patch",
    "verified_boot_state": "ro.boot.verifiedbootstate",
}

# All paths and command text are literals. No user/device values are interpolated.
REMOTE_WLAN_PROBE = r'''
for dir in /vendor/lib/modules /vendor_dlkm/lib/modules /odm/lib/modules /system/lib/modules; do
  [ -d "$dir" ] || continue
  printf 'DIR\t%s\n' "$dir"
  for mod in "$dir"/wlan.ko "$dir"/qca_cld3_wlan.ko "$dir"/*/wlan.ko "$dir"/*/qca_cld3_wlan.ko; do
    [ -f "$mod" ] || continue
    printf 'PATH\t%s\n' "$mod"
    if [ -r "$mod" ] && command -v sha256sum >/dev/null 2>&1; then
      sha256sum "$mod" | while IFS= read -r digest_and_path; do
        digest=${digest_and_path%% *}
        printf 'SHA256\t%s\t%s\n' "$digest" "$mod"
      done
    else
      printf 'HASH_UNAVAILABLE\t%s\n' "$mod"
    fi
  done
done
if [ -r /proc/modules ]; then
  while IFS= read -r line; do
    case "$line" in wlan\ *|qca_cld3_wlan\ *)
      printf 'LOADED\t%s\n' "${line%% *}" ;;
    esac
  done < /proc/modules
else
  printf 'LOADED_UNAVAILABLE\t1\n'
fi
'''


class DeviceEvidenceError(Exception):
    pass


def adb(args, serial=None):
    command = ["adb"]
    if serial is not None:
        if not SERIAL.fullmatch(serial):
            raise DeviceEvidenceError("Invalid ADB serial syntax")
        command.extend(["-s", serial])
    command.extend(args)
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=30, check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        raise DeviceEvidenceError("ADB not available, timed out or failed") from exc
    if result.returncode != 0:
        raise DeviceEvidenceError("ADB read command failed; check authorization and USB connection")
    if len(result.stdout) > 100_000:
        raise DeviceEvidenceError("ADB response exceeds evidence limit")
    return result.stdout.strip().replace("\r", "")


def parse_wlan_probe(output):
    directories = set()
    modules = {}
    loaded = set()
    warnings = []
    loaded_unavailable = False
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) == 2 and parts[0] == "DIR":
            if parts[1] in (
                "/vendor/lib/modules", "/vendor_dlkm/lib/modules",
                "/odm/lib/modules", "/system/lib/modules",
            ):
                directories.add(parts[1])
        elif len(parts) == 2 and parts[0] == "PATH":
            if SAFE_REMOTE_PATH.fullmatch(parts[1]):
                modules.setdefault(parts[1], {"path": parts[1], "sha256": None, "hash_readable": False})
        elif len(parts) == 3 and parts[0] == "SHA256":
            path = parts[2]
            if SAFE_REMOTE_PATH.fullmatch(path) and SHA256.fullmatch(parts[1]):
                modules.setdefault(path, {"path": path, "sha256": None, "hash_readable": False})
                modules[path]["sha256"] = parts[1]
                modules[path]["hash_readable"] = True
            else:
                warnings.append("Device provided invalid WLAN digest/path; ignored")
        elif len(parts) == 2 and parts[0] == "LOADED":
            if parts[1] in ("wlan", "qca_cld3_wlan"):
                loaded.add(parts[1])
        elif len(parts) == 2 and parts[0] == "LOADED_UNAVAILABLE":
            loaded_unavailable = True
    return {
        "searched_directories": sorted(directories),
        "visible_wlan_modules": [modules[p] for p in sorted(modules)],
        "loaded_wlan_names": sorted(loaded),
        "loaded_module_list_unavailable": loaded_unavailable,
        "discovery_scope": "common_adb_readable_paths_only",
        "no_visible_wlan_module_means_absent": False,
    }, warnings


def collect(serial=None):
    if adb(["get-state"], serial) != "device":
        raise DeviceEvidenceError("ADB device is not authorized and online")
    actual = {}
    for name, prop in PROPERTIES.items():
        value = adb(["shell", "getprop", prop], serial)
        if len(value) > 1024 or "\n" in value or "\t" in value:
            raise DeviceEvidenceError("Unexpected device property content")
        actual[name] = value
    if actual["device"] not in ("hotdog", "OnePlus7TPro"):
        raise DeviceEvidenceError("STOP: OnePlus 7T Pro hotdog required; hotdogg is not supported")
    if actual["android_release"] != "17":
        raise DeviceEvidenceError("STOP: Android 17 required for the pinned crDroid 13 kernel")
    kernel_release = adb(["shell", "uname", "-r"], serial)
    if not re.fullmatch(r"[A-Za-z0-9._+\-]{1,128}", kernel_release):
        raise DeviceEvidenceError("Unexpected kernel release")
    wlan, warnings = parse_wlan_probe(adb(["shell", REMOTE_WLAN_PROBE], serial))
    if not actual["crdroid_version"].startswith("17"):
        warnings.append("crDroid Android platform property is not 17.x; verify exact ROM")
    if not actual["crdroid_build_version"].startswith("13"):
        warnings.append("crDroid build.version not confirmed as v13; verify exact ROM")
    if ":12/" in actual["rom_fingerprint"]:
        warnings.append("ro.build.fingerprint carries Android 12 OEM identity; NOT exact installed Android 17 ROM provenance")
    if actual["active_slot"] not in ("_a", "_b"):
        warnings.append("Active A/B slot not verified")
    if not wlan["visible_wlan_modules"]:
        warnings.append("No WLAN .ko in visible paths; this does NOT establish module absence")
    return {
        "schema": SCHEMA,
        "target_device": "hotdog",
        "device_property_is_oem_alias": actual["device"] == "OnePlus7TPro",
        "device": actual,
        "crdroid_version_property_meaning": "android_platform_version",
        "crdroid_release_property": "ro.crdroid.build.version",
        "rom_fingerprint_is_authoritative_rom_proof": False,
        "kernel_release": kernel_release,
        "wlan": wlan,
        "warnings": warnings,
        "read_only": True,
        "exact_installed_rom_image_matched": False,
        "vendor_module_abi_verified": False,
        "trusted_kernel_module_key_verified": False,
        "boot_image_compatible": False,
        "hardware_verified": False,
        "flash_ready": False,
        "status": "READ_ONLY_DEVICE_EVIDENCE_UNVERIFIED",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", help="ADB device serial when multiple devices are attached")
    parser.add_argument("--output", type=Path,
                        help="Write local JSON evidence without overwriting an existing file")
    args = parser.parse_args(argv)
    try:
        result = collect(args.serial)
        content = json.dumps(result, indent=2, sort_keys=True) + "\n"
        if args.output is not None:
            with args.output.open("x", encoding="utf-8") as f:
                f.write(content)
            print("Read-only device evidence stored locally; flash_ready=false")
        else:
            sys.stdout.write(content)
        return 0
    except (DeviceEvidenceError, OSError) as exc:
        print(f"Device evidence FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
