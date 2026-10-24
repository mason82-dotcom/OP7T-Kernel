import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("audit_toolchain", ROOT / "scripts/audit-toolchain.py")
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def executable(path, label):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nprintf '%s\\n' '" + label + "'\n", encoding="utf-8")
    path.chmod(0o755)
    return str(path)


class ToolchainAuditTests(unittest.TestCase):
    def setUp(self):
        self.ref = AUDIT.load_reference(ROOT / "config/toolchain-reference.json")

    def test_reference_version_is_explicit_and_unverified(self):
        self.assertEqual("clang-r596125", self.ref["expected_prebuilt_directory"])
        self.assertEqual("cp2a", self.ref["selected_aosp_release"])
        self.assertFalse(self.ref["original_20261021_ota_toolchain_verified"])

    def test_aosp_path_does_not_claim_rom_compatibility(self):
        with tempfile.TemporaryDirectory() as folder:
            prefix = Path(folder) / "clang-r596125/bin"
            cc = executable(prefix / "clang", "Android clang test")
            ld = executable(prefix / "ld.lld", "Android LLD test")
            result = AUDIT.inspect_tools(cc, ld, self.ref)
            self.assertTrue(result["aosp_prebuilt_path_layout_matches"])
            self.assertFalse(result["reference_binary_identity_verified"])
            self.assertFalse(result["official_rom_build_toolchain_verified"])
            self.assertFalse(result["installed_rom_abi_compatible_verified"])
            self.assertFalse(result["flash_ready"])
            self.assertEqual(64, len(result["compiler"]["sha256"]))
            self.assertNotIn(folder, str(result))

    def test_clang14_is_observably_not_the_upstream_default(self):
        with tempfile.TemporaryDirectory() as folder:
            prefix = Path(folder) / "llvm-14/bin"
            cc = executable(prefix / "clang", "Ubuntu clang version 14")
            ld = executable(prefix / "ld.lld", "LLD 14")
            report = AUDIT.inspect_tools(cc, ld, self.ref)
            self.assertFalse(report["aosp_prebuilt_path_layout_matches"])
            self.assertEqual("EXPERIMENTAL_DIFFERENT_TOOLCHAIN_PATH", report["status"])

    def test_missing_tool_fails_closed(self):
        with self.assertRaises(ValueError):
            AUDIT.inspect_tools("/definitely/not/present/clang", "ld.lld", self.ref)

    def test_reference_must_not_assert_binary_or_rom_validation(self):
        modified = dict(self.ref, original_20261021_ota_toolchain_verified=True)
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "ref.json"
            import json
            p.write_text(json.dumps(modified), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Untrusted"):
                AUDIT.load_reference(p)

    def test_reference_commit_must_be_pinned(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "ref.json"
            import json
            modified = dict(self.ref, source_commit="17.0")
            p.write_text(json.dumps(modified), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Untrusted"):
                AUDIT.load_reference(p)


if __name__ == "__main__":
    unittest.main()
