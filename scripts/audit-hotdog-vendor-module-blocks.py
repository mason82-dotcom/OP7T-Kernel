#!/usr/bin/env python3
"""Read-only bounded module-block evidence from a hotdog vendor GitLab ZIP.

Static Blueprint inspection only. Does not parse/evaluate Soong, extract
binary payloads, infer install safety, or validate the running ROM.
"""
import argparse
import json
from pathlib import Path
import re
import stat
import sys
import zipfile

MAX_ZIP_ENTRIES = 100000
MAX_TEXT_BYTES = 512 * 1024
MAX_PACKAGES = 100
MAX_BLOCKS = 1000
ROOT = "proprietary_vendor_oneplus_hotdog-"
PACKAGE_RE = re.compile(r"^\s*PRODUCT_PACKAGES\s*(?:\+=|:=|=)\s*(.*)$")
BLOCK_RE = re.compile(r"(?m)^[ \t]*([a-zA-Z_]\w*)[ \t]*\{")
NAME_RE = re.compile(r'(?m)(?:^|[,{])[ \t]*name[ \t]*:[ \t]*"([^"\n]+)"[ \t]*,?')
SOURCE_RE = re.compile(r'(?m)\bsrcs?\s*:\s*\[([^\]]{0,8192})\]', re.S)
QUOTED_RE = re.compile(r'"([^"\n]{1,500})"')
PROPS = (
    "relative_install_path", "stem", "compile_multilib",
    "vendor", "proprietary", "device_specific", "soc_specific",
    "prefer", "check_elf_files", "strip", "arch", "multilib",
)
SIMPLE_PROPERTY = re.compile(
    r'(?m)^[ \t]*(' + "|".join(PROPS) +
    r')[ \t]*:[ \t]*(true|false|"[^"\n]{0,160}"|\{)[ \t]*,?'
)


class VendorModuleError(ValueError):
    pass


def safe_zip_members(z):
    infos = z.infolist()
    if not 0 < len(infos) <= MAX_ZIP_ENTRIES:
        raise VendorModuleError("Invalid ZIP member count")
    names = {}
    roots = set()
    for entry in infos:
        name = entry.filename
        if (not name or len(name) > 1024 or name.startswith("/") or
                "\\" in name or "\x00" in name):
            raise VendorModuleError("Unsafe ZIP filename")
        parts = name.rstrip("/").split("/")
        if any(p in ("", ".", "..") for p in parts):
            raise VendorModuleError("Unsafe ZIP path segment")
        roots.add(parts[0])
        if entry.is_dir():
            continue
        if len(parts) < 2:
            raise VendorModuleError("File outside ZIP root")
        rel = "/".join(parts[1:])
        if rel in names:
            raise VendorModuleError("Duplicate member")
        names[rel] = entry
    if len(roots) != 1 or not next(iter(roots)).startswith(ROOT):
        raise VendorModuleError("Unexpected GitLab ZIP root")
    return names


def read_text(z, entry):
    mode = (entry.external_attr >> 16) & 0o170000
    if entry.is_dir() or mode == stat.S_IFLNK or entry.file_size > MAX_TEXT_BYTES:
        raise VendorModuleError("Invalid build file")
    with z.open(entry) as reader:
        raw = reader.read(MAX_TEXT_BYTES + 1)
    if len(raw) != entry.file_size or len(raw) > MAX_TEXT_BYTES or b"\x00" in raw:
        raise VendorModuleError("Invalid build file content")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise VendorModuleError("Build file is not UTF-8") from exc


def logical_lines(text):
    continued = ""
    for line in text.splitlines():
        line = line.rstrip()
        follow = line.endswith("\\")
        continued += line[:-1] + " " if follow else line
        if not follow:
            yield continued.strip()
            continued = ""
    if continued:
        yield continued.strip()



def without_comments(text):
    """Remove Blueprint comments, retaining strings and newline positions."""
    out = []
    in_string = False
    escaped = False
    state = None
    i = 0
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if state == "line":
            if ch == "\n":
                state = None
                out.append(ch)
            else:
                out.append(" ")
        elif state == "block":
            if ch == "*" and nxt == "/":
                out.extend((" ", " "))
                i += 1
                state = None
            else:
                out.append("\n" if ch == "\n" else " ")
        elif in_string:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == "/" and nxt == "/":
            state = "line"
            out.extend((" ", " "))
            i += 1
        elif ch == "/" and nxt == "*":
            state = "block"
            out.extend((" ", " "))
            i += 1
        else:
            out.append(ch)
            if ch == '"':
                in_string = True
        i += 1
    if in_string or state == "block":
        raise VendorModuleError("Unterminated Blueprint string or comment")
    return "".join(out)


