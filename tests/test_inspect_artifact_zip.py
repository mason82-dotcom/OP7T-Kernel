import hashlib
import importlib.util
import json
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "inspect-artifact-zip.py"
SPEC = importlib.util.spec_from_file_location("artifact_zip", SCRIPT)
INTAKE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INTAKE)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def make_zip(path, *, tamper=False, duplicate=False, unsafe=False, full=False):
    module = b"synthetic module, never loaded"
    reported_path = "modules/drivers/wlan.ko"
    report = json.dumps({
        "schema": "op7t-kernel-artifact-report-v1", "device": "hotdog",
        "flash_ready": False, "profile": "core", "modules": [{
            "path": reported_path, "sha256": digest(module), "size_bytes": len(module),
        }],
    }).encode()
    checksum_lines = [
        f"{digest(report)}  ./artifact-report.json",
        f"{digest(module)}  ./{reported_path}",
        f"{digest(b'missing')}  ./Image",
    ]
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("artifact-report.json", report)
        archive.writestr("SHA256SUMS", "\n".join(checksum_lines) + "\n")
        archive.writestr(reported_path if full else "wlan.ko", b"tampered" if tamper else module)
        if full:
            archive.writestr("Image", b"missing")
        if duplicate:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                archive.writestr("wlan.ko", module)
        if unsafe:
            archive.writestr("../extra", b"x")


class IntakeTests(unittest.TestCase):
    def test_partial_export_maps_flat_module_to_reported_path(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "package.zip"
            make_zip(path)
            result = INTAKE.inspect(path)
            self.assertEqual("partial_verified_members", result["status"])
            self.assertEqual(["Image"], result["missing_manifest_members"])
            self.assertEqual("wlan.ko", result["verified_modules"][0]["zip_member"])
            self.assertFalse(result["flash_ready"])

    def test_complete_actions_export_preserves_module_path(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "package.zip"
            make_zip(path, full=True)
            result = INTAKE.inspect(path)
            self.assertEqual("complete_verified_members", result["status"])
            self.assertEqual([], result["missing_manifest_members"])
            self.assertEqual("modules/drivers/wlan.ko",
                             result["verified_modules"][0]["zip_member"])

    def test_tampered_module_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "package.zip"
            make_zip(path, tamper=True)
            with self.assertRaisesRegex(INTAKE.IntakeError, "module digest"):
                INTAKE.inspect(path)

    def test_duplicate_and_traversal_members_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "package.zip"
            make_zip(path, duplicate=True)
            with self.assertRaisesRegex(INTAKE.IntakeError, "Duplicate"):
                INTAKE.inspect(path)
            make_zip(path, unsafe=True)
            with self.assertRaisesRegex(INTAKE.IntakeError, "Unsafe"):
                INTAKE.inspect(path)


if __name__ == "__main__":
    unittest.main()
