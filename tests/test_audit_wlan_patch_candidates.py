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

    def write(self, relative, value):
        p = self.src / AUDIT.BASE / relative
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(value, encoding="utf-8")

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
