# models/users_model.py
from datetime import datetime
from typing import Optional

from beanie import Document
from pydantic import BaseModel, ConfigDict, Field


class User(Document):
    """
    Represents a user in the system.
    """

    username: str = Field()
    password: str
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    refresh_token_hash: Optional[str] = None
    token_version: int = 0
    disabled: bool = False
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    roles: list[str] = Field(default_factory=list)

    class Settings:
        """
        Pydantic and Beanie settings for the User model.
        """

        name = "users"
        # Username uniqueness is installed by the raw pre-Beanie migration.
        # Keeping it out of Beanie avoids a later non-unique index conflict.
        indexes = []

    def update_timestamp(self):
        """
        Updates the 'updated_at' timestamp to the current time.
        """
        self.updated_at = datetime.now()


class UserPublic(BaseModel):
    """Credential-free user representation for API responses."""

    model_config = ConfigDict(from_attributes=True)

    username: str
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    roles: list[str] = Field(default_factory=list)
    disabled: bool = False


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
