"""Offline build-local ABI test fixtures; never require real kernel or device."""
import hashlib
import importlib.util
import io
import json
import struct
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "built_crc_gate", ROOT / "scripts/audit-wlan-built-crcs.py"
)
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


def fake_arm64_module(symbols=None, signed=True, release=None):
    """Valid ELF64 AArch64 relocatable module with version records."""
    release = release or "4.14.357-perf-g57037290bb57"
    names = b"\0.shstrtab\0.modinfo\0__versions\0"
    modinfo = ("name=wlan\0vermagic=" + release +
               " SMP preempt mod_unload modversions aarch64\0depends=\0").encode()
    versions = b"".join(
        struct.pack("<Q56s", crc, name.encode())
        for name, crc in (symbols if symbols is not None else
                          {"module_layout": 0x12345678}).items()
    )
    blob = bytearray(64)
    records = [(0, 0, 0, 0)]
    for name, content, kind, offset in [
        (".shstrtab", names, 3, 1),
        (".modinfo", modinfo, 1, 11),
        ("__versions", versions, 1, 20),
    ]:
        pos = len(blob)
        blob.extend(content)
        records.append((offset, kind, pos, len(content)))
    while len(blob) % 8:
        blob.append(0)
    shoff = len(blob)
    for name, kind, pos, size in records:
        blob.extend(struct.pack("<IIQQQQIIQQ", name, kind, 0, 0, pos,
                                size, 0, 0, 1, 0))
    struct.pack_into(
        "<16sHHIQQQIHHHHHH", blob, 0,
        b"\x7fELF" + bytes((2, 1, 1)) + b"\0" * 9,
        1, 183, 1, 0, 0, shoff, 0, 64, 0, 0, 64, len(records), 1,
    )
    if signed:
        blob.extend(b"TESTSIGNATUREDATA")
        blob.extend(bytes((0, 0, 2, 0, 0, 0, 0, 0)))
        blob.extend((17).to_bytes(4, "big"))
        blob.extend(GATE.ABI.SIGNATURE_MARKER)
    return bytes(blob)


class BuiltWlanSelfCrcTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.art = self.root / "artifacts"
        self.art.mkdir()
        self.rel = "modules/drivers/staging/qcacld-3.0/wlan.ko"
        self.module = self.art / self.rel
        self.module.parent.mkdir(parents=True)
        self.module.write_bytes(fake_arm64_module())
        self.symvers = self.art / "Module.symvers"
        self.symvers.write_text(
            "0x12345678 module_layout vmlinux EXPORT_SYMBOL\n",
            encoding="utf-8",
        )
        self.artifact_report = {
            "schema": "op7t-kernel-artifact-report-v1",
            "device": "hotdog",
            "upstream_commit": GATE.ROM_SHA,
            "profile": "core",
            "module_signature_enforcement": True,
            "module_debug_sections_verified": True,
            "module_signature_load_blocked": False,
            "flash_ready": False,
            "kernel_release": "4.14.357-perf-g57037290bb57",
            "wlan_module_count": 1,
            "modules": [{
                "path": self.rel,
                "sha256": self.sha(),
                "size_bytes": self.module.stat().st_size,
                "has_embedded_signature": True,
                "signature_key_id": "A1B2C3",
                "debug_sections": [],
            }],
        }
        self.compiled = {
            "schema": "hotdog-wlan-icnss-compile-attestation-v4",
            "upstream_sha": GATE.ROM_SHA,
            "source_pin_role": "observed_rom_release_source_candidate",
            "all_modified_translation_units_compiled": True,
            "module_elf_audited": True,
            "flash_ready": False,
            "installed_rom_module_abi_verified": False,
            "signer_trust_on_installed_rom_verified": False,
            "wlan_module": {
                "module": self.rel,
                "sha256": self.sha(),
                "vermagic": "4.14.357-perf-g57037290bb57 SMP modversions",
                "signed_and_stripped": True,
            },
        }
        self.save()

    def sha(self):
        return hashlib.sha256(self.module.read_bytes()).hexdigest()

    def save(self):
        (self.art / "artifact-report.json").write_text(
            json.dumps(self.artifact_report), encoding="utf-8"
        )
        (self.art / "wlan-patch-experiment.json").write_text(
            json.dumps(self.compiled), encoding="utf-8"
        )

    def test_matching_self_built_crc_is_not_installed_rom_parity(self):
        report = GATE.check(self.art)
        self.assertTrue(report["built_kernel_module_self_consistency"])
        self.assertEqual(1, report["matched_against_same_build_Module_symvers"])
        self.assertEqual(0, report["mismatched_symbol_crc_count"])
        for key in (
            "compared_against_actual_ROM_Module_symvers",
            "actual_ROM_kernel_binary_identity_verified",
            "reference_OTA_WLAN_ELF_abi_verified",
            "installed_kernel_signing_trust_verified",
            "signature_cryptographically_verified",
            "rx_callback_runtime_safety_verified",
            "flash_ready",
        ):
            with self.subTest(key=key):
                self.assertFalse(report[key])

    def test_fail_on_mismatching_self_generated_crc(self):
        self.symvers.write_text(
            "0x12345679 module_layout vmlinux EXPORT_SYMBOL\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(GATE.SelfCheckError, "mismatched"):
            GATE.check(self.art)

    def test_fail_if_built_symvers_lacks_import(self):
        self.symvers.write_text(
            "0x12345678 unrelated_export vmlinux EXPORT_SYMBOL\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(GATE.SelfCheckError, "unresolved"):
            GATE.check(self.art)

    def test_unsigned_module_is_blocked_even_if_metadata_claims_signed(self):
        self.module.write_bytes(fake_arm64_module(signed=False))
        self.artifact_report["modules"][0]["sha256"] = self.sha()
        self.artifact_report["modules"][0]["size_bytes"] = self.module.stat().st_size
        self.compiled["wlan_module"]["sha256"] = self.sha()
        self.save()
        with self.assertRaisesRegex(GATE.SelfCheckError, "signature trailer"):
            GATE.check(self.art)

    def test_missing_version_records_are_not_accepted(self):
        self.module.write_bytes(fake_arm64_module(symbols={}))
        self.artifact_report["modules"][0]["sha256"] = self.sha()
        self.artifact_report["modules"][0]["size_bytes"] = self.module.stat().st_size
        self.compiled["wlan_module"]["sha256"] = self.sha()
        self.save()
        with self.assertRaisesRegex(GATE.SelfCheckError, "no imported symbol CRC"):
            GATE.check(self.art)

    def test_tampered_report_module_sha_or_signing_gate_blocked(self):
        original = self.compiled["wlan_module"]["sha256"]
        self.compiled["wlan_module"]["sha256"] = "0" * 64
        self.save()
        with self.assertRaises(GATE.SelfCheckError):
            GATE.check(self.art)
        self.compiled["wlan_module"]["sha256"] = original
        self.artifact_report["module_signature_enforcement"] = False
        self.save()
        with self.assertRaises(GATE.SelfCheckError):
            GATE.check(self.art)

    def test_wrong_parent_pin_or_untrusted_abi_claim_rejected(self):
        self.compiled["upstream_sha"] = "1083c6c5906114c71b11a429898b111a1b1b8109"
        self.save()
        with self.assertRaises(GATE.SelfCheckError):
            GATE.check(self.art)
        self.compiled["upstream_sha"] = GATE.ROM_SHA
        self.compiled["installed_rom_module_abi_verified"] = True
        self.save()
        with self.assertRaises(GATE.SelfCheckError):
            GATE.check(self.art)

    def test_symlink_to_wlan_module_not_followed(self):
        copy = self.root / "original.ko"
        self.module.rename(copy)
        self.module.symlink_to(copy)
        with self.assertRaisesRegex(GATE.SelfCheckError, "unavailable"):
            GATE.check(self.art)

    def test_invalid_path_traversal_rejected(self):
        self.compiled["wlan_module"]["module"] = "modules/../../home/secrets.ko"
        self.save()
        with self.assertRaises(GATE.SelfCheckError):
            GATE.check(self.art)

    def test_cli_writes_only_report_and_refuses_overwrite(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(0, GATE.main(["--artifacts", str(self.art)]))
        metadata = json.loads(
            (self.art / "built-wlan-self-crc-report.json").read_text()
        )
        self.assertFalse(metadata["flash_ready"])
        self.assertTrue(metadata["built_kernel_module_self_consistency"])
        with redirect_stderr(io.StringIO()):
            self.assertEqual(2, GATE.main(["--artifacts", str(self.art)]))
        self.assertNotIn("fastboot", (ROOT / "scripts/audit-wlan-built-crcs.py").read_text())
        self.assertNotIn("adb shell", (ROOT / "scripts/audit-wlan-built-crcs.py").read_text())


if __name__ == "__main__":
    unittest.main()
