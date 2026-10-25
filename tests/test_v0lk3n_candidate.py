"""Offline regression tests for the isolated V0lk3n source replacement candidate."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = (ROOT / "config/v0lk3n.lock").read_text()
SECURITY = (ROOT / "config/v0lk3n-security.fragment").read_text()
BUILD = (ROOT / "scripts/build.sh").read_text()
FETCH = (ROOT / "scripts/fetch-v0lk3n.sh").read_text()
README = (ROOT / "docs/V0LK3N_CANDIDATE.md").read_text()
WORKFLOW = (ROOT / ".github/workflows/nethunter-kernel.yml").read_text()

class V0lk3nCandidateTests(unittest.TestCase):
    def test_pinned_source_is_lineage_23_not_crdroid(self):
        self.assertIn("V0LK3N_URL=https://github.com/V0lk3n/nethunter_kernel_oneplus_sm8150.git", LOCK)
        self.assertIn("V0LK3N_REF=nethunter-lineage-23.2", LOCK)
        self.assertRegex(LOCK, r"(?m)^V0LK3N_SHA=[a-f0-9]{40}$")
        self.assertIn("V0LK3N_SOURCE_ANDROID=16", LOCK)
        self.assertIn("V0LK3N_TARGET_ANDROID=17", LOCK)

    def test_enforced_signatures_never_downgraded(self):
        for line in (
            "CONFIG_MODULE_SIG=y",
            "CONFIG_MODULE_SIG_ALL=y",
            "CONFIG_MODULE_SIG_FORCE=y",
            'CONFIG_MODULE_SIG_KEY="certs/signing_key.pem"',
        ):
            self.assertIn(line, SECURITY)
        self.assertNotIn("CONFIG_MODULE_SIG_FORCE=n", SECURITY)
        self.assertIn("V0lk3n gate: CONFIG_MODULE_SIG_FORCE=y required", BUILD)
        self.assertIn("config/v0lk3n-security.fragment", BUILD)

    def test_source_isolated_from_crdroid_and_kernelsu(self):
        self.assertIn('.work/v0lk3n-kernel', FETCH)
        self.assertIn('.work/v0lk3n-kernel', BUILD)
        self.assertIn('out-v0lk3n-$PROFILE', BUILD)
        self.assertIn('artifacts/v0lk3n-$PROFILE', BUILD)
        self.assertIn('if [[ "$KERNEL_VARIANT" == v0lk3n ]]', BUILD)
        self.assertNotIn("prepare-kernelsu-next.sh", FETCH)
        self.assertIn("CONFIG_KSU=y", BUILD)  # explicit failure if unexpectedly enabled
        self.assertIn("refusing mixed profiles", BUILD)

    def test_manual_ci_uses_separate_candidate_paths(self):
        self.assertIn("options: [crdroid, v0lk3n]", WORKFLOW)
        variant = "github.event_name == 'workflow_dispatch' && inputs.variant == 'v0lk3n'"
        self.assertGreaterEqual(WORKFLOW.count(variant), 11)
        self.assertNotIn(".work/artifacts/${{ matrix.profile }}/", WORKFLOW)
        self.assertNotIn(".work/out-${{ matrix.profile }}/", WORKFLOW)
        self.assertIn('STAGE="$ROOT/.work/module-stage-v0lk3n-$PROFILE"', BUILD)

    def test_readonly_and_incompatibility_documented(self):
        for term in ("flash_ready=false", "Android 16", "Android 17", "185", "Magisk"):
            self.assertIn(term, README)
        self.assertIn("git -C \"$KERNEL\" checkout --detach \"$V0LK3N_SHA\"", FETCH)
        self.assertIn("--submodules", FETCH)


if __name__ == "__main__":
    unittest.main()
