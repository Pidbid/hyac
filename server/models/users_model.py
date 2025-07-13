# models/users_model.py
from datetime import datetime
from typing import Optional

from beanie import Document
from pydantic import Field
from pymongo import IndexModel


class User(Document):
    """
    Represents a user in the system.
    """

    username: str = Field()
    password: str
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    refresh_token: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    roles: list[str] = Field(default_factory=list)

    class Settings:
        """
        Pydantic and Beanie settings for the User model.
        """

        name = "users"
        indexes = [
            "username",
        ]

    def update_timestamp(self):
        """
        Updates the 'updated_at' timestamp to the current time.
        """
        self.updated_at = datetime.now()


class Captcha(Document):
    """
    Represents a CAPTCHA used for verification.
    """

    text: str
    created_at: datetime = Field(default_factory=datetime.now)
    expires_at: datetime
    is_used: bool = False

    class Settings:
        """
        Pydantic and Beanie settings for the Captcha model.
        """

        name = "captchas"
