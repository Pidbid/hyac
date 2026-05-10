"""Password hashing utilities.

Uses salted PBKDF2-SHA256 hashes for new passwords while accepting legacy
unsalted MD5 hashes so existing users can be migrated on successful login.
"""

import hashlib
import hmac
import os
from base64 import urlsafe_b64decode, urlsafe_b64encode

_HASH_NAME = "sha256"
_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 260_000
_SALT_BYTES = 16
_LEGACY_MD5_HEX_LENGTH = 32


def _b64encode(value: bytes) -> str:
    return urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return urlsafe_b64decode((value + padding).encode("ascii"))


def hash_password(password: str) -> str:
    """Hash a password using salted PBKDF2-SHA256."""
    salt = os.urandom(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        _HASH_NAME, password.encode("utf-8"), salt, _ITERATIONS
    )
    return f"{_ALGORITHM}${_ITERATIONS}${_b64encode(salt)}${_b64encode(digest)}"


def _is_legacy_md5_hash(hashed_password: str) -> bool:
    return (
        len(hashed_password) == _LEGACY_MD5_HEX_LENGTH
        and all(char in "0123456789abcdefABCDEF" for char in hashed_password)
    )


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against PBKDF2-SHA256 or legacy MD5 hashes."""
    if _is_legacy_md5_hash(hashed_password):
        legacy_digest = hashlib.md5(plain_password.encode("utf-8")).hexdigest()
        return hmac.compare_digest(legacy_digest, hashed_password.lower())

    try:
        algorithm, iterations_text, salt_text, digest_text = hashed_password.split("$", 3)
        if algorithm != _ALGORITHM:
            return False
        iterations = int(iterations_text)
        salt = _b64decode(salt_text)
        expected_digest = _b64decode(digest_text)
    except (ValueError, TypeError):
        return False

    actual_digest = hashlib.pbkdf2_hmac(
        _HASH_NAME, plain_password.encode("utf-8"), salt, iterations
    )
    return hmac.compare_digest(actual_digest, expected_digest)


def password_needs_rehash(hashed_password: str) -> bool:
    """Return True when a stored hash should be upgraded."""
    if _is_legacy_md5_hash(hashed_password):
        return True
    try:
        algorithm, iterations_text, *_ = hashed_password.split("$", 3)
        return algorithm != _ALGORITHM or int(iterations_text) < _ITERATIONS
    except (ValueError, TypeError):
        return True
