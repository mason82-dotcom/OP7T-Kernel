"""Tests guarding opt-in isolated WLAN-patched kernel builds."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = (ROOT / "scripts/build.sh").read_text(encoding="utf-8")
WORKFLOW = (ROOT / ".github/workflows/nethunter-kernel.yml").read_text(
    encoding="utf-8"
)


class WlanIsolatedBuildTests(unittest.TestCase):
    def test_explicit_opt_in_only(self):
        self.assertIn('case "${WLAN_PATCH_EXPERIMENT:-0}" in', BUILD)
        self.assertIn("  0) ;;", BUILD)
        self.assertIn("  1)\n    echo", BUILD)
        self.assertIn("WLAN_PATCH_EXPERIMENT only accepts 0 or 1", BUILD)

    def test_source_isolated_in_git_worktree(self):
        self.assertIn('git -C "$ORIGINAL_KERNEL" worktree add --detach', BUILD)
        self.assertIn('git -C "$ORIGINAL_KERNEL" worktree remove --force', BUILD)
        self.assertIn('git -C "$ORIGINAL_KERNEL" status --porcelain', BUILD)
        self.assertIn('git -C "$EXP_TREE" diff --check', BUILD)
        self.assertIn('actual_paths="$(git -C "$EXP_TREE" diff --name-only)"', BUILD)
        self.assertIn('[[ "$actual_paths" == "$expected_paths" ]]', BUILD)

    def test_experimental_output_is_separate(self):
        self.assertIn('OUT="$ROOT/.work/out-wlan-$PROFILE"', BUILD)
        self.assertIn('ART="$ROOT/.work/artifacts/wlan-$PROFILE"', BUILD)
        self.assertIn('STAGE="$ROOT/.work/module-stage-wlan-$PROFILE"', BUILD)
        self.assertIn('wlan-patch-experiment.json', (ROOT / "scripts/audit-wlan-compile.py").read_text(encoding="utf-8"))
        self.assertIn('python3 "$ROOT/scripts/audit-wlan-compile.py"', BUILD)
        self.assertIn('"flash_ready": False', (ROOT / "scripts/audit-wlan-compile.py").read_text(encoding="utf-8"))
        self.assertIn('"signer_trust_on_installed_rom_verified": False', (ROOT / "scripts/audit-wlan-compile.py").read_text(encoding="utf-8"))

    def test_signed_stripped_module_audit_unchanged(self):
        self.assertIn("INSTALL_MOD_STRIP=1", BUILD)
        self.assertIn("--require-signed --require-stripped", BUILD)
        self.assertIn("CONFIG_MODULE_SIG_ALL=y", BUILD)

    def test_isolated_ci_upload_excludes_raw_kernel(self):
        self.assertIn("  wlan-isolated-compile:", WORKFLOW)
        self.assertIn("github.head_ref == 'feature/hotdog-wlan-compile-experiment'",
                      WORKFLOW)
        job = WORKFLOW.split("  wlan-isolated-compile:", 1)[1].split(
            "  build:", 1
        )[0]
        self.assertIn("WLAN_PATCH_EXPERIMENT:", job)
        self.assertIn(".work/artifacts/wlan-core/wlan-patch-experiment.json", job)
        self.assertNotIn(".work/artifacts/wlan-core/Image", job)
        self.assertNotIn(".work/artifacts/wlan-core/modules/", job)
        self.assertNotIn("workflow_dispatch", job)

    def test_normal_pr_profiles_remain_available(self):
        self.assertIn("  build:\n    if: github.event_name", WORKFLOW)
        self.assertIn('["core","external"]', WORKFLOW.replace('\\\\', '\\'))


if __name__ == "__main__":
    unittest.main()
