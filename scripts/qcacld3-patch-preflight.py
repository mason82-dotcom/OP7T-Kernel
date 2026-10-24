#!/usr/bin/env python3
"""Offline git-apply CHECK for a pinned QCACLD patch. NEVER modifies a kernel."""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "config/qcacld3-injection-candidate.json"
MAX_PATCH = 12 * 1024 * 1024
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
PATH_RE = re.compile(r"^[a-zA-Z0-9_./+\\-]+$")
HEADER_RE = re.compile(rb"^diff --git a/([^\\r\\n]+) b/([^\\r\\n]+)$", re.M)


class PreflightError(ValueError):
    pass


def reference(path):
    ref = json.loads(Path(path).read_text(encoding="utf-8"))
    for key in ("source_commit", "source_parent", "target_commit"):
        if not SHA_RE.fullmatch(str(ref.get(key, ""))):
            raise PreflightError("Invalid pinned commit: " + key)
    if (ref.get("schema") != "op7t-qcacld3-patch-candidate-v1"
        or ref.get("target_device") != "hotdog"
        or ref.get("source_repository") != "V0lk3n/nethunter_kernel_oneplus_sm8150"
        or ref.get("upstream_repository") != "crdroidandroid/android_kernel_oneplus_sm8150"
        or ref.get("automatic_patch_application") is not False
        or ref.get("flash_ready") is not False):
        raise PreflightError("Invalid source or safety manifest")
    paths = ref.get("driver_paths")
    ignored = ref.get("excluded_non_driver_paths")
    if (not isinstance(paths, list) or len(paths) < 30
        or len(paths) != len(set(paths))
        or ignored != [".gitmodules", "kali-nethunter-kernel-builder"]):
        raise PreflightError("Untrusted patch path allowlist")
    for item in paths:
        if (not isinstance(item, str)
            or not item.startswith(("drivers/staging/qcacld-3.0/",
                                     "drivers/staging/qca-wifi-host-cmn/"))
            or not PATH_RE.fullmatch(item) or ".." in Path(item).parts):
            raise PreflightError("Unexpected driver path in manifest")
    return ref


def patch_headers(data, ref):
    if not data or len(data) > MAX_PATCH:
        raise PreflightError("Empty or oversized patch")
    if b"GIT binary patch" in data or b"Binary files " in data:
        raise PreflightError("Binary patch content is not reviewed")
    # Reject unexpected file modes, path rename/copy, and unaccounted paths.
    for line in data.splitlines():
        if line.startswith((b"rename from ", b"rename to ", b"copy from ", b"copy to ")):
            raise PreflightError("Rename/copy must be reviewed separately")
        if line.startswith((b"new file mode ", b"old mode ", b"new mode ")):
            value = line.rsplit(b" ", 1)[-1]
            if value not in (b"100644", b"100755", b"160000"):
                raise PreflightError("Unexpected file mode")
    matches = HEADER_RE.findall(data)
    if not matches:
        raise PreflightError("No git diff file headers")
    files = []
    for left, right in matches:
        if left != right or b" " in left:
            raise PreflightError("Unsafe or renamed patch path")
        try:
            name = left.decode("ascii")
        except UnicodeDecodeError as error:
            raise PreflightError("Non-ASCII patch path") from error
        if not PATH_RE.fullmatch(name) or ".." in Path(name).parts or name.startswith("/"):
            raise PreflightError("Unsafe patch path")
        files.append(name)
    if len(files) != len(set(files)):
        raise PreflightError("Duplicate patch paths")
    declared = set(ref["driver_paths"]) | set(ref["excluded_non_driver_paths"])
    if set(files) != declared:
        raise PreflightError("Patch file set differs from the pinned reviewed commit")
    return files


def git(*argv):
    return subprocess.run(["git", *map(str, argv)], text=True,
                          capture_output=True, timeout=30, check=False)


def inspect(patch, kernel, ref):
    path = Path(patch)
    if not path.is_file() or path.stat().st_size > MAX_PATCH:
        raise PreflightError("Patch absent or too large")
    data = path.read_bytes()
    paths = patch_headers(data, ref)
    base = Path(kernel).resolve(strict=True)
    head = git("-C", base, "rev-parse", "HEAD")
    if head.returncode or head.stdout.strip() != ref["target_commit"]:
        raise PreflightError("Kernel checkout is not the pinned crDroid source commit")
    changes = git("-C", base, "status", "--porcelain", "--untracked-files=no")
    if changes.returncode or changes.stdout.strip():
        raise PreflightError("Kernel checkout has tracked modifications")
    # Driver paths are included; known submodule and gitmodules entries are
    # intentionally excluded, but unexpected patch paths were rejected above.
    args = ["-C", base, "apply", "--check",
            "--exclude=.gitmodules",
            "--exclude=kali-nethunter-kernel-builder",
            path.resolve(strict=True)]
    check = git(*args)
    return {
        "schema": "op7t-qcacld3-application-check-v1",
        "source_commit": ref["source_commit"],
        "target_commit": ref["target_commit"],
        "patch_sha256": hashlib.sha256(data).hexdigest(),
        "total_patched_paths": len(paths),
        "reviewed_driver_paths": len(ref["driver_paths"]),
        "excluded_repository_paths": len(ref["excluded_non_driver_paths"]),
        "git_apply_check_ok": check.returncode == 0,
        "status": ("PATCH_CONTEXT_APPLIES_ONLY" if check.returncode == 0
                   else "PATCH_CONTEXT_CONFLICTS"),
        "patch_applied": False,
        "kernel_compiled": False,
        "firmware_support_verified": False,
        "injection_verified": False,
        "installed_rom_compatibility_verified": False,
        "flash_ready": False,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--patch", type=Path, required=True)
    ap.add_argument("--kernel", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--output", type=Path)
    ap.add_argument("--strict", action="store_true",
                    help="exit 4 on a patch context mismatch, never mark flashable")
    args = ap.parse_args(argv)
    try:
        report = inspect(args.patch, args.kernel, reference(args.manifest))
    except (OSError, ValueError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print("Patch preflight rejected: " + str(exc), file=sys.stderr)
        return 3
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        if args.output.exists():
            print("Refusing to overwrite existing report", file=sys.stderr)
            return 3
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 4 if args.strict and not report["git_apply_check_ok"] else 0


if __name__ == "__main__":
    sys.exit(main())
