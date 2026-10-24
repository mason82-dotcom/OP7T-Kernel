#!/usr/bin/env python3
"""Verify Kbuild's detached module CMS signatures against one PUBLIC build certificate.

This proves only that the provided modules were signed by this certificate. It
does not prove that the installed phone trusts the certificate or accepts ABI.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

MAGIC = b"~Module signature appended~\n"
MAX_MODULE = 96 * 1024 * 1024
MAX_CERT = 64 * 1024
MAX_SIGNATURE = 64 * 1024


class VerificationError(ValueError):
    pass


def certificate(path, fingerprint_path):
    raw = path.read_bytes()
    if not raw or len(raw) > MAX_CERT or not raw.startswith(b"\x30"):
        raise VerificationError("Expected bounded DER X.509 public certificate")
    expected = fingerprint_path.read_text(encoding="ascii").strip()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise VerificationError("Invalid public certificate SHA-256 fingerprint")
    if hashlib.sha256(raw).hexdigest() != expected:
        raise VerificationError("Public certificate fingerprint mismatch")
    try:
        result = subprocess.run(
            ["openssl", "x509", "-inform", "DER", "-in", str(path), "-outform", "PEM"],
            capture_output=True, check=True, timeout=15,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise VerificationError("Invalid public X.509 certificate") from error
    return result.stdout, expected


def split_module(raw):
    if not raw.endswith(MAGIC) or len(raw) <= len(MAGIC) + 12:
        raise VerificationError("Missing module signature footer")
    footer_start = len(raw) - len(MAGIC) - 12
    footer = raw[footer_start:footer_start + 12]
    # Linux 4.14 scripts/sign-file.c emits PKCS#7 (type 2), without signer or
    # key ID fields; the 32-bit CMS length is network byte order.
    if footer[:2] != b"\x00\x00" or footer[2] != 2 or footer[3:8] != b"\x00" * 5:
        raise VerificationError("Unexpected Linux module signature footer")
    sig_len = int.from_bytes(footer[8:12], "big")
    if not 0 < sig_len <= MAX_SIGNATURE or sig_len > footer_start:
        raise VerificationError("Invalid module CMS length")
    start = footer_start - sig_len
    return raw[:start], raw[start:footer_start]


def verify(module_path, cert_pem):
    if not module_path.is_file() or not 0 < module_path.stat().st_size <= MAX_MODULE:
        raise VerificationError("Module missing, empty or too large")
    raw = module_path.read_bytes()
    payload, cms = split_module(raw)
    with tempfile.TemporaryDirectory(prefix="op7t-cms-") as directory:
        root = Path(directory)
        (root / "payload").write_bytes(payload)
        (root / "signature.der").write_bytes(cms)
        (root / "public.pem").write_bytes(cert_pem)
        try:
            subprocess.run([
                "openssl", "cms", "-verify", "-binary", "-inform", "DER",
                "-in", str(root / "signature.der"), "-content", str(root / "payload"),
                "-certfile", str(root / "public.pem"), "-nointern", "-noverify",
                "-out", str(root / "verified-output"),
            ], capture_output=True, check=True, timeout=90)
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            raise VerificationError(f"CMS signature does not verify: {module_path.name}") from error
    return {"path": str(module_path), "sha256": hashlib.sha256(raw).hexdigest(),
            "signed_payload_size_bytes": len(payload), "cms_signature_verified": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--certificate", required=True, type=Path)
    parser.add_argument("--fingerprint", required=True, type=Path)
    parser.add_argument("modules", nargs="+", type=Path)
    args = parser.parse_args()
    try:
        pem, fingerprint = certificate(args.certificate, args.fingerprint)
        results = [verify(module, pem) for module in args.modules]
    except (OSError, UnicodeError, VerificationError) as error:
        print(f"Public build signature verification FAILED: {error}", file=sys.stderr)
        return 2
    print(json.dumps({"schema": "op7t-build-module-cms-v1", "public_cert_sha256": fingerprint,
                      "modules": results, "installed_kernel_key_trust_verified": False,
                      "installed_rom_abi_verified": False, "flash_ready": False},
                     indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
