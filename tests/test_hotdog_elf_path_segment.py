"""Offline synthetic test cases for ELF embedded-path section/import probe."""
import hashlib
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "hotdog_elf_path", ROOT / "scripts/audit-hotdog-elf-path-segment.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def fixture_elf(import_dlopen=True, sections=True):
    b = bytearray(0x600)
    b[:7] = b"\x7fELF\x01\x01\x01"
    struct.pack_into(
        "<HHIIIIIHHHHHH", b, 16,
        3, 40, 1, 0, 52, 0x380 if sections else 0, 0,
        52, 32, 1, 40 if sections else 0, 5 if sections else 0, 1 if sections else 0
    )
    struct.pack_into("<IIIIIIII", b, 52, 1, 0, 0x1000, 0, 0x600, 0x600, 4, 0x1000)
    names = b"\x00.shstrtab\x00.rodata\x00.dynsym\x00.dynstr\x00"
    b[0x100:0x100+len(names)] = names
    target = mod.TARGET
    b[0x200:0x200+len(target)] = target
    symbol_names = b"\x00dlopen\x00dlsym\x00"
    b[0x260:0x260+len(symbol_names)] = symbol_names
    struct.pack_into("<IIIBBH", b, 0x2b0, 1, 0, 0, 18, 0,
                     0 if import_dlopen else 2)
    struct.pack_into("<IIIBBH", b, 0x2c0, 8, 0, 0, 18, 0, 0)
    if sections:
        def section(i, key, typ, addr, off, size, link=0, entry=0):
            struct.pack_into("<IIIIIIIIII", b, 0x380+40*i,
                names.find(b"." + key.encode()) if key else 0,
                typ, 2 if key == "rodata" else 0, addr, off, size, link, 0, 1, entry)
        section(0, "", 0, 0, 0, 0)
        section(1, "shstrtab", 3, 0, 0x100, len(names))
        section(2, "rodata", 1, 0x11e0, 0x1e0, 0x60)
        section(3, "dynsym", 11, 0, 0x2a0, 48, 4, 16)
        section(4, "dynstr", 3, 0, 0x260, len(symbol_names))
    return bytes(b)


class HotdogElfPathTests(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.zip = Path(d.name) / "vendor.zip"

    def zip_file(self, blob, extra=None):
        with zipfile.ZipFile(self.zip, "w") as z:
            z.writestr(mod.WRAPPER + mod.MEMBER, blob)
            for key, val in (extra or {}).items():
                z.writestr(mod.WRAPPER + key, val)
        return (hashlib.sha256(self.zip.read_bytes()).hexdigest(),
                hashlib.sha256(blob).hexdigest())

    def test_locates_path_in_rodata_and_undefined_dlopen(self):
        blob = fixture_elf()
        sha_zip, sha_elf = self.zip_file(blob)
        r = mod.inspect(self.zip, sha_zip, sha_elf)
        self.assertEqual(r["path_file_offset"], 0x200)
        self.assertEqual(r["load_segment_mapping"][0]["virtual_address"], 0x1200)
        self.assertEqual(r["containing_sections"][0]["name"], ".rodata")
        self.assertTrue(r["dlopen_undefined_import_observed"])
        self.assertEqual(r["status"], "PATH_MAPPED_AND_DLOPEN_IMPORT_OBSERVED")
        self.assertFalse(r["proves_runtime_dlopen_path_argument"])
        self.assertFalse(r["binary_extracted"])
        self.assertFalse(r["flash_ready"])

    def test_defined_dlopen_is_not_import(self):
        blob = fixture_elf(import_dlopen=False)
        result = mod.inspect_elf(blob)
        self.assertFalse(result["dlopen_undefined_import_observed"])
        self.assertEqual(result["status"], "PATH_MAPPED_DLOPEN_IMPORT_UNVERIFIED")

    def test_stripped_section_table_is_unknown(self):
        result = mod.inspect_elf(fixture_elf(sections=False))
        self.assertFalse(result["section_table_available"])
        self.assertIsNone(result["dlopen_undefined_import_observed"])
        self.assertEqual(result["load_segment_mapping"][0]["virtual_address"], 0x1200)

    def test_non_nul_delimited_path_refused(self):
        blob = bytearray(fixture_elf())
        blob[0x200 - 1] = 65
        with self.assertRaises(mod.ElfReferenceError):
            mod.inspect_elf(bytes(blob))

    def test_bad_sha_rejected(self):
        self.zip_file(fixture_elf())
        with self.assertRaises(mod.ElfReferenceError):
            mod.inspect(self.zip, "0" * 64, "0" * 64)

    def test_traversal_rejected(self):
        blob = fixture_elf()
        x, y = self.zip_file(blob, {"../bad": b"x"})
        with self.assertRaises(mod.ElfReferenceError):
            mod.inspect(self.zip, x, y)

    def test_wrong_arch_rejected(self):
        blob = bytearray(fixture_elf())
        struct.pack_into("<H", blob, 18, 183)
        with self.assertRaises(mod.ElfReferenceError):
            mod.inspect_elf(bytes(blob))


if __name__ == "__main__":
    unittest.main()
