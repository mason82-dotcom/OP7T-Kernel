"""Offline regression tests for the audited experimental WLAN compile."""
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "wlan_compile_audit", ROOT / "scripts/audit-wlan-compile.py"
)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class WlanCompilationEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.out = base / "out"
        self.art = base / "artifacts"
        self.out.mkdir()
        self.art.mkdir()
        for relative in AUDIT.EXPECTED_OBJECTS:
            target = self.out / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"mock-compiler-object:" + b"x" * 256)
        self.wlan = self.art / "modules/drivers/staging/qcacld-3.0/wlan.ko"
        self.wlan.parent.mkdir(parents=True)
        self.wlan.write_bytes(b"mock-wlan-fixture:" + b"a" * 500)
        self.module = {
            "path": "modules/drivers/staging/qcacld-3.0/wlan.ko",
            "sha256": hashlib.sha256(self.wlan.read_bytes()).hexdigest(),
            "size_bytes": self.wlan.stat().st_size,
            "vermagic": "4.14.357 SMP preempt mod_unload",
            "signer": "Ephemeral build signer",
            "signature_key_id": "ABCD1234",
            "has_embedded_signature": True,
            "debug_sections": [],
        }
        self.report = {
            "schema": "op7t-kernel-artifact-report-v1",
            "device": "hotdog",
            "upstream_commit": AUDIT.PIN,
            "profile": "core",
            "module_signature_enforcement": True,
            "module_debug_sections_verified": True,
            "module_signature_load_blocked": False,
            "flash_ready": False,
            "final_config": {"CONFIG_QCA_CLD_WLAN": "m"},
            "modules": [self.module],
            "wlan_module_count": 1,
            "kernel_release": "4.14.357",
        }
        self.write_report()

    def write_report(self):
        (self.art / "artifact-report.json").write_text(
            json.dumps(self.report), encoding="utf-8"
        )

    def test_attested_compiler_objects_and_signed_wlan_remain_unflashable(self):
        result = AUDIT.attest(self.out, self.art)
        self.assertTrue(result["all_modified_translation_units_compiled"])
        self.assertEqual(1, len(result["compiled_modified_translation_units"]))
        self.assertEqual("ICNSS_HELIUMPLUS", result["selected_driver_family"])
        self.assertFalse(result["inactive_lithium_patch"]["applied"])
        self.assertFalse(result["inactive_lithium_patch"]["compiled"])
        self.assertEqual(1, len(result["patches"]))
        self.assertTrue(result["module_elf_audited"])
        self.assertEqual(self.module["sha256"], result["wlan_module"]["sha256"])
        self.assertFalse(result["flash_ready"])
        self.assertFalse(result["rom_kernel_symbol_crc_compatible"])
        self.assertFalse(result["signer_trust_on_installed_rom_verified"])

    def test_inactive_lithium_patch_not_selected_or_claimed_compiled(self):
        self.assertEqual(1, len(AUDIT.EXPECTED_OBJECTS))
        self.assertEqual(1, len(AUDIT.PATCHES))
        self.assertEqual(
            "drivers/staging/qcacld-3.0/core/hdd/src/wlan_hdd_tx_rx.o",
            AUDIT.EXPECTED_OBJECTS[0],
        )
        self.assertNotIn(AUDIT.INACTIVE_LITHIUM_PATCH, AUDIT.PATCHES)
        data = AUDIT.attest(self.out, self.art)
        self.assertFalse(data["inactive_lithium_patch"]["applied"])
        self.assertFalse(data["inactive_lithium_patch"]["compiled"])

    def test_rom_source_child_requires_matching_signed_module_and_parity(self):
        self.report["upstream_commit"] = AUDIT.ROM_PIN
        self.write_report()
        patch = ROOT / AUDIT.PATCHES[0]
        parity = {
            "schema": "hotdog-wlan-rom-source-parity-v1",
            "parent_sha": AUDIT.PIN,
            "rom_source_sha": AUDIT.ROM_PIN,
            "source_equivalence_verified": True,
            "flash_ready": False,
            "rom_module_abi_verified": False,
            "rom_signing_key_trust_verified": False,
            "selected_patch": {
                "path": AUDIT.PATCHES[0],
                "sha256": hashlib.sha256(patch.read_bytes()).hexdigest(),
                "apply_check_parent": True,
                "apply_check_rom_source": True,
                "applied": False,
            },
        }
        report_path = self.art / "wlan-rom-source-parity.json"
        with self.assertRaises(AUDIT.AttestationError):
            AUDIT.attest(self.out, self.art, expected_sha=AUDIT.ROM_PIN)
        report_path.write_text(json.dumps(parity), encoding="utf-8")
        result = AUDIT.attest(self.out, self.art, expected_sha=AUDIT.ROM_PIN)
        self.assertEqual(AUDIT.ROM_PIN, result["upstream_sha"])
        self.assertEqual(
            "observed_rom_release_source_candidate", result["source_pin_role"]
        )
        self.assertTrue(result["source_parity"]["wlan_source_parity_verified"])
        self.assertFalse(result["installed_rom_kernel_binary_identical"])
        self.assertFalse(result["observed_rom_kernel_release_verified"])
        self.assertFalse(result["rfc_behavioral_equivalence_verified"])
        self.assertFalse(result["flash_ready"])

        for update in (
            {"rom_source_sha": "f" * 40},
            {"rom_module_abi_verified": True},
            {"source_equivalence_verified": False},
            {"flash_ready": True},
            {"selected_patch": {**parity["selected_patch"], "sha256": "0" * 64}},
            {"selected_patch": {**parity["selected_patch"], "applied": True}},
        ):
            invalid = dict(parity, **update)
            report_path.write_text(json.dumps(invalid), encoding="utf-8")
            with self.subTest(update=update), self.assertRaises(
                AUDIT.AttestationError
            ):
                AUDIT.attest(self.out, self.art, expected_sha=AUDIT.ROM_PIN)

    def test_unknown_source_pin_rejected_without_parity_exception(self):
        with self.assertRaises(AUDIT.AttestationError):
            AUDIT.attest(self.out, self.art, expected_sha="f" * 40)
        self.assertEqual(
            "original_experiment",
            AUDIT.attest(self.out, self.art)["source_pin_role"],
        )

    def test_each_missing_compiler_object_rejected(self):
        for name in AUDIT.EXPECTED_OBJECTS:
            target = self.out / name
            original = target.read_bytes()
            target.unlink()
            with self.subTest(name=name), self.assertRaises(AUDIT.AttestationError):
                AUDIT.attest(self.out, self.art)
            target.write_bytes(original)

    def test_tiny_compiler_object_rejected(self):
        (self.out / AUDIT.EXPECTED_OBJECTS[0]).write_bytes(b"x")
        with self.assertRaises(AUDIT.AttestationError):
            AUDIT.attest(self.out, self.art)

    def test_tampered_module_hash_rejected(self):
        self.wlan.write_bytes(self.wlan.read_bytes() + b"tampered")
        with self.assertRaises(AUDIT.AttestationError):
            AUDIT.attest(self.out, self.art)

    def test_unsigned_unstripped_and_vermagic_mismatch_rejected(self):
        for update in (
            {"signature_key_id": ""},
            {"has_embedded_signature": False},
            {"debug_sections": [".debug_info"]},
            {"vermagic": "4.14.999 SMP"},
        ):
            original = self.module.copy()
            self.module.update(update)
            self.write_report()
            with self.subTest(update=update), self.assertRaises(AUDIT.AttestationError):
                AUDIT.attest(self.out, self.art)
            self.module.clear()
            self.module.update(original)
        self.write_report()

    def test_wrong_upstream_profile_or_policy_rejected(self):
        for name, value in (
            ("upstream_commit", "f" * 40),
            ("module_signature_enforcement", False),
            ("module_debug_sections_verified", False),
            ("module_signature_load_blocked", True),
            ("profile", "external"),
            ("flash_ready", True),
        ):
            original = self.report[name]
            self.report[name] = value
            self.write_report()
            with self.subTest(name=name), self.assertRaises(AUDIT.AttestationError):
                AUDIT.attest(self.out, self.art)
            self.report[name] = original
        self.write_report()

    def test_unapproved_or_ambiguous_module_rejected(self):
        self.report["modules"].append(dict(self.module))
        self.report["wlan_module_count"] = 2
        self.write_report()
        with self.assertRaises(AUDIT.AttestationError):
            AUDIT.attest(self.out, self.art)
        self.report["modules"] = [self.module]
        self.report["wlan_module_count"] = 1
        self.module["path"] = "../outside/wlan.ko"
        self.write_report()
        with self.assertRaises(AUDIT.AttestationError):
            AUDIT.attest(self.out, self.art)

    def test_requires_existing_successful_audit_report(self):
        (self.art / "artifact-report.json").unlink()
        with self.assertRaises(AUDIT.AttestationError):
            AUDIT.attest(self.out, self.art)


if __name__ == "__main__":
    unittest.main()
