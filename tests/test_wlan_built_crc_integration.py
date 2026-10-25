"""Source-only integration checks for ROM-source CRC self-audit job."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = (ROOT / "scripts/build.sh").read_text(encoding="utf-8")
CI = (ROOT / ".github/workflows/nethunter-kernel.yml").read_text(
    encoding="utf-8"
)
CHECK = (ROOT / "scripts/audit-wlan-built-crcs.py").read_text(
    encoding="utf-8"
)


class WlanBuiltCrcIntegrationTests(unittest.TestCase):
    def test_audit_occurs_after_signed_module_and_prior_compiler_gate(self):
        sign = BUILD.index("INSTALL_MOD_STRIP=1 DEPMOD=true modules_install")
        prior = BUILD.index('python3 "$ROOT/scripts/audit-wlan-compile.py"')
        crc = BUILD.index('python3 "$ROOT/scripts/audit-wlan-built-crcs.py"')
        sums = BUILD.index("find . -type f ! -name SHA256SUMS")
        self.assertLess(sign, prior)
        self.assertLess(prior, crc)
        self.assertLess(crc, sums)

    def test_gate_is_exclusively_child_rom_source_experiment(self):
        guard = 'if [[ "${WLAN_ROM_PIN_EXPERIMENT:-0}" == 1 ]]; then'
        snippet = BUILD.split("# Checks only rebuilt ELF imports", 1)[1]
        self.assertTrue(snippet.strip().startswith("against its own generated Module.symvers."))
        self.assertIn(guard, snippet)
        self.assertIn('--artifacts "$ART"', snippet)
        self.assertIn("ROM_PIN_EXPERIMENT only accepts 0 or 1", BUILD)

    def test_ci_upload_never_exposes_module_symvers_or_signing_key(self):
        job = CI.split("  wlan-rom-pinned-compile:", 1)[1].split(
            "  wlan-isolated-compile:", 1
        )[0]
        self.assertIn("built-wlan-self-crc-report.json", job)
        self.assertIn(
            "github.head_ref == 'research/hotdog-wlan-built-crc-selfcheck'",
            job,
        )
        self.assertIn("WLAN_ROM_PIN_EXPERIMENT: '1'", job)
        self.assertIn("WLAN_PATCH_EXPERIMENT: '1'", job)
        for prohibited in (
            ".work/artifacts/wlan-rom-core/Module.symvers",
            ".work/artifacts/wlan-rom-core/modules/",
            ".work/artifacts/wlan-rom-core/Image",
            ".work/artifacts/wlan-rom-core/dtbs/",
            "signing_key.pem",
            "workflow_dispatch",
        ):
            with self.subTest(prohibited=prohibited):
                self.assertNotIn(prohibited, job)

    def test_main_pr_compiles_unchanged_while_research_stays_draft(self):
        self.assertIn(
            "github.head_ref != 'research/hotdog-wlan-built-crc-selfcheck'",
            CI,
        )
        self.assertIn('"flash_ready": False', CHECK)
        self.assertIn('"installed_kernel_signing_trust_verified": False', CHECK)
        self.assertIn('"actual_ROM_kernel_binary_identity_verified": False', CHECK)
        self.assertNotIn("fastboot flash", CHECK)
        self.assertNotIn("adb shell", CHECK)


if __name__ == "__main__":
    unittest.main()
