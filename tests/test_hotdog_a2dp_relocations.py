"""Synthetic ELF32 REL relocation probes; no original vendor files needed."""
import hashlib
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "hotdog_a2dp_relocs", ROOT / "scripts/audit-hotdog-a2dp-relocations.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def make_elf(relocation=True, pointer=True, no_sections=False):
    data = bytearray(0x800)
    data[:7] = b"\x7fELF\x01\x01\x01"
    struct.pack_into("<HHIIIIIHHHHHH", data, 16, 3, 40, 1, 0, 52,
                     0 if no_sections else 0x600, 0, 52, 32, 1,
                     0 if no_sections else 40, 0 if no_sections else 5,
                     0 if no_sections else 1)
    struct.pack_into("<IIIIIIII", data, 52, 1, 0, 0x1000, 0, 0x800, 0x800, 4, 0x1000)
    data[0x180:0x180+len(mod.NEEDLE)] = mod.NEEDLE
    if pointer:
        struct.pack_into("<I", data, 0x300, 0x1180)
    if not no_sections:
        names = b"\x00.shstrtab\x00.rodata\x00.data\x00.rel.dyn\x00"
        data[0x400:0x400+len(names)] = names

        def sec(num, name, typ, off, size, addr=0, entsize=0):
            struct.pack_into("<IIIIIIIIII", data, 0x600+40*num,
                names.find(name) if name else 0, typ, 0, addr,
                off, size, 0, 0, 4, entsize)
        sec(0, b"", 0, 0, 0)
        sec(1, b".shstrtab", 3, 0x400, len(names))
        sec(2, b".rodata", 1, 0x170, 0x70, 0x1170)
        sec(3, b".data", 1, 0x2f0, 0x60, 0x12f0)
        if relocation:
            struct.pack_into("<II", data, 0x480, 0x1300, 23)
        sec(4, b".rel.dyn", 9, 0x480, 8 if relocation else 0, 0, 8)
    return bytes(data)


class A2DPRelocationTests(unittest.TestCase):
    def setUp(self):
        context = tempfile.TemporaryDirectory()
        self.addCleanup(context.cleanup)
        self.zip = Path(context.name) / "vendor.zip"

    def make_zip(self, blob, extra=None):
        with zipfile.ZipFile(self.zip, "w") as z:
            z.writestr(mod.ZIP_ROOT + mod.MEMBER, blob)
            for name, payload in (extra or {}).items():
                z.writestr(mod.ZIP_ROOT + name, payload)
        return (hashlib.sha256(self.zip.read_bytes()).hexdigest(),
                hashlib.sha256(blob).hexdigest())

    def test_a2dp_relocation_addend_and_pointer(self):
        blob = make_elf()
        za, elf = self.make_zip(blob)
        result = mod.inspect(self.zip, za, elf)
        self.assertEqual(result["elf_path_virtual_address_hex"], "0x1180")
        self.assertEqual(result["containing_section_names"], [".rodata"])
        self.assertEqual(result["relocation_entries_with_path_equal_addend"], 1)
        self.assertEqual(result["aligned_raw_32bit_equal_value_count"], 1)
        self.assertEqual(result["status"], "A2DP_RELOCATION_CANDIDATES_FOUND")
        self.assertFalse(result["proves_dlopen_receives_a2dp_path"])
        self.assertFalse(result["elf_extracted"])
        self.assertFalse(result["flash_ready"])

    def test_absent_simple_pointer_is_not_runtime_negation(self):
        report = mod.parse_elf(make_elf(relocation=False, pointer=False))
        self.assertEqual(report["status"], "NO_SIMPLE_A2DP_POINTER_CANDIDATES")
        self.assertFalse(report["proves_instructions_reference_path"])

    def test_aligned_word_without_relocation(self):
        report = mod.parse_elf(make_elf(relocation=False, pointer=True))
        self.assertEqual(report["status"], "A2DP_ALIGNED_POINTER_VALUE_CANDIDATES_FOUND")
        self.assertEqual(report["relocation_entries_with_path_equal_addend"], 0)

    def test_sectionless_elf_keeps_mapping(self):
        report = mod.parse_elf(make_elf(no_sections=True, pointer=False))
        self.assertEqual(report["elf_path_virtual_address_hex"], "0x1180")
        self.assertEqual(report["containing_section_names"], [])
        self.assertEqual(report["total_relocation_entries"], 0)

    def test_digest_mismatch_refused(self):
        za, elf = self.make_zip(make_elf())
        with self.assertRaises(mod.ProbeError):
            mod.inspect(self.zip, "0" * 64, elf)
        with self.assertRaises(mod.ProbeError):
            mod.inspect(self.zip, za, "0" * 64)

    def test_malicious_zip_path_refused(self):
        za, elf = self.make_zip(make_elf(), {"../bad": b"no"})
        with self.assertRaises(mod.ProbeError):
            mod.inspect(self.zip, za, elf)

    def test_malformed_rel_entry_size_refused(self):
        elf = bytearray(make_elf())
        struct.pack_into("<I", elf, 0x600+40*4+36, 3)
        with self.assertRaises(mod.ProbeError):
            mod.parse_elf(bytes(elf))

    def test_wrong_elf_arch_refused(self):
        elf = bytearray(make_elf())
        struct.pack_into("<H", elf, 18, 183)
        with self.assertRaises(mod.ProbeError):
            mod.parse_elf(bytes(elf))


if __name__ == "__main__":
    unittest.main()
