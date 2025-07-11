# routers/services/users.py
import base64
import hashlib
import io
import random
import uuid
from string import ascii_lowercase, ascii_uppercase, digits
from datetime import datetime, timedelta
from typing import Any, Optional

from captcha.image import ImageCaptcha
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.jwt_auth import create_access_token, get_current_user, verify_password
from models.common_model import BaseResponse
from models.users_model import Captcha, User

router = APIRouter(
    prefix="/users",
    tags=["User Management"],
    responses={404: {"description": "User not found"}},
)


class CreateUserRequest(BaseModel):
    """Request model for creating a user."""

    username: str
    password: str
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None


class UpdateUserRequest(BaseModel):
    """Request model for updating a user."""

    password: Optional[str] = None
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None


class LoginRequest(BaseModel):
    """Request model for user login."""

    username: str
    password: str
    captcha: str


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
async def login_for_access_token(data: LoginRequest):
    """
    Handles user login, verifies credentials and CAPTCHA, and returns a JWT access token.
    """
    captcha_error = await verify_captcha(data.captcha)
    if captcha_error:
        return BaseResponse(
            code=captcha_error["code"],
            msg=captcha_error["msg"],
        )

    user = await User.find_one(User.username == data.username)
    if not user or not verify_password(data.password, user.password):
        return BaseResponse(code=107, msg="Incorrect username or password")

    access_token = create_access_token(data={"sub": user.username})
    return {
        "code": 0,
        "msg": "User login successful",
        "data": {
            "token": access_token,
            "refreshToken": "test",
        },  # refreshToken is a placeholder
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
            "roles": ["admin"],  # Placeholder roles
            "buttons": ["btn.add", "btn.delete", "btn.update"],  # Placeholder buttons
        },
    }


@router.get("/captcha", response_model=GetCaptchaResponse)
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


def hash_password(password: str) -> str:
    """
    Hashes a password using MD5.
    Note: MD5 is not recommended for new applications. Consider a stronger algorithm.
    """
    return hashlib.md5(password.encode("utf-8")).hexdigest()


@router.post("/add", response_model=User)
async def create_user(data: CreateUserRequest):
    """
    Creates a new user.
    """
    if await User.find_one(User.username == data.username):
        raise HTTPException(
            status_code=409, detail="User with this username already exists"
        )

    hashed_password = hash_password(data.password)
    new_user = User(
        username=data.username,
        password=hashed_password,
        nickname=data.nickname,
        avatar_url=data.avatar_url,
    )
    await new_user.insert()
    return new_user


@router.put("/update/{username}", response_model=User)
async def update_user(username: str, data: UpdateUserRequest):
    """
    Updates a user's information.
    """
    user = await User.find_one(User.username == username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    update_data = data.dict(exclude_unset=True)
    if "password" in update_data and update_data["password"]:
        update_data["password"] = hash_password(update_data["password"])

    for key, value in update_data.items():
        setattr(user, key, value)

    user.update_timestamp()
    await user.save()
    return user


@router.delete("/delete/{username}", response_model=BaseResponse)
async def delete_user(username: str):
    """
    Deletes a user.
    """
    user = await User.find_one(User.username == username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await user.delete()
    return BaseResponse(code=0, msg=f"User '{username}' deleted successfully")


@router.get("/get/{username}", response_model=User)
async def get_user(username: str):
    """
    Retrieves a single user by username.
    """
    user = await User.find_one(User.username == username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/list", response_model=list[User])
async def list_users(page: int = 1, size: int = 10):
    """
    Retrieves a paginated list of users.
    """
    skip = (page - 1) * size
    query = User.find_all()
    return await query.skip(skip).limit(size).to_list()
