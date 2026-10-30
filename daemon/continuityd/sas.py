"""Short authentication string (SAS) derivation and signature verification helpers.

Both devices compute the same SAS from data they both can see:

    HKDF-SHA256(ikm = client_fingerprint || server_fingerprint,
                salt = client_nonce || server_nonce,
                info = b"continuity/sas/v1") -> 8 bytes -> 6 digits + 4 emoji

The fingerprints are included so a substituted certificate changes the code, and the nonces are
fresh per session so a recorded confirmation cannot be replayed.
"""

from __future__ import annotations

import hashlib

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

EMOJI = ("🍎", "🐝", "🌙", "🚀", "🐢", "🌻", "🍀", "🎲",
         "🔑", "⭐", "🎈", "🐸", "🌵", "🍩", "🎧", "🦊",
         "🍇", "🚲", "🕯️", "🐧", "🌊", "🍄", "🦉", "🎯",
         "🧭", "🍒", "🐬", "🔔", "🌶️", "🪁", "🧩", "🎵")

EMOJI_PER_CODE = 4


def _derive(fingerprint_a: str, fingerprint_b: str,
            nonce_a: bytes, nonce_b: bytes) -> bytes:
    ikm = bytes.fromhex(fingerprint_a) + bytes.fromhex(fingerprint_b)
    hkdf = HKDF(algorithm=hashes.SHA256(), length=8, salt=nonce_a + nonce_b,
                info=b"continuity/sas/v1")
    return hkdf.derive(ikm)


def derive_sas(client_fingerprint: str, server_fingerprint: str,
               client_nonce: bytes, server_nonce: bytes) -> dict:
    """Return ``{"digits": "123456", "emoji": [...], "emoji_text": "..."}``."""
    material = _derive(client_fingerprint, server_fingerprint, client_nonce, server_nonce)
    number = int.from_bytes(material[:4], "big") % 1_000_000
    symbols = [EMOJI[b % len(EMOJI)] for b in material[4:4 + EMOJI_PER_CODE]]
    return {"digits": f"{number:06d}", "emoji": symbols, "emoji_text": " ".join(symbols)}


def sas_matches(local: dict, digits: str, emoji: str | list[str]) -> bool:
    """Compare a live SAS with what the peer confirmed (constant-time on the digits)."""
    if not isinstance(digits, str) or len(digits) != 6 or not digits.isdigit():
        return False
    peer_emoji = emoji.split() if isinstance(emoji, str) else list(emoji)
    return (hashlib.sha256(local["digits"].encode()).digest()
            == hashlib.sha256(digits.encode()).digest()
            and peer_emoji == local["emoji"])


def verify_signature(cert_der: bytes, data: bytes, signature: bytes) -> bool:
    from .identity import raw_to_dss

    try:
        cert = x509.load_der_x509_certificate(cert_der)
        key = cert.public_key()
        if not isinstance(key, ec.EllipticCurvePublicKey):
            return False
        key.verify(raw_to_dss(signature), data, ec.ECDSA(hashes.SHA256()))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False
