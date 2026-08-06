# routers/services/users.py
import base64
import io
import random
import re
from string import ascii_lowercase, ascii_uppercase, digits
from datetime import datetime, timedelta
from typing import Any, Optional

from captcha.image import ImageCaptcha
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from pymongo.errors import DuplicateKeyError

from core.database import mongodb_manager
from core.rate_limiter import LoginRateLimiter, get_request_limiter
from core.exceptions import APIException
from core.config import settings
from core.jwt_auth import (
    create_access_token,
    create_refresh_token,
    get_current_user,
    hash_refresh_token,
    verify_refresh_token_and_get_user,
)
from core.passwords import hash_password, password_needs_rehash, verify_password
from models import Application, FunctionsHistory, Function, BaseResponse, Captcha, User

router = APIRouter(
    prefix="/users",
    tags=["User Management"],
    responses={404: {"description": "User not found"}},
)


class UpdateMeRequest(BaseModel):
    """Request model for user to update their own info."""

    username: Optional[str] = None
    password: Optional[str] = None

    @field_validator("username")
    @classmethod
    def validate_username(cls, v):
        if v and not re.match(r"^[\u4e00-\u9fa5a-zA-Z0-9_-]{4,16}$", v):
            raise ValueError("Username format is incorrect")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if v is not None and not re.fullmatch(r"\S{8,128}", v):
            raise ValueError("Password format is incorrect")
        return v


class LoginRequest(BaseModel):
    """Request model for user login."""

    username: str
    password: str
    captcha: str


class RefreshTokenRequest(BaseModel):
    """Request model for refreshing a token."""

    refreshToken: str


class LoginResponse(BaseModel):
    """Response model for a successful login."""

    code: int
    msg: str
    data: Any


class GetCaptchaResponse(BaseModel):
    """Response model for the CAPTCHA image."""

    code: int
    msg: str
    data: str


async def verify_captcha(captcha: str) -> dict:
    """
    Verifies a given CAPTCHA string against the stored records.
    """
    if not captcha:
        return {"code": 108, "msg": "Captcha cannot be empty"}

    captcha_record = await Captcha.find_one(Captcha.text == captcha.lower())
    if not captcha_record:
        return {"code": 108, "msg": "Captcha not found or incorrect"}

    if captcha_record.is_used:
        return {"code": 108, "msg": "Captcha has already been used"}

    if datetime.now() > captcha_record.expires_at:
        return {"code": 108, "msg": "Captcha has expired"}

    captcha_record.is_used = True
    await captcha_record.save()
    return {}


@router.post("/login", response_model=LoginResponse)
async def login_for_access_token(data: LoginRequest, request: Request):
    """
    Handles user login, verifies credentials and CAPTCHA, and returns a JWT access token.
    """
    limiter = LoginRateLimiter(request)
    limiter.check_rate_limit()

    captcha_error = await verify_captcha(data.captcha)
    if captcha_error:
        return BaseResponse(
            code=captcha_error["code"],
            msg=captcha_error["msg"],
        )

    user = await User.find_one(User.username == data.username)
    if (
        not user
        or user.disabled
        or "admin" not in user.roles
        or not verify_password(data.password, user.password)
    ):
        limiter.record_failed_attempt()
        return BaseResponse(code=107, msg="Incorrect username or password")

    # Create access and refresh tokens
    expected_password = user.password
    expected_token_version = user.token_version
    token_data = {
        "sub": user.username,
        "token_version": expected_token_version,
    }
    refresh_token = create_refresh_token(data=token_data)
    session_fields = {
        "refresh_token_hash": hash_refresh_token(refresh_token),
        "updated_at": datetime.now(),
    }
    if password_needs_rehash(expected_password):
        session_fields["password"] = hash_password(data.password)
    result = await mongodb_manager.get_collection(User).update_one(
        {
            "_id": user.id,
            "username": user.username,
            "password": expected_password,
            "token_version": expected_token_version,
            "disabled": False,
            "roles": "admin",
        },
        {"$set": session_fields},
    )
    if result.matched_count == 0:
        raise HTTPException(
            status_code=409,
            detail="Credentials changed during login",
        )

    limiter.reset_attempts()
    access_token = create_access_token(data=token_data)

    return {
        "code": 0,
        "msg": "User login successful",
        "data": {
            "token": access_token,
            "refreshToken": refresh_token,
        },
    }


@router.get("/info", response_model=BaseResponse)
async def login_with_access_token(current_user: User = Depends(get_current_user)):
    """
    Retrieves information for the currently authenticated user.
    """
    return {
        "code": 0,
        "msg": "User info retrieved successfully",
        "data": {
            "userid": str(current_user.id),
            "nickname": current_user.nickname or current_user.username,
            "avatar": current_user.avatar_url or "",
            "username": current_user.username,
            "roles": current_user.roles,
            "buttons": ["btn.add", "btn.delete", "btn.update"],  # Placeholder buttons
        },
    }


