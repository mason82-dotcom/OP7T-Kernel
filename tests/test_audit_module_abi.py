import importlib.util
import io
import json
import struct
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit-module-abi.py"
SPEC = importlib.util.spec_from_file_location("abi_audit", SCRIPT)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def make_elf(versioned=None, vermagic="4.14.357-perf SMP modversions aarch64", sign=False):
    """Construct a minimal but layout-correct ARM64 relocatable ELF module."""
    names = b"\0.shstrtab\0.modinfo\0__versions\0"
    name_offsets = {".shstrtab": 1, ".modinfo": 11, "__versions": 20}
    modinfo = ("name=wlan\0vermagic=" + vermagic + "\0depends=\0").encode("utf-8")
    records = b"".join(
        struct.pack("<Q56s", crc, name.encode("ascii"))
        for name, crc in (versioned or {}).items()
    )
    blob = bytearray(64)
    sections = [(0, 0, 0, 0)]
    for label, data, kind in [
        (".shstrtab", names, 3),
        (".modinfo", modinfo, 1),
        ("__versions", records, 1),
    ]:
        offset = len(blob)
        blob.extend(data)
        sections.append((name_offsets[label], kind, offset, len(data)))
    while len(blob) % 8:
        blob.append(0)
    shoff = len(blob)
    for name, kind, offset, size in sections:
        blob.extend(struct.pack("<IIQQQQIIQQ", name, kind, 0, 0, offset,
                                size, 0, 0, 1, 0))
    ident = b"\x7fELF" + bytes((2, 1, 1)) + b"\0" * 9
    struct.pack_into("<16sHHIQQQIHHHHHH", blob, 0, ident, 1, 183, 1,
                     0, 0, shoff, 0, 64, 0, 0, 64, len(sections), 1)
    if sign:
        blob.extend(b"A" * 16)
        blob.extend(bytes((0, 0, 2, 0, 0, 0, 0, 0)))
        blob.extend((16).to_bytes(4, "big"))
        blob.extend(AUDIT.SIGNATURE_MARKER)
    return bytes(blob)


class AbiAuditTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)

    def file(self, name, data):
        path = self.root / name
        path.write_bytes(data)
        return path

    def test_identical_crc_still_not_approved(self):
        built = AUDIT.inspect(self.file("wlan.ko", make_elf({"module_layout": 0x1234}, sign=True)))
        rom = AUDIT.inspect(self.file("qca_cld3_wlan.ko", make_elf({"module_layout": 0x1234}, sign=True)))
        report = AUDIT.compare(built, rom)
        self.assertEqual("abi_and_trust_not_proven", report["status"])
        self.assertEqual(1, report["shared_versioned_symbol_count"])
        self.assertFalse(report["module_signature_cryptographically_verified"])
        self.assertFalse(report["flash_ready"])

    def test_disagreeing_crc_is_blocker(self):
        built = AUDIT.inspect(self.file("built.ko", make_elf({"module_layout": 0x1234})))
        rom = AUDIT.inspect(self.file("rom.ko", make_elf({"module_layout": 0x7777})))
        report = AUDIT.compare(built, rom)
        self.assertIn("shared_symbol_crc_mismatch", report["blockers"])
        self.assertEqual(["module_layout"], report["different_symbol_crc_samples"])
        self.assertFalse(report["flash_ready"])

    def test_rom_crc_against_built_symvers(self):
        built = AUDIT.inspect(self.file("built.ko", make_elf({"something_else": 4})))
        rom = AUDIT.inspect(self.file("rom.ko", make_elf({"module_layout": 0xAABBCCDD})))
        path = self.file("Module.symvers", b"0xaabbccde\tmodule_layout\tvmlinux\tEXPORT_SYMBOL\n")
        report = AUDIT.compare(built, rom, AUDIT.parse_symvers(path))
        self.assertIn("rom_symbol_crc_differs_from_built_Module.symvers", report["blockers"])
        self.assertEqual(1, report["rom_symbol_mismatches_built_symvers_count"])

    def test_valid_symvers_with_unresolved_symbols(self):
        built = AUDIT.inspect(self.file("built.ko", make_elf({"module_layout": 0xBEEF})))
        rom = AUDIT.inspect(self.file("rom.ko", make_elf({"module_layout": 0xBEEF, "other": 2})))
        syms = AUDIT.parse_symvers(self.file("Module.symvers", b"0x0000beef module_layout vmlinux EXPORT_SYMBOL\n"))
        report = AUDIT.compare(built, rom, syms)
        self.assertEqual(1, report["rom_symbols_not_in_built_symvers_count"])
        self.assertIn("rom_symbols_missing_from_built_Module.symvers", report["unknowns"])

    def test_truncated_or_wrong_elf_fails_closed(self):
        for name, data in [("tiny.ko", b"\x7fELF"), ("x86.ko", b"\x7fELF" + b"0" * 100)]:
            with self.subTest(name=name):
                with self.assertRaises(AUDIT.AuditError):
                    AUDIT.inspect(self.file(name, data))

    def test_malformed_version_records_fail(self):
        data = bytearray(make_elf({"module_layout": 42}))
        sections = AUDIT.section_data(bytes(data))
        self.assertEqual(64, len(sections["__versions"]))
        start = data.find(b"module_layout")
        data[start:start + len(b"module_layout")] = b"\xff" * len(b"module_layout")
        with self.assertRaises(AUDIT.AuditError):
            AUDIT.inspect(self.file("bad.ko", bytes(data)))

    def test_signature_marker_is_not_crypto_proof(self):
        obj = AUDIT.inspect(self.file("signed.ko", make_elf({"module_layout": 1}, sign=True)))
        self.assertTrue(obj["signature"]["trailer_present"])
        self.assertFalse(obj["signature"]["cryptographically_verified"])

    def test_missing_symbol_versions_remains_unknown(self):
        built = AUDIT.inspect(self.file("built.ko", make_elf()))
        rom = AUDIT.inspect(self.file("rom.ko", make_elf()))
        result = AUDIT.compare(built, rom)
        self.assertIn("no_common_versioned_symbols", result["unknowns"])
        self.assertFalse(result["flash_ready"])

    def test_cli_emits_json_and_failure_exit_code(self):
        built = self.file("built.ko", make_elf({"module_layout": 10}))
        rom = self.file("rom.ko", make_elf({"module_layout": 11}))
        buf = io.StringIO()
        with redirect_stdout(buf):
            exitcode = AUDIT.main(["--built", str(built), "--rom", str(rom)])
        self.assertEqual(2, exitcode)
        self.assertFalse(json.loads(buf.getvalue())["flash_ready"])

    def test_conflicting_symvers_rejected(self):
        path = self.file("Module.symvers", b"0x1 foo vmlinux EXPORT_SYMBOL\n0x2 foo vmlinux EXPORT_SYMBOL\n")
        with self.assertRaises(AUDIT.AuditError):
            AUDIT.parse_symvers(path)


if __name__ == "__main__":
    unittest.main()
