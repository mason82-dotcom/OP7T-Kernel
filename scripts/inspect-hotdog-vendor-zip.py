#!/usr/bin/env python3
"""Offline, metadata-only audit of the crDroid 17.0 hotdog GitLab vendor ZIP.

Never extracts, executes, flashes, installs or republishes proprietary blobs.
A ZIP file can be well-formed without being authentic or matching the installed ROM.
"""
import argparse
import hashlib
import json
import re
import stat
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REFERENCE = ROOT / "config/hotdog-vendor-reference.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_ARCHIVE_BYTES = 8 * 1024**3
MAX_ENTRIES = 100_000
MAX_MEMBER_BYTES = 2 * 1024**3
MAX_UNCOMPRESSED_BYTES = 12 * 1024**3


class VendorArchiveError(ValueError):
    pass


def file_sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def inspect(archive, reference_path=DEFAULT_REFERENCE, expected_sha256=None):
    if expected_sha256 is not None and not SHA256.fullmatch(expected_sha256):
        raise VendorArchiveError("Expected SHA-256 must be 64 lowercase hex chars")

    cfg = json.loads(reference_path.read_text(encoding="utf-8"))
    if (cfg.get("schema") != "op7t-hotdog-proprietary-vendor-reference-v1"
            or cfg.get("device") != "hotdog"
            or cfg.get("android_major") != 17
            or cfg.get("crdroid_major") != 13
            or cfg.get("branch") != "17.0"
            or cfg.get("full_rom_target_path") != "vendor/oneplus/hotdog"
            or cfg.get("remote") != "crdroid-gitlab"):
        raise VendorArchiveError("Wrong or malformed hotdog vendor reference")

    archive = Path(archive)
    if not archive.is_file() or not 0 < archive.stat().st_size <= MAX_ARCHIVE_BYTES:
        raise VendorArchiveError("Archive missing, empty or exceeds bounded size")

    digest = file_sha256(archive)
    if expected_sha256 is not None and digest != expected_sha256:
        raise VendorArchiveError("Local vendor ZIP SHA-256 does not match expected")

    members = set()
    roots = set()
    total_bytes = 0
    symlinks = 0
    module_paths = []
    top_groups = {}
    with zipfile.ZipFile(archive) as z:
        all_infos = z.infolist()
        if not all_infos or len(all_infos) > MAX_ENTRIES:
            raise VendorArchiveError("Empty or excessively large ZIP directory")
        for entry in all_infos:
            name = entry.filename
            if ("\x00" in name or "\\" in name or name.startswith("/")
                    or len(name) > 1024 or any(part in ("", ".", "..") for part in
                         name.rstrip("/").split("/"))):
                raise VendorArchiveError("Unsafe ZIP path")
            parts = name.rstrip("/").split("/")
            root = parts[0]
            roots.add(root)
            if not root.startswith("proprietary_vendor_oneplus_hotdog-"):
                raise VendorArchiveError("Unexpected GitLab vendor archive root")
            if entry.is_dir():
                continue
            if len(parts) < 2:
                raise VendorArchiveError("File outside ZIP wrapper directory")
            relative = "/".join(parts[1:])
            if relative in members:
                raise VendorArchiveError("Duplicate normalized ZIP member")
            members.add(relative)
            mode = (entry.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                symlinks += 1
            if entry.file_size > MAX_MEMBER_BYTES:
                raise VendorArchiveError("Unreasonably large single ZIP entry")
            total_bytes += entry.file_size
            if total_bytes > MAX_UNCOMPRESSED_BYTES:
                raise VendorArchiveError("Unreasonably large total uncompressed size")
            group = parts[1] if len(parts) > 2 else "(root)"
            top_groups[group] = top_groups.get(group, 0) + 1
            if relative.endswith(".ko"):
                module_paths.append(relative)

    if len(roots) != 1:
        raise VendorArchiveError("More than one ZIP wrapper directory")

    expected = [cfg["expected_boardconfig"], cfg["expected_product_makefile"]]
    observed = {name: name in members for name in expected}
    completeness = all(observed.values())
    return {
        "schema": "op7t-hotdog-vendor-zip-inventory-v1",
        "device": "hotdog",
        "repository": cfg["repository"],
        "branch": cfg["branch"],
        "remote": cfg["remote"],
        "intended_full_rom_target_path": cfg["full_rom_target_path"],
        "archive_name": archive.name,
        "archive_bytes": archive.stat().st_size,
        "archive_sha256": digest,
        "expected_sha256_verified": expected_sha256 is not None,
        "gitlab_zip_wrapper": next(iter(roots)),
        "file_count": len(members),
        "uncompressed_member_bytes": total_bytes,
        "symbolic_link_count": symlinks,
        "top_level_groups": dict(sorted(top_groups.items())),
        "required_vendor_makefiles_present": observed,
        "kernel_module_count_in_archive": len(module_paths),
        "kernel_module_path_samples": sorted(module_paths)[:20],
        "expected_makefiles_present": completeness,
        "archive_source_commit_verified": False,
        "complete_proprietary_payload_verified": False,
        "installed_partition_identity_verified": False,
        "signing_key_trust_verified": False,
        "flash_ready": False,
        "status": "VENDOR_ZIP_METADATA_ONLY" if completeness
                  else "VENDOR_ZIP_EXPECTED_MAKEFILES_MISSING",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="Previously downloaded local GitLab 17.0 ZIP")
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--expect-sha256", help="Trusted, separately obtained exact ZIP SHA-256")
    args = parser.parse_args(argv)
    try:
        data = inspect(args.archive, args.reference, args.expect_sha256)
    except (VendorArchiveError, OSError, json.JSONDecodeError,
            KeyError, zipfile.BadZipFile, RuntimeError) as exc:
        print(f"Vendor ZIP inventory FAILED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(data, indent=2, sort_keys=True))
    return 0 if data["expected_makefiles_present"] else 3


if __name__ == "__main__":
    sys.exit(main())
