import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import subprocess

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "compare-kernel-references.py"
SPEC = importlib.util.spec_from_file_location("reference_compare", SCRIPT)
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)

SHA_A = "a" * 40
SHA_B = "b" * 40


def create_tree(base, suffix, overlay="", defconfig=""):
    base.mkdir()
    (base / "arch/arm64/configs/vendor").mkdir(parents=True)
    (base / "drivers/staging/qcacld-3.0").mkdir(parents=True)
    (base / "Makefile").write_text(
        "VERSION = 4\nPATCHLEVEL = 14\nSUBLEVEL = 357\nEXTRAVERSION = " + suffix + "\n"
    )
    (base / "arch/arm64/configs/vendor/sm8150-perf_defconfig").write_text(
        'CONFIG_LOCALVERSION="-perf"\nCONFIG_MODULE_SIG=y\n'
        "CONFIG_MODULE_SIG_FORCE=y\nCONFIG_MODVERSIONS=y\n" + defconfig
    )
    (base / "arch/arm64/configs/vendor/oplus.config").write_text(
        "CONFIG_QCA_CLD_WLAN=m\n" + overlay
    )
    (base / "drivers/staging/qcacld-3.0/Kconfig").write_text("config QCA_CLD_WLAN\n")


def git_fake(cmd, **kwargs):
    if cmd[0] != "git" or cmd[1] != "-C":
        raise AssertionError("only local git reads are allowed")
    if cmd[3:] == ["rev-parse", "HEAD"]:
        out = SHA_A if cmd[2].endswith("cr") else SHA_B
    elif cmd[3:] == ["status", "--porcelain", "--untracked-files=no"]:
        out = ""
    else:
        raise AssertionError("unknown git command")
    return subprocess.CompletedProcess(cmd, 0, out + ("\n" if out else ""), "")


class KernelReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cr = Path(self.temp.name) / "cr"
        self.lo = Path(self.temp.name) / "lo"
        create_tree(self.cr, "")
        create_tree(self.lo, "-openela", overlay="# CONFIG_MODULE_SIG is not set\n")
        self.manifest = {
            "schema": "op7t-kernel-reference-comparison-v1",
            "android_major": 17,
            "flash_ready": False,
            "target": "hotdog",
            "primary": {"sha": SHA_A},
            "alternative": {"sha": SHA_B},
        }

    @patch.object(M.subprocess, "run", side_effect=git_fake)
    def test_pinned_compare_is_explicitly_unverified(self, fake):
        cr = M.local_snapshot(self.cr, SHA_A)
        lo = M.local_snapshot(self.lo, SHA_B)
        result = M.compare(self.manifest, cr, lo)
        self.assertEqual("source_configuration_reference_only", result["status"])
        self.assertFalse(result["flash_ready"])
        self.assertFalse(result["effective_kernel_config_verified"])
        self.assertFalse(result["module_signatures_or_abi_verified"])
        self.assertIn("makefile_kernel_version_or_suffix_differs", result["manual_review_flags"])
        self.assertIn("lineage_oplus_overlay_explicitly_disables_module_signing",
                      result["manual_review_flags"])
        self.assertEqual("m", result["critical_requested_symbols"]["CONFIG_QCA_CLD_WLAN"]["lineage"])
        self.assertEqual("n", result["critical_requested_symbols"]["CONFIG_MODULE_SIG"]["lineage"])

    @patch.object(M.subprocess, "run", side_effect=git_fake)
    def test_wrong_source_pin_is_rejected(self, fake):
        with self.assertRaisesRegex(M.ReferenceError, "HEAD differs"):
            M.local_snapshot(self.cr, SHA_B)

    @patch.object(M.subprocess, "run", side_effect=git_fake)
    def test_missing_kconfig_source_fails_closed(self, fake):
        (self.lo / "drivers/staging/qcacld-3.0/Kconfig").unlink()
        with self.assertRaisesRegex(M.ReferenceError, "Missing"):
            M.local_snapshot(self.lo, SHA_B)

    def test_duplicate_config_symbol_rejected(self):
        with self.assertRaisesRegex(M.ReferenceError, "Duplicate"):
            M.config_entries("CONFIG_FOO=y\n# CONFIG_FOO is not set\n", "fixture")

    def test_makefile_version_has_bounds(self):
        with self.assertRaises(M.ReferenceError):
            M.parse_makefile("VERSION = 4\nPATCHLEVEL = 14\nSUBLEVEL = xyz\nEXTRAVERSION =\n")

    def test_invalid_manifest_cannot_claim_flash_readiness(self):
        a = {
            "source_sha": SHA_A,
            "kernel_makefile": {"version": "4.14.357", "extraversion": ""},
            "requested": {}, "overlay": {}, "source_sha256": {}, "qcacld_kconfig_exists": True
        }
        with self.assertRaisesRegex(M.ReferenceError, "Unsafe"):
            M.compare({**self.manifest, "flash_ready": True}, a, a)

    @patch.object(M.subprocess, "run", side_effect=git_fake)
    def test_end_to_end_local_json_cli(self, fake):
        target = Path(self.temp.name) / "manifest.json"
        target.write_text(json.dumps(self.manifest))
        import io
        from contextlib import redirect_stdout
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = M.main(["--crdroid-tree", str(self.cr), "--lineage-tree",
                           str(self.lo), "--manifest", str(target)])
        self.assertEqual(0, code)
        self.assertFalse(json.loads(stdout.getvalue())["flash_ready"])

    @patch.object(M.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "failed"))
    def test_git_failure_blocks_unverified_checkout(self, fake):
        with self.assertRaisesRegex(M.ReferenceError, "verification failed"):
            M.local_snapshot(self.cr, SHA_A)


if __name__ == "__main__":
    unittest.main()
