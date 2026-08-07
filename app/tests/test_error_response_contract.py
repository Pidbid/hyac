import json

import pytest
from fastapi import HTTPException

import main as runtime_main


@pytest.mark.asyncio
async def test_http_authentication_error_uses_standard_response_shape():
    response = await runtime_main.http_exception_handler(
        None,
        HTTPException(status_code=401, detail="Access token required"),
    )

    assert response.status_code == 401
    assert json.loads(response.body) == {
        "code": 401,
        "msg": "Access token required",
        "data": None,
    }
