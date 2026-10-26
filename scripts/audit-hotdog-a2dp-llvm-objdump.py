#!/usr/bin/env python3
"""Read-only LLVM or ARM GNU objdump text hints for the A2DP ELF string.

Verifies both pinned SHA256s; passes ELF via stdin or Linux anonymous memfd.
Never writes to disk, executes the ELF or attests a runtime call chain.
"""
import argparse
from collections import deque
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = "proprietary_vendor_oneplus_hotdog-17.0/"
MEMBER = "proprietary/odm/lib/hw/audio.primary.msmnile.so"
OLD_SHA = "c038a3ccab574795c496d043f4d735b920dbbbab279232229a80c94aa32a0078"
ELF_SHA = "08a20a73c123c793d717f1b8e7078df1b9efb3853753fae7fac269d3a20a829f"
PATH_BYTES = b"/odm/lib/liba2dpoffload.so"
MAX_ARCHIVE = 8 * 1024**3
MAX_ELF = 8 * 1024**2
MAX_ENTRIES = 100000
MAX_DISASM_OUTPUT = 64 * 1024 * 1024
MAX_CANDIDATES = 25
MAX_LINE = 350
ADDR = re.compile(r"^\s*([0-9a-fA-F]{4,8}):\s+")
A2DP_ADDR = re.compile(r"(?i)(?:0x)?0*1654f\b")
DLOPEN = re.compile(r"\b(?:dlopen|dlsym)(?:@plt|@.*)?\b", re.I)
# Previously cross-checked from original ELF A32 three-opcode PLT stubs and
# their independently parsed R_ARM_JUMP_SLOT relocation destinations.
PINNED_LOADER_PLT_TARGETS = {
    "dlopen": 0xB12A0,
    "dlsym": 0xB12B0,
}
MAX_PLT_CALLER_SAMPLES = 32
DIRECT_BRANCH = re.compile(
    r"^\s*(?P<pc>[0-9a-fA-F]{4,8}):\s+"
    r"(?P<opcode>blx?(?:\.w)?|b(?:\.w|\.n)?)\s+"
    r"(?P<target>(?:0x)?[0-9a-fA-F]{4,8})(?![0-9a-fA-F])(?=\s|$|<)",
    re.I,
)


# Search installed (possibly version-suffixed) executables before suggesting apt.
LLVM_CANDIDATES = (
    "llvm-objdump", "llvm-objdump-22", "llvm-objdump-21",
    "llvm-objdump-20", "llvm-objdump-19", "llvm-objdump-18",
    "llvm-objdump-17", "llvm-objdump-16",
)
GNU_CANDIDATES = (
    "arm-linux-gnueabi-objdump", "arm-linux-gnueabihf-objdump",
    "arm-none-eabi-objdump",
)


class ObjdumpProbeError(ValueError):
    pass


