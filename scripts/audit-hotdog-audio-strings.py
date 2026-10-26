#!/usr/bin/env python3
"""Locate bounded ASCII string occurrences in the existing hotdog Audio HAL ELF.

Read-only: verifies ZIP and ELF SHA256 if supplied, reads one bounded ZIP
member into memory, never executes or writes any ELF/firmware payload.
Offsets are ELF-file offsets, NOT addresses or proven call sites.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

MEMBER = "proprietary/odm/lib/hw/audio.primary.msmnile.so"
ROOT = "proprietary_vendor_oneplus_hotdog-17.0/"
MARKERS = (
    b"liba2dpoffload",
    b"/odm/lib/",
    b"/vendor/lib/",
    b"/odm/lib/liba2dpoffload.so",
    b"/vendor/lib/liba2dpoffload.so",
    b"dlopen",
    b"android_dlopen_ext",
    b"dlsym",
    b"libaudioEngineerTest",
)
MAX_ARCHIVE_BYTES = 8 * 1024**3
MAX_ZIP_ENTRIES = 100000
MAX_ELF_BYTES = 8 * 1024 * 1024
MAX_ASCII_BYTES = 320
MAX_SAMPLES = 8
MAX_MATCHES = 1000


class AudioStringError(ValueError):
    pass


def sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def get_ascii_string(data, position):
    """Return whole NUL-delimited printable string, else unspecified."""
    start = data.rfind(b"\x00", max(0, position - MAX_ASCII_BYTES), position)
    if start < 0:
        return None
    start += 1
    end = data.find(b"\x00", position, min(len(data), start + MAX_ASCII_BYTES + 1))
    if end < 0 or end - start > MAX_ASCII_BYTES:
        return None
    value = data[start:end]
    if not value or any(not 32 <= char <= 126 for char in value):
        return None
    return {"offset": start, "text": value.decode("ascii")}


def marker_report(data, marker):
    offsets = []
    samples = []
    cursor = 0
    matches = 0
    while True:
        location = data.find(marker, cursor)
        if location < 0:
            break
        matches += 1
        if matches > MAX_MATCHES:
            raise AudioStringError("Marker occurrence limit exceeded")
        if len(offsets) < MAX_SAMPLES:
            offsets.append(location)
            sample = get_ascii_string(data, location)
            if sample is not None:
                samples.append(sample)
        cursor = location + 1
    return {
        "count": matches,
        "offset_samples": offsets,
        "nul_delimited_ascii_samples": samples,
        "samples_capped": matches > MAX_SAMPLES,
    }


def inspect(archive_path, expected_archive_sha256=None, expected_elf_sha256=None):
    archive_path = Path(archive_path)
    if not archive_path.is_file() or not 0 < archive_path.stat().st_size <= MAX_ARCHIVE_BYTES:
        raise AudioStringError("Missing or oversized vendor ZIP")
    for expected in (expected_archive_sha256, expected_elf_sha256):
        if expected is not None and (
            len(expected) != 64 or any(x not in "0123456789abcdef" for x in expected)
        ):
            raise AudioStringError("Expected SHA256 must be 64 lowercase hex chars")
    if expected_archive_sha256 is not None and sha256_file(archive_path) != expected_archive_sha256:
        raise AudioStringError("Local ZIP SHA256 mismatch")

    with zipfile.ZipFile(archive_path) as z:
        entries = z.infolist()
        if not 0 < len(entries) <= MAX_ZIP_ENTRIES:
            raise AudioStringError("Invalid ZIP member count")
        roots = set()
        target = []
        for e in entries:
            name = e.filename
            if not name or len(name) > 1024 or name.startswith("/") or "\\" in name or "\x00" in name:
                raise AudioStringError("Unsafe ZIP entry")
            parts = name.rstrip("/").split("/")
            if any(x in ("", ".", "..") for x in parts):
                raise AudioStringError("Unsafe ZIP path")
            roots.add(parts[0])
            if name == ROOT + MEMBER and not e.is_dir():
                target.append(e)
        if roots != {ROOT[:-1]} or len(target) != 1:
            raise AudioStringError("Unexpected vendor root or audio file")
        entry = target[0]
        if not 52 <= entry.file_size <= MAX_ELF_BYTES:
            raise AudioStringError("Unexpected ELF member size")
        with z.open(entry) as f:
            data = f.read(MAX_ELF_BYTES + 1)
        if len(data) != entry.file_size:
            raise AudioStringError("ZIP member decompression size mismatch")

    digest = hashlib.sha256(data).hexdigest()
    if expected_elf_sha256 is not None and expected_elf_sha256 != digest:
        raise AudioStringError("Audio ELF SHA256 mismatch")
    if data[:4] != b"\x7fELF" or data[4:7] != b"\x01\x01\x01":
        raise AudioStringError("Not ELF32 little-endian")
    patterns = {m.decode("ascii"): marker_report(data, m) for m in MARKERS}
    return {
        "schema": "op7t-hotdog-audio-string-locations-v1",
        "member": MEMBER,
        "elf_sha256": digest,
        "archive_sha256_matched": expected_archive_sha256 is not None,
        "elf_sha256_matched": expected_elf_sha256 is not None,
        "elf_bytes": len(data),
        "patterns": patterns,
        "status": "ELF_STRING_OFFSETS_OBSERVED",
        "proves_dlopen_call": False,
        "proves_runtime_dependency": False,
        "elf_executed": False,
        "elf_written_to_disk": False,
        "flash_ready": False,
        "limitations": "String offsets and NUL-delimited text only; not .rodata provenance, code references, relocation or dynamic loader call verification."
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--expect-archive-sha256")
    parser.add_argument("--expect-elf-sha256")
    opts = parser.parse_args(argv)
    try:
        result = inspect(opts.archive, opts.expect_archive_sha256, opts.expect_elf_sha256)
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        print(f"ELF string audit FAILED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
