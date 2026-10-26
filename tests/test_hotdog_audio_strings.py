"""Offline bounded ELF string-offset probes with entirely synthetic ZIP fixtures."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "hotdog_audio_strings", ROOT / "scripts/audit-hotdog-audio-strings.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
PREFIX = "proprietary_vendor_oneplus_hotdog-17.0/"


def fake_elf(payload=b"\x00/odm/lib/liba2dpoffload.so\x00dlopen\x00dlsym\x00"):
    return b"\x7fELF\x01\x01\x01" + b"\x00" * 90 + payload + b"\x00" * 128


class AudioStringAuditTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.zip = Path(temp.name) / "vendor.zip"

    def build(self, payload=None, extra=None):
        content = fake_elf() if payload is None else payload
        with zipfile.ZipFile(self.zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr(PREFIX + mod.MEMBER, content)
            for name, blob in (extra or {}).items():
                z.writestr(PREFIX + name, blob)
        return content

    def test_expected_odm_string_and_precise_offset(self):
        content = self.build()
        result = mod.inspect(self.zip)
        a = result["patterns"]["/odm/lib/liba2dpoffload.so"]
        self.assertEqual(a["count"], 1)
        self.assertEqual(a["offset_samples"][0], content.index(b"/odm/lib/liba2dpoffload.so"))
        self.assertEqual(a["nul_delimited_ascii_samples"][0]["text"],
                         "/odm/lib/liba2dpoffload.so")
        self.assertEqual(result["patterns"]["dlopen"]["count"], 1)
        self.assertFalse(result["proves_dlopen_call"])
        self.assertFalse(result["elf_executed"])
        self.assertFalse(result["flash_ready"])

    def test_both_hashes_enforced(self):
        content = self.build()
        archive_digest = hashlib.sha256(self.zip.read_bytes()).hexdigest()
        elf_digest = hashlib.sha256(content).hexdigest()
        result = mod.inspect(self.zip, archive_digest, elf_digest)
        self.assertTrue(result["archive_sha256_matched"])
        self.assertTrue(result["elf_sha256_matched"])
        with self.assertRaises(mod.AudioStringError):
            mod.inspect(self.zip, "0" * 64, elf_digest)
        with self.assertRaises(mod.AudioStringError):
            mod.inspect(self.zip, archive_digest, "0" * 64)

    def test_legacy_vendor_string(self):
        self.build(fake_elf(b"\x00/vendor/lib/liba2dpoffload.so\x00"))
        result = mod.inspect(self.zip)
        self.assertEqual(result["patterns"]["/odm/lib/liba2dpoffload.so"]["count"], 0)
        self.assertEqual(result["patterns"]["/vendor/lib/liba2dpoffload.so"]["count"], 1)

    def test_bounded_unterminated_long_string_not_rendered(self):
        payload = b"\x00" + b"A" * 400 + b"dlopen" + b"\x00"
        self.build(fake_elf(payload))
        report = mod.inspect(self.zip)["patterns"]["dlopen"]
        self.assertEqual(report["count"], 1)
        self.assertEqual(report["nul_delimited_ascii_samples"], [])

    def test_deny_non_elf(self):
        self.build(b"x" * 120)
        with self.assertRaises(mod.AudioStringError):
            mod.inspect(self.zip)

    def test_deny_path_traversal(self):
        self.build(extra={"../evil.txt": b"x"})
        with self.assertRaises(mod.AudioStringError):
            mod.inspect(self.zip)

    def test_no_archive_member_missing(self):
        with zipfile.ZipFile(self.zip, "w") as z:
            z.writestr(PREFIX + "hotdog-vendor.mk", "nothing")
        with self.assertRaises(mod.AudioStringError):
            mod.inspect(self.zip)


if __name__ == "__main__":
    unittest.main()