@router.get(
    "/captcha",
    response_model=GetCaptchaResponse,
    dependencies=[Depends(get_request_limiter(limit=100, period=timedelta(days=1)))],
)
async def get_captcha():
    """
    Generates a new CAPTCHA image and returns it as a base64 encoded string.
    """
    image = ImageCaptcha(width=160, height=60)
    captcha_text = ""

    def captcha_filter(pos_cap_list: list[list[str]], captcha: str) -> bool:
        if len(captcha) != 4:
            return False
        for pos in pos_cap_list:
            if pos[0] in captcha.lower() and pos[1] in captcha.lower():
                return False
        return True

    while not captcha_filter([["o", "0"], ["l", "1"], ["7", "1"]], captcha_text):
        captcha_text = "".join(
            [
                str(random.choice(ascii_lowercase + ascii_uppercase + digits))
                for _ in range(4)
            ]
        )
    data = image.generate(captcha_text)
    image_bytes = io.BytesIO(data.read())
    image_base64 = base64.b64encode(image_bytes.getvalue()).decode("utf-8")

    expires_at = datetime.now() + timedelta(minutes=5)
    new_captcha = Captcha(text=captcha_text.lower(), expires_at=expires_at)
    await new_captcha.insert()

    return {
        "code": 0,
        "msg": "success",
        "data": "data:image/png;base64," + image_base64,
    }

@router.post("/me", response_model=BaseResponse)
async def update_me(
    data: UpdateMeRequest, current_user: User = Depends(get_current_user)
):
    """
    Allows a user to update their own information.
    """
    if settings.DEMO_MODE:
        raise APIException(
            code=114, msg="Username and password cannot be updated in demo mode"
        )
    update_data = data.model_dump(exclude_unset=True)
    if not update_data:
        return BaseResponse(code=0, msg="No information provided to update.")

    requested_username = update_data.get("username")
    if (
        requested_username
        and current_user.username == settings.DEFAULT_ADMIN_USER
    ):
        raise HTTPException(
            status_code=403,
            detail="The configured administrator username cannot be changed",
        )

    user_id = current_user.id
    old_username = current_user.username
    expected_token_version = current_user.token_version
    expected_refresh_hash = current_user.refresh_token_hash
    new_username = requested_username
    new_password = update_data.get("password")
    credential_change = bool(new_username or new_password)

    user_query = {
        "_id": user_id,
        "username": old_username,
        "token_version": expected_token_version,
        "refresh_token_hash": expected_refresh_hash,
    }
    set_fields = {"updated_at": datetime.now()}
    if new_username:
        set_fields["username"] = new_username
    if new_password:
        set_fields["password"] = hash_password(new_password)
    if credential_change:
        set_fields["refresh_token_hash"] = None

    user_update = {"$set": set_fields}
    if credential_change:
        user_update["$inc"] = {"token_version": 1}

    user_collection = mongodb_manager.get_collection(User)

    async def update_user(*, session=None):
        result = await user_collection.update_one(
            user_query,
            user_update,
            session=session,
        )
        if result.matched_count == 0:
            raise HTTPException(
                status_code=409,
                detail="User or session changed during profile update",
            )

    if new_username:
        application_collection = mongodb_manager.get_collection(Application)
        history_collection = mongodb_manager.get_collection(FunctionsHistory)
        function_collection = mongodb_manager.get_collection(Function)

        async def rename_in_transaction(session):
            duplicate = await user_collection.find_one(
                {"username": new_username, "_id": {"$ne": user_id}},
                projection={"_id": 1},
                session=session,
            )
            if duplicate:
                raise HTTPException(
                    status_code=409,
                    detail="User with this username already exists",
                )

            await update_user(session=session)
            await application_collection.update_many(
                {"users": old_username},
                {"$set": {"users.$": new_username}},
                session=session,
            )
            await history_collection.update_many(
                {"updated_by": old_username},
                {"$set": {"updated_by": new_username}},
                session=session,
            )
            await function_collection.update_many(
                {"users": old_username},
                {"$set": {"users.$": new_username}},
                session=session,
            )

        try:
            async with mongodb_manager.client.start_session() as session:
                await session.with_transaction(rename_in_transaction)
        except DuplicateKeyError as exc:
            raise HTTPException(
                status_code=409,
                detail="User with this username already exists",
            ) from exc
    else:
        await update_user()

    return BaseResponse(code=0, msg="User information updated successfully")
@router.post("/refreshToken", response_model=LoginResponse)
async def refresh_token(data: RefreshTokenRequest):
    """
    Refreshes an access token using a refresh token.
    """
    user = await verify_refresh_token_and_get_user(data.refreshToken)

    expected_token_version = user.token_version
    expected_refresh_hash = user.refresh_token_hash
    token_data = {
        "sub": user.username,
        "token_version": expected_token_version,
    }
    new_refresh_token = create_refresh_token(data=token_data)
    result = await mongodb_manager.get_collection(User).update_one(
        {
            "_id": user.id,
            "username": user.username,
            "token_version": expected_token_version,
            "refresh_token_hash": expected_refresh_hash,
            "disabled": False,
        },
        {
            "$set": {
                "refresh_token_hash": hash_refresh_token(new_refresh_token),
                "updated_at": datetime.now(),
            }
        },
    )
    if result.matched_count == 0:
        raise HTTPException(
            status_code=409,
            detail="Session changed during token refresh",
        )

    new_access_token = create_access_token(data=token_data)

    return {
        "code": 0,
        "msg": "Token refreshed successfully",
        "data": {
            "token": new_access_token,
            "refreshToken": new_refresh_token,
        },
    }
