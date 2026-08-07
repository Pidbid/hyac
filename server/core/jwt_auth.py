from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
from typing import Optional

import jwt
from fastapi import HTTPException, Query, Security, WebSocket
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.exceptions import WebSocketException
from starlette import status
from jwt import ExpiredSignatureError, PyJWTError

from core.config import settings
from core.exceptions import APIException
from core.token_claims import TokenClaimsError, validate_token_claims
from models import User

# JWT Configuration
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30  # 30 minutes
REFRESH_TOKEN_EXPIRE_DAYS = 7  # 7 days

# Authentication scheme
security = HTTPBearer()


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Creates a new JWT access token.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )
    to_encode.update(
        {"exp": expire, "type": "access", "jti": secrets.token_urlsafe(24)}
    )
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Creates a new JWT refresh token.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update(
        {"exp": expire, "type": "refresh", "jti": secrets.token_urlsafe(24)}
    )
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def hash_refresh_token(token: str) -> str:
    """Return the one-way digest persisted for refresh-token rotation."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _validate_user_session(payload: dict, user: User, expected_type: str) -> None:
    validate_token_claims(
        payload,
        expected_type=expected_type,
        token_version=user.token_version,
    )
    if user.disabled:
        raise TokenClaimsError("User is disabled")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> User:
    """
    Dependency to get the current authenticated user from a JWT token.
    Raises HTTPException if the token is invalid or the user is not found.
    """
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = validate_token_claims(payload, expected_type="access")
    except ExpiredSignatureError:
        raise APIException(code=109, msg="Token has expired")
    except (PyJWTError, TokenClaimsError):
        raise APIException(code=103, msg="Invalid authentication credentials")

    user = await User.find_one(User.username == username)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    try:
        _validate_user_session(payload, user, "access")
    except TokenClaimsError:
        raise APIException(code=103, msg="Invalid authentication credentials")
    return user


async def get_current_user_for_websocket(
    websocket: WebSocket, token: Optional[str] = Query(None)
) -> User:
    """
    Dependency to get the current authenticated user for a WebSocket connection.
    The token is expected as a query parameter.
    """
    if token is None:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Authentication token is missing",
        )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = validate_token_claims(payload, expected_type="access")
    except (PyJWTError, TokenClaimsError):
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Invalid authentication credentials",
        )

    user = await User.find_one(User.username == username)
    if user is None:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION, reason="User not found"
        )
    try:
        _validate_user_session(payload, user, "access")
    except TokenClaimsError:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Invalid authentication credentials",
        )
    return user


async def optional_get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
) -> Optional[User]:
    """
    Dependency to optionally get the current authenticated user.
    Returns the user if the token is valid, otherwise returns None without raising an error.
    """
    if credentials:
        token = credentials.credentials
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username = validate_token_claims(payload, expected_type="access")
        except (PyJWTError, TokenClaimsError):
            return None  # Token is invalid, but don't raise an error.

        user = await User.find_one(User.username == username)
        if not user:
            return None
        try:
            _validate_user_session(payload, user, "access")
        except TokenClaimsError:
            return None
        return user
    return None



async def verify_refresh_token_and_get_user(
    refresh_token: str,
) -> User:
    """
    Verifies a refresh token and returns the associated user.
    """
    try:
        payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        username = validate_token_claims(payload, expected_type="refresh")
    except (PyJWTError, TokenClaimsError):
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    user = await User.find_one(User.username == username)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    try:
        _validate_user_session(payload, user, "refresh")
    except TokenClaimsError:
        raise HTTPException(status_code=401, detail="Invalid or revoked refresh token")

    expected_hash = user.refresh_token_hash or ""
    if not hmac.compare_digest(expected_hash, hash_refresh_token(refresh_token)):
        raise HTTPException(status_code=401, detail="Refresh token has been revoked")

    return user


# async def get_app_for_user(request: Request, current_user: User = Depends(get_current_user)):
#     app_id = request.json().get("app_id")
#     app = await Application.find_one(
#         Application.app_id == app_id, Application.users == current_user.username
#     )
#     if not app:
#         raise HTTPException(
#             status_code=404, detail="Application not found or permission denied"
#         )
#     return app
