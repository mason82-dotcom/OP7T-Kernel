"""Offline synthetic ELF32 ARM DT_NEEDED tests; no proprietary files."""
import hashlib
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "hotdog_audio_elf", ROOT / "scripts/audit-hotdog-audio-elf.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
WRAP = "proprietary_vendor_oneplus_hotdog-17.0/"


def fake_elf(needed, soname="audio.primary.msmnile.so"):
    """Minimal syntactically valid ELF32 program headers and string table."""
    buf = bytearray(0x400)
    buf[0:16] = b"\x7fELF" + bytes([1, 1, 1, 0]) + b"\x00" * 8
    struct.pack_into(
        "<HHIIIIIHHHHHH", buf, 16,
        3, 40, 1, 0, 52, 0, 0, 52, 32, 2, 0, 0, 0
    )
    # Load everything including PT_DYNAMIC, with 0x1000 file virtual base.
    struct.pack_into("<IIIIIIII", buf, 52, 1, 0, 0x1000, 0, 0x400, 0x400, 4, 0x1000)
    strings = b"\x00"
    offsets = []
    for name in needed:
        offsets.append(len(strings))
        strings += name.encode("ascii") + b"\x00"
    soname_offset = len(strings)
    strings += soname.encode("ascii") + b"\x00"
    assert len(strings) < 0x200
    buf[0x180:0x180 + len(strings)] = strings
    tags = [(5, 0x1180), (10, len(strings))]
    tags.extend((1, offset) for offset in offsets)
    tags.extend(((14, soname_offset), (0, 0)))
    dynsize = 8 * len(tags)
    struct.pack_into("<IIIIIIII", buf, 84, 2, 0x100, 0x1100, 0, dynsize, dynsize, 4, 4)
    for i, (tag, value) in enumerate(tags):
        struct.pack_into("<II", buf, 0x100 + i * 8, tag, value)
    return bytes(buf)


class AudioELFAuditTests(unittest.TestCase):
    def setUp(self):
        workspace = tempfile.TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        self.archive = Path(workspace.name) / "vendor.zip"

    def makezip(self, data):
        with zipfile.ZipFile(self.archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr(
                WRAP + "proprietary/odm/lib/hw/audio.primary.msmnile.so", data
            )
        return hashlib.sha256(self.archive.read_bytes()).hexdigest()

    def test_expected_odm_needed_path(self):
        self.makezip(fake_elf([mod.NEW_NEEDED, "libc.so"]))
        report = mod.inspect_archive(self.archive)
        self.assertEqual(report["status"], "EXPECTED_ODM_NEEDED_PATH_PRESENT")
        self.assertTrue(report["expected_dynamic_fixup_verified"])
        self.assertEqual(report["needed_count"], 2)
        self.assertEqual(report["soname"], "audio.primary.msmnile.so")
        self.assertFalse(report["elf_written_to_disk"])
        self.assertFalse(report["elf_executed"])
        self.assertFalse(report["flash_ready"])

    def test_legacy_vendor_path(self):
        self.makezip(fake_elf([mod.OLD_NEEDED]))
        report = mod.inspect_archive(self.archive)
        self.assertEqual(report["status"], "LEGACY_VENDOR_NEEDED_PATH_PRESENT")
        self.assertFalse(report["expected_dynamic_fixup_verified"])

    def test_no_expected_full_path(self):
        self.makezip(fake_elf(["liba2dpoffload.so"]))
        report = mod.inspect_archive(self.archive)
        self.assertEqual(report["status"], "EXPECTED_FULLPATH_NEEDED_NOT_OBSERVED")

    def test_both_paths_ambiguous(self):
        self.makezip(fake_elf([mod.OLD_NEEDED, mod.NEW_NEEDED]))
        report = mod.inspect_archive(self.archive)
        self.assertEqual(report["status"], "BOTH_LEGACY_AND_ODM_NEEDED_PATHS")
        self.assertFalse(report["expected_dynamic_fixup_verified"])

    def test_user_archive_digest_must_match(self):
        expected = self.makezip(fake_elf([mod.NEW_NEEDED]))
        self.assertTrue(mod.inspect_archive(self.archive, expected)["local_zip_sha256_verified"])
        with self.assertRaises(mod.ElfAuditError):
            mod.inspect_archive(self.archive, "0" * 64)

    def test_deny_invalid_elf_magic(self):
        self.makezip(b"\x00" * 600)
        with self.assertRaises(mod.ElfAuditError):
            mod.inspect_archive(self.archive)

    def test_deny_out_of_bounds_string_pointer(self):
        blob = bytearray(fake_elf([mod.NEW_NEEDED]))
        struct.pack_into("<II", blob, 0x100, 5, 0x999999)
        self.makezip(bytes(blob))
        with self.assertRaises(mod.ElfAuditError):
            mod.inspect_archive(self.archive)

    def test_deny_path_traversal(self):
        self.makezip(fake_elf([mod.NEW_NEEDED]))
        with zipfile.ZipFile(self.archive, "a") as z:
            z.writestr(WRAP + "../bad", b"bad")
        with self.assertRaises(mod.ElfAuditError):
            mod.inspect_archive(self.archive)

    def test_no_dependency_rejected(self):
        blob = bytearray(fake_elf([mod.NEW_NEEDED]))
        # The third entry originally is DT_NEEDED; replace with unknown tag.
        struct.pack_into("<I", blob, 0x110, 777)
        self.makezip(bytes(blob))
        with self.assertRaises(mod.ElfAuditError):
            mod.inspect_archive(self.archive)


if __name__ == "__main__":
    unittest.main()
