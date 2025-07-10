# models/functions_history_model.py
from datetime import datetime

from beanie import Document
from pydantic import Field


class FunctionsHistory(Document):
    """
    Represents the version history of a function's code.
    """

    function_id: str
    updated_at: datetime = Field(default_factory=datetime.now)
    old_code: str
    new_code: str
    updated_by: str

    class Settings:
        """
        Pydantic and Beanie settings for the FunctionsHistory model.
        """

        name = "functions_history"
