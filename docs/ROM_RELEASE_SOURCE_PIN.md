# Experimental source pin matching the observed ROM kernel release

The physical `hotdog` reports `4.14.357-perf-g57037290bb57`; the verified reference OTA's `qca_cld3_wlan.ko` has the same kernel-release component in `vermagic`. The [commit `57037290bb57caefd3c337db3511fca5751fb4ef`](https://github.com/crdroidandroid/android_kernel_oneplus_sm8150/commit/57037290bb57caefd3c337db3511fca5751fb4ef) in the official kernel repository resolves that prefix. It is the **direct child** of the earlier project pin `1083c6c5906114c71b11a429898b111a1b1b8109`.

On 25 October 2026, the repository's `17.0` branch HEAD resolves to the **parent** `1083c6c5906114c71b11a429898b111a1b1b8109`, not the child. This may reflect an upstream rollback; its reason has not been established. `fetch-source.sh` must fetch the exact historical SHA if it is absent from a single-branch clone and fail if the server will not provide it. Do not promote this experiment to the main default merely because the release suffix matches.

This branch changes only the source lock and test fixture SHA. Existing profile/config and signing gates remain in force. CI must compile `core` and `external` at the new pin and report the resulting kernel release, modules, configuration and toolchain. A separate manual baseline build can be compared after the source experiment passes. No boot image or flash package is generated.

The intervening commit reverts a backward-RTC sleep-time clamp in `drivers/power/oplus/charger_ic/oplus_battery_msm8150Q.c` and `oplus_mp2650.c`. It does **not** directly patch QCACLD, but can alter charging/suspend behavior. Review the diff and test charging, RTC rollback, suspend and resume on owned hardware only after the release gates permit a live boot.

Expected result: the new build may produce `4.14.357-perf-g57037290bb57` and remove the **release-string** mismatch observed with the previous pin. This alone cannot establish identical compiler flags, kernel config, symbol CRCs, original vendor module ABI, installed-image identity or trusted module-signing keys. The build creates a new ephemeral key, so the original ROM key ID still cannot be assumed to match. Preserve `flash_ready=false`.

The previous known-good experimental build artifacts remain identifiable by their own `upstream-commit.txt` and hashes. Never combine their `Image`, DTBs, modules or signatures with outputs from this new pin.
