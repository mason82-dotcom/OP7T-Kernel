import hashlib
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify-build-module-cms.py"
SPEC = importlib.util.spec_from_file_location("cms_verify", SCRIPT)
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


def run(*args):
    subprocess.run(args, check=True, capture_output=True)


class CmsTests(unittest.TestCase):
    def test_build_exports_only_public_certificate_and_verifies_before_checksums(self):
        script = (SCRIPT.parent / "build.sh").read_text()
        self.assertIn('install -m 0644 "$PUBCERT" "$ART/signing-cert.x509"', script)
        self.assertIn('"${SIGNED_MODULES[@]}" > "$ART/build-module-cms.json"', script)
        self.assertLess(script.index("verify-build-module-cms.py"), script.index("find . -type f ! -name SHA256SUMS"))
        self.assertNotIn('cp "$OUT/certs/signing_key.pem"', script)

    def make_signed_module(self, root):
        key, pem, der = (root / name for name in ("private.pem", "public.pem", "public.x509"))
        run("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-subj", "/CN=synthetic test key/", "-days", "1", "-keyout", str(key),
            "-out", str(pem))
        run("openssl", "x509", "-in", str(pem), "-outform", "DER", "-out", str(der))
        (root / "signing-cert.sha256").write_text(hashlib.sha256(der.read_bytes()).hexdigest() + "\n")
        (root / "payload").write_bytes(b"Synthetic AArch64 module bytes, not executable")
        run("openssl", "cms", "-sign", "-binary", "-noattr", "-nocerts",
            "-nosmimecap", "-md", "sha512", "-in", str(root / "payload"),
            "-signer", str(pem), "-inkey", str(key), "-outform", "DER",
            "-out", str(root / "signature.der"))
        cms = (root / "signature.der").read_bytes()
        module = root / "module.ko"
        module.write_bytes((root / "payload").read_bytes() + cms +
                           bytes((0, 0, 2, 0, 0, 0, 0, 0)) + len(cms).to_bytes(4, "big") + VERIFY.MAGIC)
        return module, der, root / "signing-cert.sha256"

    def test_detached_signature_verifies_with_pinned_public_certificate(self):
        with tempfile.TemporaryDirectory() as directory:
            module, der, fingerprint = self.make_signed_module(Path(directory))
            pem, _ = VERIFY.certificate(der, fingerprint)
            self.assertTrue(VERIFY.verify(module, pem)["cms_signature_verified"])
            raw = bytearray(module.read_bytes())
            raw[4] ^= 1
            module.write_bytes(raw)
            with self.assertRaisesRegex(VERIFY.VerificationError, "does not verify"):
                VERIFY.verify(module, pem)

    def test_changed_certificate_fingerprint_and_bad_footer_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            module, der, fingerprint = self.make_signed_module(Path(directory))
            fingerprint.write_text("0" * 64 + "\n")
            with self.assertRaisesRegex(VERIFY.VerificationError, "fingerprint mismatch"):
                VERIFY.certificate(der, fingerprint)
            module.write_bytes(module.read_bytes()[:-1] + b"X")
            with self.assertRaisesRegex(VERIFY.VerificationError, "footer"):
                VERIFY.split_module(module.read_bytes())


if __name__ == "__main__":
    unittest.main()
