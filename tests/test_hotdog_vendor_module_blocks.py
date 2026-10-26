"""Synthetic non-networked checks of hotdog vendor Blueprint module block probes."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "hotdog_bp_blocks", HERE / "scripts/audit-hotdog-vendor-module-blocks.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
PREFIX = "proprietary_vendor_oneplus_hotdog-17.0/"


class ModuleBlockProbeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "test.zip"

    def make_zip(self, bp, product=b"PRODUCT_PACKAGES += libone\n", extras=None):
        entries = {
            "hotdog-vendor.mk": product,
            "Android.bp": bp,
            "proprietary/odm/lib64/libone.so": b"SENSITIVE-BINARY-CONTENTS",
        }
        entries.update(extras or {})
        with zipfile.ZipFile(self.path, "w") as z:
            for rel, data in entries.items():
                z.writestr(PREFIX + rel, data)

    def test_typical_prebuilt_module_and_static_srcs(self):
        self.make_zip(b"""soong_namespace {}
cc_prebuilt_library_shared {
 name: "libone",
 vendor: true,
 compile_multilib: "64",
 arch: {
   arm64: {
     srcs: ["proprietary/odm/lib64/libone.so"],
   },
 },
 relative_install_path: "hw",
}
""")
        r = module.inspect(self.path)
        self.assertEqual(r["status"], "STATIC_BP_MODULE_CANDIDATES_FOUND")
        self.assertEqual(r["blueprint_top_level_blocks_found"], 2)
        m = r["product_package_blocks"]["libone"][0]
        self.assertEqual(m["module_type"], "cc_prebuilt_library_shared")
        self.assertEqual(m["src_literal_path_count"], 1)
        self.assertEqual(m["src_literal_found_count"], 1)
        self.assertFalse(r["flash_ready"])
        self.assertNotIn("SENSITIVE-BINARY-CONTENTS", str(r))

    def test_unmatched_src_fails_closed(self):
        self.make_zip(b'cc_prebuilt_library_shared {\n'
                      b' name: "libone",\n'
                      b' srcs: ["proprietary/odm/lib64/missing.so"],\n'
                      b'}\n')
        r = module.inspect(self.path)
        self.assertEqual(r["missing_static_src_path_samples_total"], 1)
        self.assertEqual(r["status"], "STATIC_BP_MODULE_GAPS")

    def test_comments_and_braces_in_string_not_end_block(self):
        self.make_zip(b'''// ignored: cc_prebuilt_library_shared {
// } tricky
cc_prebuilt_library_shared {
 name: "libone",
 stem: "literal } marker",
 srcs: ["proprietary/odm/lib64/libone.so"],
 /* fake nested }
 name: "not-a-real-module",
 */
}
''')
        r = module.inspect(self.path)
        self.assertEqual(len(r["product_package_blocks"]["libone"]), 1)
        self.assertEqual(r["status"], "STATIC_BP_MODULE_CANDIDATES_FOUND")

    def test_duplicate_block_name_fails(self):
        self.make_zip(b'cc_prebuilt_library_shared { name: "libone", }\n'
                      b'cc_prebuilt_library_shared { name: "libone", }\n')
        r = module.inspect(self.path)
        self.assertEqual(r["status"], "STATIC_BP_MODULE_GAPS")
        self.assertEqual(r["duplicate_package_module_names"], ["libone"])

    def test_missing_block_reports_gap(self):
        self.make_zip(b'cc_prebuilt_library_shared { name: "libtwo", }\n')
        r = module.inspect(self.path)
        self.assertEqual(r["missing_package_module_names"], ["libone"])

    def test_invalid_binary_blueprint_rejected(self):
        self.make_zip(b'\xff\xfe')
        with self.assertRaises(module.VendorModuleError):
            module.inspect(self.path)

    def test_traversal_rejected(self):
        self.make_zip(b'name: "libone",')
        with zipfile.ZipFile(self.path, "a") as z:
            z.writestr(PREFIX + "../unsafe.txt", b"evil")
        with self.assertRaises(module.VendorModuleError):
            module.inspect(self.path)

    def test_multiline_package_and_arch_sources(self):
        self.make_zip(
            b'cc_prebuilt_library_shared {\n name: "libone",\n'
            b' arch: { arm: { srcs: ["proprietary/odm/lib64/libone.so"] } },\n'
            b'}\n',
            product=b'PRODUCT_PACKAGES += \\\n libone\n',
        )
        self.assertEqual(module.inspect(self.path)["status"],
                         "STATIC_BP_MODULE_CANDIDATES_FOUND")


if __name__ == "__main__":
    unittest.main()
