import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "compare-rom-modules.py"
SPEC = importlib.util.spec_from_file_location("module_comparison", SCRIPT)
COMPARE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COMPARE)


def sample():
    return {
        "name": "wlan",
        "vermagic": "4.14.357-perf SMP preempt mod_unload modversions aarch64",
        "signer": "Kernel build key",
        "sig_key": "AB:CD",
        "sig_hashalgo": "sha512",
    }


class ModuleComparisonTests(unittest.TestCase):
    def test_same_metadata_still_not_flash_approved(self):
        result = COMPARE.compare(sample(), sample())
        self.assertEqual("needs_live_trust_and_abi_review", result["status"])
        self.assertFalse(result["flash_ready"])
        self.assertFalse(result["installed_kernel_key_trust_verified"])

    def test_vermagic_difference_blocks(self):
        built, rom = sample(), sample()
        rom["vermagic"] = "4.14.350-perf SMP"
        result = COMPARE.compare(built, rom)
        self.assertEqual("known_metadata_mismatch", result["status"])
        self.assertIn("vermagic strings differ", result["metadata_mismatches"])

    def test_signing_key_difference_blocks(self):
        built, rom = sample(), sample()
        rom["sig_key"] = "EF:99"
        result = COMPARE.compare(built, rom)
        self.assertIn("module signature key identifiers differ", result["metadata_mismatches"])

    def test_absent_signature_is_unknown_not_success(self):
        built, rom = sample(), sample()
        built["sig_key"] = None
        result = COMPARE.compare(built, rom)
        self.assertEqual("needs_live_trust_and_abi_review", result["status"])
        self.assertTrue(result["metadata_unknowns"])
        self.assertFalse(result["flash_ready"])


if __name__ == "__main__":
    unittest.main()
