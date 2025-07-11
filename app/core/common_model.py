# models/common_model.py
from typing import Any

from pydantic import BaseModel


class BaseResponse(BaseModel):
    """
    A standard base model for API responses.
    """

    code: int
    msg: str
    data: Any = None


class PaginationResponse(BaseModel):
    """
    A standard model for paginated API responses.
    """

    total: int
    pageNum: int
    pageSize: int
    data: Any = None
