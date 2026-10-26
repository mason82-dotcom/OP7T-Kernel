#!/usr/bin/env python3
"""Read-only LLVM ARM32 disassembly hints for embedded audio A2DP path.

This tool verifies original ZIP and ELF SHA-256, reads only the hotdog Audio
HAL into memory, and pipes the bytes to installed llvm-objdump via stdin.
No file extraction, ELF execution, firmware change, or trusted code-reference
claim. Disassembly is evidence for expert review, not proof of runtime flow.
"""
import argparse
from collections import deque
import hashlib
import json
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
    """Collect candidate lines only; no instruction-level dataflow reconstruction."""
    candidates = []
    a2dp = 0
    loader = 0
    instruction_lines = 0
    tail = deque(maxlen=2)
    for raw in output.splitlines():
        line = raw.strip()[:MAX_LINE]
        if not ADDR.match(line):
            continue
        instruction_lines += 1
        if instruction_lines > max_lines:
            raise ObjdumpProbeError("Disassembler emitted excessive instruction lines")
        # Only look within assembler operand / comment, never match instruction's
        # own address. ARM/thumb symbolization differs between LLVM versions.
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
                "preceding_lines": list(tail),
                "disassembler_line": line,
            })
        tail.append(line)
    return {
        "instruction_lines_parsed": instruction_lines,
        "a2dp_exact_address_text_hit_count": a2dp,
        "loader_symbol_text_hit_count": loader,
        "candidate_lines": candidates,
        "candidates_capped": a2dp + loader > MAX_CANDIDATES,
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


def inspect(path, llvm_objdump_path=None):
    elf = verified_audio(path)
    if llvm_objdump_path:
        binary = Path(llvm_objdump_path)
        if not binary.is_file():
            raise ObjdumpProbeError("Specified llvm-objdump does not exist")
        exe = str(binary.resolve())
    else:
        exe = shutil.which("llvm-objdump")
    disassembly = run_objdump(elf, exe)
    return {
        "schema": "op7t-hotdog-a2dp-llvm-objdump-text-v1",
        "input_zip_sha256_verified": True,
        "input_elf_sha256_verified": True,
        "path_string_offset_hex": "0x1654f",
        "disassembly": disassembly,
        "disassembly_does_not_prove_direct_code_xref": True,
        "proves_dlopen_receives_a2dp_path": False,
        "proves_runtime_loading": False,
        "binary_executed": False,
        "binary_extracted_to_disk": False,
        "flash_ready": False,
        "limitations": "llvm-objdump consumes ELF via stdin, not executed. Full ARM/Thumb control-flow, PC-relative calculations, GOT and indirect loads are NOT resolved. Text hits may be false positives; zero hits do not disprove dynamic A2DP use."
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip", type=Path)
    parser.add_argument("--llvm-objdump")
    args = parser.parse_args(argv)
    try:
        result = inspect(args.zip, args.llvm_objdump)
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        print(f"ELF disassembly text probe FAILED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
