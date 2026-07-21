"""
Token Encryption Utility

Provides symmetric encryption for sensitive tokens (e.g., GitHub OAuth tokens)
stored in the database. Uses Fernet (AES-128-CBC) from the cryptography library.

Design decision: Even though this is a student project, encrypting stored tokens
demonstrates defense-in-depth thinking. If the database is ever compromised,
raw OAuth tokens won't be exposed in plaintext.

The encryption key is read from the ENCRYPTION_KEY environment variable.
Generate one with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

If ENCRYPTION_KEY is not set, tokens are stored/returned as-is (plaintext fallback)
so the project still works out of the box during local development.
"""

import os
import logging

logger = logging.getLogger(__name__)

# Try to import cryptography — it's an optional dependency.
# If not installed, we fall back to plaintext storage.
try:
    from cryptography.fernet import Fernet, InvalidToken
    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False


def _get_cipher():
    """Return a Fernet cipher using the ENCRYPTION_KEY env var, or None."""
    if not _HAS_CRYPTO:
        return None

    key = os.environ.get("ENCRYPTION_KEY")
    if not key:
        return None

    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception:
        logger.warning("ENCRYPTION_KEY is set but invalid. Tokens will be stored in plaintext.")
        return None


def encrypt_token(plaintext: str) -> str:
    """Encrypt a token string. Returns the ciphertext as a UTF-8 string.

    Falls back to returning the plaintext unchanged if encryption is unavailable.
    """
    if not plaintext:
        return plaintext

    cipher = _get_cipher()
    if cipher is None:
        return plaintext

    return cipher.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_token(ciphertext: str) -> str:
    """Decrypt a token string. Returns the original plaintext.

    Falls back to returning the ciphertext unchanged if decryption is unavailable
    or if the value was never encrypted (graceful migration from plaintext).
    """
    if not ciphertext:
        return ciphertext

    cipher = _get_cipher()
    if cipher is None:
        return ciphertext

    try:
        return cipher.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except Exception:
        # Value was likely stored before encryption was enabled — return as-is
        # so we don't break existing tokens during migration.
        return ciphertext
