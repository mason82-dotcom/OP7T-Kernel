# ICNSS monitor RX: softirq behavior and release blockers

This is a **host-side, read-only source audit**, not a change to the WLAN driver or an invitation to flash an experimental module. Target: OnePlus 7T Pro (`hotdog`) and crDroid 13 / Android 17; immutable upstream source `1083c6c5906114c71b11a429898b111a1b1b8109`. The observed ROM-source child commit `57037290bb57caefd3c337db3511fca5751fb4ef` has unchanged WLAN build inputs (see draft PR #34).

## What the pinned Linux 4.14 kernel does

In `net/core/dev.c`, `netif_rx()` queues the skb via `netif_rx_internal()` and returns. `netif_rx_ni()` also calls `netif_rx_internal()`, but disables preemption and, if `local_softirq_pending()`, calls `do_softirq()` before returning. This is **observable scheduling semantics**, not a cosmetic API choice.

In the selected QCACLD-3.0 source `drivers/staging/qcacld-3.0/core/hdd/src/wlan_hdd_tx_rx.c`, the monitor callback `hdd_mon_rx_packet_cbk()` enqueues all non-final skbs using `netif_rx()` and the last skb with `netif_rx_ni()`. The original final-skb comment explicitly says it schedules the RX softirq.

The callback has two distinct registration paths:

- `hdd_set_mon_rx_cb()` assigns it to `txrx_ops.rx.rx` then registers via `cdp_vdev_register()`.
- `hdd_set_pktcapture_cb()` registers it with `cdp_register_pktcapture_cb()` when packet capture is compiled; packet capture is conditional and should not be presumed enabled.

The experimental ICNSS RFC from PR #23 / compile experiment PR #27 changes the final-skb call to `netif_rx()`, **removing the direct pending-softirq drain** from this callback. Static source and compiler tests cannot determine which context invokes it, whether a softirq is already running, or how the firmware's monitor traffic actually arrives.

## Added guard

`scripts/audit-wlan-monitor-rx-softirq.py` fails closed unless the unmodified original Git source has the exact pinned SHA and is clean, the board selects ICNSS and the default module profile, the two callback registration sites are present, both original skb branches remain as expected, Linux's `netif_rx` versus `netif_rx_ni` implementation still differs as described, and the RFC still changes **only** the selected final-skb backlog call/comment.

For a read-only local source analysis:

```sh
bash scripts/fetch-source.sh
python3 scripts/audit-wlan-monitor-rx-softirq.py --kernel .work/kernel
```

The gated `wlan-monitor-rx-softirq` GitHub Actions job emits a small JSON report; it does not build or publish modules or raw kernels. Eight regression tests reject missing callback/registration, altered softirq behavior, changed target, nonselected profile and patch-scope expansion.

## Promotion blocked by missing evidence

1. A trustworthy trace or full review of the actual `cdp_vdev_register` and optional packet-capture callback invocation chain, especially process/softirq/IRQ/BH/NAPI execution contexts. A registration function is **not** evidence of caller context.
2. Validation that last-skb backlog delivery and scheduling remain correct, with no packets stranded and no unacceptable recursion, backlog drop or latency changes.
3. Independent exact-ROM build and module ABI/CRC and trust analysis (the current experimental source is the *parent* of the observed ROM commit). Charger-source changes in the ROM child also require independent safety review.
4. Hardware tests of ordinary Wi-Fi stability and authorized passive monitor reception before any runtime feature claims. This project does not assume packet injection works.

**Source audit success is explicitly `rfc_behavioral_equivalence_verified=false`, `caller_bh_and_napi_state_verified=false`, `flash_ready=false`. No boot image creation, flashing, module signature bypass, AVB changes, or automatic merges.**

## Legacy datapath branch analysis

The pinned compiled `core/dp/txrx/ol_txrx.c` stores `txrx_ops->rx.rx` in `vdev->rx`. Its RX handler obtains this callback and releases the peer BH spinlock before invoking `data_rx(osif_dev, buf)`. The path is not single-mode: `ol_rx_data_process()` calls `ol_rx_data_handler()` directly when the RX thread is disabled; when enabled under `QCA_CONFIG_SMP` it submits `ol_rx_data_cb` through `cds_indicate_rxpkt()`. The source comment states T2H traffic may run in SIRQ context. These branches demonstrate **possible** execution paths, **not** which branch is active for monitor traffic on the physical device. Actual BH/NAPI state remains unknown.

The static auditor now checks these dispatch anchors and emits a separate `legacy_rx_dispatch` object; all runtime-context flags remain false. If upstream callback assignment, dispatch, or lock ordering differs, the audit refuses to claim even static parity.
