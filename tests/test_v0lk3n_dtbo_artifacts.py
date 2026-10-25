"""Regression gates for V0lk3n-only DTBO capture and artifact validation."""
import runpy
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = runpy.run_path(str(ROOT / "scripts/audit-artifacts.py"))
collect_dtbo_files = AUDIT["collect_dtbo_files"]


class V0lk3nDTBOTests(unittest.TestCase):
    def test_missing_dtbos_fail_for_v0lk3n_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(collect_dtbo_files(root, False), [])
            with self.assertRaisesRegex(ValueError, "no captured DTBO"):
                collect_dtbo_files(root, True)

    def test_valid_dtbo_header_and_corruption_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file = root / "dtbos" / "arch/arm64/boot/dts/19801/hotdog.dtbo"
            file.parent.mkdir(parents=True)
            file.write_bytes(bytes.fromhex("d00dfeed") + (40).to_bytes(4, "big") + b"\\0" * 32)
            self.assertEqual(collect_dtbo_files(root, True), [file])
            file.write_bytes(bytes.fromhex("d00dfeed") + (400).to_bytes(4, "big") + b"\\0" * 32)
            with self.assertRaisesRegex(ValueError, "Invalid DTBO"):
                collect_dtbo_files(root, True)
            file.write_bytes(b"not-an-fdt" + b"\\0" * 40)
            with self.assertRaisesRegex(ValueError, "Invalid DTBO"):
                collect_dtbo_files(root, True)

    def test_build_captures_real_overlays_and_enforces_requirement(self):
        build = (ROOT / "scripts/build.sh").read_text()
        audit = (ROOT / "scripts/audit-artifacts.py").read_text()
        self.assertIn("-name '*.dtbo' -print0", build)
        self.assertIn('"$ART/dtbos/$relative"', build)
        self.assertIn("--require-dtbo", build)
        self.assertIn('"dtbo_count": len(dtbos)', audit)
        self.assertIn('"dtbo_required": require_dtbo', audit)
        self.assertIn('"flash_ready": False', audit)


if __name__ == "__main__":
    unittest.main()
