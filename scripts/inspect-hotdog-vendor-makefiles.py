#!/usr/bin/env python3
"""Read-only, bounded inspection of hotdog vendor Android makefiles inside a ZIP.

Reads only exact-name makefiles and never extracts or executes vendor content.
Build dependencies are reported as *untrusted text observations*.
"""
import argparse
import json
import re
import stat
import sys
import zipfile
from pathlib import Path

ROOT_FILES = ("BoardConfigVendor.mk", "hotdog-vendor.mk")
MAX_FILE_SIZE = 512 * 1024
MAX_LINES_PER_FILE = 12000
MAX_REPORTED_LINES = 70
FILTER = re.compile(
    r"\\binclude\\b|inherit-product|PRODUCT_PACKAGES|PRODUCT_COPY_FILES|"
    r"\\bBOARD_\\w*|\\bTARGET_\\w*|\\bVENDOR_\\w*|\\bSOONG_\\w*|"
    r"vendor_dlkm|\\.ko\\b|firmware",
    re.IGNORECASE,
)


class VendorMakefileError(ValueError):
    pass


def inspect_makefiles(path):
    """Return bounded data; does not extract files or evaluate make syntax."""
    result = {
        "schema": "op7t-hotdog-vendor-makefile-audit-v1",
        "scope": "zip-member-text-only",
        "original_zip_extracted": False,
        "vendor_makefiles_executed": False,
        "flash_ready": False,
        "makefiles": {},
    }

    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        matches = {}
        for name in names:
            if name.startswith("/") or "\\" in name or "\x00" in name:
                raise VendorMakefileError("Invalid ZIP entry name")
            if any(seg in ("", ".", "..") for seg in name.rstrip("/").split("/")):
                raise VendorMakefileError("ZIP path traversal or invalid segment")
            parts = name.rstrip("/").split("/")
            if not parts[0].startswith("proprietary_vendor_oneplus_hotdog-"):
                raise VendorMakefileError("Unexpected ZIP root")
            if len(parts) == 2 and parts[1] in ROOT_FILES:
                matches.setdefault(parts[1], []).append(name)

        if set(matches) != set(ROOT_FILES) or any(len(v) != 1 for v in matches.values()):
            raise VendorMakefileError("Expected exactly one of each hotdog vendor makefile")

        for short_name in ROOT_FILES:
            entry = z.getinfo(matches[short_name][0])
            mode = (entry.external_attr >> 16) & 0o170000
            if entry.is_dir() or mode == stat.S_IFLNK:
                raise VendorMakefileError("Expected ordinary vendor makefile")
            if entry.file_size > MAX_FILE_SIZE:
                raise VendorMakefileError("Vendor makefile exceeds bounded size")
            with z.open(entry) as f:
                blob = f.read(MAX_FILE_SIZE + 1)
            if len(blob) > MAX_FILE_SIZE or len(blob) != entry.file_size:
                raise VendorMakefileError("Vendor makefile decompression size mismatch")
            if b"\x00" in blob:
                raise VendorMakefileError("Binary data in vendor makefile")
            try:
                content = blob.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise VendorMakefileError("Vendor makefile is not UTF-8") from exc
            lines = content.splitlines()
            if len(lines) > MAX_LINES_PER_FILE:
                raise VendorMakefileError("Vendor makefile has too many lines")

            observations = []
            count = 0
            for lineno, value in enumerate(lines, 1):
                line = value.strip()
                if not line or line.startswith("#") or not FILTER.search(line):
                    continue
                count += 1
                if len(observations) < MAX_REPORTED_LINES:
                    observations.append({
                        "line": lineno,
                        "text": line[:250],
                        "truncated": len(line) > 250
                    })

            result["makefiles"][short_name] = {
                "bytes": len(blob),
                "line_count": len(lines),
                "matching_line_count": count,
                "observations_capped": count > MAX_REPORTED_LINES,
                "observations": observations,
            }
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip", type=Path)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(inspect_makefiles(args.zip), indent=2, sort_keys=True))
    except (VendorMakefileError, OSError, zipfile.BadZipFile,
            RuntimeError, NotImplementedError) as exc:
        print(f"Vendor makefile audit FAILED: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
