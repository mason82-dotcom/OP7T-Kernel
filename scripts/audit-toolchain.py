#!/usr/bin/env python3
"""Read-only provenance evidence for the host kernel toolchain; NEVER a flash gate pass."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REF = ROOT / "config/toolchain-reference.json"
SHA = re.compile(r"^[a-f0-9]{40}$")
RELEASE = re.compile(r"^clang-r[0-9]+[a-zA-Z0-9._-]*$")


def load_reference(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if (
        data.get("schema") != "op7t-crdroid17-toolchain-reference-v1"
        or data.get("device") != "hotdog"
        or data.get("android_version") != 17
        or data.get("crdroid_version") != 13
        or data.get("branch") != "17.0"
        or not SHA.fullmatch(str(data.get("source_commit", "")))
        or not RELEASE.fullmatch(str(data.get("expected_prebuilt_directory", "")))
        or data.get("original_20261021_ota_toolchain_verified") is not False
        or data.get("binary_checksum_from_official_build_verified") is not False
    ):
        raise ValueError("Untrusted or inconsistent toolchain reference")
    return data


def inspect_executable(command):
    found = shutil.which(command)
    if not found:
        raise ValueError("Tool not found: " + command)
    path = Path(found).resolve(strict=True)
    if not path.is_file():
        raise ValueError("Resolved tool is not a file")
    try:
        result = subprocess.run([str(path), "--version"], capture_output=True, text=True,
                                timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("Unable to query tool version") from exc
    if result.returncode != 0:
        raise ValueError("Tool --version failed")
    first_line = (result.stdout or "").splitlines()
    if not first_line:
        raise ValueError("Tool version is missing")
    version = first_line[0].strip()[:240]
    if not version:
        raise ValueError("Tool version is empty")
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"executable_name": path.name, "version_first_line": version,
            "sha256": digest.hexdigest(), "_resolved": path}


def inspect_tools(clang, linker, reference):
    cc = inspect_executable(clang)
    ld = inspect_executable(linker)
    directory = reference["expected_prebuilt_directory"]
    def matches(p):
        return p.parent.name == "bin" and p.parent.parent.name == directory
    layout = matches(cc["_resolved"]) and matches(ld["_resolved"]) and (
        cc["_resolved"].parent == ld["_resolved"].parent)
    for item in (cc, ld):
        del item["_resolved"]  # No private host paths in uploaded reports.
    return {
        "schema": "op7t-toolchain-provenance-v1",
        "device": "hotdog",
        "upstream_branch": reference["branch"],
        "upstream_reference_commit": reference["source_commit"],
        "upstream_selected_release": reference["selected_aosp_release"],
        "upstream_expected_clang_prebuilt": directory,
        "compiler": cc,
        "linker": ld,
        "aosp_prebuilt_path_layout_matches": layout,
        "reference_binary_identity_verified": False,
        "official_rom_build_toolchain_verified": False,
        "installed_rom_abi_compatible_verified": False,
        "flash_ready": False,
        "status": "PREBUILT_PATH_MATCH_ONLY" if layout else "EXPERIMENTAL_DIFFERENT_TOOLCHAIN_PATH",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clang", default="clang")
    parser.add_argument("--ld", default="ld.lld")
    parser.add_argument("--reference", type=Path, default=DEFAULT_REF)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-reference-layout", action="store_true",
                        help="Fail if selected binaries are not laid out under the expected AOSP prebuilt directory")
    args = parser.parse_args()
    try:
        report = inspect_tools(args.clang, args.ld, load_reference(args.reference))
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.exit(2, "Toolchain audit failed: " + str(exc) + "\n")
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    if args.require_reference_layout and not report["aosp_prebuilt_path_layout_matches"]:
        parser.exit(3, "Official AOSP prebuilt path layout not observed; never assume ROM parity.\n")


if __name__ == "__main__":
    main()
