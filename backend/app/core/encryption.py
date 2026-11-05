# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Versioned AES-256-GCM envelopes for secrets stored in TEXT columns."""

import base64
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings

ENVELOPE_PREFIX = "aes256gcm:v1:"
NONCE_BYTES = 12
TAG_BYTES = 16


class SecretEncryptionError(Exception):
    """A secret could not be encrypted or authenticated with the configured key."""


def _cipher() -> AESGCM:
    key = get_settings().pos_credentials_encryption_key
    if key is None:
        raise SecretEncryptionError("POS_CREDENTIALS_ENCRYPTION_KEY is not configured.")
    decoded = base64.b64decode(key.get_secret_value(), altchars=b"-_", validate=True)
    return AESGCM(decoded)


def encrypt_secret(value: str, *, context: str) -> str:
    """Use a fresh nonce and authenticate both the envelope version and field context."""
    nonce = secrets.token_bytes(NONCE_BYTES)
    ciphertext = _cipher().encrypt(
        nonce, value.encode("utf-8"), (ENVELOPE_PREFIX + context).encode("utf-8")
    )
    return ENVELOPE_PREFIX + base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt_secret(value: str, *, context: str) -> str:
    """Reject plaintext, unknown versions, tampering, and mismatched provider/field contexts."""
    if not value.startswith(ENVELOPE_PREFIX):
        raise SecretEncryptionError("Stored secret is not a supported encrypted envelope.")
    try:
        payload = base64.b64decode(value[len(ENVELOPE_PREFIX) :], altchars=b"-_", validate=True)
        if len(payload) < NONCE_BYTES + TAG_BYTES:
            raise SecretEncryptionError("Stored secret envelope is incomplete.")
        plaintext = _cipher().decrypt(
            payload[:NONCE_BYTES],
            payload[NONCE_BYTES:],
            (ENVELOPE_PREFIX + context).encode("utf-8"),
        )
        return plaintext.decode("utf-8")
    except (InvalidTag, ValueError) as exc:
        raise SecretEncryptionError("Stored secret could not be authenticated.") from exc
