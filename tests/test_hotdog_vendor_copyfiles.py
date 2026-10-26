"""Synthetic tests for metadata-only, static hotdog vendor PRODUCT_COPY_FILES audit."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "vendor_copyfiles", ROOT / "scripts/audit-hotdog-vendor-copyfiles.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
ROOT_ZIP = "proprietary_vendor_oneplus_hotdog-17.0/"


class CopyfileAuditTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.zip = Path(temp.name) / "vendor.zip"

    def make_zip(self, product, extra=None, board=b"# BoardConfigVendor.mk\n"):
        files = {
            ROOT_ZIP + "BoardConfigVendor.mk": board,
            ROOT_ZIP + "hotdog-vendor.mk": product,
            ROOT_ZIP + "proprietary/odm/etc/wifi/config.bin": b"\x01\x02\x03",
        }
        files.update(extra or {})
        with zipfile.ZipFile(self.zip, "w") as z:
            for name, data in files.items():
                z.writestr(name, data)

    def test_local_copyfile_found_across_backslash_lines(self):
        self.make_zip(
            b"PRODUCT_COPY_FILES += \\\n"
            b" vendor/oneplus/hotdog/proprietary/odm/etc/wifi/config.bin:"
            b"$(TARGET_COPY_OUT_ODM)/etc/wifi/config.bin\n"
        )
        result = module.inspect(self.zip)
        self.assertEqual(result["copy_tokens"], 1)
        self.assertEqual(result["local_source_rules_found_in_zip"], 1)
        self.assertEqual(result["local_source_rules_missing_in_zip"], 0)
        self.assertEqual(result["status"], "STATIC_COPY_REFERENCES_RESOLVE")
        self.assertFalse(result["flash_ready"])
        self.assertFalse(result["vendor_files_extracted"])

    def test_missing_and_duplicate_destinations_reported(self):
        self.make_zip(
            b"PRODUCT_COPY_FILES += \\\n"
            b" vendor/oneplus/hotdog/proprietary/no-such.bin:odm/etc/target \\\n"
            b" vendor/oneplus/hotdog/proprietary/odm/etc/wifi/config.bin:odm/etc/target\n"
        )
        result = module.inspect(self.zip)
        self.assertEqual(result["local_source_rules_missing_in_zip"], 1)
        self.assertEqual(result["duplicate_destination_count"], 1)
        self.assertEqual(result["status"], "COPY_SOURCE_REFERENCE_GAPS")

    def test_dynamic_source_is_unresolved_not_missing(self):
        self.make_zip(
            b"PRODUCT_COPY_FILES += $(VENDOR_ROOT)/generated.bin:odm/etc/generated.bin\n"
        )
        result = module.inspect(self.zip)
        self.assertEqual(result["nonliteral_or_unparsed_rule_count"], 1)
        self.assertEqual(result["local_source_rules_missing_in_zip"], 0)
        self.assertFalse(result["installed_rom_compatibility_verified"])

    def test_nonliteral_external_source_not_considered_local(self):
        self.make_zip(
            b"PRODUCT_COPY_FILES += external/project/a.bin:vendor/etc/a.bin\n"
        )
        result = module.inspect(self.zip)
        self.assertEqual(result["external_source_rule_count"], 1)
        self.assertEqual(result["local_source_rules_missing_in_zip"], 0)

    def test_active_board_lines_and_package_count(self):
        self.make_zip(
            b"PRODUCT_PACKAGES += TestPackage\n",
            board=b"# comment\nBOARD_BOOT_HEADER_VERSION := 2\n",
        )
        result = module.inspect(self.zip)
        self.assertIn("BOARD_BOOT_HEADER_VERSION",
                      result["boardconfig_active_lines"][0]["text"])
        self.assertEqual(result["package_token_count"], 1)

    def test_path_traversal_rejected(self):
        self.make_zip(
            b"PRODUCT_PACKAGES += TestPackage\n",
            extra={ROOT_ZIP + "../unexpected": b"bad"},
        )
        with self.assertRaises(module.VendorAuditError):
            module.inspect(self.zip)

    def test_missing_required_makefile_rejected(self):
        with zipfile.ZipFile(self.zip, "w") as z:
            z.writestr(ROOT_ZIP + "BoardConfigVendor.mk", b"# only\n")
        with self.assertRaises(module.VendorAuditError):
            module.inspect(self.zip)


    def test_radio_names_match_board_ota_partition_inventory(self):
        self.make_zip(
            b"PRODUCT_PACKAGES += audio.primary.msmnile_odm com.qti.sensor.imx471\n",
            board=b"AB_OTA_PARTITIONS += \\\n LOGO \\\n modem\n",
            extra={
                ROOT_ZIP + "radio/LOGO.img": b"do not flash",
                ROOT_ZIP + "radio/modem.img": b"do not flash",
                ROOT_ZIP + "proprietary/odm/lib/hw/audio.primary.msmnile.so": b"fake",
                ROOT_ZIP + "proprietary/odm/lib64/camera/com.qti.sensor.imx471.so": b"fake",
            },
        )
        result = module.inspect(self.zip)
        self.assertEqual(result["ab_ota_partition_count"], 2)
        self.assertEqual(result["radio_image_count"], 2)
        self.assertEqual(result["radio_partition_filename_alignment"], "STATIC_NAMES_MATCH")
        self.assertEqual(result["ab_ota_partitions_without_radio_image"], [])
        self.assertEqual(result["radio_images_without_ab_ota_partition"], [])
        self.assertEqual(result["package_with_heuristic_library_candidate_count"], 2)
        self.assertEqual(result["package_without_heuristic_library_candidate_count"], 0)
        self.assertFalse(result["flash_ready"])

    def test_radio_gap_not_considered_resolved(self):
        self.make_zip(
            b"PRODUCT_PACKAGES += FakeModule\n",
            board=b"AB_OTA_PARTITIONS += modem dsp\n",
            extra={ROOT_ZIP + "radio/modem.img": b"fake"},
        )
        result = module.inspect(self.zip)
        self.assertEqual(result["ab_ota_partitions_without_radio_image"], ["dsp"])
        self.assertEqual(result["radio_partition_filename_alignment"],
                         "RADIO_NAMES_UNVERIFIED_OR_DIFFERENT")
        self.assertEqual(result["package_without_heuristic_library_candidate_count"], 1)

    def test_no_board_ota_evidence_is_not_vacuous_match(self):
        self.make_zip(b"PRODUCT_PACKAGES += FakeModule\n")
        result = module.inspect(self.zip)
        self.assertEqual(result["ab_ota_partition_count"], 0)
        self.assertEqual(result["radio_partition_filename_alignment"],
                         "RADIO_NAMES_UNVERIFIED_OR_DIFFERENT")

    def test_duplicate_board_ota_partition_rejected_as_match(self):
        self.make_zip(
            b"PRODUCT_PACKAGES += FakeModule\n",
            board=b"AB_OTA_PARTITIONS += modem modem\n",
            extra={ROOT_ZIP + "radio/modem.img": b"fake"},
        )
        result = module.inspect(self.zip)
        self.assertEqual(result["ab_ota_duplicate_partition_count"], 1)
        self.assertEqual(result["radio_partition_filename_alignment"],
                         "RADIO_NAMES_UNVERIFIED_OR_DIFFERENT")


if __name__ == "__main__":
    unittest.main()
