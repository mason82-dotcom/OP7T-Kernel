# Documentation map

This index assigns **one canonical home per topic**. Other pages link here instead of copying status tables, release gates, commands or historical evidence verbatim.

| Question | Canonical document |
| --- | --- |
| What is the project, and where do I start? | [Repository README](../README.md) |
| How do I build, configure and interpret CI artifacts? | [BUILD.md](BUILD.md) |
| Which upstream ROM, board and compiler assumptions are in scope? | [CRDROID_17_BUILD_REFERENCE.md](CRDROID_17_BUILD_REFERENCE.md) |
| Which read-only device, OTA and artifact tools can I use? | [EVIDENCE_TOOLS.md](EVIDENCE_TOOLS.md) |
| What has been **observed** on physical hardware, and which gates remain open? | [HARDWARE_EVIDENCE.md](HARDWARE_EVIDENCE.md) |
| Why is flashing currently prohibited; what must be proven first? | [FLASHING.md](FLASHING.md) |
| How are module ABI differences compared offline? | [MODULE_ABI_AUDIT.md](MODULE_ABI_AUDIT.md) |
| Which NetHunter features and drivers have actually been implemented/tested? | [NETHUNTER_FEATURES.md](NETHUNTER_FEATURES.md) |
| How do candidate kernel patches get accepted? | [Patch staging](../patches/README.md) |

## Reading the evidence correctly

- **Implemented** means code or configuration exists on `main`, not that the connected device has accepted it.
- **CI PASS** means the specified CI assertions completed for a specific commit/artifact; it does not mean installed-ROM compatibility.
- **Reference OTA** means a locally or publicly verified reference archive; it is **not proof of what is installed**.
- **Draft PR** means optional, unmerged research. Review its base branch and commit before treating a result as applicable to `main`.
- **UNKNOWN** means the acceptance evidence has not been obtained, not that it passed or failed.
- **NOT FLASHABLE** is the current repository-wide release state; see [FLASHING.md](FLASHING.md).

Do not request repetition of already-completed device inventories merely because a topic appears on multiple pages. The [hardware evidence ledger](HARDWARE_EVIDENCE.md) records which observations already exist and what genuinely new evidence is needed.

## Source of truth

Configuration: [`config/upstream.lock`](../config/upstream.lock), [`config/rom-reference.json`](../config/rom-reference.json), [`config/toolchain-reference.json`](../config/toolchain-reference.json). Behavior: checked-in [`scripts/`](../scripts) and [GitHub Actions](../.github/workflows/nethunter-kernel.yml). Research status: [pull requests](https://github.com/mason82-dotcom/OP7T-Kernel/pulls). **Docs do not override code or hardware evidence.**
