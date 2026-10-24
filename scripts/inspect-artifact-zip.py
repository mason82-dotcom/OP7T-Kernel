#!/usr/bin/env python3
"""Read-only integrity inventory for raw kernel artifact ZIPs, including partial exports."""
import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path, PurePosixPath

SHA_LINE = re.compile(r"^([a-f0-9]{64})  \./(.+)$")
MAX_MEMBER = 128 * 1024 * 1024
MAX_TOTAL = 512 * 1024 * 1024
MAX_ENTRIES = 256


class IntakeError(ValueError):
    pass


def safe_name(name):
    path = PurePosixPath(name)
    if (not name or name.startswith("/") or "\\" in name or
            any(part in ("", ".", "..") for part in name.split("/")) or
            path.as_posix() != name):
        raise IntakeError("Unsafe ZIP member name")
    return name


def inspect(path):
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if not members or len(members) > MAX_ENTRIES:
            raise IntakeError("Invalid ZIP entry count")
        names = [safe_name(item.filename) for item in members]
        if len(names) != len(set(names)) or any(item.is_dir() for item in members):
            raise IntakeError("Duplicate or directory ZIP entry")
        if any(item.file_size > MAX_MEMBER for item in members) or sum(
                item.file_size for item in members) > MAX_TOTAL:
            raise IntakeError("ZIP exceeds uncompressed size limit")
        required = {"SHA256SUMS", "artifact-report.json"}
        if not required.issubset(names):
            raise IntakeError("Missing SHA256SUMS or artifact-report.json")
        if any(i.file_size > 1024 * 1024 for i in members if i.filename in required):
            raise IntakeError("Manifest exceeds size limit")
        digests = {}
        small = {}
        for item in members:
            h = hashlib.sha256()
            count = 0
            with archive.open(item) as stream:
                while block := stream.read(1024 * 1024):
                    count += len(block)
                    if count > MAX_MEMBER:
                        raise IntakeError("ZIP member exceeds size limit")
                    h.update(block)
                    if item.filename in required:
                        small.setdefault(item.filename, bytearray()).extend(block)
            if count != item.file_size:
                raise IntakeError("ZIP member size changed")
            digests[item.filename] = h.hexdigest()
        sums = {}
        for line in small["SHA256SUMS"].decode("ascii").splitlines():
            match = SHA_LINE.fullmatch(line)
            if not match:
                raise IntakeError("Malformed SHA256SUMS line")
            digest, filename = match.groups()
            safe_name(filename)
            if filename in sums or filename == "SHA256SUMS":
                raise IntakeError("Duplicate or recursive SHA256SUMS entry")
            sums[filename] = digest
        report = json.loads(small["artifact-report.json"])
        if not isinstance(report, dict) or not isinstance(report.get("modules"), list):
            raise IntakeError("Invalid artifact report structure")
        if (report.get("schema") != "op7t-kernel-artifact-report-v1" or
                report.get("flash_ready") is not False or report.get("device") != "hotdog"):
            raise IntakeError("Invalid artifact report or unsafe flash claim")
        mismatched = sorted(n for n, h in digests.items() if n in sums and sums[n] != h)
        if mismatched:
            raise IntakeError("Member hash mismatch: " + ", ".join(mismatched))
        module_results = []
        for module in report.get("modules", []):
            if not isinstance(module, dict):
                raise IntakeError("Invalid reported module")
            original = module.get("path")
            if not isinstance(original, str):
                raise IntakeError("Invalid reported module path")
            safe_name(original)
            basename = PurePosixPath(original).name
            if basename in digests:
                if (module.get("sha256") != digests[basename] or
                        sums.get(original) != digests[basename] or
                        module.get("size_bytes") != next(i.file_size for i in members
                                                          if i.filename == basename)):
                    raise IntakeError("Reported module digest or size mismatch")
                module_results.append({"reported_path": original, "zip_member": basename,
                                       "sha256": digests[basename]})
        if len({m["zip_member"] for m in module_results}) != len(module_results):
            raise IntakeError("Ambiguous module basenames")
        if any(n.endswith(".ko") and n not in {m["zip_member"] for m in module_results}
               for n in digests):
            raise IntakeError("Unreported module in ZIP")
        if set(digests) - {"SHA256SUMS"} - set(sums) - {
                m["zip_member"] for m in module_results}:
            raise IntakeError("Unlisted ZIP member")
        missing = sorted(set(sums) - set(digests) - {
            m["reported_path"] for m in module_results})
        zip_digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                zip_digest.update(block)
        return {
            "schema": "op7t-kernel-artifact-zip-intake-v1",
            "status": "partial_verified_members" if missing else "complete_verified_members",
            "zip_sha256": zip_digest.hexdigest(),
            "present_members": sorted(digests), "missing_manifest_members": missing,
            "verified_modules": module_results,
            "reported_profile": report.get("profile"),
            "reported_upstream_commit": report.get("upstream_commit"),
            "module_signature_cryptographically_verified": False,
            "installed_rom_abi_and_key_trust_verified": False,
            "flash_ready": False,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip_path", type=Path)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    try:
        result = inspect(args.zip_path)
    except (IntakeError, OSError, ValueError, zipfile.BadZipFile, UnicodeError) as error:
        print(f"Artifact ZIP intake FAILED: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 4 if args.require_complete and result["missing_manifest_members"] else 0


if __name__ == "__main__":
    sys.exit(main())
