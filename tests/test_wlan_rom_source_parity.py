"""Offline tests for pinned ICNSS ROM-source parity; no device access."""
import difflib
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/check-wlan-rom-source-parity.py"
SPEC = importlib.util.spec_from_file_location("hotdog_rom_source_parity", SCRIPT)
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)

RX = GATE.WLAN_INPUTS[-1]
RX_BODY = (
    "static QDF_STATUS hdd_mon_rx_packet_cbk(void *context)\n"
    "{\n"
    "rxstat = netif_rx_ni(skb);\n"
    "}\n"
)


class RomSourceParityTests(unittest.TestCase):
    def git(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.repo), *args],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
        ).stdout.strip()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.repo = base / "source"
        self.repo.mkdir()
        self.git("init")
        self.git("config", "user.email", "rom-parity-fixture@example.invalid")
        self.git("config", "user.name", "ROM parity fixture")
        contents = {
            GATE.WLAN_INPUTS[0]: "CONFIG_ICNSS=y\n",
            GATE.WLAN_INPUTS[1]: (
                'CONFIG_QCA_CLD_WLAN=m\n'
                'CONFIG_QCA_CLD_WLAN_PROFILE="default"\n'
            ),
            GATE.WLAN_INPUTS[2]: "HDD_OBJS := $(HDD_SRC_DIR)/wlan_hdd_tx_rx.o\n",
            GATE.WLAN_INPUTS[3]: (
                "ifeq ($(CONFIG_ICNSS), y)\n"
                "\tCONFIG_HELIUMPLUS := y\n"
                "endif\n"
                "CONFIG_FEATURE_MONITOR_MODE_SUPPORT := y\n"
            ),
            RX: RX_BODY,
        }
        for path in GATE.ALLOWED_ROM_CHANGES:
            contents[path] = "charger-state-original\n"
        for name, data in contents.items():
            file = self.repo / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(data, encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", "pinned parent")
        self.parent = self.git("rev-parse", "HEAD")
        for name in GATE.ALLOWED_ROM_CHANGES:
            (self.repo / name).write_text(
                "charger-state-observed-in-ROM\n", encoding="utf-8"
            )
        self.git("add", ".")
        self.git("commit", "-m", "later ROM source")
        self.child = self.git("rev-parse", "HEAD")
        self.git("checkout", "--detach", self.parent)
        patched = RX_BODY.replace("netif_rx_ni(skb)", "netif_rx(skb)")
        diff = "".join(difflib.unified_diff(
            RX_BODY.splitlines(keepends=True),
            patched.splitlines(keepends=True),
            fromfile="a/" + RX,
            tofile="b/" + RX,
        ))
        self.patch = base / "icnss.patch"
        self.patch.write_text(
            "diff --git a/" + RX + " b/" + RX + "\n" + diff,
            encoding="utf-8",
        )

    def test_exact_parent_child_and_identical_wlan_sources(self):
        result = GATE.inspect_revisions(self.repo, self.parent, self.child)
        self.assertEqual(len(GATE.WLAN_INPUTS), len(result))
        self.assertEqual(
            [x["path"] for x in result], list(GATE.WLAN_INPUTS)
        )

    def test_patch_applies_to_both_read_only_and_stays_unflashable(self):
        result = GATE.qualify(self.repo, self.patch, self.parent, self.child)
        self.assertTrue(result["source_equivalence_verified"])
        self.assertTrue(result["selected_patch"]["apply_check_parent"])
        self.assertTrue(result["selected_patch"]["apply_check_rom_source"])
        self.assertFalse(result["selected_patch"]["applied"])
        self.assertFalse(result["rom_module_abi_verified"])
        self.assertFalse(result["rom_signing_key_trust_verified"])
        self.assertFalse(result["charger_change_safety_verified"])
        self.assertFalse(result["flash_ready"])
        self.assertEqual(self.parent, self.git("rev-parse", "HEAD"))
        self.assertEqual("", self.git("status", "--porcelain"))
        worktrees = self.git("worktree", "list", "--porcelain")
        self.assertEqual(1, worktrees.count("worktree "))

    def test_rejects_unknown_revision_or_non_direct_child(self):
        with self.assertRaises(GATE.ParityError):
            GATE.inspect_revisions(self.repo, self.parent, self.parent)
        with self.assertRaises(GATE.ParityError):
            GATE.inspect_revisions(self.repo, "f" * 40, self.child)

    def test_unexpected_driver_change_fails_closed(self):
        self.git("checkout", "--detach", self.child)
        (self.repo / RX).write_text(RX_BODY + "\nchanged\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", "unexpected driver alteration")
        third = self.git("rev-parse", "HEAD")
        self.git("checkout", "--detach", self.child)
        with self.assertRaises(GATE.ParityError):
            GATE.inspect_revisions(self.repo, self.child, third)

    def test_missing_charger_changed_path_is_not_accepted(self):
        self.git("checkout", "--detach", self.parent)
        file = self.repo / sorted(GATE.ALLOWED_ROM_CHANGES)[0]
        file.write_text("single-charger-change\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", "only one charger source changed")
        one = self.git("rev-parse", "HEAD")
        self.git("checkout", "--detach", self.parent)
        with self.assertRaises(GATE.ParityError):
            GATE.inspect_revisions(self.repo, self.parent, one)

    def test_rejects_unchecked_dirty_original_source(self):
        (self.repo / RX).write_text("DIRTY\n", encoding="utf-8")
        with self.assertRaises(GATE.ParityError):
            GATE.inspect_revisions(self.repo, self.parent, self.child)

    def test_invalid_candidate_patch_fails_and_removes_worktree(self):
        self.patch.write_text("not a patch\n", encoding="utf-8")
        with self.assertRaises(GATE.ParityError):
            GATE.qualify(self.repo, self.patch, self.parent, self.child)
        self.assertEqual(1, self.git("worktree", "list", "--porcelain").count("worktree "))
        self.assertEqual("", self.git("status", "--porcelain"))

    def test_absent_or_large_patch_fails_closed(self):
        self.patch.unlink()
        with self.assertRaises((OSError, GATE.ParityError)):
            GATE.qualify(self.repo, self.patch, self.parent, self.child)
        self.patch.write_bytes(b"a" * (65536 + 1))
        with self.assertRaises(GATE.ParityError):
            GATE.qualify(self.repo, self.patch, self.parent, self.child)

    def test_no_network_or_device_changes(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('"flash_ready": False', source)
        self.assertIn('"charger_change_safety_verified": False', source)
        self.assertIn('git(root, "worktree", "remove", "--force"', source)
        self.assertNotIn("adb shell", source)
        self.assertNotIn("fastboot", source)
        self.assertNotIn('"apply", str(patch)', source)


if __name__ == "__main__":
    unittest.main()
