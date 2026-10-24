"""Repository-level integration contract: fail closed across source workflows.

These checks inspect only repository source files. They do not establish
hardware compatibility or produce flashable artifacts.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class IntegratedKernelSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = (ROOT / "scripts/build.sh").read_text(encoding="utf-8")
        cls.ci = (ROOT / ".github/workflows/nethunter-kernel.yml").read_text(encoding="utf-8")

    def test_strip_occurs_during_module_install_before_signing(self):
        self.assertIn("INSTALL_MOD_STRIP=1", self.build)
        self.assertIn("modules_install", self.build)
        self.assertLess(self.build.index("INSTALL_MOD_STRIP=1"), self.build.index('STAGED_KERNEL='))
        self.assertIn("--require-signed --require-stripped", self.build)

    def test_toolchain_provenance_is_generated_with_each_profile(self):
        self.assertIn('scripts/audit-toolchain.py" --clang "$CC_BIN" --ld "$LD_BIN"', self.build)
        self.assertIn('--output "$ART/toolchain-report.json"', self.build)
        self.assertIn(".work/artifacts/${{ matrix.profile }}/toolchain-report.json", self.ci)

    def test_abi_audit_remains_offline(self):
        src = (ROOT / "scripts/audit-module-abi.py").read_text(encoding="utf-8")
        self.assertIn('"flash_ready": False', src)
        self.assertIn("--fail-on-unknown", src)
        self.assertNotIn("adb shell", src)
        self.assertNotIn("fastboot flash", src)

    def test_project_never_disables_signature_gates(self):
        self.assertIn("CONFIG_MODULE_SIG_FORCE", (ROOT / "scripts/audit-artifacts.py").read_text(encoding="utf-8"))
        self.assertIn('CONFIG_MODULE_SIG_KEY="certs/signing_key.pem"', self.build)
        self.assertIn("binutils", self.ci)


if __name__ == "__main__":
    unittest.main()
