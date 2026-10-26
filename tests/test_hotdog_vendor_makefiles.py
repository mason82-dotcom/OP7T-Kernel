"""Offline synthetic tests for bounded vendor Makefile text reading."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "hotdog_vendor_makefile", ROOT / "scripts/inspect-hotdog-vendor-makefiles.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
PREFIX = "proprietary_vendor_oneplus_hotdog-17.0/"


class VendorMakefileTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.archive = Path(temp.name) / "vendor.zip"

    def write(self, extra=None, board=b"BOARD_VENDORIMAGE_PARTITION_SIZE := 123\n",
              product=b"PRODUCT_PACKAGES += Foo\n"):
        files = {
            PREFIX + "BoardConfigVendor.mk": board,
            PREFIX + "hotdog-vendor.mk": product,
        }
        files.update(extra or {})
        with zipfile.ZipFile(self.archive, "w") as f:
            for name, blob in files.items():
                f.writestr(name, blob)

    def test_only_makefile_text_reported(self):
        self.write(extra={
            PREFIX + "proprietary/vendor/lib64/libsecret.so": b"PRIVATE-SENTINEL",
        })
        result = module.inspect_makefiles(self.archive)
        self.assertFalse(result["flash_ready"])
        self.assertFalse(result["original_zip_extracted"])
        self.assertEqual(result["makefiles"]["BoardConfigVendor.mk"]["matching_line_count"], 1)
        self.assertEqual(result["makefiles"]["hotdog-vendor.mk"]["matching_line_count"], 1)
        self.assertNotIn("PRIVATE-SENTINEL", str(result))

    def test_missing_makefile_rejected(self):
        self.write()
        with zipfile.ZipFile(self.archive, "w") as z:
            pass
        self.archive.unlink()
        with zipfile.ZipFile(self.archive, "w") as z:
            z.writestr(PREFIX + "BoardConfigVendor.mk", b"BOARD_X=y\n")
        with self.assertRaises(module.VendorMakefileError):
            module.inspect_makefiles(self.archive)

    def test_binary_makefile_rejected(self):
        self.write(product=b"PRODUCT_PACKAGES\x00")
        with self.assertRaises(module.VendorMakefileError):
            module.inspect_makefiles(self.archive)

    def test_path_traversal_rejected(self):
        self.write(extra={PREFIX + "../bad": b""})
        with self.assertRaises(module.VendorMakefileError):
            module.inspect_makefiles(self.archive)

    def test_board_and_product_directive_detection(self):
        self.write(board=b"BOARD_BOOT_HEADER_VERSION := 2\n", product=
                   b"$(call inherit-product, vendor/oneplus/hotdog/hotdog-vendor.mk)\n")
        audit = module.inspect_makefiles(self.archive)
        lines = str(audit["makefiles"])
        self.assertIn("BOARD_BOOT_HEADER_VERSION", lines)
        self.assertIn("inherit-product", lines)


if __name__ == "__main__":
    unittest.main()
