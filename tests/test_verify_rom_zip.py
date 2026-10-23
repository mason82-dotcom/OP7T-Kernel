import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify-rom-zip.py"
SPEC = importlib.util.spec_from_file_location("rom_zip", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RomZipTests(unittest.TestCase):
    def fixture(self, root):
        archive = root / "crDroidAndroid-17.0-20261021-hotdog-v13.0.zip"
        with ZipFile(archive, "w") as z:
            z.writestr("payload.bin", b"mock-payload")
            z.writestr("payload_properties.txt", "FILE_HASH=mock")
        reference = {
            "schema": "op7t-crdroid-ota-reference-v1",
            "device": "hotdog",
            "crdroid_major": 13,
            "android_major": 17,
            "filename": archive.name,
            "size_bytes": archive.stat().st_size,
            "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        }
        manifest = root / "manifest.json"
        manifest.write_text(json.dumps(reference))
        return archive, manifest

    def test_exact_zip_never_claims_flash_compatibility(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive, reference = self.fixture(Path(tmp))
            output = MODULE.verify(archive, reference)
            self.assertTrue(output["sha256_verified"])
            self.assertTrue(output["has_payload_bin"])
            self.assertFalse(output["installed_rom_verified"])
            self.assertFalse(output["flash_ready"])

    def test_tampered_zip_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive, reference = self.fixture(Path(tmp))
            archive.write_bytes(archive.read_bytes() + b"tampering")
            with self.assertRaisesRegex(ValueError, "size"):
                MODULE.verify(archive, reference)

    def test_wrong_device_reference_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive, reference = self.fixture(Path(tmp))
            manifest = json.loads(reference.read_text())
            manifest["device"] = "hotdogg"
            reference.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "wrong device"):
                MODULE.verify(archive, reference)


if __name__ == "__main__":
    unittest.main()
