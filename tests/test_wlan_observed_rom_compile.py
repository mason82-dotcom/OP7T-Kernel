"""Guards the exact observed-ROM-source WLAN compiler experiment."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = (ROOT / "scripts/build.sh").read_text(encoding="utf-8")
WORKFLOW = (ROOT / ".github/workflows/nethunter-kernel.yml").read_text(
    encoding="utf-8"
)
LOCK = (ROOT / "config/upstream.lock").read_text(encoding="utf-8")
AUDIT = (ROOT / "scripts/audit-wlan-compile.py").read_text(encoding="utf-8")
PARENT = "1083c6c5906114c71b11a429898b111a1b1b8109"
ROM = "57037290bb57caefd3c337db3511fca5751fb4ef"


class ObservedRomWlanCompilerTests(unittest.TestCase):
    def test_exact_rom_pin_is_opt_in_and_parent_lock_remains_intact(self):
        self.assertIn("UPSTREAM_SHA=" + PARENT, LOCK)
        self.assertNotIn("UPSTREAM_SHA=" + ROM, LOCK)
        self.assertIn('case "${WLAN_ROM_PIN_EXPERIMENT:-0}" in', BUILD)
        self.assertIn('WLAN_ROM_PIN_EXPERIMENT only accepts 0 or 1', BUILD)
        self.assertIn('ROM_SOURCE_SHA=' + ROM, BUILD)
        self.assertIn('[[ "$UPSTREAM_SHA" == ' + PARENT + ' ]]', BUILD)
        self.assertIn('WLAN_PATCH_EXPERIMENT=1 and core profile', BUILD)

    def test_sha_fetch_and_parity_precede_rom_worktree(self):
        fetch = 'git -C "$KERNEL" fetch --no-tags --depth=2 origin "$ROM_SOURCE_SHA"'
        preflight = 'python3 "$ROOT/scripts/check-wlan-rom-source-parity.py"'
        checkout = 'git -C "$ORIGINAL_KERNEL" worktree add --detach'
        self.assertLess(BUILD.index(fetch), BUILD.index(preflight))
        self.assertLess(BUILD.index(preflight), BUILD.index(checkout))
        self.assertIn('UPSTREAM_SHA="$ROM_SOURCE_SHA"', BUILD)
        self.assertIn('git -C "$ORIGINAL_KERNEL" worktree remove --force', BUILD)

    def test_observed_rom_wlan_build_and_stage_fully_isolated(self):
        for token in (
            'kernel-wlan${ROM_SUFFIX}-rfc-$PROFILE',
            'out-wlan${ROM_SUFFIX}-$PROFILE',
            'artifacts/wlan${ROM_SUFFIX}-$PROFILE',
            'module-stage-wlan${ROM_SUFFIX}-$PROFILE',
            'if [[ "${WLAN_ROM_PIN_EXPERIMENT:-0}" == 1 ]]',
            'wlan-rom-source-parity.json',
            'install -m 0644',
        ):
            with self.subTest(token=token):
                self.assertIn(token, BUILD)
        self.assertIn('--expected-sha "$UPSTREAM_SHA"', BUILD)
        self.assertIn('--require-signed --require-stripped', BUILD)

    def test_exact_two_sha_attestor_never_trusts_observed_rom_binary(self):
        self.assertIn('ROM_PIN = "' + ROM + '"', AUDIT)
        self.assertIn('expected_sha not in (PIN, ROM_PIN)', AUDIT)
        self.assertIn('rom_source_parity(artifacts, patches[0]["sha256"])', AUDIT)
        self.assertIn('"source_equivalence_verified") is True', AUDIT)
        self.assertIn('"rom_signing_key_trust_verified") is False', AUDIT)
        self.assertIn('"observed_rom_kernel_release_verified": False', AUDIT)
        self.assertIn('"installed_rom_kernel_binary_identical": False', AUDIT)
        self.assertIn('"rfc_behavioral_equivalence_verified": False', AUDIT)
        self.assertIn('"flash_ready": False', AUDIT)

    def test_ci_only_builds_opt_in_exact_rom_source_for_this_branch(self):
        key = "  wlan-rom-pinned-compile:"
        self.assertEqual(1, WORKFLOW.count(key))
        job = WORKFLOW.split(key, 1)[1].split(
            "  wlan-isolated-compile:", 1
        )[0]
        self.assertIn(
            "github.head_ref == 'experiment/hotdog-wlan-observed-rom-compile'",
            job,
        )
        self.assertIn("WLAN_ROM_PIN_EXPERIMENT: '1'", job)
        self.assertIn("WLAN_PATCH_EXPERIMENT: '1'", job)
        self.assertIn('needs: [lint, wlan-patch-qualification]', job)
        self.assertIn("wlan-rom-source-parity.json", job)
        self.assertNotIn("artifacts/wlan-rom-core/Image", job)
        self.assertNotIn("artifacts/wlan-rom-core/modules/", job)
        self.assertNotIn("signing_key.pem", job)
        self.assertNotIn("workflow_dispatch", job)
        self.assertIn(
            "github.head_ref != 'experiment/hotdog-wlan-observed-rom-compile'",
            WORKFLOW,
        )


if __name__ == "__main__":
    unittest.main()
