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
    "ro.crdroid.version": "17.0",
    "ro.crdroid.build.version": "13.0",
    "ro.crdroid.display.version": "v13.0-20261021",
    "ro.system.build.fingerprint": "crdroid/hotdog/hotdog:17/test",
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
    elif len(tail) == 4 and tail[:3] == ["shell", "ls", "-ld"]:
        path = tail[3]
        if path == "/vendor/lib/modules":
            return subprocess.CompletedProcess(
                command, 0, "lrwxrwxrwx /vendor/lib/modules -> /vendor_dlkm/lib/modules\n", ""
            )
        if path == "/vendor/lib/modules/qca_cld3_wlan.ko":
            return subprocess.CompletedProcess(
                command, 1, "", "ls: Permission denied"
            )
        if path.endswith("/wlan.ko"):
            return subprocess.CompletedProcess(
                command, 1, "", "No such file or directory"
            )
        return subprocess.CompletedProcess(command, 0, "metadata available", "")
    elif len(tail) == 3 and tail[:2] == ["shell", "cat"]:
        if tail[2].endswith("/initstate"):
            return subprocess.CompletedProcess(command, 1, "", "Permission denied")
        return subprocess.CompletedProcess(command, 1, "", "No such file or directory")
    else:
        raise AssertionError(f"Unexpected ADB arguments: {tail}")
    return subprocess.CompletedProcess(command, 0, result, "")


class EvidenceTests(unittest.TestCase):
    @patch.object(MODULE.subprocess, "run", side_effect=fake_run)
    def test_real_device_style_access_denial_is_not_absence(self, run):
        report = MODULE.collect()
        diag = report["wlan"]["access_diagnostics"]
        self.assertEqual(
            "permission_denied",
            diag["paths"]["wlan_vendor_alias"]["status"],
        )
        self.assertEqual(
            "not_found_in_this_path",
            diag["paths"]["wlan_vendor_original"]["status"],
        )
        self.assertEqual(
            "permission_denied",
            diag["paths"]["wlan_kernel_initstate"]["status"],
        )
        self.assertEqual(
            "not_found_in_this_path",
            diag["paths"]["wlan_kernel_srcversion"]["status"],
        )
        self.assertTrue(diag["vendor_modules_link_to_vendor_dlkm_observed"])
        self.assertTrue(diag["no_access_is_not_evidence_of_absence"])
        self.assertFalse(diag["actual_module_source_or_abi_verified"])
        self.assertFalse(report["flash_ready"])

    def test_errno_classification_does_not_confuse_failures(self):
        self.assertEqual(
            "permission_denied",
            MODULE.classify_access(1, "", "Permission denied", "ls")
        )
        self.assertEqual(
            "not_found_in_this_path",
            MODULE.classify_access(1, "", "No such file or directory", "ls")
        )
        self.assertEqual(
            "unknown_error", MODULE.classify_access(42, "", "other error", "cat")
        )
        self.assertEqual(
            "metadata_visible", MODULE.classify_access(0, "ok", "", "ls")
        )
        self.assertEqual(
            "readable", MODULE.classify_access(0, "live", "", "cat")
        )

    @patch.object(MODULE.subprocess, "run", side_effect=fake_run)
    def test_fixed_probe_commands_never_write_or_exfiltrate_files(self, run):
        MODULE.probe_fixed_paths()
        self.assertEqual(len(MODULE.EXACT_ACCESS_PROBES), len(run.call_args_list))
        for call in run.call_args_list:
            command = call.args[0]
            self.assertEqual("adb", command[0])
            self.assertEqual("shell", command[1])
            self.assertIn(command[2], ("ls", "cat"))
            self.assertNotIn(command[2], ("pull", "push", "root", "remount"))
            self.assertTrue(command[-1].startswith(("/vendor/", "/vendor_dlkm/", "/sys/")))

    @patch.object(MODULE.subprocess, "run", side_effect=fake_run)
    def test_successful_read_only_json(self, run):
        report = MODULE.collect()
        self.assertEqual("hotdog", report["device"]["device"])
        self.assertFalse(report["flash_ready"])
        self.assertEqual("a" * 64, report["wlan"]["visible_wlan_modules"][0]["sha256"])
        self.assertEqual("_b", report["device"]["active_slot"])
        self.assertEqual("17.0", report["device"]["crdroid_version"])
        self.assertEqual("13.0", report["device"]["crdroid_build_version"])
        self.assertEqual("android_platform_version", report["crdroid_version_property_meaning"])
        self.assertFalse(any("crDroid" in w for w in report["warnings"]))
        self.assertIn("-r", [x for call in run.call_args_list for x in call.args[0]])

    @patch.object(MODULE.subprocess, "run", side_effect=fake_run)
    def test_serial_passed_only_as_separate_argument(self, run):
        MODULE.collect("device-123:5555")
        self.assertTrue(all(call.args[0][1:3] == ["-s", "device-123:5555"]
                            for call in run.call_args_list))

    @patch.object(MODULE.subprocess, "run", side_effect=fake_run)
    def test_missing_crdroid_release_emits_warning_not_approval(self, run):
        with patch.dict(PROPS, {"ro.crdroid.build.version": ""}):
            report = MODULE.collect()
        self.assertTrue(any("not confirmed as v13" in w for w in report["warnings"]))
        self.assertFalse(report["flash_ready"])

    @patch.object(MODULE.subprocess, "run", side_effect=fake_run)
    def test_stock_android_12_fingerprint_is_not_exact_rom_proof(self, run):
        with patch.dict(PROPS, {"ro.build.fingerprint": "OnePlus/OnePlus7TPro:12/stock-release"}):
            report = MODULE.collect()
        self.assertTrue(any("Android 12 OEM" in w for w in report["warnings"]))
        self.assertFalse(report["rom_fingerprint_is_authoritative_rom_proof"])

    def test_rejects_serial_shell_metacharacters(self):
        with self.assertRaisesRegex(MODULE.DeviceEvidenceError, "serial"):
            MODULE.adb(["get-state"], "device; reboot")

    @patch.object(MODULE.subprocess, "run", side_effect=fake_run)
    def test_oneplus_vendor_property_alias_accepted(self, run):
        with patch.dict(PROPS, {"ro.product.device": "OnePlus7TPro"}):
            result = MODULE.collect()
        self.assertTrue(result["device_property_is_oem_alias"])
        self.assertEqual("hotdog", result["target_device"])
        self.assertFalse(result["flash_ready"])

    @patch.object(MODULE.subprocess, "run", side_effect=fake_run)
    def test_mclaren_5g_alias_rejected(self, run):
        with patch.dict(PROPS, {"ro.product.device": "OnePlus7TProNR"}):
            with self.assertRaisesRegex(MODULE.DeviceEvidenceError, "hotdog"):
                MODULE.collect()

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
