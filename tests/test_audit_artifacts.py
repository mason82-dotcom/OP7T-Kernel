import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit-artifacts.py"
SPEC = importlib.util.spec_from_file_location("audit_artifacts", SCRIPT)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)
SOURCE_SHA = "1083c6c5906114c71b11a429898b111a1b1b8109"


def fixture(root):
    image = bytearray(64)
    image[0x38:0x3c] = b"ARM\x64"
    (root / "Image").write_bytes(image)
    (root / "kernel.config").write_text(
        "CONFIG_MODULE_SIG_FORCE=y\nCONFIG_QCA_CLD_WLAN=m\nCONFIG_USB_CONFIGFS_F_HID=y\n"
    )
    (root / "upstream-commit.txt").write_text(SOURCE_SHA + "\n")
    (root / "kernel.release").write_text("4.14.357-perf\n")
    (root / "dtbs").mkdir()
    (root / "dtbs" / "hotdog.dtb").write_bytes(b"dtb-data")
    (root / "modules").mkdir()
    (root / "modules" / "wlan.ko").write_bytes(b"not-ELF-for-mocking")


class AuditTests(unittest.TestCase):
    def test_good_fixture_never_claims_flash_ready(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            fixture(root)
            fake = {
                "path": "modules/wlan.ko",
                "size_bytes": 16,
                "sha256": "0" * 64,
                "vermagic": "4.14.357-perf SMP",
                "signer": "testing-only",
                "has_embedded_signature": True,
            }
            with patch.object(AUDIT, "module_metadata", return_value=fake):
                report = AUDIT.collect(root, SOURCE_SHA, "baseline")
            self.assertFalse(report["flash_ready"])
            self.assertFalse(report["rom_module_key_trust_verified"])
            self.assertFalse(report["module_signature_load_blocked"])
            self.assertEqual(1, report["module_count"])
            self.assertEqual(1, report["dtb_count"])
            self.assertEqual("RAW_ARTIFACT_ONLY_UNVERIFIED", report["status"])

    def test_unsigned_module_marks_runtime_load_blocker(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            fixture(root)
            unsigned = {
                "path": "modules/wlan.ko",
                "vermagic": "4.14.357-perf SMP",
                "signer": None,
                "has_embedded_signature": False,
            }
            with patch.object(AUDIT, "module_metadata", return_value=unsigned):
                report = AUDIT.collect(root, SOURCE_SHA, "baseline")
            self.assertTrue(report["module_signature_enforcement"])
            self.assertTrue(report["module_signature_load_blocked"])
            self.assertEqual(["modules/wlan.ko"], report["unsigned_modules"])
            self.assertEqual("blocked_unsigned_modules", report["module_runtime_compatibility"])
            self.assertFalse(report["flash_ready"])

    def test_corrupt_image_fails_closed(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            fixture(root)
            (root / "Image").write_bytes(b"not a kernel")
            with self.assertRaisesRegex(ValueError, "too short"):
                AUDIT.collect(root, SOURCE_SHA, "baseline")

    def test_mismatching_commit_fails_closed(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            fixture(root)
            with self.assertRaisesRegex(ValueError, "source mismatch"):
                AUDIT.collect(root, "0" * 40, "baseline")

    def test_missing_dtb_fails_closed(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            fixture(root)
            (root / "dtbs" / "hotdog.dtb").unlink()
            with self.assertRaisesRegex(ValueError, "No DTBs"):
                AUDIT.collect(root, SOURCE_SHA, "baseline")

    def test_vermagic_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            fixture(root)
            bad = {
                "path": "modules/wlan.ko",
                "vermagic": "4.14.350-perf SMP",
                "signer": None,
                "has_embedded_signature": False,
            }
            with patch.object(AUDIT, "module_metadata", return_value=bad):
                with self.assertRaisesRegex(ValueError, "vermagic"):
                    AUDIT.collect(root, SOURCE_SHA, "baseline")

    def test_missing_wlan_module_fails_closed(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            fixture(root)
            unrelated = {
                "path": "modules/other.ko",
                "vermagic": "4.14.357-perf SMP",
                "signer": None,
                "has_embedded_signature": False,
            }
            with patch.object(AUDIT, "module_metadata", return_value=unrelated):
                with self.assertRaisesRegex(ValueError, "no built Qualcomm WLAN"):
                    AUDIT.collect(root, SOURCE_SHA, "baseline")

    def test_missing_modinfo_fails_closed(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            fixture(root)
            with patch.object(AUDIT.subprocess, "run", side_effect=FileNotFoundError()):
                with self.assertRaisesRegex(ValueError, "Cannot inspect module"):
                    AUDIT.collect(root, SOURCE_SHA, "baseline")


if __name__ == "__main__":
    unittest.main()
