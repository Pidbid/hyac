"""Application-scoped control plane used by untrusted runtime containers."""

import hashlib
import hmac
from datetime import datetime
from typing import Annotated, Optional

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from core.config import settings
from core.database import mongodb_manager
from core.environment_contract import (
    RESERVED_ENV_KEYS,
    filter_user_environment_variables,
)
from core.token_claims import TokenClaimsError, validate_token_claims
from models import Application, EnvironmentVariable, Function, FunctionMetric, User
from models.applications_model import ApplicationStatus
from models.functions_model import FunctionStatus, FunctionType


router = APIRouter(
    prefix="/internal/runtime",
    tags=["Runtime Control"],
    include_in_schema=False,
)
runtime_security = HTTPBearer(auto_error=False)


class RuntimeIdentity(BaseModel):
    app_id: str
    generation: int
    runtime_token_hash: str = ""
    lifecycle_revision: int = 0


class RuntimeMetricRequest(BaseModel):
    function_id: str
    function_name: str
    status: str
    execution_time: float = Field(ge=0)
    extra: Optional[dict] = None


class RuntimeEnvironmentRequest(BaseModel):
    value: str


def _runtime_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def require_runtime_identity(
    credentials: Annotated[
        Optional[HTTPAuthorizationCredentials], Depends(runtime_security)
    ],
    x_app_id: Annotated[str, Header(alias="X-App-Id")],
    x_runtime_generation: Annotated[int, Header(alias="X-Runtime-Generation")],
) -> RuntimeIdentity:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Runtime credential required")

    application = await Application.find_one(Application.app_id == x_app_id)
    if (
        not application
        or application.status
        not in {ApplicationStatus.STARTING, ApplicationStatus.RUNNING}
        or not application.runtime_token_hash
    ):
        raise HTTPException(status_code=401, detail="Unknown runtime")
    if application.runtime_generation != x_runtime_generation:
        raise HTTPException(status_code=401, detail="Stale runtime generation")
    if not hmac.compare_digest(
        application.runtime_token_hash,
        _runtime_digest(credentials.credentials),
    ):
        raise HTTPException(status_code=401, detail="Invalid runtime credential")
    return RuntimeIdentity(
        app_id=x_app_id,
        generation=x_runtime_generation,
        runtime_token_hash=application.runtime_token_hash,
        lifecycle_revision=application.lifecycle_revision,
    )


def _public_application(application: Application) -> dict:
    data = application.model_dump(mode="json", by_alias=True)
    data.pop("runtime_token_hash", None)
    data.pop("lifecycle_completed_task_id", None)
    data.pop("runtime_cleanup_task_id", None)
    data.pop("runtime_cleanup_lease_owner", None)
    data.pop("runtime_cleanup_lease_expires_at", None)
    data["environment_variables"] = [
        item
        for item in data.get("environment_variables", [])
        if item.get("key") not in RESERVED_ENV_KEYS
    ]
    return data


