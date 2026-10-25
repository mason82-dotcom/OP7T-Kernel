# Patch staging and acceptance

`patches/` is **not** an automatically applied collection of NetHunter patches. The `main` profile builder uses only the pinned upstream source plus explicitly defined configuration fragments. Research-only QCACLD monitor RX, monitor VDEV and injection candidates exist in separate draft PRs; never imply a candidate is enabled by default.

Before introducing a patch, record its upstream URL and **exact commit**, original author/license, target file/line context, applicability to the current [kernel source lock](../config/upstream.lock), expected kernel/firmware interactions, rollback and independent review. Prefer a small opt-in change applied in an isolated worktree with compile tests over a wholesale older driver-tree import.

Promotion requires a source-parity comparison, correct callback context/locking and error-path review, isolated build tests, and documented, authorized hardware behavior **after** [release gates](../docs/FLASHING.md) pass. See the [feature matrix](../docs/NETHUNTER_FEATURES.md) and [evidence ledger](../docs/HARDWARE_EVIDENCE.md). No current experimental patch grants flash authorization.