def sha_file(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for data in iter(lambda: f.read(1024 * 1024), b""):
            h.update(data)
    return h.hexdigest()


def verified_audio(path):
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_ARCHIVE:
        raise ObjdumpProbeError("Missing or oversized ZIP")
    if sha_file(path) != OLD_SHA:
        raise ObjdumpProbeError("ZIP SHA256 differs from pinned local observation")
    with zipfile.ZipFile(path) as z:
        entries = z.infolist()
        if not 0 < len(entries) <= MAX_ENTRIES:
            raise ObjdumpProbeError("Unexpected ZIP directory length")
        targets = []
        roots = set()
        for entry in entries:
            name = entry.filename
            if not name or "\\" in name or "\x00" in name or name.startswith("/") or len(name) > 1024:
                raise ObjdumpProbeError("Unsafe archive filename")
            parts = name.rstrip("/").split("/")
            if any(p in ("", ".", "..") for p in parts):
                raise ObjdumpProbeError("Unsafe archive path segment")
            roots.add(parts[0])
            if name == ROOT + MEMBER and not entry.is_dir():
                targets.append(entry)
        if roots != {ROOT[:-1]} or len(targets) != 1:
            raise ObjdumpProbeError("Wrong archive or audio member")
        entry = targets[0]
        if not 52 <= entry.file_size <= MAX_ELF:
            raise ObjdumpProbeError("Unexpected audio ELF size")
        with z.open(entry) as f:
            data = f.read(MAX_ELF + 1)
        if len(data) != entry.file_size:
            raise ObjdumpProbeError("Audio ELF length mismatch")
    if hashlib.sha256(data).hexdigest() != ELF_SHA:
        raise ObjdumpProbeError("Audio ELF SHA256 differs from pinned observation")
    if data[:7] != b"\x7fELF\x01\x01\x01":
        raise ObjdumpProbeError("Not ELF32 little-endian")
    if data.count(PATH_BYTES) != 1:
        raise ObjdumpProbeError("Expected one complete ODM A2DP string")
    pos = data.index(PATH_BYTES)
    if pos == 0 or data[pos - 1] != 0 or data[pos+len(PATH_BYTES):pos+len(PATH_BYTES)+1] != b"\x00":
        raise ObjdumpProbeError("Embedded A2DP string is not NUL-delimited")
    if pos != 91471:
        raise ObjdumpProbeError("Unexpected original audio A2DP offset")
    return data


def parse_disassembly(output, max_lines=250000):
    """Find text-only hints AND exact target operands of direct branch lines.

    Branch target matches imply a static direct code-edge candidate at the
    *disassembled text level*. They do not prove whether an execution path
    reaches it, whether an indirect BLX calls it, or the runtime r0 argument.
    """
    candidates = []
    a2dp = 0
    loader = 0
    instruction_lines = 0
    tail = deque(maxlen=8)
    plt_caller_counts = {name: 0 for name in PINNED_LOADER_PLT_TARGETS}
    plt_caller_samples = {name: [] for name in PINNED_LOADER_PLT_TARGETS}
    for raw in output.splitlines():
        line = raw.strip()[:MAX_LINE]
        if not ADDR.match(line):
            continue
        instruction_lines += 1
        if instruction_lines > max_lines:
            raise ObjdumpProbeError("Disassembler emitted excessive instruction lines")
        # Ignore instruction address when detecting A2DP literal operands.
        parts = line.split(":", 1)
        operands = parts[1]
        is_a2dp = bool(A2DP_ADDR.search(operands))
        is_loader = bool(DLOPEN.search(operands))
        if is_a2dp:
            a2dp += 1
        if is_loader:
            loader += 1
        if (is_a2dp or is_loader) and len(candidates) < MAX_CANDIDATES:
            candidates.append({
                "instruction_vaddr": parts[0].strip(),
                "reason": (["literal_a2dp_address_text"] if is_a2dp else []) +
                          (["mentions_loader_symbol"] if is_loader else []),
                "preceding_lines": list(tail)[-2:],
                "disassembler_line": line,
            })
        match = DIRECT_BRANCH.match(line)
        if match:
            target = int(match.group("target"), 16)
            for name, expected in PINNED_LOADER_PLT_TARGETS.items():
                if target == expected:
                    plt_caller_counts[name] += 1
                    if len(plt_caller_samples[name]) < MAX_PLT_CALLER_SAMPLES:
                        plt_caller_samples[name].append({
                            "instruction_vaddr_hex": "0x" + match.group("pc").lower(),
                            "instruction": match.group("opcode").lower(),
                            "target_vaddr_hex": hex(target),
                            "instruction_line": line,
                            "preceding_disassembly_lines": list(tail),
                            "is_direct_branch_text": True,
                            "a2dp_argument_verified": False,
                        })
        tail.append(line)
    return {
        "instruction_lines_parsed": instruction_lines,
        "a2dp_exact_address_text_hit_count": a2dp,
        "loader_symbol_text_hit_count": loader,
        "candidate_lines": candidates,
        "candidates_capped": a2dp + loader > MAX_CANDIDATES,
        "direct_plt_branch_targets": {
            name: {
                "target_vaddr_hex": hex(target),
                "direct_branch_text_hits": plt_caller_counts[name],
                "caller_samples": plt_caller_samples[name],
                "caller_samples_capped": plt_caller_counts[name] > MAX_PLT_CALLER_SAMPLES,
                "indirect_blx_register_calls_not_resolved": True,
                "runtime_branch_reachability_verified": False,
                "r0_a2dp_path_argument_verified": False,
            }
            for name, target in PINNED_LOADER_PLT_TARGETS.items()
        },
    }


def run_objdump(elf, binary):
    if binary is None:
        return {
            "status": "LLVM_OBJDUMP_NOT_INSTALLED",
            "tool_available": False,
            "note": "Probe requires llvm-objdump. No files or system packages were changed.",
        }
    command = [binary, "--disassemble", "--print-imm-hex", "-"]
    try:
        out = subprocess.run(
            command, input=elf, capture_output=True, timeout=45,
            check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ObjdumpProbeError("Unable to complete llvm-objdump in 45s") from exc
    if len(out.stdout) > MAX_DISASM_OUTPUT or len(out.stderr) > 8192:
        raise ObjdumpProbeError("Disassembler output exceeds size limits")
    if out.returncode:
        return {
            "status": "LLVM_OBJDUMP_CANNOT_DISASSEMBLE_INPUT",
            "tool_available": True,
            "return_code": out.returncode,
            "diagnostic": out.stderr.decode("utf-8", "replace")[:1200],
        }
    parsed = parse_disassembly(out.stdout.decode("utf-8", "replace"))
    return {
        "status": "DISASSEMBLY_TEXT_CANDIDATES_RECORDED",
        "tool_available": True,
        "tool_command": ["llvm-objdump", "--disassemble", "--print-imm-hex", "<ELF stdin>"],
        **parsed,
    }



def discover_disassembler(llvm_override=None, gnu_override=None):
    """Return flavor/path/executable name; do not install packages."""
    if llvm_override and gnu_override:
        raise ObjdumpProbeError("Choose only one explicit objdump override")
    for flavor, value in (("llvm", llvm_override), ("gnu-arm", gnu_override)):
        if value:
            executable = Path(value)
            if not executable.is_file():
                raise ObjdumpProbeError("Selected objdump executable does not exist")
            return flavor, str(executable.resolve()), executable.name
    for name in LLVM_CANDIDATES:
        found = shutil.which(name)
        if found:
            return "llvm", found, name
    for name in GNU_CANDIDATES:
        found = shutil.which(name)
        if found:
            return "gnu-arm", found, name
    return None, None, None


def run_gnu_objdump(elf, binary):
    """GNU objdump receives an anonymous RAM fd, never an extracted disk file."""
    if not hasattr(os, "memfd_create") or not Path("/proc/self/fd").is_dir():
        return {
            "status": "GNU_OBJDUMP_REQUIRES_LINUX_MEMFD",
            "tool_available": True,
            "note": "Memory-only file descriptors unavailable; no data exported.",
        }
    fd = os.memfd_create("op7t-hotdog-audio-metadata", flags=0)
    try:
        written = 0
        while written < len(elf):
            amount = os.write(fd, elf[written:])
            if amount <= 0:
                raise ObjdumpProbeError("Unable to write anonymous memory FD")
            written += amount
        os.lseek(fd, 0, os.SEEK_SET)
        cmd = [binary, "--disassemble", "--no-show-raw-insn",
               "/proc/self/fd/" + str(fd)]
        try:
            out = subprocess.run(cmd, capture_output=True, pass_fds=(fd,),
                                 timeout=45, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ObjdumpProbeError("ARM GNU objdump failed to finish") from exc
    finally:
        os.close(fd)
    if len(out.stdout) > MAX_DISASM_OUTPUT or len(out.stderr) > 8192:
        raise ObjdumpProbeError("GNU objdump output exceeded safe limits")
    if out.returncode:
        return {
            "status": "GNU_OBJDUMP_CANNOT_DISASSEMBLE_INPUT",
            "tool_available": True,
            "return_code": out.returncode,
            "diagnostic": out.stderr.decode("utf-8", "replace")[:1200],
        }
    return {
        "status": "DISASSEMBLY_TEXT_CANDIDATES_RECORDED",
        "tool_available": True,
        "tool_command": ["ARM GNU objdump", "--disassemble",
                         "--no-show-raw-insn", "<anonymous RAM fd>"],
        **parse_disassembly(out.stdout.decode("utf-8", "replace")),
    }


def inspect(path, llvm_objdump_path=None, gnu_objdump_path=None):
    elf = verified_audio(path)
    flavor, tool_path, tool_name = discover_disassembler(
        llvm_objdump_path, gnu_objdump_path
    )
    if flavor == "llvm":
        disassembly = run_objdump(elf, tool_path)
    elif flavor == "gnu-arm":
        disassembly = run_gnu_objdump(elf, tool_path)
    else:
        disassembly = {
            "status": "NO_ARM_DISASSEMBLER_AVAILABLE",
            "tool_available": False,
            "note": "No preinstalled supported disassembler detected; "
                    "no packages installed and no files changed.",
            "checked_binary_names": list(LLVM_CANDIDATES + GNU_CANDIDATES),
        }
    return {
        "schema": "op7t-hotdog-a2dp-disassembler-text-v3",
        "input_zip_sha256_verified": True,
        "input_elf_sha256_verified": True,
        "path_string_offset_hex": "0x1654f",
        "selected_tool_flavor": flavor,
        "selected_tool_name": tool_name,
        "disassembly": disassembly,
        "disassembly_does_not_prove_direct_code_xref": True,
        "proves_dlopen_receives_a2dp_path": False,
        "proves_runtime_loading": False,
        "binary_executed": False,
        "binary_extracted_to_disk": False,
        "flash_ready": False,
        "limitations": "LLVM reads ELF through stdin; ARM GNU through anonymous "
                       "Linux memfd. Static textual direct branch targets matching "
                       "previously confirmed PLT stubs do not establish runtime execution "
                       "or prove r0 points to A2DP. Indirect register calls, dataflow, "
                       "and nonstandard disassembler formats are not resolved.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip", type=Path)
    parser.add_argument("--llvm-objdump")
    parser.add_argument("--gnu-objdump")
    args = parser.parse_args(argv)
    try:
        result = inspect(args.zip, args.llvm_objdump, args.gnu_objdump)
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        print(f"ELF disassembly text probe FAILED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