@router.get("/bootstrap")
async def runtime_bootstrap(
    identity: RuntimeIdentity = Depends(require_runtime_identity),
):
    application = await Application.find_one(Application.app_id == identity.app_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    functions = await Function.find(
        Function.app_id == identity.app_id,
        Function.status == FunctionStatus.PUBLISHED,
    ).to_list()
    return {
        "application": _public_application(application),
        "functions": [item.model_dump(mode="json", by_alias=True) for item in functions],
    }


@router.get("/functions/{function_id}")
async def runtime_function(
    function_id: str,
    identity: RuntimeIdentity = Depends(require_runtime_identity),
):
    function = await Function.find_one(
        Function.app_id == identity.app_id,
        Function.function_id == function_id,
        Function.status == FunctionStatus.PUBLISHED,
    )
    if not function:
        raise HTTPException(status_code=404, detail="Function not found")
    return function.model_dump(mode="json", by_alias=True)


@router.get("/functions")
async def runtime_functions(
    function_type: Optional[FunctionType] = None,
    identity: RuntimeIdentity = Depends(require_runtime_identity),
):
    filters = [
        Function.app_id == identity.app_id,
        Function.status == FunctionStatus.PUBLISHED,
    ]
    if function_type:
        filters.append(Function.function_type == function_type)
    functions = await Function.find(*filters).to_list()
    return [item.model_dump(mode="json", by_alias=True) for item in functions]


async def _access_user(token: str) -> User:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        username = validate_token_claims(payload, expected_type="access")
    except (jwt.PyJWTError, TokenClaimsError):
        raise HTTPException(status_code=401, detail="Invalid access token")

    user = await User.find_one(User.username == username)
    if not user or user.disabled:
        raise HTTPException(status_code=401, detail="Invalid access token")
    try:
        validate_token_claims(
            payload,
            expected_type="access",
            token_version=user.token_version,
        )
    except TokenClaimsError:
        raise HTTPException(status_code=401, detail="Invalid access token")
    return user


@router.post("/authorize/{function_id}")
async def authorize_function(
    function_id: str,
    identity: RuntimeIdentity = Depends(require_runtime_identity),
    x_function_authorization: Annotated[
        Optional[str], Header(alias="X-Function-Authorization")
    ] = None,
):
    function = await Function.find_one(
        Function.app_id == identity.app_id,
        Function.function_id == function_id,
        Function.status == FunctionStatus.PUBLISHED,
    )
    if not function:
        raise HTTPException(status_code=404, detail="Function not found")
    if not function.requires_auth:
        return {"authorized": True, "username": None}

    if not x_function_authorization or not x_function_authorization.startswith(
        "Bearer "
    ):
        raise HTTPException(status_code=401, detail="Access token required")
    user = await _access_user(x_function_authorization.removeprefix("Bearer ").strip())
    application = await Application.find_one(
        Application.app_id == identity.app_id,
        Application.users == user.username,
    )
    if not application:
        raise HTTPException(status_code=403, detail="Application membership required")
    return {"authorized": True, "username": user.username}


@router.post("/metrics", status_code=204)
async def write_metric(
    data: RuntimeMetricRequest,
    identity: RuntimeIdentity = Depends(require_runtime_identity),
):
    metric = FunctionMetric(
        function_id=data.function_id,
        function_name=data.function_name,
        app_id=identity.app_id,
        status=data.status,
        execution_time=data.execution_time,
        extra=data.extra,
    )
    await metric.insert()


@router.put("/environment/{key}", status_code=204)
async def update_environment(
    key: str,
    data: RuntimeEnvironmentRequest,
    identity: RuntimeIdentity = Depends(require_runtime_identity),
):
    application = await Application.find_one(Application.app_id == identity.app_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    if key in RESERVED_ENV_KEYS:
        raise HTTPException(status_code=400, detail="Reserved environment key")
    application.environment_variables = filter_user_environment_variables(
        application.environment_variables
    )
    for item in application.environment_variables:
        if item.key == key:
            item.value = data.value
            break
    else:
        application.environment_variables.append(
            EnvironmentVariable(key=key, value=data.value)
        )
    result = await mongodb_manager.get_collection(Application).update_one(
        {
            "app_id": identity.app_id,
            "runtime_generation": identity.generation,
            "runtime_token_hash": identity.runtime_token_hash,
            "lifecycle_revision": identity.lifecycle_revision,
            "environment_revision": application.environment_revision,
        },
        {
            "$set": {
                "environment_variables": [
                    item.model_dump(mode="python")
                    if hasattr(item, "model_dump")
                    else item
                    for item in application.environment_variables
                ],
                "updated_at": datetime.now(),
            },
            "$inc": {"environment_revision": 1},
        },
    )
    if result.matched_count == 0:
        raise HTTPException(
            status_code=409,
            detail="Runtime authority changed before environment update",
        )
