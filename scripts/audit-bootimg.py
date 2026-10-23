#!/usr/bin/env python3
"""Read-only Android boot.img v2 header/section audit for OnePlus 7T Pro (hotdog).

Based on AOSP boot_img_hdr_v0/v1/v2, bootimg.h android17-release.
Does not unpack, repack, sign, patch or flash the input.
"""
import argparse
import hashlib
import json
import re
import struct
import sys
from pathlib import Path

BOOT_MAGIC = b"ANDROID!"
ARM64_MAGIC = b"ARM\x64"
FDT_MAGIC = b"\xd0\x0d\xfe\xed"
HEADER_V2_SIZE = 1660
EXPECTED_PAGE_SIZE = 4096
SHA256 = re.compile(r"^[a-f0-9]{64}$")
# Exact offsets from packed AOSP boot_img_hdr_v0/v1/v2 structures.
FIELDS32 = {
    "kernel_size": 8,
    "ramdisk_size": 16,
    "second_size": 24,
    "page_size": 36,
    "header_version": 40,
    "os_version": 44,
    "recovery_dtbo_size": 1632,
    "header_size": 1644,
    "dtb_size": 1648,
}


def align(size, page):
    return ((size + page - 1) // page) * page


def u32(header, offset):
    return struct.unpack_from("<I", header, offset)[0]


def u64(header, offset):
    return struct.unpack_from("<Q", header, offset)[0]


def hash_range(handle, start, length):
    h = hashlib.sha256()
    handle.seek(start)
    remaining = length
    while remaining:
        data = handle.read(min(1024 * 1024, remaining))
        if not data:
            raise ValueError("Truncated boot image while hashing section")
        h.update(data)
        remaining -= len(data)
    return h.hexdigest()


def inspect(path: Path, expected_sha256=None):
    if expected_sha256 is not None and not SHA256.fullmatch(expected_sha256):
        raise ValueError("--expect-sha256 must be 64 lowercase hexadecimal characters")
    size = path.stat().st_size
    if size < HEADER_V2_SIZE:
        raise ValueError("Boot image too short for a v2 header")
    with path.open("rb") as f:
        header = f.read(HEADER_V2_SIZE)
        if header[:8] != BOOT_MAGIC:
            raise ValueError("Not an Android boot image (ANDROID! magic missing)")
        values = {name: u32(header, offset) for name, offset in FIELDS32.items()}
        if values["header_version"] != 2:
            raise ValueError(f"Expected boot header v2, found v{values['header_version']}")
        page = values["page_size"]
        if page != EXPECTED_PAGE_SIZE:
            raise ValueError(f"Wrong page size: {page}; board expects 4096")
        if values["header_size"] != HEADER_V2_SIZE:
            raise ValueError(f"Unexpected header struct size: {values['header_size']}")
        for name in ("kernel_size", "ramdisk_size", "dtb_size"):
            if values[name] == 0:
                raise ValueError(f"Required {name} is zero")
        recovery_offset = u64(header, 1636)
        dtb_addr = u64(header, 1652)
        sizes = (
            ("kernel", values["kernel_size"]),
            ("ramdisk", values["ramdisk_size"]),
            ("second", values["second_size"]),
            ("recovery_dtbo", values["recovery_dtbo_size"]),
            ("dtb", values["dtb_size"]),
        )
        current = page
        sections = {}
        for name, length in sizes:
            if length:
                if current + length > size:
                    raise ValueError(f"Truncated {name}: end {current + length}, file {size}")
                sections[name] = {
                    "offset": current,
                    "size": length,
                    "sha256": hash_range(f, current, length),
                }
            current += align(length, page)
        if values["recovery_dtbo_size"]:
            if recovery_offset != sections["recovery_dtbo"]["offset"]:
                raise ValueError("Recovery DTBO offset does not match v2 layout")
        elif recovery_offset:
            raise ValueError("Recovery DTBO offset set but section size is zero")
        f.seek(sections["kernel"]["offset"] + 0x38)
        if f.read(4) != ARM64_MAGIC:
            raise ValueError("Kernel payload does not have ARM64 Image magic at +0x38")
        f.seek(sections["dtb"]["offset"])
        if f.read(4) != FDT_MAGIC:
            raise ValueError("Embedded DTB does not start with FDT magic")
        actual_sha = hash_range(f, 0, size)
    if expected_sha256 and expected_sha256 != actual_sha:
        raise ValueError("Original boot image SHA-256 does not match expected value")
    return {
        "schema": "op7t-bootimg-v2-readonly-audit-v1",
        "device_build_target": "hotdog",
        "filename": path.name,
        "bytes": size,
        "sha256": actual_sha,
        "hash_matched_expected": expected_sha256 is not None,
        "header_version": values["header_version"],
        "header_size": values["header_size"],
        "page_size": page,
        "kernel_format": "raw_arm64_Image",
        "dtb_addr": dtb_addr,
        "sections": sections,
        "trailing_bytes_after_sections": size - current,
        "exact_installed_rom_provenance_verified": False,
        "avb_verified": False,
        "dtbo_partition_verified": False,
        "signing_key_trust_verified": False,
        "boot_compatibility_verified": False,
        "flash_ready": False,
        "status": "STRUCTURE_VALID_ONLY_NOT_FLASHABLE",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("boot_image", type=Path, help="Local original boot.img, never modified")
    parser.add_argument("--expect-sha256", help="Out-of-band SHA-256 of exact original boot.img")
    args = parser.parse_args()
    try:
        result = inspect(args.boot_image, args.expect_sha256)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (ValueError, OSError) as exc:
        print(f"Boot header audit FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
