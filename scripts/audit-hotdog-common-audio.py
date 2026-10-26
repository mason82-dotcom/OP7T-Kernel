#!/usr/bin/env python3
"""Static, read-only link audit of hotdog and SM8150-common ODM audio modules.

Input: existing hotdog ZIP and three verified common vendor build text files.
No ELF/library payloads are read, extracted, executed, or modified.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import sys
import zipfile

HOTDOG_PACKAGE = "audio.primary.msmnile_odm"
COMMON_PACKAGE = "liba2dpoffload_odm"
HOTDOG_SRC = "proprietary/odm/lib/hw/audio.primary.msmnile.so"
COMMON_SRC = "proprietary/odm/lib/liba2dpoffload.so"
MAX_TEXT = 1_000_000
MAX_FILES = 100000
MODULE_RE = re.compile(r"(?m)^[ \t]*cc_prebuilt_library_shared[ \t]*\{")
NAME = re.compile(r'(?m)(?:^|[,{\n])[ \t]*name[ \t]*:[ \t]*"([^"\n]+)"')
PACKAGES = re.compile(r"^\s*PRODUCT_PACKAGES\s*(?:\+=|:=|=)\s*(.*)$")


class AudioLinkAuditError(ValueError):
    pass


def read_bounded(z, info):
    if info.file_size > MAX_TEXT:
        raise AudioLinkAuditError("Build text exceeds size limit")
    mode = (info.external_attr >> 16) & 0o170000
    if info.is_dir() or mode == stat.S_IFLNK:
        raise AudioLinkAuditError("Build text must be an ordinary file")
    with z.open(info) as stream:
        blob = stream.read(MAX_TEXT + 1)
    return text_from_bytes(blob, info.file_size)


def text_from_bytes(blob, expected=None):
    if len(blob) > MAX_TEXT or b"\x00" in blob or (expected is not None and len(blob) != expected):
        raise AudioLinkAuditError("Invalid build text")
    try:
        return blob.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AudioLinkAuditError("Build text is not UTF-8") from exc


def git_blob_sha(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\x00" + data).hexdigest()


def untrusted_build_text(path, expected_git_sha):
    if not re.fullmatch(r"[0-9a-f]{40}", expected_git_sha or ""):
        raise AudioLinkAuditError("Invalid pinned git blob hash")
    path = Path(path)
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_TEXT:
        raise AudioLinkAuditError("Common build file missing, linked or oversized")
    data = path.read_bytes()
    if git_blob_sha(data) != expected_git_sha:
        raise AudioLinkAuditError("Common vendor build file hash mismatch: " + path.name)
    return text_from_bytes(data)


def remove_comments(src):
    """Mask Blueprint comments, maintaining newline and character positions."""
    buf = []
    quote = False
    escaped = False
    state = None
    i = 0
    while i < len(src):
        c = src[i]
        n = src[i + 1] if i + 1 < len(src) else ""
        if state == "line":
            if c == "\n":
                state = None
                buf.append("\n")
            else:
                buf.append(" ")
        elif state == "block":
            if c == "*" and n == "/":
                buf.extend((" ", " "))
                i += 1
                state = None
            else:
                buf.append("\n" if c == "\n" else " ")
        elif quote:
            buf.append(c)
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                quote = False
        elif c == "/" and n == "/":
            state = "line"
            buf.extend((" ", " "))
            i += 1
        elif c == "/" and n == "*":
            state = "block"
            buf.extend((" ", " "))
            i += 1
        else:
            buf.append(c)
            if c == '"':
                quote = True
        i += 1
    if quote or state == "block":
        raise AudioLinkAuditError("Unterminated Blueprint comment or string")
    return "".join(buf)


def blueprint_modules(text, target):
    """Find balanced cc_prebuilt_library_shared blocks; not a Soong parser."""
    txt = remove_comments(text)
    results = []
    for match in MODULE_RE.finditer(txt):
        p = match.end() - 1
        depth = 0
        in_string = False
        escaped = False
        end = None
        for j in range(p, len(txt)):
            ch = txt[j]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
            elif ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = j + 1
                    break
        if end is None:
            raise AudioLinkAuditError("Unclosed Blueprint module")
        block = txt[p:end]
        names = NAME.findall(block)
        if len(names) == 1 and names[0] == target:
            results.append(block)
    return results


def package_tokens(text):
    lines = []
    carry = ""
    for line in text.splitlines():
        line = line.rstrip()
        continuation = line.endswith("\\")
        carry += line[:-1] + " " if continuation else line
        if not continuation:
            lines.append(carry.strip())
            carry = ""
    if carry:
        lines.append(carry.strip())
    result = []
    for line in lines:
        if line.startswith("#"):
            continue
        match = PACKAGES.match(line)
        if match:
            result.extend(match.group(1).split())
    return result


def value_is(block, prop, val):
    return bool(re.search(r"(?m)^[ \t]*" + re.escape(prop) +
                          r'[ \t]*:[ \t]*' + re.escape(val) + r"[ \t]*,", block))


def source_list_contains(block, source):
    # Literal source string in a srcs array; does not resolve arch/select/defaults.
    return bool(re.search(r'\bsrcs?[ \t]*:[ \t]*\[[^\]]{0,10000}' +
                          re.escape('"' + source + '"') + r'[^\]]{0,10000}\]',
                          block, re.S))


def inspect(zip_path, common_dir, reference_path, expected_zip_sha256=None):
    reference = json.loads(Path(reference_path).read_text(encoding="utf-8"))
    if (reference.get("schema") != "op7t-sm8150-common-vendor-reference-v1" or
        reference.get("branch") != "17.0" or
        reference.get("branch_commit_observed_2026_10_26") !=
            "6586000353465cc53b42189be056d5c037e14ef9"):
        raise AudioLinkAuditError("Unexpected common vendor source reference")
    expected_hashes = reference.get("verified_build_file_git_blob_shas", {})
    files = {}
    for name in ("Android.bp", "sm8150-common-vendor.mk", "BoardConfigVendor.mk"):
        files[name] = untrusted_build_text(Path(common_dir) / name, expected_hashes.get(name))
    zip_path = Path(zip_path)
    if not zip_path.is_file() or zip_path.stat().st_size > 8 * 1024**3:
        raise AudioLinkAuditError("Hotdog ZIP missing or oversized")
    if expected_zip_sha256:
        if not re.fullmatch(r"[0-9a-f]{64}", expected_zip_sha256):
            raise AudioLinkAuditError("Malformed expected ZIP SHA256")
        digest = hashlib.sha256()
        with zip_path.open("rb") as reader:
            for block in iter(lambda: reader.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != expected_zip_sha256:
            raise AudioLinkAuditError("Hotdog ZIP SHA256 mismatch")
    with zipfile.ZipFile(zip_path) as z:
        info = z.infolist()
        if not 0 < len(info) <= MAX_FILES:
            raise AudioLinkAuditError("Invalid ZIP directory")
        entries = {}
        roots = set()
        for member in info:
            n = member.filename
            if not n or n.startswith("/") or "\\" in n or "\x00" in n or len(n) > 1024:
                raise AudioLinkAuditError("Unsafe ZIP path")
            parts = n.rstrip("/").split("/")
            if any(p in ("", ".", "..") for p in parts):
                raise AudioLinkAuditError("Unsafe ZIP path component")
            roots.add(parts[0])
            if member.is_dir():
                continue
            if len(parts) < 2:
                raise AudioLinkAuditError("Unexpected ZIP file")
            rel = "/".join(parts[1:])
            if rel in entries:
                raise AudioLinkAuditError("Duplicate ZIP path")
            entries[rel] = member
        if len(roots) != 1 or not next(iter(roots)).startswith(
            "proprietary_vendor_oneplus_hotdog-"):
            raise AudioLinkAuditError("Unexpected vendor ZIP wrapper")
        if "Android.bp" not in entries or "hotdog-vendor.mk" not in entries:
            raise AudioLinkAuditError("Hotdog vendor build files missing")
        hotdog_bp = read_bounded(z, entries["Android.bp"])
        hotdog_mk = read_bounded(z, entries["hotdog-vendor.mk"])
        hotdog_audio_src_exists = HOTDOG_SRC in entries

    hotdog_blocks = blueprint_modules(hotdog_bp, HOTDOG_PACKAGE)
    common_blocks = blueprint_modules(files["Android.bp"], COMMON_PACKAGE)

    checks = {
        "common_build_texts_git_blob_hash_verified": True,
        "hotdog_audio_package_listed": HOTDOG_PACKAGE in package_tokens(hotdog_mk),
        "common_audio_package_listed": COMMON_PACKAGE in package_tokens(files["sm8150-common-vendor.mk"]),
        "hotdog_audio_module_exactly_once": len(hotdog_blocks) == 1,
        "common_audio_module_exactly_once": len(common_blocks) == 1,
        "hotdog_audio_src_zip_filename_present": hotdog_audio_src_exists,
    }
    if len(hotdog_blocks) == 1:
        block = hotdog_blocks[0]
        checks.update({
            "hotdog_module_32bit": value_is(block, "compile_multilib", '"32"'),
            "hotdog_module_device_specific": value_is(block, "device_specific", "true"),
            "hotdog_module_relative_install_path_hw": value_is(block, "relative_install_path", '"hw"'),
            "hotdog_module_stem_audio_primary": value_is(block, "stem", '"audio.primary.msmnile"'),
            "hotdog_module_src_literal_matches_zip": source_list_contains(block, HOTDOG_SRC),
        })
    if len(common_blocks) == 1:
        block = common_blocks[0]
        checks.update({
            "common_module_32bit": value_is(block, "compile_multilib", '"32"'),
            "common_module_device_specific": value_is(block, "device_specific", "true"),
            "common_module_stem_liba2dpoffload": value_is(block, "stem", '"liba2dpoffload"'),
            "common_module_src_path_literal": source_list_contains(block, COMMON_SRC),
        })
    return {
        "schema": "op7t-hotdog-common-audio-source-chain-v1",
        "reference_commit": reference["branch_commit_observed_2026_10_26"],
        "hotdog_zip_sha256_matches_user_observation": bool(expected_zip_sha256),
        "checks": checks,
        "checks_satisfied": sum(checks.values()),
        "checks_total": len(checks),
        "status": "STATIC_AUDIO_SOURCE_CHAIN_ALIGNS" if checks and all(checks.values())
                  else "STATIC_AUDIO_SOURCE_CHAIN_GAPS",
        "expected_audio_linker_fixup_from_official_device_tree": {
            "old_needed": "/vendor/lib/liba2dpoffload.so",
            "new_needed": "/odm/lib/liba2dpoffload.so"
        },
        "common_vendor_blob_file_existence_verified": False,
        "elf_dt_needed_verified": False,
        "cross_tree_soong_resolution_verified": False,
        "vendor_binaries_read_or_extracted": False,
        "installed_rom_compatibility_verified": False,
        "flash_ready": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hotdog-zip", type=Path, required=True)
    parser.add_argument("--common-dir", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--expect-hotdog-sha256")
    args = parser.parse_args(argv)
    try:
        report = inspect(args.hotdog_zip, args.common_dir, args.reference,
                         args.expect_hotdog_sha256)
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        print(f"Cross-tree audio audit FAILED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "STATIC_AUDIO_SOURCE_CHAIN_ALIGNS" else 3


if __name__ == "__main__":
    sys.exit(main())
