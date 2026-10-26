#!/usr/bin/env python3
"""Bounded, read-only scan of generated Soong/Make module names in hotdog vendor ZIP.

This is a lexical check, NOT evaluation of Android.bp/Android.mk semantics,
dependency resolution, ELF parsing or authorization to install firmware.
"""
import argparse
import json
from pathlib import Path
import re
import stat
import sys
import zipfile

MAX_FILES = 100_000
MAX_TEXT = 8 * 1024 * 1024
MAX_LINES = 100_000
MAX_EXPECTED_PACKAGES = 2_000
BP_NAME = re.compile(r'(?m)^\s*name\s*:\s*"([^"\n]+)"\s*,')
MK_NAME = re.compile(r'(?m)^\s*LOCAL_MODULE\s*(?::=|\+=|=)\s*([^\s#\\]+)')
PACKAGE = re.compile(r'^\s*PRODUCT_PACKAGES\s*(?:\+=|:=|=)\s*(.*)$')


class VendorSoongAuditError(ValueError):
    pass


def logical_lines(text):
    carry = ""
    for line in text.splitlines():
        line = line.rstrip()
        continued = line.endswith("\\")
        if continued:
            line = line[:-1]
        carry += line + (" " if continued else "")
        if not continued:
            yield carry.strip()
            carry = ""
    if carry:
        yield carry.strip()


def read_member(z, info):
    mode = (info.external_attr >> 16) & 0o170000
    if info.is_dir() or mode == stat.S_IFLNK or info.file_size > MAX_TEXT:
        raise VendorSoongAuditError("Invalid, symlinked or oversized build file")
    with z.open(info) as reader:
        raw = reader.read(MAX_TEXT + 1)
    if len(raw) != info.file_size or len(raw) > MAX_TEXT or b"\x00" in raw:
        raise VendorSoongAuditError("Invalid or oversized build file data")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise VendorSoongAuditError("Build file is not UTF-8") from exc
    if text.count("\n") > MAX_LINES:
        raise VendorSoongAuditError("Too many build-file lines")
    return text


def inspect(archive):
    with zipfile.ZipFile(archive) as z:
        info = z.infolist()
        if not info or len(info) > MAX_FILES:
            raise VendorSoongAuditError("Invalid ZIP member count")
        roots = set()
        by_rel = {}
        for item in info:
            name = item.filename
            if name.startswith("/") or "\\" in name or "\x00" in name or len(name) > 1024:
                raise VendorSoongAuditError("Unsafe ZIP member path")
            parts = name.rstrip("/").split("/")
            if any(p in (".", "..", "") for p in parts):
                raise VendorSoongAuditError("Unsafe ZIP path component")
            roots.add(parts[0])
            if item.is_dir():
                continue
            if len(parts) < 2:
                raise VendorSoongAuditError("Unexpected ZIP root file")
            rel = "/".join(parts[1:])
            if rel in by_rel:
                raise VendorSoongAuditError("Duplicate ZIP filename")
            by_rel[rel] = item
        if len(roots) != 1 or not next(iter(roots)).startswith(
            "proprietary_vendor_oneplus_hotdog-"
        ):
            raise VendorSoongAuditError("Unexpected ZIP wrapper")
        if "hotdog-vendor.mk" not in by_rel:
            raise VendorSoongAuditError("Missing hotdog-vendor.mk")

        product_text = read_member(z, by_rel["hotdog-vendor.mk"])
        package_names = []
        for line in logical_lines(product_text):
            if not line or line.startswith("#"):
                continue
            match = PACKAGE.match(line)
            if match:
                package_names.extend(match.group(1).split())
                if len(package_names) > MAX_EXPECTED_PACKAGES:
                    raise VendorSoongAuditError("Too many product package names")
        package_names = sorted(set(package_names))
        # Only scan the generated top-level vendor build files.
        checked_files = {}
        bp_names, mk_names = set(), set()
        for basename in ("Android.bp", "Android.mk"):
            if basename not in by_rel:
                checked_files[basename] = {"present": False}
                continue
            contents = read_member(z, by_rel[basename])
            names = set((BP_NAME if basename.endswith(".bp") else MK_NAME).findall(contents))
            checked_files[basename] = {
                "present": True,
                "bytes": by_rel[basename].file_size,
                "candidate_module_name_count": len(names),
            }
            if basename.endswith(".bp"):
                bp_names |= names
            else:
                mk_names |= names

    matches = {
        name: {
            "android_bp_name_token": name in bp_names,
            "android_mk_local_module_token": name in mk_names,
        }
        for name in package_names
    }
    missing = [name for name, v in matches.items()
               if not v["android_bp_name_token"] and not v["android_mk_local_module_token"]]
    return {
        "schema": "op7t-hotdog-vendor-soong-name-probe-v1",
        "device": "hotdog",
        "scope": "root_vendor_build_files_lexical_scan_only",
        "product_package_count": len(package_names),
        "product_package_name_candidates": matches,
        "missing_module_name_token_count": len(missing),
        "missing_module_name_token_samples": missing[:30],
        "checked_build_files": checked_files,
        "status": ("ALL_PACKAGE_NAMES_LEXICALLY_PRESENT" if package_names and not missing
                   else "PACKAGE_NAME_TOKENS_MISSING_OR_UNDECLARED"),
        "module_definitions_semantically_verified": False,
        "full_soong_build_verified": False,
        "vendor_archive_extracted": False,
        "vendor_binary_executed": False,
        "installed_rom_compatibility_verified": False,
        "flash_ready": False,
        "limitations": "Name tokens may be in comments/nested objects; scripts do not parse full Blueprint or Android Make semantics, module types, dependency graph, DT_NEEDED fixups, blobs, AVB, signatures or installed firmware.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    args = parser.parse_args(argv)
    try:
        result = inspect(args.archive)
    except (OSError, ValueError, RuntimeError, NotImplementedError,
            zipfile.BadZipFile) as exc:
        print(f"Vendor Soong-name probe FAILED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
