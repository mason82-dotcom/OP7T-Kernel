"""Synthetic, offline checks for the pinned hotdog/common ODM audio link audit."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "hotdog_common_audio", REPO / "scripts/audit-hotdog-common-audio.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
WRAPPER = "proprietary_vendor_oneplus_hotdog-17.0/"


class CrossTreeAudioTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.zip = self.root / "hotdog.zip"
        self.common = self.root / "common"
        self.common.mkdir()
        self.reference = self.root / "reference.json"
        self.common_bp = b"""soong_namespace {}
cc_prebuilt_library_shared {
 name: "liba2dpoffload_odm",
 stem: "liba2dpoffload",
 target: { android_arm: { srcs: [
   "proprietary/odm/lib/liba2dpoffload.so",
 ] } },
 compile_multilib: "32",
 device_specific: true,
}
"""
        self.hotdog_bp = b"""soong_namespace {}
cc_prebuilt_library_shared {
 name: "audio.primary.msmnile_odm",
 stem: "audio.primary.msmnile",
 target: { android_arm: {
  srcs: ["proprietary/odm/lib/hw/audio.primary.msmnile.so"],
 } },
 compile_multilib: "32",
 relative_install_path: "hw",
 device_specific: true,
}
"""
        self.hotdog_mk = b"PRODUCT_PACKAGES += audio.primary.msmnile_odm\n"
        self.common_mk = b"PRODUCT_PACKAGES += liba2dpoffload_odm\n"
        self.make()

    def make(self, hotdog_bp=None, common_bp=None, hotdog_mk=None,
             common_mk=None, blob_present=True):
        texts = {
            "Android.bp": self.common_bp if common_bp is None else common_bp,
            "sm8150-common-vendor.mk": self.common_mk if common_mk is None else common_mk,
            "BoardConfigVendor.mk": b"# generated\n",
        }
        hashes = {}
        for name, data in texts.items():
            (self.common / name).write_bytes(data)
            hashes[name] = mod.git_blob_sha(data)
        ref = {
            "schema": "op7t-sm8150-common-vendor-reference-v1",
            "branch": "17.0",
            "branch_commit_observed_2026_10_26":
                "6586000353465cc53b42189be056d5c037e14ef9",
            "verified_build_file_git_blob_shas": hashes,
        }
        self.reference.write_text(json.dumps(ref), encoding="utf-8")
        with zipfile.ZipFile(self.zip, "w") as z:
            z.writestr(WRAPPER + "Android.bp",
                       self.hotdog_bp if hotdog_bp is None else hotdog_bp)
            z.writestr(WRAPPER + "hotdog-vendor.mk",
                       self.hotdog_mk if hotdog_mk is None else hotdog_mk)
            if blob_present:
                z.writestr(
                    WRAPPER + "proprietary/odm/lib/hw/audio.primary.msmnile.so",
                    b"NOT_EXECUTABLE_TEST_BLOB"
                )

    def audit(self):
        return mod.inspect(self.zip, self.common, self.reference)

    def test_positive_exact_metadata_alignment(self):
        report = self.audit()
        self.assertEqual(report["status"], "STATIC_AUDIO_SOURCE_CHAIN_ALIGNS")
        self.assertEqual(report["checks_satisfied"], report["checks_total"])
        self.assertFalse(report["elf_dt_needed_verified"])
        self.assertFalse(report["common_vendor_blob_file_existence_verified"])
        self.assertFalse(report["flash_ready"])
        self.assertNotIn("NOT_EXECUTABLE_TEST_BLOB", str(report))

    def test_missing_hotdog_source_detected(self):
        self.make(blob_present=False)
        report = self.audit()
        self.assertEqual(report["status"], "STATIC_AUDIO_SOURCE_CHAIN_GAPS")
        self.assertFalse(report["checks"]["hotdog_audio_src_zip_filename_present"])

    def test_bad_common_git_blob_hash_rejected(self):
        (self.common / "Android.bp").write_bytes(b"tampered\n")
        with self.assertRaises(mod.AudioLinkAuditError):
            self.audit()

    def test_wrong_common_multilib_flag_is_gap(self):
        self.make(common_bp=self.common_bp.replace(b'"32"', b'"64"'))
        report = self.audit()
        self.assertEqual(report["status"], "STATIC_AUDIO_SOURCE_CHAIN_GAPS")
        self.assertFalse(report["checks"]["common_module_32bit"])

    def test_expected_zip_sha256_rejected_if_mismatch(self):
        with self.assertRaises(mod.AudioLinkAuditError):
            mod.inspect(self.zip, self.common, self.reference, "0" * 64)

    def test_comment_and_string_brace_ignored(self):
        bp = self.hotdog_bp.replace(
            b' name: "audio.primary.msmnile_odm",',
            b' // fake name: "wrong", and } brace\n'
            b' name: "audio.primary.msmnile_odm",\n'
            b' strip: { none: true },'
        )
        self.make(hotdog_bp=bp)
        self.assertEqual(self.audit()["status"], "STATIC_AUDIO_SOURCE_CHAIN_ALIGNS")

    def test_archive_path_traversal_rejected(self):
        with zipfile.ZipFile(self.zip, "a") as z:
            z.writestr(WRAPPER + "../evil.txt", "x")
        with self.assertRaises(mod.AudioLinkAuditError):
            self.audit()


if __name__ == "__main__":
    unittest.main()
