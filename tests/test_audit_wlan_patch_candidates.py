import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/audit-wlan-patch-candidates.py"
SPEC = importlib.util.spec_from_file_location("wlan_audit", SCRIPT)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class WlanPatchCandidateTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.src = Path(self.folder.name)
        self.write("configs/default_defconfig", "CONFIG_FEATURE_MONITOR_MODE_SUPPORT := y\n")
        self.write("Kbuild", "HDD_OBJS += wlan_hdd_rx_monitor.o\nCONFIG_LITHIUM\nCONFIG_WLAN_FEATURE_PKT_CAPTURE\n")
        self.write("core/hdd/src/wlan_hdd_rx_monitor.c", "rxstat = netif_rx(skb);\nrxstat = netif_rx_ni(skb);\n")
        self.write("core/hdd/src/wlan_hdd_tx_rx.c",
                   "static QDF_STATUS hdd_mon_rx_packet_cbk(void *context, qdf_nbuf_t rxbuf)\n"
                   "{\n"
                   "\trxstat = netif_rx(skb);\n"
                   "\trxstat = netif_rx_ni(skb);\n"
                   "}\n#endif\n")
        self.write_extra("arch/arm64/configs/vendor/sm8150-perf_defconfig",
                         "CONFIG_ICNSS=y\n")
        self.write_extra("arch/arm64/configs/vendor/oplus.config",
                         'CONFIG_QCA_CLD_WLAN=m\nCONFIG_QCA_CLD_WLAN_PROFILE="default"\n')

    def write(self, relative, value):
        p = self.src / AUDIT.BASE / relative
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(value, encoding="utf-8")

    def write_extra(self, relative, value):
        path = self.src / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")

    def test_hotdog_icnss_callback_is_selected(self):
        report = AUDIT.inspect_source(self.src)
        self.assertTrue(report["hotdog_icnss_configured"])
        self.assertTrue(report["hotdog_icnss_rx_rfc_anchor_matches"])
        self.assertTrue(report["hotdog_patch_applicable_by_source"])
        self.assertEqual(
            "0002-qcacld-hotdog-icnss-monitor-rx-rfc.patch",
            report["selected_monitor_rx_candidate"],
        )
        self.assertFalse(report["flash_ready"])
        self.assertFalse(report["patch_applied"])

    def test_lithium_callback_does_not_prove_hotdog_rx_compatibility(self):
        self.write("core/hdd/src/wlan_hdd_tx_rx.c",
                   "static QDF_STATUS hdd_mon_rx_packet_cbk(void *x, qdf_nbuf_t y)\n"
                   "{\nrxstat = netif_rx(skb);\n}\n#endif\n")
        report = AUDIT.inspect_source(self.src)
        self.assertTrue(report["rx_rfc_anchor_matches"])
        self.assertFalse(report["hotdog_icnss_rx_rfc_anchor_matches"])
        self.assertFalse(report["hotdog_patch_applicable_by_source"])

    def test_non_icnss_source_cannot_claim_hotdog_patch(self):
        self.write_extra("arch/arm64/configs/vendor/sm8150-perf_defconfig",
                         "# CONFIG_ICNSS is not set\n")
        report = AUDIT.inspect_source(self.src)
        self.assertFalse(report["hotdog_icnss_configured"])
        self.assertFalse(report["hotdog_patch_applicable_by_source"])
        self.assertIsNone(report["selected_monitor_rx_candidate"])

    def test_unsigned_or_unknown_qcacld_mode_not_assumed(self):
        self.write_extra("arch/arm64/configs/vendor/oplus.config",
                         'CONFIG_QCA_CLD_WLAN=y\nCONFIG_QCA_CLD_WLAN_PROFILE="default"\n')
        report = AUDIT.inspect_source(self.src)
        self.assertFalse(report["qcacld_is_module"])
        self.assertFalse(report["hotdog_patch_applicable_by_source"])

    def test_candidate_patch_is_off_by_default_and_scoped(self):
        patch = (SCRIPT.parent.parent / "patches/candidates/"
                 "0002-qcacld-hotdog-icnss-monitor-rx-rfc.patch").read_text()
        self.assertIn("core/hdd/src/wlan_hdd_tx_rx.c", patch)
        self.assertIn("-\t\t\trxstat = netif_rx_ni(skb);", patch)
        self.assertIn("+\t\t\trxstat = netif_rx(skb);", patch)
        self.assertNotIn("wlan_hdd_frame_inject.c", patch)
        self.assertNotIn("fastboot", patch)

    def test_existing_monitor_flag_means_patch_is_redundant(self):
        result = AUDIT.inspect_source(self.src)
        self.assertTrue(result["kimocoder_patch_redundant"])
        self.assertTrue(result["rx_rfc_anchor_matches"])
        self.assertFalse(result["patch_applied"])
        self.assertFalse(result["flash_ready"])

    def test_changed_source_anchor_not_eligible(self):
        self.write("core/hdd/src/wlan_hdd_rx_monitor.c", "void callback() {}\n")
        self.assertFalse(AUDIT.inspect_source(self.src)["rx_rfc_anchor_matches"])

    def test_duplicate_config_fails_closed(self):
        self.write("configs/default_defconfig", "CONFIG_FEATURE_MONITOR_MODE_SUPPORT := y\nCONFIG_FEATURE_MONITOR_MODE_SUPPORT := n\n")
        with self.assertRaises(ValueError):
            AUDIT.inspect_source(self.src)

    def test_missing_rx_source_fails_closed(self):
        (self.src / AUDIT.BASE / "core/hdd/src/wlan_hdd_rx_monitor.c").unlink()
        with self.assertRaises(ValueError):
            AUDIT.inspect_source(self.src)

    def test_patch_is_not_wired_into_kernel_build(self):
        build = (SCRIPT.parent / "build.sh").read_text(encoding="utf-8")
        self.assertNotIn("patches/candidates/", build)
        self.assertNotIn("audit-wlan-patch-candidates.py", build)


if __name__ == "__main__":
    unittest.main()
