import hashlib
import importlib.util
import struct
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit-bootimg.py"
SPEC = importlib.util.spec_from_file_location("bootimg_audit", SCRIPT)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)
PAGE = 4096


def fixture(root):
    boot = bytearray(PAGE * 4)
    boot[:8] = b"ANDROID!"
    fields = {
        8: 96, 16: 20, 24: 0, 36: PAGE, 40: 2,
        44: 0, 1632: 0, 1644: 1660, 1648: 128,
    }
    for pos, value in fields.items():
        struct.pack_into("<I", boot, pos, value)
    struct.pack_into("<Q", boot, 1636, 0)
    struct.pack_into("<Q", boot, 1652, 0xA00000)
    boot[PAGE + 0x38:PAGE + 0x3C] = b"ARM\x64"
    boot[PAGE * 2:PAGE * 2 + 4] = b"\x04\x22\x4d\x18"
    boot[PAGE * 3:PAGE * 3 + 4] = b"\xd0\x0d\xfe\xed"
    path = root / "original-boot.img"
    path.write_bytes(boot)
    return path


class BootImageTests(unittest.TestCase):
    def test_valid_structure_does_not_approve_flash(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = fixture(Path(tmp))
            report = MOD.inspect(file, hashlib.sha256(file.read_bytes()).hexdigest())
            self.assertEqual(2, report["header_version"])
            self.assertEqual(PAGE * 3, report["sections"]["dtb"]["offset"])
            self.assertEqual(20, report["sections"]["ramdisk"]["size"])
            self.assertTrue(report["hash_matched_expected"])
            self.assertFalse(report["avb_verified"])
            self.assertFalse(report["flash_ready"])

    def test_wrong_device_page_size_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = fixture(Path(tmp))
            data = bytearray(file.read_bytes())
            struct.pack_into("<I", data, 36, 2048)
            file.write_bytes(data)
            with self.assertRaisesRegex(ValueError, "Wrong page size"):
                MOD.inspect(file)

    def test_header_v3_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = fixture(Path(tmp))
            data = bytearray(file.read_bytes())
            struct.pack_into("<I", data, 40, 3)
            file.write_bytes(data)
            with self.assertRaisesRegex(ValueError, "Expected boot header v2"):
                MOD.inspect(file)

    def test_truncated_dtb_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = fixture(Path(tmp))
            file.write_bytes(file.read_bytes()[:PAGE * 3 + 64])
            with self.assertRaisesRegex(ValueError, "Truncated dtb"):
                MOD.inspect(file)

    def test_kernel_magic_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = fixture(Path(tmp))
            data = bytearray(file.read_bytes())
            data[PAGE + 0x38] = 0
            file.write_bytes(data)
            with self.assertRaisesRegex(ValueError, "ARM64"):
                MOD.inspect(file)

    def test_dtb_magic_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = fixture(Path(tmp))
            data = bytearray(file.read_bytes())
            data[PAGE * 3] = 0
            file.write_bytes(data)
            with self.assertRaisesRegex(ValueError, "FDT magic"):
                MOD.inspect(file)

    def test_expected_hash_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = fixture(Path(tmp))
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                MOD.inspect(file, "0" * 64)

    def test_nonzero_recovery_offset_without_payload_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = fixture(Path(tmp))
            data = bytearray(file.read_bytes())
            struct.pack_into("<Q", data, 1636, PAGE * 3)
            file.write_bytes(data)
            with self.assertRaisesRegex(ValueError, "Recovery DTBO offset set"):
                MOD.inspect(file)

    def test_recovery_dtbo_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = fixture(Path(tmp))
            data = bytearray(file.read_bytes())
            # recovery dtbo occupies fourth page, then DTB moves to fifth.
            data.extend(bytearray(PAGE))
            struct.pack_into("<I", data, 1632, 64)
            struct.pack_into("<Q", data, 1636, PAGE * 3)
            data[PAGE * 3:PAGE * 3 + 64] = bytes(64)
            data[PAGE * 4:PAGE * 4 + 4] = b"\xd0\x0d\xfe\xed"
            file.write_bytes(data)
            report = MOD.inspect(file)
            self.assertEqual(PAGE * 4, report["sections"]["dtb"]["offset"])
            self.assertEqual(PAGE * 3, report["sections"]["recovery_dtbo"]["offset"])


if __name__ == "__main__":
    unittest.main()
