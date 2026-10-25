"""Synthetic regression tests only; no actual ROM/CI WLAN ELF or private keys."""
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(label, filename):
    spec = importlib.util.spec_from_file_location(label, ROOT / "scripts" / filename)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


EXP = load("wlan_ci_crc_export_test", "export-wlan-build-crcs.py")
COMP = load("wlan_ci_crc_compare_test", "compare-wlan-build-crcs-to-rom.py")
ROM_SHA = "57037290bb57caefd3c337db3511fca5751fb4ef"
OLD_RELEASE = "4.14.357-perf-g1083c6c59061"
NEW_RELEASE = "4.14.357-perf-g57037290bb57-dirty"
ORIGINAL_RELEASE = "4.14.357-perf-g57037290bb57"
FLAGS = " SMP preempt mod_unload modversions aarch64"


class CrcMapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.art = self.root / "artifacts"
        (self.art / EXP.WLAN_REL).parent.mkdir(parents=True)
        (self.art / EXP.WLAN_REL).write_bytes(b"synthetic-module")
        self.original = self.root / "qca_cld3_wlan.ko"
        self.original.write_bytes(b"synthetic-original-module")
        self.original_sha = hashlib.sha256(self.original.read_bytes()).hexdigest()
        self.built_sha = hashlib.sha256(b"synthetic-module").hexdigest()
        self.symvers_sha = "a" * 64
        self.values = {"__alloc_skb": 0x11111111, "netif_rx": 0x22222222, "printk": 0x33333333}
        self.selfcheck = {
            "schema": "hotdog-built-wlan-self-crc-v1",
            "kernel_source_sha": ROM_SHA,
            "kernel_release": NEW_RELEASE,
            "wlan_module_sha256": self.built_sha,
            "built_Module_symvers_sha256": self.symvers_sha,
            "built_kernel_module_self_consistency": True,
            "missing_exported_symbol_count": 0,
            "mismatched_symbol_crc_count": 0,
            "built_module_symbols_versioned": 3,
            "matched_against_same_build_Module_symvers": 3,
            "flash_ready": False,
        }

    def compiled_report(self):
        return {
            "schema": "hotdog-wlan-icnss-compile-attestation-v4",
            "upstream_sha": ROM_SHA,
            "wlan_module": {
                "sha256": self.built_sha,
                "vermagic": NEW_RELEASE + FLAGS,
                "signed_and_stripped": True,
            },
            "installed_rom_module_abi_verified": False,
            "signer_trust_on_installed_rom_verified": False,
            "flash_ready": False,
        }

    def elf(self, sha, versions, release):
        return {
            "sha256": sha,
            "versions": versions,
            "signature": {"trailer_present": True},
            "has_versions_section": True,
            "vermagic": release + FLAGS,
        }

    def generated(self):
        with patch.object(EXP.SELF, "check", return_value=self.selfcheck):
            with patch.object(EXP.ABI, "inspect", return_value=self.elf(self.built_sha, self.values, NEW_RELEASE)):
                return EXP.generate(self.art)

    def fixture_inputs(self, map_record=None):
        report = self.root / "report.json"
        selfreport = self.root / "selfcheck.json"
        bmap = self.root / "crcmap.json"
        report.write_text(json.dumps(self.compiled_report()))
        selfreport.write_text(json.dumps(self.selfcheck))
        bmap.write_text(json.dumps(map_record or self.generated()))
        return bmap, report, selfreport

    def test_export_creates_bounded_crc_map_for_approved_source(self):
        report = self.generated()
        self.assertEqual(3, report["imported_symbol_count"])
        self.assertEqual("0x11111111", report["imported_symbol_crcs"]["__alloc_skb"])
        self.assertEqual(EXP.canonical_map_digest(report["imported_symbol_crcs"]),
                         report["imported_symbol_map_sha256"])
        self.assertEqual(self.built_sha, report["rebuilt_wlan_module_sha256"])
        self.assertFalse(report["flash_ready"])

    def test_export_refuses_old_source_pin(self):
        evidence = dict(self.selfcheck, kernel_source_sha="1083c6c5906114c71b11a429898b111a1b1b8109")
        with patch.object(EXP.SELF, "check", return_value=evidence):
            with self.assertRaisesRegex(ValueError, "not approved"):
                EXP.generate(self.art)

    def test_export_refuses_unsigned_module(self):
        obj = self.elf(self.built_sha, self.values, NEW_RELEASE)
        obj["signature"]["trailer_present"] = False
        with (patch.object(EXP.SELF, "check", return_value=self.selfcheck),
              patch.object(EXP.ABI, "inspect", return_value=obj)):
            with self.assertRaisesRegex(ValueError, "invalid"):
                EXP.generate(self.art)

    def test_compare_detects_real_numeric_mismatch_and_vermagic(self):
        files = self.fixture_inputs()
        rom_crcs = {"__alloc_skb": 0xABCDEF01, "netif_rx": 0x22222222, "printk": 0x33333333}
        with patch.object(COMP.ABI, "inspect",
                          return_value=self.elf(self.original_sha, rom_crcs, ORIGINAL_RELEASE)):
            report = COMP.compare(self.original, self.original_sha, *files)
        self.assertEqual(1, report["different_crc_count"])
        self.assertEqual(2, report["matching_crc_count"])
        self.assertEqual(3, report["common_symbol_count"])
        self.assertIn("shared_symbol_crc_mismatch", report["blockers"])
        self.assertIn("vermagic_mismatch", report["blockers"])
        self.assertFalse(report["flash_ready"])

    def test_compare_rejects_unbound_crc_map(self):
        report = self.generated()
        report["imported_symbol_crcs"]["netif_rx"] = "0x00000000"
        files = self.fixture_inputs(report)
        with self.assertRaisesRegex(ValueError, "malformed"):
            COMP.compare(self.original, self.original_sha, *files)

    def test_compare_refuses_old_source_pin_even_if_crc_map_is_consistent(self):
        report = self.generated()
        report["kernel_source_sha"] = "1083c6c5906114c71b11a429898b111a1b1b8109"
        files = self.fixture_inputs(report)
        with self.assertRaisesRegex(ValueError, "attestations"):
            COMP.compare(self.original, self.original_sha, *files)

    def test_compare_requires_same_run_selfcheck_count(self):
        self.selfcheck["built_module_symbols_versioned"] = 4
        files = self.fixture_inputs()
        with self.assertRaisesRegex(ValueError, "does not bind"):
            COMP.compare(self.original, self.original_sha, *files)

    def test_compare_rejects_wrong_original_sha(self):
        files = self.fixture_inputs()
        with self.assertRaisesRegex(ValueError, "differs from expected"):
            COMP.compare(self.original, "f" * 64, *files)


    def test_compare_rejects_non_string_vermagic_without_traceback(self):
        for value in (None, 123, [], {}):
            with self.subTest(vermagic=value):
                files = self.fixture_inputs()
                compiled = self.compiled_report()
                compiled["wlan_module"]["vermagic"] = value
                files[1].write_text(json.dumps(compiled))
                with self.assertRaisesRegex(ValueError, "malformed"):
                    COMP.compare(self.original, self.original_sha, *files)

    def test_compare_rejects_unapproved_module_signing_claim(self):
        files = self.fixture_inputs()
        compiled = self.compiled_report()
        compiled["wlan_module"]["signed_and_stripped"] = False
        files[1].write_text(json.dumps(compiled))
        with self.assertRaisesRegex(ValueError, "unsigned or malformed"):
            COMP.compare(self.original, self.original_sha, *files)

    def test_compare_rejects_nonzero_same_build_crc_errors(self):
        for flag in ("missing_exported_symbol_count", "mismatched_symbol_crc_count"):
            with self.subTest(flag=flag):
                selfcheck = dict(self.selfcheck, **{flag: 1})
                files = self.fixture_inputs()
                files[2].write_text(json.dumps(selfcheck))
                with self.assertRaisesRegex(ValueError, "attestations"):
                    COMP.compare(self.original, self.original_sha, *files)

    def test_compare_rejects_unverified_trust_claims(self):
        files = self.fixture_inputs()
        compiled = self.compiled_report()
        compiled["signer_trust_on_installed_rom_verified"] = True
        files[1].write_text(json.dumps(compiled))
        with self.assertRaisesRegex(ValueError, "attestations"):
            COMP.compare(self.original, self.original_sha, *files)

    def test_compare_strict_mode_never_implies_flash_ready(self):
        files = self.fixture_inputs()
        with patch.object(COMP.ABI, "inspect",
                          return_value=self.elf(self.original_sha, self.values, NEW_RELEASE)):
            result = COMP.compare(self.original, self.original_sha, *files)
        self.assertFalse(result["blockers"])
        self.assertFalse(result["flash_ready"])
        self.assertFalse(result["kernel_signing_trust_verified"])
        self.assertEqual("OFFLINE_SYMBOL_PARITY_ONLY", result["status"])


if __name__ == "__main__":
    unittest.main()
