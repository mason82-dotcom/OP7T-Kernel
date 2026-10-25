# OP7T-Kernel

Experimental **standalone kernel, module and NetHunter research workspace** for the **OnePlus 7T Pro (`hotdog`)** on **crDroid 13 / Android 17**. The upstream SM8150 kernel is fetched on demand at the exact commit in [`config/upstream.lock`](config/upstream.lock); this repository does not vendor the large kernel source tree.

> **NOT FLASHABLE.** This project does not produce a validated `boot.img`, flashable ZIP or a proven compatible signed vendor-module set. `flash_ready=false`. Compilation, structural validation and build-local cryptographic verification do **not** authorize installing artifacts on a phone.

## Start here

1. [Documentation index](docs/INDEX.md) — where each topic is maintained.
2. [Build guide](docs/BUILD.md) — profiles, Linux prerequisites, configuration checks, compiled artifacts and CI.
3. [Evidence and inspection tools](docs/EVIDENCE_TOOLS.md) — read-only ADB/OTA/ELF/boot-image investigations.
4. [Hardware evidence ledger](docs/HARDWARE_EVIDENCE.md) — previously recorded device results and **still-open** ROM, module, boot and recovery gates.
5. [Release and flashing safety](docs/FLASHING.md) — why nothing may be flashed yet.

## Project facts

| Item | Current `main` configuration |
| --- | --- |
| Device | OnePlus 7T Pro `hotdog`, **not** `hotdogg` / McLaren 5G |
| ROM target | crDroid **v13** on Android **17**, upstream branch `17.0` |
| Kernel | Official [crDroid SM8150 kernel](https://github.com/crdroidandroid/android_kernel_oneplus_sm8150/tree/17.0), pinned via `config/upstream.lock` |
| Source kernel version | Linux **4.14.357** |
| Profiles | `baseline`, `core`, `external` — all experimental |
| Build compiler | Experimental **Clang 14**, **not** validated as the compiler of the installed ROM |
| Packaging | Raw `Image`, DTBs, rebuilt modules and audit metadata; **no boot-image packager or flashing workflow** |

**Important source discrepancy:** the physical-device evidence reports running kernel suffix `g57037290bb57`, while current `main` pins source `1083c6c5906114c71b11a429898b111a1b1b8109`. Source-parity and KernelSU / QCACLD research exist in separate **draft PRs**; their results are **not** the current mainline release. Track proposed work in [open pull requests](https://github.com/mason82-dotcom/OP7T-Kernel/pulls) rather than assuming a draft has shipped.

## Quick check (Linux x86_64)

~~~bash
# See docs/BUILD.md for the required packages and toolchain.
bash scripts/fetch-source.sh
CONFIG_ONLY=1 bash scripts/build.sh baseline
CONFIG_ONLY=1 bash scripts/build.sh core
CONFIG_ONLY=1 bash scripts/build.sh external
~~~

`CONFIG_ONLY=1` validates configuration and **does not compile a kernel**. For full builds, commands, signing details and artifact limitations use [the build guide](docs/BUILD.md).

## Scope and constraints

The `core` profile requests additional USB/BT features; `external` adds selected in-tree USB Wi-Fi drivers. **Internal QCACLD injection has not been implemented or hardware-validated.** Driver presence, a Kconfig symbol or a signed module does not establish a functioning NetHunter feature. See [feature matrix](docs/NETHUNTER_FEATURES.md) and [patch staging policy](patches/README.md).

The authoritative upstream source and board-configuration assumptions are documented in [crDroid 17.0 build reference](docs/CRDROID_17_BUILD_REFERENCE.md). Compare every proposed change against the exact installed ROM before attempting compatibility claims. Use wireless security functionality only on systems and networks you are authorized to test.
