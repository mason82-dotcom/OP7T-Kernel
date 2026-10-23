#!/usr/bin/env python3
"""Read-only verification of an exact crDroid OTA ZIP against official published hash."""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from zipfile import BadZipFile, ZipFile

SHA256 = re.compile(r"^[0-9a-f]{64}$")


def verify(archive: Path, manifest: Path) -> dict:
    data = json.loads(manifest.read_text(encoding="utf-8"))
    required = {"schema", "device", "android_major", "crdroid_major", "filename", "size_bytes", "sha256"}
    if not required.issubset(data) or data["schema"] != "op7t-crdroid-ota-reference-v1":
        raise ValueError("ROM reference schema or fields invalid")
    if data["device"] != "hotdog" or data["android_major"] != 17 or data["crdroid_major"] != 13:
        raise ValueError("ROM reference is for the wrong device or Android version")
    sha = data["sha256"]
    if not isinstance(sha, str) or not SHA256.fullmatch(sha):
        raise ValueError("Invalid SHA-256 in ROM reference")
    if archive.name != data["filename"]:
        raise ValueError("ROM ZIP filename does not match pinned reference release")
    if archive.stat().st_size != data["size_bytes"]:
        raise ValueError("ROM ZIP size does not match pinned reference release")
    digest = hashlib.sha256()
    with archive.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != sha:
        raise ValueError("ROM ZIP SHA-256 mismatch")
    with ZipFile(archive) as z:
        members = z.namelist()
        if not members:
            raise ValueError("ROM ZIP has no entries")
        if any(name.startswith("/") or ".." in name.split("/") or "\\\\" in name for name in members):
            raise ValueError("ROM ZIP contains unsafe entry paths")
    return {
        "schema": "op7t-rom-verification-v1",
        "device": "hotdog",
        "archive": archive.name,
        "size_bytes": archive.stat().st_size,
        "sha256": sha,
        "sha256_verified": True,
        "has_payload_bin": "payload.bin" in members,
        "has_payload_properties": "payload_properties.txt" in members,
        "installed_rom_verified": False,
        "boot_image_compatible": False,
        "flash_ready": False,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("archive", type=Path)
    p.add_argument("--manifest", type=Path, default=Path(__file__).resolve().parents[1] / "config" / "rom-reference.json")
    args = p.parse_args()
    try:
        print(json.dumps(verify(args.archive, args.manifest), indent=2))
        return 0
    except (ValueError, OSError, BadZipFile, json.JSONDecodeError) as error:
        print(f"ROM verification FAILED: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
