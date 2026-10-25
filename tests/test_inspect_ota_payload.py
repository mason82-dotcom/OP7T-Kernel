import importlib.util
import json
import struct
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from zipfile import ZipFile

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "inspect-ota-payload.py"
SPEC = importlib.util.spec_from_file_location("inspect_payload", SCRIPT)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def vi(number):
    result = bytearray()
    while number >= 128:
        result.append((number & 127) | 128)
        number >>= 7
    result.append(number)
    return bytes(result)


def length_field(field, content):
    return vi(field << 3 | 2) + vi(len(content)) + content


def number_field(field, value):
    return vi(field << 3) + vi(value)


def payload(names, minor=0, partial=False, emit_partial=True):
    manifest = number_field(12, minor)
    if emit_partial:
        manifest += number_field(16, int(partial))
    for name in names:
        partition = length_field(1, name.encode("ascii"))
        manifest += length_field(13, partition)
    return struct.pack(">4sQQI", b"CrAU", 2, len(manifest), 0) + manifest + b"blobs"


class PayloadInventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "crdroid-ota.zip"

    def zip(self, content=None, entries=None):
        with ZipFile(self.path, "w") as z:
            if entries is None:
                z.writestr("payload.bin", content if content is not None else payload(["boot", "dtbo", "vendor_dlkm"]))
            else:
                for name, data in entries:
                    z.writestr(name, data)
        return self.path

    def test_full_payload_partitions_are_evidence_not_installed_proof(self):
        result = MOD.inspect(self.zip(payload(["boot", "dtbo", "vendor_dlkm"])))
        self.assertEqual(["boot", "dtbo", "vendor_dlkm"], result["partition_names"])
        self.assertTrue(result["requested_partition_names_present"]["vendor_dlkm"])
        self.assertTrue(result["full_payload_confirmed"])
        self.assertFalse(result["exact_installed_rom_provenance_verified"])
        self.assertFalse(result["flash_ready"])

    def test_omitted_optional_partial_update_defaults_to_false(self):
        # Real hotdog October 2026 OTA: minor=0, no field 16 in the manifest.
        # Proto2 treats absent optional bool as false; don't mistake that
        # for proof that these images are installed on the phone.
        result = MOD.inspect(self.zip(payload(
            ["LOGO", "boot", "dtbo", "vendor_dlkm"], emit_partial=False
        )))
        self.assertIsNone(result["partial_update_declared"])
        self.assertEqual(0, result["payload_minor_version"])
        self.assertTrue(result["full_payload_confirmed"])
        self.assertFalse(result["all_installed_partitions_enumerated"])
        self.assertFalse(result["exact_installed_rom_provenance_verified"])
        self.assertFalse(result["flash_ready"])

    def test_omitted_partial_update_with_delta_minor_not_full(self):
        result = MOD.inspect(self.zip(payload(
            ["boot"], minor=4, emit_partial=False
        )))
        self.assertIsNone(result["partial_update_declared"])
        self.assertFalse(result["full_payload_confirmed"])

    def test_delta_payload_never_claims_full(self):
        result = MOD.inspect(self.zip(payload(["boot"], minor=4)))
        self.assertFalse(result["full_payload_confirmed"])
        self.assertFalse(result["requested_partition_names_present"]["vendor_dlkm"])
        self.assertFalse(result["all_installed_partitions_enumerated"])

    def test_partial_payload_never_claims_full(self):
        result = MOD.inspect(self.zip(payload(["vendor"], partial=True)))
        self.assertTrue(result["partial_update_declared"])
        self.assertFalse(result["full_payload_confirmed"])

    def test_wrong_header_magic_fails(self):
        broken = bytearray(payload(["boot"]))
        broken[:4] = b"BAD!"
        with self.assertRaisesRegex(MOD.PayloadError, "CrAU"):
            MOD.inspect(self.zip(broken))

    def test_excessive_manifest_length_rejected_without_reading_content(self):
        broken = bytearray(payload(["boot"]))
        broken[12:20] = (MOD.MAX_MANIFEST_BYTES + 1).to_bytes(8, "big")
        with self.assertRaisesRegex(MOD.PayloadError, "bounded"):
            MOD.inspect(self.zip(broken))

    def test_duplicate_partition_name_rejected(self):
        with self.assertRaisesRegex(MOD.PayloadError, "duplicate"):
            MOD.inspect(self.zip(payload(["boot", "boot"])))

    def test_invalid_partition_names_fail_closed(self):
        with self.assertRaisesRegex(MOD.PayloadError, "invalid"):
            MOD.inspect(self.zip(payload(["../vendor_dlkm"])))

    def test_update_engine_platform_specific_safe_names(self):
        # Android's required PartitionUpdate.partition_name is not limited
        # to lowercase-starting Linux path components.
        names = ["0boot", "LOGO", "xbl-config", "vendor_dlkm", "modem.1",
                 "modem+firmware", "_firmware"]
        report = MOD.inspect(self.zip(payload(names)))
        self.assertEqual(sorted(names), report["partition_names"])
        self.assertTrue(report["requested_partition_names_present"]["vendor_dlkm"])
        self.assertFalse(report["flash_ready"])

    def test_partition_names_reject_path_traversal_and_controls(self):
        for name in ("/vendor", "../vendor_dlkm", "vendor/other", "a..b",
                     "vendor.", "vendor\\\\name", "vendor:name", "name space",
                     "a" * 65, "vendor\\nname", ""):
            with self.subTest(name=name):
                with self.assertRaisesRegex(MOD.PayloadError, "invalid"):
                    MOD.inspect(self.zip(payload([name])))

    def test_rejected_partitions_show_bounded_diagnostic(self):
        with self.assertRaisesRegex(
                MOD.PayloadError, "Unsafe or invalid partition name: 'vendor/other'"):
            MOD.inspect(self.zip(payload(["vendor/other"])))

    def test_duplicate_zip_payload_bin_fails(self):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            self.zip(entries=[("payload.bin", payload(["boot"])), ("payload.bin", payload(["dtbo"]))])
        with self.assertRaisesRegex(MOD.PayloadError, "exactly one"):
            MOD.inspect(self.path)

    def test_truncated_protobuf_fails(self):
        data = b"\x6a\x05\x0a"
        broken = struct.pack(">4sQQI", b"CrAU", 2, len(data), 0) + data
        with self.assertRaises(MOD.PayloadError):
            MOD.inspect(self.zip(broken))

    def test_missing_payload_member_fails(self):
        with self.assertRaisesRegex(MOD.PayloadError, "payload.bin"):
            MOD.inspect(self.zip(entries=[("metadata", b"abc")]))

    def test_cli_emits_safe_json(self):
        self.zip()
        buf = StringIO()
        with redirect_stdout(buf):
            code = MOD.main([str(self.path)])
        self.assertEqual(0, code)
        record = json.loads(buf.getvalue())
        self.assertFalse(record["ota_zip_sha256_verified"])
        self.assertFalse(record["flash_ready"])

    def test_unknown_protobuf_fields_are_ignored(self):
        content = payload(["boot"])
        hdr, manifest = content[:24], content[24:-5]
        manifest += length_field(30, b"opaque")
        new = struct.pack(">4sQQI", b"CrAU", 2, len(manifest), 0) + manifest
        result = MOD.inspect(self.zip(new))
        self.assertIn("boot", result["partition_names"])


if __name__ == "__main__":
    unittest.main()
