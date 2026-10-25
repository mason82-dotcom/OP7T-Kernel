# Hotdog ROM source / ICNSS WLAN parity (read-only)

This research compares two immutable upstream commits in the official crDroid OnePlus SM8150 repository. It never compiles, changes the smartphone, installs modules or relaxes kernel security.

| Role | Source commit |
| --- | --- |
| Previous experimental source | `1083c6c5906114c71b11a429898b111a1b1b8109` |
| Observed ROM source candidate | `57037290bb57caefd3c337db3511fca5751fb4ef` |

The second is a direct child of the first. An upstream compare shows changes exclusively in two charging-source files:

- `drivers/power/oplus/charger_ic/oplus_battery_msm8150Q.c`
- `drivers/power/oplus/charger_ic/oplus_mp2650.c`

These changes revert charging resume-time logic and may affect device safety. **This gate does not approve the charger changes or their inclusion in a replacement boot image.** [PR #30](https://github.com/mason82-dotcom/OP7T-Kernel/pull/30) studies the source commit corresponding to observed release `4.14.357-perf-g57037290bb57`.

## Acceptance checks

The dedicated `wlan-rom-source-parity` job fetches the pinned original checkout and then only the exact second commit. The Python checker requires the direct parent-child relation and exact two-path charger-only diff. It compares SHA-256 of five WLAN build/config inputs on both revisions, verifies the ICNSS/HELIUMPLUS profile and selected RX callback, and invokes only `git apply --check` for the RFC patch against each temporary detached source worktree. A failed comparison blocks; successful verification publishes a bounded JSON report. No raw Image, module, OTA content or signing keys are uploaded.

To run on a Linux development host after the usual repository checkout:

```sh
bash scripts/fetch-source.sh
git -C .work/kernel fetch --no-tags --depth=2 origin 57037290bb57caefd3c337db3511fca5751fb4ef
python3 scripts/check-wlan-rom-source-parity.py --kernel .work/kernel
```

## Interpretation

Only unchanged WLAN source inputs and patch applicability are established. Compilation of the exact ROM-source module, runtime callback validity, signer trust, `Module.symvers` / CRC parity, vendor firmware, charger behavior, actual ROM binary identity, physical passive-monitor RX, injection and flash compatibility remain unverified. Matching a release suffix is not equivalent to binary or ABI identity.

The selected change `netif_rx_ni` to `netif_rx` remains experimental until its execution context is proven safe. **No flashing, ADB writes, AVB or module-signature bypass, device modification or automatic merge. `flash_ready=false`.**
