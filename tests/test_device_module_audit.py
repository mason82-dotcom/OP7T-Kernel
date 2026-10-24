import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "device-module-audit.sh"


class DeviceModuleInventoryTests(unittest.TestCase):
    def probe(self, device="hotdog", android="17", arguments=()):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "adb"
            fake.write_text("""#!/bin/sh
if [ "$1" = "-s" ]; then shift 2; fi
case "$1" in
  get-state) echo device ;;
  shell)
    shift
    case "$1" in
      getprop)
        case "$2" in
          ro.product.device) echo "$MOCK_DEVICE" ;;
          ro.build.version.release) echo "$MOCK_ANDROID" ;;
          ro.build.fingerprint) echo crdroid/test/fingerprint ;;
          ro.boot.slot_suffix) echo _a ;;
          ro.crdroid.version) echo 13.0 ;;
          ro.vendor.build.fingerprint) echo vendor/test/fingerprint ;;
          ro.build.version.security_patch) echo 2026-10-01 ;;
          ro.vendor.build.security_patch) echo 2026-10-01 ;;
          ro.boot.verifiedbootstate) echo green ;;
        esac
        ;;
      uname) echo 4.14.357-perf ;;
      *) echo 'MODULE_PATH /vendor/lib/modules/wlan.ko' ;;
    esac
    ;;
  *) exit 9 ;;
esac
""", encoding="utf-8")
            fake.chmod(0o755)
            env = dict(os.environ)
            env["PATH"] = tmp + os.pathsep + env.get("PATH", "")
            env["MOCK_DEVICE"] = device
            env["MOCK_ANDROID"] = android
            return subprocess.run(
                ["bash", str(SCRIPT), *arguments],
                cwd=ROOT, env=env, text=True, capture_output=True,
                timeout=20, check=False,
            )

    def test_read_only_inventory(self):
        r = self.probe()
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertIn("vendor/test/fingerprint", r.stdout)
        self.assertIn("MODULE_PATH /vendor/lib/modules/wlan.ko", r.stdout)
        self.assertIn("flash_ready=false", r.stdout)

    def test_device_serial_is_passed(self):
        r = self.probe(arguments=("--serial", "TESTDEVICE123"))
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertIn("Kernel release:", r.stdout)

    def test_oem_device_alias_accepted(self):
        r = self.probe(device="OnePlus7TPro")
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertIn("OEM product device alias", r.stdout)
        self.assertIn("flash_ready=false", r.stdout)

    def test_mclaren_5g_property_rejected(self):
        r = self.probe(device="OnePlus7TProNR")
        self.assertEqual(3, r.returncode)
        self.assertIn("STOP: device is not", r.stderr)
        self.assertNotIn("MODULE_PATH", r.stdout)

    def test_wrong_device_rejected(self):
        r = self.probe(device="hotdogg")
        self.assertEqual(3, r.returncode)
        self.assertIn("STOP: device is not", r.stderr)
        self.assertNotIn("MODULE_PATH", r.stdout)

    def test_wrong_android_version_rejected(self):
        r = self.probe(android="16")
        self.assertEqual(3, r.returncode)
        self.assertIn("STOP: this project's source", r.stderr)

    def test_bad_option_rejected(self):
        r = self.probe(arguments=("--root",))
        self.assertEqual(2, r.returncode)

    def test_source_has_no_device_mutation_commands(self):
        text = SCRIPT.read_text(encoding="utf-8")
        for pattern in ("adb push", "adb reboot", "adb remount", "fastboot flash", "su -c", "dd if="):
            self.assertNotIn(pattern, text)


if __name__ == "__main__":
    unittest.main()
