"""No-network synthetic fixture tests for the hotdog vendor Soong name probe."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

BASE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "hotdog_soong_probe", BASE / "scripts/audit-hotdog-vendor-soong-names.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
ROOT = "proprietary_vendor_oneplus_hotdog-17.0/"


class VendorSoongNameTests(unittest.TestCase):
    def setUp(self):
        workspace = tempfile.TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        self.path = Path(workspace.name) / "vendor.zip"

    def write_zip(self, bp=None, mk=None, packages=b"PRODUCT_PACKAGES += liba libb\n"):
        members = {
            ROOT + "hotdog-vendor.mk": packages,
            ROOT + "BoardConfigVendor.mk": b"# not installed\n",
        }
        if bp is not None:
            members[ROOT + "Android.bp"] = bp
        if mk is not None:
            members[ROOT + "Android.mk"] = mk
        with zipfile.ZipFile(self.path, "w") as z:
            for path, data in members.items():
                z.writestr(path, data)

    def test_detect_blueprint_package_name_tokens(self):
        self.write_zip(bp=b'cc_prebuilt_library_shared {\n    name: "liba",\n'
                          b'    srcs: ["proprietary/odm/lib64/liba.so"],\n}\n'
                          b'cc_prebuilt_library_shared {\n    name: "libb",\n}\n')
        r = module.inspect(self.path)
        self.assertEqual(r["missing_module_name_token_count"], 0)
        self.assertEqual(r["status"], "ALL_PACKAGE_NAMES_LEXICALLY_PRESENT")
        self.assertFalse(r["module_definitions_semantically_verified"])
        self.assertFalse(r["flash_ready"])

    def test_detect_make_based_module(self):
        self.write_zip(mk=b'include $(CLEAR_VARS)\nLOCAL_MODULE := liba\n'
                          b'include $(BUILD_PREBUILT)\nLOCAL_MODULE := libb\n')
        r = module.inspect(self.path)
        self.assertEqual(r["missing_module_name_token_count"], 0)
        self.assertTrue(r["product_package_name_candidates"]["liba"]
                        ["android_mk_local_module_token"])

    def test_report_missing_when_not_generated(self):
        self.write_zip(bp=b'cc_prebuilt_library_shared { name: "other", }\n')
        r = module.inspect(self.path)
        self.assertEqual(r["missing_module_name_token_count"], 2)
        self.assertEqual(r["status"], "PACKAGE_NAME_TOKENS_MISSING_OR_UNDECLARED")

    def test_zip_traversal_rejected(self):
        self.write_zip()
        with zipfile.ZipFile(self.path, "a") as z:
            z.writestr(ROOT + "../unsafe", "fake")
        with self.assertRaises(module.VendorSoongAuditError):
            module.inspect(self.path)

    def test_no_binary_contents_read(self):
        self.write_zip(bp=b'name: "liba"\nname: "libb"\n')
        with zipfile.ZipFile(self.path, "a") as z:
            z.writestr(ROOT + "proprietary/odm/secret.so", b"SECRET")
        r = module.inspect(self.path)
        self.assertNotIn("SECRET", str(r))
        self.assertFalse(r["vendor_archive_extracted"])

    def test_reject_invalid_utf8(self):
        self.write_zip(bp=b"\xff\xfe")
        with self.assertRaises(module.VendorSoongAuditError):
            module.inspect(self.path)

    def test_product_multiline_rules(self):
        self.write_zip(bp=b'name: "liba",\nname: "libb",\n',
                       packages=b"PRODUCT_PACKAGES += \\\n liba \\\n libb\n")
        self.assertEqual(module.inspect(self.path)["product_package_count"], 2)


if __name__ == "__main__":
    unittest.main()
