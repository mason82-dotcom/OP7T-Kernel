"""Offline safety and parsing tests for the optional LLVM text disassembly probe."""
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "a2dp_llvm_text", ROOT / "scripts/audit-hotdog-a2dp-llvm-objdump.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class A2DPLlvmTextTests(unittest.TestCase):
    def test_detect_a2dp_text_and_symbol_mentions(self):
        text = """audio.so:\n
00001000 <foo>:
    1000: movw r0, #0x654f
    1004: bl 0x1654f <target>
    1008: bl 0x3000 <dlopen@plt>
    100c: bl 0x3020 <dlsym@plt>
"""
        r = mod.parse_disassembly(text)
        self.assertEqual(r["instruction_lines_parsed"], 4)
        self.assertEqual(r["a2dp_exact_address_text_hit_count"], 1)
        self.assertEqual(r["loader_symbol_text_hit_count"], 2)
        self.assertEqual(len(r["candidate_lines"]), 3)
        self.assertEqual(r["candidate_lines"][0]["instruction_vaddr"], "1004")

    def test_own_instruction_address_not_counted_as_literal_ref(self):
        result = mod.parse_disassembly("    1654f: bx lr\n")
        self.assertEqual(result["a2dp_exact_address_text_hit_count"], 0)

    def test_disassembler_missing_no_fake_provenance(self):
        r = mod.run_objdump(b"ELF is not executed", None)
        self.assertEqual(r["status"], "LLVM_OBJDUMP_NOT_INSTALLED")
        self.assertFalse(r["tool_available"])

    def test_subprocess_reads_stdin_and_does_not_execute_elf(self):
        mock_result = SimpleNamespace(
            stdout=b"   1234: bl 0x4321 <dlopen@plt>\n",
            stderr=b"", returncode=0
        )
        with patch.object(mod.subprocess, "run", return_value=mock_result) as runner:
            out = mod.run_objdump(b"FAKE_AUDIO_BYTES", "/usr/bin/llvm-objdump")
        args, kwargs = runner.call_args
        self.assertEqual(args[0][-1], "-")
        self.assertEqual(kwargs["input"], b"FAKE_AUDIO_BYTES")
        self.assertEqual(out["loader_symbol_text_hit_count"], 1)

    def test_nonzero_disassembler_exit_is_not_success(self):
        with patch.object(mod.subprocess, "run", return_value=SimpleNamespace(
            stdout=b"", stderr=b"unknown format", returncode=1
        )):
            r = mod.run_objdump(b"fake", "/usr/bin/llvm-objdump")
        self.assertEqual(r["status"], "LLVM_OBJDUMP_CANNOT_DISASSEMBLE_INPUT")

    def test_excess_disassembly_text_rejected(self):
        with patch.object(mod.subprocess, "run", return_value=SimpleNamespace(
            stdout=b"x" * (mod.MAX_DISASM_OUTPUT + 1), stderr=b"", returncode=0
        )):
            with self.assertRaises(mod.ObjdumpProbeError):
                mod.run_objdump(b"fake", "/usr/bin/llvm-objdump")

    def test_excess_instruction_lines_rejected(self):
        with self.assertRaises(mod.ObjdumpProbeError):
            mod.parse_disassembly("1000: nop\n1004: nop\n", max_lines=1)

    def test_path_not_in_test_data_is_not_treated_as_reference(self):
        text = "1000: mov r0, #0x654f\n1004: bl 0x4560 <foo>\n"
        r = mod.parse_disassembly(text)
        self.assertEqual(r["a2dp_exact_address_text_hit_count"], 0)
        self.assertEqual(r["loader_symbol_text_hit_count"], 0)


    def test_exact_dlopen_dlsym_direct_branch_targets(self):
        output = """\
     9000: mov r0, r4
     9004: bl b12a0 <audio_load_a2dp_stub>
     9008: blx 0xb12b0 <audio_sym_stub>
     900c: bl b12a0
     9010: bx r3
"""
        result = mod.parse_disassembly(output)
        dl = result["direct_plt_branch_targets"]["dlopen"]
        sym = result["direct_plt_branch_targets"]["dlsym"]
        self.assertEqual(dl["direct_branch_text_hits"], 2)
        self.assertEqual(sym["direct_branch_text_hits"], 1)
        self.assertEqual(dl["target_vaddr_hex"], "0xb12a0")
        self.assertEqual(dl["caller_samples"][0]["instruction_vaddr_hex"], "0x9004")
        self.assertEqual(dl["caller_samples"][0]["preceding_disassembly_lines"][-1],
                         "9000: mov r0, r4")
        self.assertFalse(dl["r0_a2dp_path_argument_verified"])

    def test_direct_branch_only_not_embedded_hex_or_other_address(self):
        output = """\
    b12a0: bx lr
    9000: bl 0xb12a1
    9004: movw r1, #0xb12a0
    9008: blx r3
    900c: bl 0xb12a000
    9010: bl b12a0
"""
        result = mod.parse_disassembly(output)
        self.assertEqual(result["direct_plt_branch_targets"]["dlopen"]
                         ["direct_branch_text_hits"], 1)

    def test_gnu_branch_suffix_variants(self):
        output = """\
     9000: bl.w 000b12a0 <stub>
     9004: b.w 000b12b0 <tail_stub>
     9008: blx 0x000b12b0
"""
        result = mod.parse_disassembly(output)
        self.assertEqual(result["direct_plt_branch_targets"]["dlopen"]
                         ["direct_branch_text_hits"], 1)
        self.assertEqual(result["direct_plt_branch_targets"]["dlsym"]
                         ["direct_branch_text_hits"], 2)

    def test_discover_versioned_llvm19_in_path(self):
        with patch.object(mod.shutil, "which", side_effect=lambda name:
                          "/usr/bin/llvm-objdump-19" if name == "llvm-objdump-19" else None):
            flavor, path, label = mod.discover_disassembler()
        self.assertEqual(flavor, "llvm")
        self.assertEqual(path, "/usr/bin/llvm-objdump-19")
        self.assertEqual(label, "llvm-objdump-19")

    def test_discover_arm_gnu_when_llvm_absent(self):
        with patch.object(mod.shutil, "which", side_effect=lambda name:
                          "/usr/bin/arm-linux-gnueabi-objdump"
                          if name == "arm-linux-gnueabi-objdump" else None):
            flavor, path, label = mod.discover_disassembler()
        self.assertEqual(flavor, "gnu-arm")
        self.assertEqual(label, "arm-linux-gnueabi-objdump")

    @unittest.skipUnless(hasattr(os, "memfd_create") and
                         Path("/proc/self/fd").is_dir(), "Requires Linux anonymous memfd")
    def test_gnu_objdump_reads_only_ram_fd(self):
        observed = {}
        def fake_objdump(command, **kw):
            self.assertEqual(command[-2], "--no-show-raw-insn")
            self.assertTrue(command[-1].startswith("/proc/self/fd/"))
            fd = kw["pass_fds"][0]
            self.assertEqual(command[-1], f"/proc/self/fd/{fd}")
            self.assertEqual(kw["timeout"], 45)
            os.lseek(fd, 0, os.SEEK_SET)
            observed["input"] = os.read(fd, 1024)
            return SimpleNamespace(
                stdout=b" 1004: bl 0x3000 <dlopen@plt>\n",
                stderr=b"", returncode=0
            )
        with patch.object(mod.subprocess, "run", side_effect=fake_objdump):
            result = mod.run_gnu_objdump(b"RAM_ONLY_TEST_ELF_BYTES", "/usr/bin/arm-linux-gnueabi-objdump")
        self.assertEqual(observed["input"], b"RAM_ONLY_TEST_ELF_BYTES")
        self.assertEqual(result["status"], "DISASSEMBLY_TEXT_CANDIDATES_RECORDED")
        self.assertEqual(result["loader_symbol_text_hit_count"], 1)

    def test_missing_all_disassemblers_no_install(self):
        with patch.object(mod, "verified_audio", return_value=b"test data"):
            with patch.object(mod, "discover_disassembler", return_value=(None, None, None)):
                result = mod.inspect(Path("fake.zip"))
        self.assertEqual(result["disassembly"]["status"], "NO_ARM_DISASSEMBLER_AVAILABLE")
        self.assertFalse(result["binary_extracted_to_disk"])
        self.assertFalse(result["flash_ready"])

    def test_both_tool_overrides_rejected(self):
        with self.assertRaises(mod.ObjdumpProbeError):
            mod.discover_disassembler("/usr/bin/llvm-objdump",
                                     "/usr/bin/arm-linux-gnueabi-objdump")

    @unittest.skipUnless(hasattr(os, "memfd_create") and
                         Path("/proc/self/fd").is_dir(), "Requires Linux anonymous memfd")
    def test_gnu_objdump_failure_does_not_fake_disassembly(self):
        with patch.object(mod.subprocess, "run", return_value=SimpleNamespace(
            stdout=b"", stderr=b"unrecognized ELF target", returncode=1
        )):
            out = mod.run_gnu_objdump(b"not-an-ELF", "/usr/bin/arm-linux-gnueabi-objdump")
        self.assertEqual(out["status"], "GNU_OBJDUMP_CANNOT_DISASSEMBLE_INPUT")



if __name__ == "__main__":
    unittest.main()
