# server/core/exceptions.py
from typing import Optional


class APIException(Exception):
    """
    Custom API Exception class to be used throughout the application for handling
    API-specific errors. It allows for a consistent error response format.
    """

    def __init__(
        self,
        code: int,
        msg: Optional[str] = None,
    ):
        """
        Initializes the APIException.

        Args:
            code: The error code.
            msg: The error message.
        """
        self.code = code
        self.msg = msg
        super().__init__(self.msg)
