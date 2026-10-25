#!/usr/bin/env python3
"""Read-only QCACLD source-parity gate across the observed hotdog ROM pin.

Compares exact official Git commits and checks the ICNSS RX patch in temporary
worktrees. Does not apply any patch, compile, install or approve flashing.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
PARENT_SHA = "1083c6c5906114c71b11a429898b111a1b1b8109"
ROM_SHA = "57037290bb57caefd3c337db3511fca5751fb4ef"
ROM_RELEASE_OBSERVED = "4.14.357-perf-g57037290bb57"
PATCH = "patches/candidates/0002-qcacld-hotdog-icnss-monitor-rx-rfc.patch"
ALLOWED_ROM_CHANGES = frozenset((
    "drivers/power/oplus/charger_ic/oplus_battery_msm8150Q.c",
    "drivers/power/oplus/charger_ic/oplus_mp2650.c",
))
WLAN_INPUTS = (
    "arch/arm64/configs/vendor/sm8150-perf_defconfig",
    "arch/arm64/configs/vendor/oplus.config",
    "drivers/staging/qcacld-3.0/Kbuild",
    "drivers/staging/qcacld-3.0/configs/default_defconfig",
    "drivers/staging/qcacld-3.0/core/hdd/src/wlan_hdd_tx_rx.c",
)
HEX_SHA = re.compile(r"^[0-9a-f]{40}$")


class ParityError(ValueError):
    pass


def git(root, *args, binary=False):
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            check=True, capture_output=True, timeout=90,
        )
        return result.stdout if binary else result.stdout.decode("utf-8").strip()
    except (OSError, UnicodeDecodeError, subprocess.TimeoutExpired,
            subprocess.CalledProcessError) as exc:
        # Avoid exposing network credentials, local paths or untrusted Git
        # diagnostic text in the public report.
        raise ParityError("Git read-only/source-check operation failed") from exc


def object_hash(root, revision, name):
    data = git(root, "show", revision + ":" + name, binary=True)
    return hashlib.sha256(data).hexdigest()


def inspect_revisions(root, parent, rom):
    if not HEX_SHA.fullmatch(parent) or not HEX_SHA.fullmatch(rom):
        raise ParityError("Expected exact 40-character commit identifiers")
    if git(root, "rev-parse", "HEAD") != parent:
        raise ParityError("Original checkout is not the pinned parent")
    if git(root, "status", "--porcelain"):
        raise ParityError("Original source checkout is dirty")
    if git(root, "rev-parse", parent + "^{commit}") != parent:
        raise ParityError("Parent is not a valid commit")
    if git(root, "rev-parse", rom + "^{commit}") != rom:
        raise ParityError("ROM revision is not a valid commit")
    ancestors = git(root, "rev-list", "--parents", "-n", "1", rom).split()
    if ancestors != [rom, parent]:
        raise ParityError("ROM revision is not the direct child of the source pin")
    raw = git(root, "diff", "--name-only", "-z", parent, rom, binary=True)
    try:
        names = frozenset(x.decode("utf-8") for x in raw.split(b"\0") if x)
    except UnicodeDecodeError as exc:
        raise ParityError("Changed file name is not UTF-8") from exc
    if names != ALLOWED_ROM_CHANGES:
        raise ParityError("ROM revision unexpectedly changed files outside charger scope")
    identical = []
    for name in WLAN_INPUTS:
        old = object_hash(root, parent, name)
        new = object_hash(root, rom, name)
        if old != new:
            raise ParityError("Driver/config input changed between ROM source pins")
        identical.append({"path": name, "sha256": old})
    # Verify the selected ICNSS config/conditional build inputs on ROM SHA.
    config = git(root, "show", rom + ":" + WLAN_INPUTS[0])
    oplus = git(root, "show", rom + ":" + WLAN_INPUTS[1])
    build = git(root, "show", rom + ":" + WLAN_INPUTS[2])
    default = git(root, "show", rom + ":" + WLAN_INPUTS[3])
    callback = git(root, "show", rom + ":" + WLAN_INPUTS[4])
    if not (
        re.search(r"^CONFIG_ICNSS=y$", config, re.MULTILINE)
        and re.search(r"^CONFIG_QCA_CLD_WLAN=m$", oplus, re.MULTILINE)
        and re.search(r'^CONFIG_QCA_CLD_WLAN_PROFILE="default"$',
                      oplus, re.MULTILINE)
        and re.search(r"ifeq\s*\(\$\(CONFIG_ICNSS\),\s*y\)\s*"
                      r"CONFIG_HELIUMPLUS\s*:=\s*y", default)
        and "CONFIG_FEATURE_MONITOR_MODE_SUPPORT := y" in default
        and "$(HDD_SRC_DIR)/wlan_hdd_tx_rx.o" in build
        and "static QDF_STATUS hdd_mon_rx_packet_cbk(" in callback
        and "rxstat = netif_rx_ni(skb);" in callback
    ):
        raise ParityError("Observed ROM's ICNSS build path or monitor callback changed")
    return identical


def check_patch_on_revision(root, revision, patch):
    # Do not checkout, reset or patch the caller's original source. A new
    # temporary worktree is created and removed regardless of check outcome.
    with tempfile.TemporaryDirectory(prefix="hotdog-wlan-parity-") as temp:
        tree = Path(temp) / "source"
        added = False
        failure = None
        try:
            git(root, "worktree", "add", "--detach", str(tree), revision)
            added = True
            git(tree, "apply", "--check", str(patch))
            if git(tree, "status", "--porcelain"):
                raise ParityError("Read-only patch check modified temporary source")
        except ParityError as exc:
            failure = exc
        finally:
            if added:
                try:
                    git(root, "worktree", "remove", "--force", str(tree))
                except ParityError as exc:
                    failure = exc
        if failure:
            raise failure


def qualify(root, patch, parent=PARENT_SHA, rom=ROM_SHA):
    root = Path(root).resolve(strict=True)
    original_patch = Path(patch)
    if original_patch.is_symlink() or not original_patch.is_file():
        raise ParityError("Missing or symlinked candidate patch")
    patch = original_patch.resolve(strict=True)
    if not root.is_dir() or not patch.is_file():
        raise ParityError("Source or selected patch missing")
    if patch.stat().st_size > 65536:
        raise ParityError("Unexpectedly large candidate patch")
    hashes = inspect_revisions(root, parent, rom)
    check_patch_on_revision(root, parent, patch)
    check_patch_on_revision(root, rom, patch)
    if git(root, "rev-parse", "HEAD") != parent or git(root, "status", "--porcelain"):
        raise ParityError("Original checkout modified during source-parity check")
    return {
        "schema": "hotdog-wlan-rom-source-parity-v1",
        "parent_sha": parent,
        "rom_source_sha": rom,
        "observed_rom_release_reference_only": ROM_RELEASE_OBSERVED,
        "rom_changed_paths": sorted(ALLOWED_ROM_CHANGES),
        "wlan_source_inputs_identical": hashes,
        "active_driver_family": "ICNSS_HELIUMPLUS",
        "selected_patch": {
            "path": PATCH,
            "sha256": hashlib.sha256(patch.read_bytes()).hexdigest(),
            "apply_check_parent": True,
            "apply_check_rom_source": True,
            "applied": False,
        },
        "source_equivalence_verified": True,
        "rom_pin_kernel_compiled": False,
        "rom_module_abi_verified": False,
        "rom_signing_key_trust_verified": False,
        "installed_binary_identity_verified": False,
        "charger_change_safety_verified": False,
        "physical_wifi_monitor_mode_verified": False,
        "packet_injection_verified": False,
        "flash_ready": False,
        "status": "SOURCE_ONLY_ROM_PIN_PARITY_NO_RUNTIME_APPROVAL",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", type=Path, required=True)
    args = parser.parse_args()
    try:
        patch = PROJECT / PATCH
        # Project-integrity gate: only this reviewed candidate is allowed.
        if patch.is_symlink() or not patch.is_file():
            raise ParityError("Selected repository patch missing")
        info = qualify(args.kernel, patch)
        print(json.dumps(info, indent=2, sort_keys=True))
        return 0
    except (ParityError, OSError, ValueError) as exc:
        print("ROM SOURCE PARITY BLOCKED: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
