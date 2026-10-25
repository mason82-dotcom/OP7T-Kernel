"""Read-only tests for the pinned hotdog WLAN candidate gate."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/qualify-wlan-patches.py"
SPEC = importlib.util.spec_from_file_location("hotdog_wlan_gate", SCRIPT)
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class CandidateGateTests(unittest.TestCase):
    def test_real_candidate_paths_remain_bounded(self):
        self.assertEqual(2, len(GATE.CANDIDATES))
        seen = set()
        for name, relative, allowed in GATE.CANDIDATES:
            digest = GATE.validate_patch(ROOT / relative, allowed)
            self.assertEqual(64, len(digest))
            self.assertTrue(allowed.isdisjoint(seen))
            seen.update(allowed)
        self.assertEqual(3, len(seen))

    def test_unapproved_file_path_rejected(self):
        _, relative, allowed = GATE.CANDIDATES[1]
        raw = (ROOT / relative).read_text(encoding="utf-8")
        raw += ("diff --git a/arch/arm64/configs/vendor/oplus.config "
                "b/arch/arm64/configs/vendor/oplus.config\n"
                "--- a/arch/arm64/configs/vendor/oplus.config\n"
                "+++ b/arch/arm64/configs/vendor/oplus.config\n"
                "@@ -1 +1 @@\n-a\n+b\n")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "unexpected.patch"
            path.write_text(raw, encoding="utf-8")
            with self.assertRaises(GATE.GateError):
                GATE.validate_patch(path, allowed)

    def test_binary_rename_and_security_expansion_rejected(self):
        _, relative, allowed = GATE.CANDIDATES[0]
        content = (ROOT / relative).read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "unsafe.patch"
            for text in ("GIT binary patch\n", "rename from a/b\n",
                         "new file mode 100644\n",
                         "+CONFIG_MODULE_SIG_FORCE=n\n"):
                file.write_text(content + text, encoding="utf-8")
                with self.assertRaises(GATE.GateError):
                    GATE.validate_patch(file, allowed)

    def test_source_gates_distinguish_hotdog_and_other_branches(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            sample = {
                "defconfig": "CONFIG_ICNSS=y\n",
                "oplus": 'CONFIG_QCA_CLD_WLAN=m\nCONFIG_QCA_CLD_WLAN_PROFILE="default"\n',
                "profile": "CONFIG_FEATURE_MONITOR_MODE_SUPPORT := y\n",
                "icnss_rx": ("static QDF_STATUS hdd_mon_rx_packet_cbk(void *p)\n"
                             "{\nrxstat = netif_rx(skb);\n"
                             "rxstat = netif_rx_ni(skb);\n}\n#endif\n"),
                "lithium_rx": ("if (vdev_id < 0)\n"
                               "cdp_get_mon_vdev_from_pdev(soc, id);\n"),
                "dp": ("static uint8_t dp_get_mon_vdev_from_pdev_wifi3(void *soc)\n"
                       "{\nif (qdf_unlikely(!pdev))\n"
                       "return pdev->monitor_vdev->vdev_id;\n}\n"
                       "static int dp_other(void *soc)\n"
                       "{\nif (qdf_unlikely(!pdev))\nreturn -EINVAL;\n}\n"),
            }
            for label, value in sample.items():
                path = root / GATE.SOURCE[label]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(value, encoding="utf-8")
            ok = GATE.inspect_source(root)
            self.assertTrue(ok["eligible"])
            path = root / GATE.SOURCE["defconfig"]
            path.write_text("# CONFIG_ICNSS is not set\n", encoding="utf-8")
            self.assertFalse(GATE.inspect_source(root)["eligible"])

    def test_callback_ambiguous_or_missing_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            contents = {
                "defconfig": "CONFIG_ICNSS=y\n",
                "oplus": 'CONFIG_QCA_CLD_WLAN=m\nCONFIG_QCA_CLD_WLAN_PROFILE="default"\n',
                "profile": "CONFIG_FEATURE_MONITOR_MODE_SUPPORT := y\n",
                "icnss_rx": "static QDF_STATUS hdd_mon_rx_packet_cbk(void *p) {}\n",
                "lithium_rx": "if (vdev_id < 0)\ncdp_get_mon_vdev_from_pdev(soc, id);\n",
                "dp": ("static uint8_t dp_get_mon_vdev_from_pdev_wifi3(void *soc)\n"
                       "{\nif (qdf_unlikely(!pdev))\n"
                       "return pdev->monitor_vdev->vdev_id;\n}\n"),
            }
            for label, value in contents.items():
                path = root / GATE.SOURCE[label]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(value, encoding="utf-8")
            result = GATE.inspect_source(root)
            self.assertFalse(result["eligible"])
            self.assertFalse(result["legacy_callback_anchor_matched"])

    def test_mon_vdev_getter_missing_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            samples = {
                "defconfig": "CONFIG_ICNSS=y\n",
                "oplus": 'CONFIG_QCA_CLD_WLAN=m\nCONFIG_QCA_CLD_WLAN_PROFILE="default"\n',
                "profile": "CONFIG_FEATURE_MONITOR_MODE_SUPPORT := y\n",
                "icnss_rx": ("static QDF_STATUS hdd_mon_rx_packet_cbk(void *p)\n"
                             "{\nrxstat = netif_rx(skb);\n"
                             "rxstat = netif_rx_ni(skb);\n}\n#endif\n"),
                "lithium_rx": ("if (vdev_id < 0)\n"
                               "cdp_get_mon_vdev_from_pdev(soc, id);\n"),
                "dp": ("static int dp_other(void)\n"
                       "{\nif (qdf_unlikely(!pdev))\n"
                       "return pdev->monitor_vdev->vdev_id;\n}\n"),
            }
            for label, content in samples.items():
                path = root / GATE.SOURCE[label]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            self.assertFalse(GATE.inspect_source(root)["vdev_safety_anchor_matched"])
            self.assertFalse(GATE.inspect_source(root)["eligible"])

    def test_build_keeps_wlan_patches_disabled(self):
        text = (ROOT / "scripts/build.sh").read_text(encoding="utf-8")
        self.assertIn('case "${WLAN_PATCH_EXPERIMENT:-0}" in', text)
        self.assertIn("  0) ;;", text)
        self.assertIn("  1)\n    echo", text)
        self.assertIn('python3 "$ROOT/scripts/qualify-wlan-patches.py"', text)
        self.assertIn('git -C "$EXP_TREE" apply', text)
        self.assertLess(text.index("  0) ;;"), text.index('git -C "$EXP_TREE" apply'))
        self.assertIn("INSTALL_MOD_STRIP=1", text)
        self.assertIn("--require-signed --require-stripped", text)
        self.assertIn('ART="$ROOT/.work/artifacts/wlan${ROM_SUFFIX}-$PROFILE"', text)

    def test_no_runtime_or_flash_claim(self):
        script = SCRIPT.read_text(encoding="utf-8")
        for marker in ('"patch_applied": False', '"flash_ready": False',
                       '"patched_modules_compiled": False',
                       '"packet_injection_verified": False'):
            self.assertIn(marker, script)


if __name__ == "__main__":
    unittest.main()
