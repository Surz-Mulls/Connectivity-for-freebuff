"""Device identity: a self-signed ECDSA P-256 certificate generated on first run.

The certificate fingerprint (SHA-256 over the DER) is the device identity used by the trust
store and the SAS derivation. The private key never leaves this directory (0600) and is never
logged or exported by diagnostics.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import secrets
import uuid
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import (
    decode_dss_signature,
    encode_dss_signature,
)
from cryptography.x509.oid import NameOID

CERT_FILE = "device-cert.pem"
KEY_FILE = "device-key.pem"
META_FILE = "device.json"


class IdentityError(Exception):
    pass


def fingerprint_of_der(der: bytes) -> str:
    """Lower-case hex SHA-256 of a certificate DER. Stable, comparable, safe to display."""
    return hashlib.sha256(der).hexdigest()


def format_fingerprint(fpr: str) -> str:
    """Group a fingerprint for humans: ``ab12 cd34 ...``."""
    return " ".join(fpr[i:i + 4] for i in range(0, len(fpr), 4))


def _write_private(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)
    os.replace(tmp, path)
    os.chmod(path, 0o600)


@dataclass
class Identity:
    device_id: str
    name: str
    cert_pem: bytes
    key_pem: bytes
    cert: x509.Certificate
    key: ec.EllipticCurvePrivateKey
    directory: Path

    @property
    def cert_der(self) -> bytes:
        return self.cert.public_bytes(serialization.Encoding.DER)

    @property
    def fingerprint(self) -> str:
        return fingerprint_of_der(self.cert_der)

    def info(self, platform: str = "linux", caps: list[str] | None = None) -> dict:
        from . import PROTOCOL_VERSION, __version__

        return {
            "id": self.device_id,
            "name": self.name,
            "platform": platform,
            "app_version": __version__,
            "proto": PROTOCOL_VERSION,
            "caps": sorted(caps or []),
        }

    def sign(self, data: bytes) -> bytes:
        """ECDSA/SHA-256 over ``data``, normalised to raw r||s (64 bytes) for portability."""
        r, s = decode_dss_signature(self.key.sign(data, ec.ECDSA(hashes.SHA256())))
        return r.to_bytes(32, "big") + s.to_bytes(32, "big")

    def nonce(self) -> bytes:
        return secrets.token_bytes(32)

    @classmethod
    def load_or_create(cls, directory: Path, name_hint: str | None = None) -> "Identity":
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
        cert_path = directory / CERT_FILE
        key_path = directory / KEY_FILE
        meta_path = directory / META_FILE

        if cert_path.exists() and key_path.exists() and meta_path.exists():
            cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
            key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
            if not isinstance(key, ec.EllipticCurvePrivateKey):
                raise IdentityError("identity key is not an EC key")
            meta = json.loads(meta_path.read_text())
            return cls(meta["device_id"], meta["name"], cert_path.read_bytes(),
                       key_path.read_bytes(), cert, key, directory)

        name = (name_hint or os.environ.get("HOSTNAME") or "continuity-device").strip()[:64]
        device_id = str(uuid.uuid4())
        key = ec.generate_private_key(ec.SECP256R1())
        now = _dt.datetime.now(_dt.timezone.utc)
        subject = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, f"Continuity {name}"[:64]),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Continuity"),
        ])
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - _dt.timedelta(minutes=5))
            .not_valid_after(now + _dt.timedelta(days=1825))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("continuity.local")]),
                           critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(
                digital_signature=True, content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=False,
                crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
            .sign(key, hashes.SHA256())
        )
        cert_pem = cert.public_bytes(serialization.Encoding.PEM)
        key_pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        _write_private(key_path, key_pem)
        cert_path.write_bytes(cert_pem)
        os.chmod(cert_path, 0o644)
        meta_path.write_text(json.dumps({"device_id": device_id, "name": name,
                                         "created": now.isoformat()}, indent=2))
        os.chmod(meta_path, 0o600)
        return cls(device_id, name, cert_pem, key_pem, cert, key, directory)


def raw_to_dss(signature: bytes) -> bytes:
    if len(signature) != 64:
        raise IdentityError("raw ECDSA signature must be 64 bytes (r||s)")
    return encode_dss_signature(int.from_bytes(signature[:32], "big"),
                                int.from_bytes(signature[32:], "big"))
