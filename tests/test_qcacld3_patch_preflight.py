import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/qcacld3-patch-preflight.py"
SPEC = importlib.util.spec_from_file_location("qcacld3_preflight", SCRIPT)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class Qcacld3PatchPreflightTests(unittest.TestCase):
    def setUp(self):
        self.ref = AUDIT.reference(ROOT / "config/qcacld3-injection-candidate.json")

    def test_candidate_is_pinned_and_never_flashable(self):
        self.assertEqual("2ea326d095d723b62c896160a1810f0c95bcc5bb", self.ref["source_commit"])
        self.assertEqual(43, len(self.ref["driver_paths"]))
        self.assertFalse(self.ref["automatic_patch_application"])
        self.assertFalse(self.ref["flash_ready"])

    def test_reviewed_file_list_is_exact(self):
        heads = b"".join(("diff --git a/" + p + " b/" + p + "\n").encode()
                         for p in self.ref["driver_paths"] + self.ref["excluded_non_driver_paths"])
        self.assertEqual(45, len(AUDIT.patch_headers(heads, self.ref)))

    def test_unexpected_path_rejected(self):
        heads = b"".join(("diff --git a/" + p + " b/" + p + "\n").encode()
                         for p in self.ref["driver_paths"] + self.ref["excluded_non_driver_paths"])
        with self.assertRaisesRegex(AUDIT.PreflightError, "file set"):
            AUDIT.patch_headers(heads + b"diff --git a/scripts/build.sh b/scripts/build.sh\n", self.ref)

    def test_duplicate_path_rejected(self):
        heads = b"".join(("diff --git a/" + p + " b/" + p + "\n").encode()
                         for p in self.ref["driver_paths"] + self.ref["excluded_non_driver_paths"])
        with self.assertRaisesRegex(AUDIT.PreflightError, "Duplicate"):
            AUDIT.patch_headers(heads + ("diff --git a/" + self.ref["driver_paths"][0] + " b/" + self.ref["driver_paths"][0] + "\n").encode(), self.ref)

    def test_binary_patch_rejected(self):
        with self.assertRaises(AUDIT.PreflightError):
            AUDIT.patch_headers(b"diff --git a/example b/example\nGIT binary patch\n", self.ref)

    def test_inconsistent_manifest_fails_closed(self):
        changed = dict(self.ref, flash_ready=True)
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "candidate.json"
            file.write_text(json.dumps(changed))
            with self.assertRaisesRegex(AUDIT.PreflightError, "Invalid source"):
                AUDIT.reference(file)

    def test_clean_dummy_repo_reports_conflict_not_application(self):
        with tempfile.TemporaryDirectory() as folder:
            d = Path(folder)
            subprocess.run(["git", "init", "-q", str(d / "kernel")], check=True)
            subprocess.run(["git", "-C", str(d / "kernel"), "-c", "user.email=x@y.local",
                            "-c", "user.name=Unit Test", "commit", "-q", "--allow-empty", "-m", "empty"], check=True)
            head = subprocess.check_output(["git", "-C", str(d / "kernel"), "rev-parse", "HEAD"], text=True).strip()
            changed = dict(self.ref, target_commit=head)
            paths = self.ref["driver_paths"] + self.ref["excluded_non_driver_paths"]
            text = "".join("diff --git a/" + p + " b/" + p + "\n"
                           for p in paths)
            patchfile = d / "example.patch"
            patchfile.write_text(text)
            with patch.object(AUDIT, "patch_headers", return_value=paths):
                result = AUDIT.inspect(patchfile, d / "kernel", changed)
            self.assertEqual("PATCH_CONTEXT_CONFLICTS", result["status"])
            self.assertFalse(result["flash_ready"])
            self.assertFalse(result["patch_applied"])


if __name__ == "__main__":
    unittest.main()
