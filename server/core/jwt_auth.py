import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Query, Security, WebSocket, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError

from core.config import settings
from models import User, Application

# JWT Configuration
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 24 * 60

# Authentication scheme
security = HTTPBearer()


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Creates a new JWT access token.

    Args:
        data: The data to encode in the token (typically user identifier).
        expires_delta: An optional timedelta object for token expiration.

    Returns:
        The encoded JWT token as a string.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


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
        username: Optional[str] = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=401, detail="Invalid authentication credentials"
            )
    except PyJWTError:
        raise HTTPException(
            status_code=401, detail="Invalid authentication credentials"
        )

    user = await User.find_one(User.username == username)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def get_current_user_for_websocket(
    websocket: WebSocket, token: Optional[str] = Query(None)
) -> User:
    """
    Dependency to get the current authenticated user for a WebSocket connection.
    The token is expected as a query parameter.
    """
    if token is None:
        await websocket.close(code=4001, reason="Authentication token is missing")
        raise HTTPException(status_code=403, detail="Not authenticated")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: Optional[str] = payload.get("sub")
        if username is None:
            await websocket.close(
                code=4001, reason="Invalid authentication credentials"
            )
            raise HTTPException(
                status_code=401, detail="Invalid authentication credentials"
            )
    except PyJWTError:
        await websocket.close(code=4001, reason="Invalid authentication credentials")
        raise HTTPException(
            status_code=401, detail="Invalid authentication credentials"
        )

    user = await User.find_one(User.username == username)
    if user is None:
        await websocket.close(code=4001, reason="User not found")
        raise HTTPException(status_code=401, detail="User not found")
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
            username: Optional[str] = payload.get("sub")
            if username is None:
                return None  # Token is invalid, but don't raise an error.
        except PyJWTError:
            return None  # Token is invalid, but don't raise an error.

        user = await User.find_one(User.username == username)
        return user
    return None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifies a plain password against a hashed password (MD5).

    Args:
        plain_password: The plain text password.
        hashed_password: The MD5 hashed password.

    Returns:
        True if the passwords match, False otherwise.
    """
    return hashlib.md5(plain_password.encode("utf-8")).hexdigest() == hashed_password


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
