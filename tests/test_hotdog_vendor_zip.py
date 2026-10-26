"""Synthetic ZIP-only tests; never download or open proprietary vendor blobs."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/inspect-hotdog-vendor-zip.py"
spec = importlib.util.spec_from_file_location("hotdog_vendor_zip", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
PREFIX = "proprietary_vendor_oneplus_hotdog-17.0-abcdef123/"


class VendorArchiveTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "vendor.zip"

    def make_zip(self, names):
        with zipfile.ZipFile(self.path, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for name in names:
                z.writestr(name, b"test")

    def test_expected_makefiles_and_module_metadata(self):
        self.make_zip([
            PREFIX + "BoardConfigVendor.mk",
            PREFIX + "hotdog-vendor.mk",
            PREFIX + "proprietary/vendor/lib/modules/example.ko",
        ])
        actual = module.inspect(self.path)
        self.assertTrue(actual["expected_makefiles_present"])
        self.assertEqual(actual["kernel_module_count_in_archive"], 1)
        self.assertEqual(actual["status"], "VENDOR_ZIP_METADATA_ONLY")
        self.assertFalse(actual["flash_ready"])
        self.assertFalse(actual["archive_source_commit_verified"])

    def test_zip_slip_path_rejected(self):
        self.make_zip([PREFIX + "../bad", PREFIX + "BoardConfigVendor.mk"])
        with self.assertRaises(module.VendorArchiveError):
            module.inspect(self.path)

    def test_duplicate_rejected(self):
        self.make_zip([PREFIX + "BoardConfigVendor.mk",
                       PREFIX + "hotdog-vendor.mk",
                       PREFIX + "hotdog-vendor.mk"])
        with self.assertRaises(module.VendorArchiveError):
            module.inspect(self.path)

    def test_absent_makefile_reported_incomplete(self):
        self.make_zip([PREFIX + "BoardConfigVendor.mk"])
        actual = module.inspect(self.path)
        self.assertEqual(actual["status"], "VENDOR_ZIP_EXPECTED_MAKEFILES_MISSING")
        self.assertFalse(actual["expected_makefiles_present"])

    def test_wrong_root_rejected(self):
        self.make_zip(["proprietary_vendor_oneplus_hotdogg-17.0/BoardConfigVendor.mk"])
        with self.assertRaises(module.VendorArchiveError):
            module.inspect(self.path)

    def test_wrong_expected_sha_rejected(self):
        self.make_zip([PREFIX + "BoardConfigVendor.mk",
                       PREFIX + "hotdog-vendor.mk"])
        with self.assertRaises(module.VendorArchiveError):
            module.inspect(self.path, expected_sha256="0" * 64)

    def test_correct_expected_sha_passes_but_not_provenance(self):
        import hashlib
        self.make_zip([PREFIX + "BoardConfigVendor.mk",
                       PREFIX + "hotdog-vendor.mk"])
        digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        actual = module.inspect(self.path, expected_sha256=digest)
        self.assertTrue(actual["expected_sha256_verified"])
        self.assertFalse(actual["archive_source_commit_verified"])
        self.assertFalse(actual["flash_ready"])


if __name__ == "__main__":
    unittest.main()
