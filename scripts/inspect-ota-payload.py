#!/usr/bin/env python3
"""Inspect a local A/B OTA payload manifest, strictly offline and read-only.

No image extraction, update_engine, ADB, root, signature validation or flashing.
In particular, payload partition names never prove an image is installed.
"""
import argparse
import json
import re
import struct
import sys
from pathlib import Path
from zipfile import BadZipFile, ZipFile

MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_SIGNATURE_BYTES = 8 * 1024 * 1024
MAX_PARTITIONS = 128
# Android update_engine's PartitionUpdate.partition_name is a platform-specific
# string, not necessarily a lowercase Linux directory name. Still disallow
# path separators, traversal components, controls and oversized identifiers.
PARTITION_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.+-]{0,63}$", re.ASCII)


class PayloadError(ValueError):
    pass


def read_exact(stream, length):
    chunks = []
    while length:
        chunk = stream.read(length)
        if not chunk:
            raise PayloadError("Truncated payload header or manifest")
        chunks.append(chunk)
        length -= len(chunk)
    return b"".join(chunks)


def varint(data, pos):
    value = 0
    for index in range(10):
        if pos >= len(data):
            raise PayloadError("Truncated protobuf varint")
        byte = data[pos]
        pos += 1
        if index == 9 and byte > 1:
            raise PayloadError("Overlong protobuf varint")
        value |= (byte & 0x7f) << (7 * index)
        if not byte & 0x80:
            return value, pos
    raise PayloadError("Overlong protobuf varint")


def protobuf_fields(data):
    pos = 0
    while pos < len(data):
        tag, pos = varint(data, pos)
        field, wire = tag >> 3, tag & 7
        if field < 1 or wire not in (0, 1, 2, 5):
            raise PayloadError("Invalid or unsupported protobuf field")
        if wire == 0:
            value, pos = varint(data, pos)
            yield field, wire, value
        elif wire in (1, 5):
            size = 8 if wire == 1 else 4
            if pos + size > len(data):
                raise PayloadError("Truncated fixed protobuf field")
            pos += size
        else:
            size, pos = varint(data, pos)
            if size > len(data) - pos:
                raise PayloadError("Protobuf field exceeds manifest bounds")
            yield field, wire, data[pos:pos + size]
            pos += size


def parse_partition(record):
    found = []
    for field, wire, value in protobuf_fields(record):
        if field == 1:
            if wire != 2:
                raise PayloadError("Malformed partition name field")
            try:
                name = value.decode("ascii")
            except UnicodeDecodeError as exc:
                raise PayloadError("Non-ASCII partition name") from exc
            if (not PARTITION_NAME.fullmatch(name) or
                    ".." in name or name.endswith(".")):
                # Bounded literal representation helps diagnose official but
                # unexpected partition names; do not interpret as a path.
                raise PayloadError(
                    f"Unsafe or invalid partition name: {name[:64]!r}"
                )
            found.append(name)
    if len(found) != 1:
        raise PayloadError("Missing or repeated partition name")
    return found[0]


def parse_manifest(raw):
    names = []
    minor = None
    partial = None
    for field, wire, value in protobuf_fields(raw):
        if field == 13:
            if wire != 2 or len(names) >= MAX_PARTITIONS:
                raise PayloadError("Malformed or excessive partition records")
            names.append(parse_partition(value))
        elif field == 12:
            if wire != 0 or minor is not None:
                raise PayloadError("Malformed or duplicate payload minor version")
            minor = value
        elif field == 16:
            if wire != 0 or partial is not None or value not in (0, 1):
                raise PayloadError("Malformed or duplicate partial-update value")
            partial = bool(value)
    if not names or len(names) != len(set(names)):
        raise PayloadError("Manifest has no partitions or duplicate partitions")
    return sorted(names), minor, partial


def inspect(archive: Path):
    if not archive.is_file() or archive.stat().st_size == 0:
        raise PayloadError("OTA ZIP missing or empty")
    with ZipFile(archive, "r") as z:
        payloads = [info for info in z.infolist() if info.filename == "payload.bin"]
        if len(payloads) != 1 or payloads[0].is_dir():
            raise PayloadError("Expected exactly one regular payload.bin ZIP member")
        info = payloads[0]
        if info.file_size < 24:
            raise PayloadError("Truncated payload.bin")
        with z.open(info, "r") as stream:
            header = read_exact(stream, 24)
            magic, major, manifest_len, sig_len = struct.unpack(">4sQQI", header)
            if magic != b"CrAU" or major != 2:
                raise PayloadError("Expected Android A/B CrAU payload major v2")
            if not 0 < manifest_len <= MAX_MANIFEST_BYTES:
                raise PayloadError("Manifest size outside bounded limit")
            if sig_len > MAX_SIGNATURE_BYTES:
                raise PayloadError("Metadata signature size outside bounded limit")
            if 24 + manifest_len + sig_len > info.file_size:
                raise PayloadError("Manifest/signature lengths exceed payload.bin")
            manifest = read_exact(stream, manifest_len)
    names, minor, partial = parse_manifest(manifest)
    wanted = ("boot", "dtbo", "vendor", "vendor_dlkm", "vbmeta", "vbmeta_system")
    return {
        "schema": "op7t-offline-ota-payload-partitions-v1",
        "input_archive_filename": archive.name,
        "payload_major_version": 2,
        "payload_minor_version": minor,
        "metadata_signature_bytes": sig_len,
        "metadata_signature_cryptographically_verified": False,
        "payload_member_size_bytes": info.file_size,
        "partition_names": names,
        "requested_partition_names_present": {name: name in names for name in wanted},
        "partial_update_declared": partial,
        "full_payload_confirmed": minor == 0 and partial is False,
        "all_installed_partitions_enumerated": False,
        "ota_zip_sha256_verified": False,
        "images_extracted_or_validated": False,
        "exact_installed_rom_provenance_verified": False,
        "flash_ready": False,
        "status": "OFFLINE_OTA_MANIFEST_ONLY",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ota_zip", type=Path, help="local, already separately verified OTA ZIP")
    args = parser.parse_args(argv)
    try:
        result = inspect(args.ota_zip)
    except (PayloadError, OSError, BadZipFile, RuntimeError) as exc:
        print(f"OTA manifest inspection FAILED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
