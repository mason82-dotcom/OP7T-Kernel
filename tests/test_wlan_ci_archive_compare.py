"""Host-only ZIP intake regressions; no actual phone, kernel or binaries."""
import hashlib
import importlib.util
import json
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "hotdog_ci_archive_test", ROOT / "scripts/compare-wlan-ci-archive-to-rom.py"
)
MOD = importlib.util.module_from_spec(spec)
spec.loader.exec_module(MOD)
RELEASE = "4.14.357-perf-g57037290bb57-dirty"
WLAN_SHA = "a" * 64
MAP_SHA = "b" * 64


class ArchiveComparisonTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name)
        self.archive = self.dir / "ci.zip"
        self.original = self.dir / "qca_cld3_wlan.ko"
        self.original.write_bytes(b"fixture-no-real-elf")
        self.orig_sha = hashlib.sha256(self.original.read_bytes()).hexdigest()

    def inputs(self):
        doc = {
            "kernel.config": b"CONFIG_MODULES=y\n",
            "upstream-commit.txt": (MOD.ROM_SHA + "\n").encode(),
            "kernel.release": (RELEASE + "\n").encode(),
            "toolchain-report.json": b"{}",
            "wlan-rom-source-parity.json": b"{}",
        }
        doc["artifact-report.json"] = json.dumps({
            "schema": "op7t-kernel-artifact-report-v1", "device": "hotdog",
            "profile": "core", "upstream_commit": MOD.ROM_SHA,
            "module_signature_enforcement": True, "flash_ready": False,
            "kernel_release": RELEASE,
            "modules": [{"path": "modules/drivers/staging/qcacld-3.0/wlan.ko",
                         "sha256": WLAN_SHA, "has_embedded_signature": True}],
        }).encode()
        doc["wlan-patch-experiment.json"] = json.dumps({
            "schema": "hotdog-wlan-icnss-compile-attestation-v4",
            "upstream_sha": MOD.ROM_SHA, "flash_ready": False,
            "wlan_module": {"sha256": WLAN_SHA,
                            "vermagic": RELEASE + " SMP preempt modversions aarch64",
                            "signed_and_stripped": True},
        }).encode()
        doc["built-wlan-self-crc-report.json"] = json.dumps({
            "schema": "hotdog-built-wlan-self-crc-v1",
            "kernel_release": RELEASE, "flash_ready": False,
            "built_kernel_module_self_consistency": True,
        }).encode()
        doc["built-wlan-import-crcs.json"] = json.dumps({
            "schema": "hotdog-wlan-built-import-crc-map-v1",
            "kernel_release": RELEASE, "flash_ready": False,
        }).encode()
        self.assertEqual(set(doc), MOD.ALLOWED)
        return doc

    def pack(self, files=None):
        with zipfile.ZipFile(self.archive, "w", zipfile.ZIP_DEFLATED) as z:
            for name, content in (self.inputs() if files is None else files).items():
                z.writestr(name, content)
        return hashlib.sha256(self.archive.read_bytes()).hexdigest()

    def fake_result(self):
        return {
            "original_crc_map_sha256": MAP_SHA,
            "blockers": ["vermagic_mismatch"],
            "flash_ready": False,
            "installed_ROM_provenance_verified": False,
        }

    def test_pinned_archive_can_be_compared_read_only(self):
        digest = self.pack()
        with patch.object(MOD.COMP, "compare", return_value=self.fake_result()) as compare:
            outcome = MOD.compare_archive(
                self.archive, digest, self.original, self.orig_sha, MAP_SHA
            )
        self.assertEqual(1, compare.call_count)
        self.assertEqual(digest, outcome["ci_artifact_zip_sha256"])
        self.assertTrue(outcome["ci_metadata_archive_verified_against_operator_digest"])
        self.assertFalse(outcome["flash_ready"])

    def test_wrong_zip_hash_refuses_input_before_compare(self):
        self.pack()
        with patch.object(MOD.COMP, "compare") as compare:
            with self.assertRaisesRegex(MOD.ArchiveAuditError, "SHA-256 differs"):
                MOD.compare_archive(self.archive, "0" * 64, self.original, self.orig_sha, MAP_SHA)
            compare.assert_not_called()

    def test_duplicate_and_unexpected_zip_names_rejected(self):
        for bad in ("duplicate", "traversal"):
            with self.subTest(bad=bad):
                doc = self.inputs()
                with zipfile.ZipFile(self.archive, "w") as z:
                    for name, value in doc.items():
                        z.writestr(name, value)
                    z.writestr("kernel.release" if bad == "duplicate"
                               else "../artifacts/private", b"bad")
                digest = hashlib.sha256(self.archive.read_bytes()).hexdigest()
                with self.assertRaisesRegex(MOD.ArchiveAuditError, "duplicate or absent"):
                    MOD.validate_zip(self.archive, digest)

    def test_zip_symlink_member_refused(self):
        with zipfile.ZipFile(self.archive, "w") as z:
            for name, value in self.inputs().items():
                member = zipfile.ZipInfo(name)
                if name == "kernel.release":
                    member.create_system = 3
                    member.external_attr = (stat.S_IFLNK | 0o777) << 16
                z.writestr(member, value)
        digest = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        with self.assertRaisesRegex(MOD.ArchiveAuditError, "Unsafe"):
            MOD.validate_zip(self.archive, digest)

    def test_conflicting_kernel_release_refused(self):
        doc = self.inputs()
        doc["kernel.release"] = b"4.14.357-perf-g1083c6c59061\n"
        digest = self.pack(doc)
        with self.assertRaisesRegex(MOD.ArchiveAuditError, "attestations conflict"):
            MOD.validate_zip(self.archive, digest)

    def test_unsigned_module_metadata_refused(self):
        doc = self.inputs()
        report = json.loads(doc["artifact-report.json"])
        report["modules"][0]["has_embedded_signature"] = False
        doc["artifact-report.json"] = json.dumps(report).encode()
        digest = self.pack(doc)
        with self.assertRaisesRegex(MOD.ArchiveAuditError, "attestations conflict"):
            MOD.validate_zip(self.archive, digest)

    def test_original_crc_digest_must_match_independent_record(self):
        digest = self.pack()
        with patch.object(MOD.COMP, "compare", return_value=self.fake_result()):
            with self.assertRaisesRegex(MOD.ArchiveAuditError, "map differs"):
                MOD.compare_archive(self.archive, digest, self.original, self.orig_sha, "c" * 64)

    def test_cli_has_no_success_exit_even_when_no_blocker(self):
        doc = self.fake_result()
        doc["blockers"] = []
        digest = self.pack()
        argv = [
            "--ci-zip", str(self.archive), "--ci-zip-sha256", digest,
            "--original-rom-wlan", str(self.original),
            "--original-rom-sha256", self.orig_sha,
            "--original-rom-crc-map-sha256", MAP_SHA,
        ]
        with patch.object(MOD.COMP, "compare", return_value=doc):
            with patch("builtins.print"):
                self.assertEqual(4, MOD.main(argv))

    def test_zip_size_bomb_refused_before_decompression(self):
        doc = self.inputs()
        doc["kernel.config"] = b"A" * (MOD.MAX_MEMBER + 1)
        digest = self.pack(doc)
        with self.assertRaisesRegex(MOD.ArchiveAuditError, "oversized"):
            MOD.validate_zip(self.archive, digest)


if __name__ == "__main__":
    unittest.main()
