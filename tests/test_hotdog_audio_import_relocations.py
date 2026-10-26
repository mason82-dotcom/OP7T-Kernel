"""Offline ELF32 synthetic import relocation slot audits for the audio HAL."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "hotdog_audio_import_relocations",
    ROOT / "scripts/audit-hotdog-audio-import-relocations.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def make_elf(include_dlopen=True, add_bad_symbol=False):
    b = bytearray(0x800)
    b[:7] = b"\x7fELF\x01\x01\x01"
    struct.pack_into(
        "<HHIIIIIHHHHHH", b, 16,
        3, 40, 1, 0, 52, 0x600, 0, 52, 32, 0, 40, 5, 1
    )
    shstr = b"\0.shstrtab\0.dynstr\0.dynsym\0.rel.plt\0"
    names = b"\0dlopen\0dlsym\0"
    b[0x200:0x200 + len(shstr)] = shstr
    b[0x260:0x260 + len(names)] = names
    # SHT_DYNSYM, 3 symbols including null, each 16 bytes.
    struct.pack_into("<IIIBBH", b, 0x310, 1, 0, 0, 18, 0, 0)
    struct.pack_into("<IIIBBH", b, 0x320, 8, 0, 0, 18, 0, 0)
    if include_dlopen:
        struct.pack_into("<II", b, 0x420, 0xF010, (1 << 8) | 22)
    else:
        struct.pack_into("<II", b, 0x420, 0xF010, (2 << 8) | 22)
    struct.pack_into("<II", b, 0x428, 0xF014,
                     ((99 if add_bad_symbol else 2) << 8) | 22)
    def sh(i, name, kind, off, size, link=0, entsize=0):
        struct.pack_into("<IIIIIIIIII", b, 0x600 + i * 40,
                         shstr.find(name) if name else 0, kind,
                         0, 0, off, size, link, 0, 4, entsize)
    sh(0, b"", 0, 0, 0)
    sh(1, b".shstrtab", 3, 0x200, len(shstr))
    sh(2, b".dynstr", 3, 0x260, len(names))
    sh(3, b".dynsym", 11, 0x300, 48, 2, 16)
    sh(4, b".rel.plt", 9, 0x420, 16, 3, 8)
    return bytes(b)


class AudioImportRelocationTests(unittest.TestCase):
    def test_two_dynsym_imports_and_plt_relocations(self):
        r = mod.inspect_elf(make_elf())
        self.assertEqual(r["total_relocation_entries_examined"], 2)
        dlopen = r["loader_imports"]["dlopen"]
        self.assertEqual(dlopen["undefined_dynsym_count"], 1)
        self.assertEqual(dlopen["relocation_entry_count"], 1)
        self.assertEqual(dlopen["relocation_samples"][0]["relocation_type_id"], 22)
        self.assertEqual(
            dlopen["relocation_samples"][0]["relocation_offset_vaddr_hex"],
            "0xf010"
        )
        self.assertEqual(r["loader_imports"]["dlsym"]["relocation_entry_count"], 1)
        self.assertEqual(r["loader_imports"]["android_dlopen_ext"]["undefined_dynsym_count"], 0)
        self.assertFalse(r["proves_dlopen_called_from_audio_hal"])
        self.assertFalse(r["proves_a2dp_path_argument_passed_to_dlopen"])
        self.assertFalse(r["elf_extracted_to_disk"])
        self.assertFalse(r["flash_ready"])

    def test_symbol_import_does_not_imply_plt_relocation(self):
        r = mod.inspect_elf(make_elf(include_dlopen=False))
        self.assertEqual(r["loader_imports"]["dlopen"]["undefined_dynsym_count"], 1)
        self.assertEqual(r["loader_imports"]["dlopen"]["relocation_entry_count"], 0)

    def test_malformed_relocation_symbol_index_rejected(self):
        with self.assertRaises(mod.ImportRelocationError):
            mod.inspect_elf(make_elf(add_bad_symbol=True))

    def test_wrong_arch_rejected(self):
        b = bytearray(make_elf())
        struct.pack_into("<H", b, 18, 183)
        with self.assertRaises(mod.ImportRelocationError):
            mod.inspect_elf(bytes(b))

    def test_truncated_table_rejected(self):
        with self.assertRaises(mod.ImportRelocationError):
            mod.inspect_elf(make_elf()[:0x640])

    def test_corrupt_section_entsize_rejected(self):
        b = bytearray(make_elf())
        struct.pack_into("<I", b, 0x600 + 4 * 40 + 36, 3)
        with self.assertRaises(mod.ImportRelocationError):
            mod.inspect_elf(bytes(b))

    def test_pinned_archive_hash_rejects_synthetic_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "fake.zip"
            with zipfile.ZipFile(f, "w") as z:
                z.writestr(mod.ZIP_ROOT + mod.MEMBER, make_elf())
            with self.assertRaises(mod.ImportRelocationError):
                mod.checked_zip(f)


if __name__ == "__main__":
    unittest.main()
