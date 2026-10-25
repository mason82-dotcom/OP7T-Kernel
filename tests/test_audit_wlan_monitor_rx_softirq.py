"""Offline source-level guard against calling a behavioral RX patch proven safe."""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/audit-wlan-monitor-rx-softirq.py"
SPEC = importlib.util.spec_from_file_location("softirq_context", SCRIPT)
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)

WLAN = """
#ifdef FEATURE_MONITOR_MODE_SUPPORT
static QDF_STATUS hdd_mon_rx_packet_cbk(void *context, qdf_nbuf_t rxbuf)
{
    struct sk_buff *skb;
    skb_next = skb->next;
    qdf_net_buf_debug_release_skb(skb);
    if (skb->next) {
        rxstat = netif_rx(skb);
    } else {
        /* This is the last packet on the chain
         * Scheduling rx sirq
         */
        rxstat = netif_rx_ni(skb);
    }
    return QDF_STATUS_SUCCESS;
}
#endif
#ifdef WLAN_FEATURE_PKT_CAPTURE
int hdd_set_pktcapture_cb(struct net_device *dev, uint8_t pdev_id)
{
    return cdp_register_pktcapture_cb(soc, pdev_id, adapter,
                                      hdd_mon_rx_packet_cbk);
}
#endif
#ifdef FEATURE_MONITOR_MODE_SUPPORT
int hdd_set_mon_rx_cb(struct net_device *dev)
{
    txrx_ops.rx.rx = hdd_mon_rx_packet_cbk;
    cdp_vdev_register(soc, adapter->vdev_id, adapter, &txrx_ops);
    return 0;
}
#endif
"""
DEV = """
int netif_rx(struct sk_buff *skb)
{
    trace_netif_rx_entry(skb);
    return netif_rx_internal(skb);
}
int netif_rx_ni(struct sk_buff *skb)
{
    int err;
    preempt_disable();
    err = netif_rx_internal(skb);
    if (local_softirq_pending())
        do_softirq();
    preempt_enable();
    return err;
}
"""
KBUILD = """
HDD_OBJS := $(HDD_SRC_DIR)/wlan_hdd_tx_rx.o
ifeq ($(CONFIG_LITHIUM), y)
HDD_OBJS += $(HDD_SRC_DIR)/wlan_hdd_rx_monitor.o
endif
"""
PROFILE = """
ifeq ($(CONFIG_ICNSS), y)
CONFIG_HELIUMPLUS := y
endif
"""
PATCH = (
    "diff --git a/" + CHECK.WLAN_PATH + " b/" + CHECK.WLAN_PATH + "\n"
    "--- a/" + CHECK.WLAN_PATH + "\n"
    "+++ b/" + CHECK.WLAN_PATH + "\n"
    "@@ -1,3 +1,3 @@\n"
    "- * Scheduling rx sirq\n"
    "+ * Same backlog path; avoid _ni BH handling\n"
    "- rxstat = netif_rx_ni(skb);\n"
    "+ rxstat = netif_rx(skb);\n"
)


class MonitorRxSoftirqContextTests(unittest.TestCase):
    def inspect(self, **overrides):
        sample = dict(wlan=WLAN, dev=DEV, kbuild=KBUILD,
                      profile=PROFILE, patch=PATCH)
        sample.update(overrides)
        return CHECK.inspect_sources(**sample)

    def test_original_semantics_and_runtime_blockers(self):
        result = self.inspect()
        self.assertEqual("ICNSS_HELIUMPLUS", result["driver_family"])
        self.assertTrue(result["original_last_skb_uses_netif_rx_ni"])
        self.assertTrue(result["kernel_netif_rx_ni_explicitly_drains_pending_softirq"])
        self.assertTrue(result["rfc_changes_last_skb_immediate_softirq_drain"])
        self.assertFalse(result["caller_cpu_context_verified"])
        self.assertFalse(result["caller_bh_and_napi_state_verified"])
        self.assertFalse(result["rfc_behavioral_equivalence_verified"])
        self.assertFalse(result["flash_ready"])

    def test_missing_or_double_callback_definition_fails(self):
        with self.assertRaises(CHECK.ContextAuditError):
            self.inspect(wlan=WLAN.replace("hdd_mon_rx_packet_cbk(void", "other_cb(void"))
        cb = WLAN.split("#endif", 1)[0]
        with self.assertRaises(CHECK.ContextAuditError):
            self.inspect(wlan=WLAN + cb)

    def test_changed_last_skb_dispatch_fails(self):
        with self.assertRaises(CHECK.ContextAuditError):
            self.inspect(wlan=WLAN.replace("rxstat = netif_rx_ni(skb);",
                                           "rxstat = netif_rx(skb);"))
        with self.assertRaises(CHECK.ContextAuditError):
            self.inspect(wlan=WLAN.replace("if (skb->next)", "if (other)"))

    def test_missing_monitor_registration_fails(self):
        with self.assertRaises(CHECK.ContextAuditError):
            self.inspect(wlan=WLAN.replace("cdp_vdev_register(", "cdp_vdev_attach("))
        with self.assertRaises(CHECK.ContextAuditError):
            self.inspect(wlan=WLAN.replace("cdp_register_pktcapture_cb(",
                                           "cdp_deregister_pktcapture_cb("))

    def test_kernel_softirq_semantics_divergence_is_required(self):
        with self.assertRaises(CHECK.ContextAuditError):
            self.inspect(dev=DEV.replace("do_softirq();", "raise_softirq();"))
        with self.assertRaises(CHECK.ContextAuditError):
            self.inspect(dev=DEV.replace(
                "return netif_rx_internal(skb);",
                "do_softirq();\n    return netif_rx_internal(skb);", 1
            ))

    def test_build_uses_heliumplus_and_excludes_lithium(self):
        with self.assertRaises(CHECK.ContextAuditError):
            self.inspect(profile=PROFILE.replace("CONFIG_HELIUMPLUS", "CONFIG_LITHIUM"))
        with self.assertRaises(CHECK.ContextAuditError):
            self.inspect(kbuild=KBUILD.replace(
                "$(HDD_SRC_DIR)/wlan_hdd_rx_monitor.o",
                "$(HDD_SRC_DIR)/mon_legacy.o",
            ))

    def test_patch_extra_modification_or_tampering_fails_closed(self):
        with self.assertRaises(CHECK.ContextAuditError):
            self.inspect(patch=PATCH + "+ disable_kernel_signature_check();\n")
        with self.assertRaises(CHECK.ContextAuditError):
            self.inspect(patch=PATCH.replace(
                "+ rxstat = netif_rx(skb);",
                "+ rxstat = netif_receive_skb(skb);",
            ))
        with self.assertRaises(CHECK.ContextAuditError):
            self.inspect(patch=PATCH + "\ndiff --git a/other.c b/other.c\n")

    def test_raw_source_code_is_read_only_and_no_runtime_approval(self):
        body = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('"flash_ready": False', body)
        self.assertIn('"rfc_behavioral_equivalence_verified": False', body)
        self.assertIn('"caller_bh_and_napi_state_verified": False', body)
        self.assertNotIn("fastboot flash", body)
        self.assertNotIn("adb shell", body)
        self.assertNotIn('git", "apply"', body)


if __name__ == "__main__":
    unittest.main()
