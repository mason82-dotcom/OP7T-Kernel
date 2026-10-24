import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "device-evidence.py"
SPEC = importlib.util.spec_from_file_location("device_evidence", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

PROPS = {
    "ro.product.device": "hotdog",
    "ro.build.version.release": "17",
    "ro.build.fingerprint": "crdroid/hotdog/test",
    "ro.crdroid.version": "13.0",
    "ro.boot.slot_suffix": "_b",
    "ro.vendor.build.fingerprint": "oneplus/vendor/test",
    "ro.build.version.security_patch": "2026-10-01",
    "ro.vendor.build.security_patch": "2026-10-01",
    "ro.boot.verifiedbootstate": "green",
}
PROBE = (
    "DIR\t/vendor/lib/modules\n"
    "PATH\t/vendor/lib/modules/wlan.ko\n"
    "SHA256\t" + "a" * 64 + "\t/vendor/lib/modules/wlan.ko\n"
    "LOADED\twlan\n"
)


def fake_run(command, **kwargs):
    if command[0] != "adb":
        raise AssertionError("Only ADB can be invoked")
    if any(arg in command for arg in ("push", "pull", "root", "remount", "reboot", "shell su")):
        raise AssertionError("Unexpected mutating ADB call")
    tail = command[3:] if len(command) >= 3 and command[1] == "-s" else command[1:]
    if tail == ["get-state"]:
        result = "device\n"
    elif tail[:3] == ["shell", "getprop", tail[-1]]:
        result = PROPS[tail[-1]] + "\n"
    elif tail == ["shell", "uname", "-r"]:
        result = "4.14.357-perf\n"
    elif len(tail) == 2 and tail[0] == "shell" and "WLAN" not in tail[1]:
        result = PROBE
    else:
        raise AssertionError(f"Unexpected ADB arguments: {tail}")
    return subprocess.CompletedProcess(command, 0, result, "")


class EvidenceTests(unittest.TestCase):
    @patch.object(MODULE.subprocess, "run", side_effect=fake_run)
    def test_successful_read_only_json(self, run):
        report = MODULE.collect()
        self.assertEqual("hotdog", report["device"]["device"])
        self.assertFalse(report["flash_ready"])
        self.assertEqual("a" * 64, report["wlan"]["visible_wlan_modules"][0]["sha256"])
        self.assertEqual("_b", report["device"]["active_slot"])
        self.assertIn("-r", [x for call in run.call_args_list for x in call.args[0]])

    @patch.object(MODULE.subprocess, "run", side_effect=fake_run)
    def test_serial_passed_only_as_separate_argument(self, run):
        MODULE.collect("device-123:5555")
        self.assertTrue(all(call.args[0][1:3] == ["-s", "device-123:5555"]
                            for call in run.call_args_list))

    def test_rejects_serial_shell_metacharacters(self):
        with self.assertRaisesRegex(MODULE.DeviceEvidenceError, "serial"):
            MODULE.adb(["get-state"], "device; reboot")

    @patch.object(MODULE.subprocess, "run", side_effect=fake_run)
    def test_wrong_device_is_fail_closed(self, run):
        with patch.dict(PROPS, {"ro.product.device": "hotdogg"}):
            with self.assertRaisesRegex(MODULE.DeviceEvidenceError, "hotdog"):
                MODULE.collect()
        self.assertFalse(any("uname" in call.args[0] for call in run.call_args_list))

    @patch.object(MODULE.subprocess, "run", side_effect=fake_run)
    def test_android_16_is_fail_closed(self, run):
        with patch.dict(PROPS, {"ro.build.version.release": "16"}):
            with self.assertRaisesRegex(MODULE.DeviceEvidenceError, "Android 17"):
                MODULE.collect()
        self.assertFalse(any("uname" in call.args[0] for call in run.call_args_list))

    def test_untrusted_probe_values_are_ignored(self):
        text = "PATH\t/tmp/wlan.ko\nSHA256\t" + "b" * 64 + "\t/tmp/wlan.ko\n"
        inventory, _ = MODULE.parse_wlan_probe(text)
        self.assertEqual([], inventory["visible_wlan_modules"])

    def test_unreadable_module_never_counts_as_abi_verified(self):
        inventory, warnings = MODULE.parse_wlan_probe("PATH\t/vendor/lib/modules/wlan.ko\n")
        self.assertIsNone(inventory["visible_wlan_modules"][0]["sha256"])
        self.assertEqual([], warnings)

    @patch.object(MODULE.subprocess, "run", side_effect=fake_run)
    def test_optional_json_writes_only_to_local_new_file(self, run):
        with tempfile.TemporaryDirectory() as td:
            outfile = Path(td) / "evidence.json"
            self.assertEqual(0, MODULE.main(["--output", str(outfile)]))
            data = json.loads(outfile.read_text())
            self.assertFalse(data["flash_ready"])
            self.assertEqual(1, MODULE.main(["--output", str(outfile)]))

    @patch.object(MODULE.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "unauthorized"))
    def test_adb_failure_does_not_expose_stderr_or_approve(self, run):
        with self.assertRaisesRegex(MODULE.DeviceEvidenceError, "read command failed"):
            MODULE.collect()


if __name__ == "__main__":
    unittest.main()
