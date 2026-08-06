"""Framework-independent validation helpers for authentication token claims."""

from collections.abc import Mapping
from typing import Any


class TokenClaimsError(ValueError):
    """Raised when decoded JWT claims do not satisfy the auth contract."""


def validate_token_claims(
    payload: Mapping[str, Any],
    *,
    expected_type: str,
    token_version: int | None = None,
) -> str:
    """Validate token purpose, subject and optional session version."""
    if payload.get("type") != expected_type:
        raise TokenClaimsError("Invalid token type")

    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject:
        raise TokenClaimsError("Invalid token subject")

    claim_version = payload.get("token_version", 0)
    if not isinstance(claim_version, int):
        raise TokenClaimsError("Invalid token version")
    if token_version is not None and claim_version != token_version:
        raise TokenClaimsError("Token has been revoked")

    return subject
