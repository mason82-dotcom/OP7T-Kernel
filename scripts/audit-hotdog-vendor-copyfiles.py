#!/usr/bin/env python3
"""Read-only, static PRODUCT_COPY_FILES vs ZIP membership audit for hotdog 17.0."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import stat
import sys
import zipfile

PREFIX = "vendor/oneplus/hotdog/"
ROOT_FILES = ("BoardConfigVendor.mk", "hotdog-vendor.mk")
ASSIGNMENT = re.compile(
    r"^\s*(PRODUCT_COPY_FILES|PRODUCT_PACKAGES|PRODUCT_PACKAGES_DEBUG|PRODUCT_PACKAGES_ENG)"
    r"\s*(\+=|:=|=|\?=)\s*(.*)$"
)
MAX_MEMBER_COUNT = 100000
MAX_MAKEFILE_SIZE = 512 * 1024
MAX_LINES = 12000
MAX_SAMPLES = 20


class VendorAuditError(ValueError):
    pass


def read_makefile(z, path):
    entry = z.getinfo(path)
    mode = (entry.external_attr >> 16) & 0o170000
    if entry.is_dir() or mode == stat.S_IFLNK or entry.file_size > MAX_MAKEFILE_SIZE:
        raise VendorAuditError("Invalid or oversized Makefile")
    with z.open(entry) as reader:
        raw = reader.read(MAX_MAKEFILE_SIZE + 1)
    if len(raw) != entry.file_size or len(raw) > MAX_MAKEFILE_SIZE or b"\x00" in raw:
        raise VendorAuditError("Invalid Makefile data")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise VendorAuditError("Makefile is not UTF-8") from exc


def logical_lines(text):
    lines = text.splitlines()
    if len(lines) > MAX_LINES:
        raise VendorAuditError("Too many Makefile lines")
    accum = ""
    first_line = 1
    for number, line in enumerate(lines, 1):
        line = line.rstrip()
        continuation = line.endswith("\\")
        if continuation:
            line = line[:-1]
        if not accum:
            first_line = number
        accum += line + (" " if continuation else "")
        if not continuation:
            yield first_line, accum.strip()
            accum = ""
    if accum:
        yield first_line, accum.strip()


def first(values):
    return sorted(set(values))[:MAX_SAMPLES]


def inspect(archive):
    with zipfile.ZipFile(archive) as z:
        infos = z.infolist()
        if not infos or len(infos) > MAX_MEMBER_COUNT:
            raise VendorAuditError("Invalid ZIP entry count")
        roots = set()
        files = set()
        makefiles = defaultdict(list)
        for entry in infos:
            name = entry.filename
            if ("\x00" in name or "\\" in name or name.startswith("/") or
                    len(name) > 1024):
                raise VendorAuditError("Unsafe ZIP path")
            parts = name.rstrip("/").split("/")
            if any(p in ("", ".", "..") for p in parts):
                raise VendorAuditError("Unsafe ZIP path segment")
            roots.add(parts[0])
            if entry.is_dir():
                continue
            if len(parts) < 2:
                raise VendorAuditError("Unexpected ZIP root file")
            rel = "/".join(parts[1:])
            if rel in files:
                raise VendorAuditError("Duplicate ZIP file")
            files.add(rel)
            if len(parts) == 2 and parts[1] in ROOT_FILES:
                makefiles[parts[1]].append(name)
        if len(roots) != 1 or not next(iter(roots)).startswith(
                "proprietary_vendor_oneplus_hotdog-"):
            raise VendorAuditError("Wrong GitLab ZIP wrapper")
        if any(len(makefiles[name]) != 1 for name in ROOT_FILES):
            raise VendorAuditError("Missing or duplicate root Makefile")
        board_text = read_makefile(z, makefiles["BoardConfigVendor.mk"][0])
        product_text = read_makefile(z, makefiles["hotdog-vendor.mk"][0])

    board_active = [
        {"line": number, "text": line[:300]}
        for number, line in logical_lines(board_text)
        if line and not line.lstrip().startswith("#")
    ][:40]

    copy_tokens, missing, external, unknown, packages = [], [], [], [], []
    destinations = defaultdict(list)
    category = Counter()
    referenced_files = set()
    local_source_count = 0
    assignments = 0
    for number, line in logical_lines(product_text):
        if not line or line.lstrip().startswith("#"):
            continue
        match = ASSIGNMENT.match(line)
        if not match:
            if "PRODUCT_COPY_FILES" in line:
                unknown.append(f"line {number}: {line[:140]}")
            continue
        variable, _, value = match.groups()
        assignments += 1
        if variable != "PRODUCT_COPY_FILES":
            packages.extend(value.split())
            continue
        for token in value.split():
            copy_tokens.append(token)
            if token.count(":") != 1 or "$(" in token.split(":", 1)[0]:
                unknown.append(f"line {number}: {token[:140]}")
                continue
            src, dst = token.split(":", 1)
            if not dst:
                unknown.append(f"line {number}: {token[:140]}")
                continue
            destinations[dst].append(src)
            if src.startswith(PREFIX):
                relative = src[len(PREFIX):]
                local_source_count += 1
                category[relative.split("/")[0]] += 1
                if relative in files:
                    referenced_files.add(relative)
                else:
                    missing.append(relative)
            else:
                external.append(src)

    # Static filename alignment only: AB OTA partition tokens are *not*
    # authorization to flash radio images or proof of installed firmware.
    ota_partitions = []
    ota_unparsed = []
    for line_number, line in logical_lines(board_text):
        if not line or line.lstrip().startswith("#"):
            continue
        match = re.match(r"^AB_OTA_PARTITIONS\s*(?:\+=|:=|=)\s*(.*)$", line)
        if not match:
            if "AB_OTA_PARTITIONS" in line:
                ota_unparsed.append(f"line {line_number}: {line[:120]}")
            continue
        for token in match.group(1).split():
            if re.fullmatch(r"[A-Za-z0-9_]+", token):
                ota_partitions.append(token)
            else:
                ota_unparsed.append(f"line {line_number}: {token[:120]}")
    ota_dupes = sorted(p for p, n in Counter(ota_partitions).items() if n > 1)
    radio_images = sorted(
        name[len("radio/"):-len(".img")]
        for name in files
        if name.startswith("radio/") and name.endswith(".img")
        and "/" not in name[len("radio/"):]
    )
    ota_set = set(ota_partitions)
    radio_set = set(radio_images)
    package_so_candidates = {}
    for package in sorted(set(packages)):
        package_so_candidates[package] = sorted(
            name for name in files if name.startswith("proprietary/")
            and name.endswith(".so")
            and (Path(name).name[:-3] == package or
                 Path(name).name[:-3] + "_odm" == package)
        )[:5]

    duplicates = [d for d, sources in destinations.items() if len(sources) > 1]
    payloads = [f for f in files if f.startswith(("proprietary/", "radio/"))]
    unreferenced = [f for f in payloads if f not in referenced_files]
    return {
        "schema": "op7t-hotdog-vendor-copyfiles-audit-v1",
        "device": "hotdog",
        "scope": "static_zip_makefile_and_names_only",
        "boardconfig_active_lines": board_active,
        "product_makefile_logical_assignments": assignments,
        "copy_tokens": len(copy_tokens),
        "local_source_rules": local_source_count,
        "local_source_rules_found_in_zip": local_source_count - len(missing),
        "local_source_rules_missing_in_zip": len(missing),
        "missing_local_source_samples": first(missing),
        "external_source_rule_count": len(external),
        "external_source_samples": first(external),
        "nonliteral_or_unparsed_rule_count": len(unknown),
        "nonliteral_or_unparsed_rule_samples": first(unknown),
        "duplicate_destination_count": len(duplicates),
        "duplicate_destination_samples": first(duplicates),
        "copy_source_category_counts": dict(sorted(category.items())),
        "package_token_count": len(packages),
        "package_token_samples": first(packages),
        "package_library_basename_candidates": package_so_candidates,
        "package_with_heuristic_library_candidate_count":
            sum(bool(v) for v in package_so_candidates.values()),
        "package_without_heuristic_library_candidate_count":
            sum(not v for v in package_so_candidates.values()),
        "ab_ota_partition_count": len(ota_partitions),
        "ab_ota_partition_samples": first(ota_partitions),
        "ab_ota_duplicate_partition_count": len(ota_dupes),
        "ab_ota_duplicate_partition_samples": first(ota_dupes),
        "ab_ota_unparsed_rule_count": len(ota_unparsed),
        "ab_ota_unparsed_rule_samples": first(ota_unparsed),
        "radio_image_count": len(radio_images),
        "ab_ota_partitions_without_radio_image": sorted(ota_set - radio_set),
        "radio_images_without_ab_ota_partition": sorted(radio_set - ota_set),
        "radio_partition_filename_alignment":
            "STATIC_NAMES_MATCH" if ota_partitions and not ota_dupes
            and not ota_unparsed and ota_set == radio_set
            else "RADIO_NAMES_UNVERIFIED_OR_DIFFERENT",
        "zip_proprietary_and_radio_files": len(payloads),
        "zip_proprietary_and_radio_files_not_in_literal_copy_rules": len(unreferenced),
        "unreferenced_zip_file_samples": first(unreferenced),
        "status": ("COPY_SOURCE_REFERENCE_GAPS" if missing or duplicates or unknown
                   else "STATIC_COPY_REFERENCES_RESOLVE"),
        "source_commit_verified": False,
        "makefiles_executed": False,
        "vendor_files_extracted": False,
        "installed_rom_compatibility_verified": False,
        "flash_ready": False,
        "limitations": "Only static filename and optional library-basename heuristics; no Android.bp/Android.mk evaluation, Make variable resolution, archive member content authentication, device, AVB, module signing or bootability validation",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    args = parser.parse_args(argv)
    try:
        result = inspect(args.archive)
    except (OSError, ValueError, RuntimeError, NotImplementedError,
            zipfile.BadZipFile) as exc:
        print(f"Vendor copyfile audit FAILED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
