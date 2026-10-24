import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from subprocess import CompletedProcess

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("wlan_patch_preflight", ROOT / "scripts/check-wlan-patches.py")
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)
COMMIT = "1083c6c5906114c71b11a429898b111a1b1b8109"


class WlanPatchPreflightTests(unittest.TestCase):
    def test_only_two_expected_driver_paths_are_touched(self):
        value = M.validate_patch()
        self.assertEqual(64, len(value))
        self.assertEqual(2, len(M.ALLOWED))

    def test_source_commit_is_pinned(self):
        self.assertEqual(COMMIT, M.expected_commit())

    def test_unknown_patch_destination_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad.patch"
            p.write_text(
                "diff --git a/arch/arm64/kernel/start.S b/arch/arm64/kernel/start.S\\n"
                "diff --git a/other b/other\\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(M.PreflightError, "unexpected source paths"):
                M.validate_patch(p)

    def test_success_never_applies_or_verifies_runtime(self):
        with tempfile.TemporaryDirectory() as d:
            kernel = Path(d) / "kernel"
            (kernel / ".git").mkdir(parents=True)
            fake = [
                CompletedProcess([], 0, stdout=COMMIT + "\\n"),
                CompletedProcess([], 0, stdout=""),
                CompletedProcess([], 0, stdout=""),
            ]
            with patch.object(M.subprocess, "run", side_effect=fake) as run:
                report = M.check(kernel)
            self.assertTrue(report["patch_applicable_to_clean_source"])
            self.assertFalse(report["patch_applied"])
            self.assertFalse(report["patch_compiled"])
            self.assertFalse(report["flash_ready"])
            self.assertEqual(3, run.call_count)
            arguments = run.call_args_list[-1].args[0]
            self.assertEqual(["apply", "--check"], arguments[3:5])

    def test_modified_source_is_rejected_before_patch_check(self):
        with tempfile.TemporaryDirectory() as d:
            kernel = Path(d) / "kernel"
            (kernel / ".git").mkdir(parents=True)
            fake = [
                CompletedProcess([], 0, stdout=COMMIT + "\\n"),
                CompletedProcess([], 0, stdout=" M driver.c\\n"),
            ]
            with patch.object(M.subprocess, "run", side_effect=fake) as run:
                with self.assertRaisesRegex(M.PreflightError, "clean"):
                    M.check(kernel)
            self.assertEqual(2, run.call_count)

    def test_mismatched_kernel_sha_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            kernel = Path(d) / "kernel"
            (kernel / ".git").mkdir(parents=True)
            with patch.object(M.subprocess, "run",
                              return_value=CompletedProcess([], 0, stdout="0" * 40)):
                with self.assertRaisesRegex(M.PreflightError, "differs"):
                    M.check(kernel)


if __name__ == "__main__":
    unittest.main()