def find_end(text, start):
    """Balanced Blueprint braces, ignoring strings and // and /* */ comments."""
    depth = 0
    string = False
    escaped = False
    comment = None
    i = start
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if comment == "line":
            if ch == "\n":
                comment = None
        elif comment == "block":
            if ch == "*" and nxt == "/":
                comment = None
                i += 1
        elif string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                string = False
        elif ch == "/" and nxt == "/":
            comment = "line"
            i += 1
        elif ch == "/" and nxt == "*":
            comment = "block"
            i += 1
        elif ch == '"':
            string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
            if depth < 0:
                raise VendorModuleError("Unbalanced Blueprint closing brace")
        i += 1
    raise VendorModuleError("Unterminated Blueprint module")


def module_blocks(text):
    matches = list(BLOCK_RE.finditer(text))
    if len(matches) > MAX_BLOCKS:
        raise VendorModuleError("Too many Blueprint block candidates")
    result = []
    pos = 0
    for m in matches:
        if m.start() < pos:
            continue
        begin = m.end() - 1
        end = find_end(text, begin)
        result.append((m.group(1), text[m.start():end], text.count("\n", 0, m.start()) + 1))
        pos = end
    return result


def inspect(path):
    with zipfile.ZipFile(path) as z:
        files = safe_zip_members(z)
        required = ("hotdog-vendor.mk", "Android.bp")
        if not all(name in files for name in required):
            raise VendorModuleError("Missing root hotdog-vendor.mk or Android.bp")
        product = read_text(z, files["hotdog-vendor.mk"])
        blueprint = read_text(z, files["Android.bp"])
        expected = []
        for line in logical_lines(product):
            if line.startswith("#"):
                continue
            m = PACKAGE_RE.match(line)
            if m:
                expected += m.group(1).split()
        if not expected or len(expected) > MAX_PACKAGES:
            raise VendorModuleError("No packages or unexpected package count")
        expected = sorted(set(expected))
        blocks = module_blocks(blueprint)

        observed = {name: [] for name in expected}
        for block_type, block, lineno in blocks:
            block = without_comments(block)
            names = NAME_RE.findall(block)
            if len(names) != 1 or names[0] not in observed:
                continue
            name = names[0]
            candidate_srcs = []
            for body in SOURCE_RE.findall(block):
                candidate_srcs += QUOTED_RE.findall(body)
            paths = sorted(set(v for v in candidate_srcs if not any(
                syntax in v for syntax in ("*", "?", "$", ":"))))
            missing = [p for p in paths if p not in files]
            attrs = {}
            for match in SIMPLE_PROPERTY.finditer(block):
                attrs.setdefault(match.group(1), [])
                if len(attrs[match.group(1)]) < 12:
                    attrs[match.group(1)].append(match.group(2))
            observed[name].append({
                "module_type": block_type,
                "blueprint_line": lineno,
                "src_literal_paths": paths[:25],
                "src_literal_path_count": len(paths),
                "src_literal_found_count": len(paths) - len(missing),
                "src_literal_missing": missing[:20],
                "property_observations": attrs,
                "static_srcs_found": bool(candidate_srcs),
            })

    missing_names = [name for name, entries in observed.items() if not entries]
    duplicates = [name for name, entries in observed.items() if len(entries) > 1]
    missing_srcs = sum(len(entry["src_literal_missing"]) for entries in observed.values() for entry in entries)
    return {
        "schema": "op7t-hotdog-vendor-module-blocks-v1",
        "scope": "root_Android.bp_top_level_blocks_static_only",
        "expected_product_packages": expected,
        "expected_product_package_count": len(expected),
        "blueprint_top_level_blocks_found": len(blocks),
        "product_package_blocks": observed,
        "missing_package_module_names": missing_names,
        "duplicate_package_module_names": duplicates,
        "missing_static_src_path_samples_total": missing_srcs,
        "status": ("STATIC_BP_MODULE_CANDIDATES_FOUND" if not missing_names and not duplicates and not missing_srcs
                   else "STATIC_BP_MODULE_GAPS"),
        "soong_semantics_verified": False,
        "make_inheritance_verified": False,
        "binary_integrity_verified": False,
        "module_runtime_verified": False,
        "archive_extracted": False,
        "flash_ready": False,
        "limitations": "Blueprint lexical/brace structural scan only; property values may be nested; does not resolve arch/multilib, source expressions, defaults, DT_NEEDED, package dependencies or installed firmware.",
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("zip", type=Path)
    args = p.parse_args(argv)
    try:
        result = inspect(args.zip)
    except (OSError, ValueError, RuntimeError, NotImplementedError, zipfile.BadZipFile) as exc:
        print(f"Hotdog vendor BP block audit failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "STATIC_BP_MODULE_CANDIDATES_FOUND" else 3


if __name__ == "__main__":
    sys.exit(main())
