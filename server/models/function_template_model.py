# models/function_template_model.py
from datetime import datetime
from enum import Enum
from typing import List

from beanie import Document
from pydantic import Field


class FunctionType(str, Enum):
    """
    Enum for the type of a function.
    """

    ENDPOINT = "endpoint"
    COMMON = "common"


class TemplateType(str, Enum):
    """
    Enum for the type of a function template.
    """

    SYSTEM = "system"
    USER = "user"


class FunctionTemplate(Document):
    """
    Represents a serverless function in the system.
    """

    app_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    description: str = Field(default="", min_length=0)
    code: str = Field(..., min_length=10)
    type: TemplateType = Field(default=TemplateType.SYSTEM)
    function_type: FunctionType = Field(default_factory=FunctionType.ENDPOINT)
    created_at: datetime = Field(default_factory=datetime.now)
    shared: bool = Field(default=False)

    class Settings:
        """
        Pydantic and Beanie settings for the Function template.
        """

        name = "function_templates"
        use_cache = False
        indexes = ["name"]
