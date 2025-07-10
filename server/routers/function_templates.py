# routers/services/function_templates.py
import math
from typing import Optional

from beanie.odm.operators.update.general import Set
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.jwt_auth import get_current_user
from models.common_model import BaseResponse
from models.function_template_model import FunctionTemplate, TemplateType
from models.functions_model import FunctionType
from models.users_model import User

router = APIRouter(
    prefix="/function_templates",
    tags=["Function Templates"],
    responses={404: {"description": "Not found"}},
)


class GetFunctionTemplatesRequest(BaseModel):
    """Request model for getting function templates."""

    appId: str
    page: int = 1
    length: int = 10
    function_type: Optional[FunctionType] = None


class CreateFunctionTemplateRequest(BaseModel):
    """Request model for creating a function template."""

    appId: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    description: str = Field(default="")
    code: str = Field(..., min_length=10)
    type: TemplateType = Field(default=TemplateType.USER)
    shared: bool = Field(default=False)


class UpdateFunctionTemplateRequest(BaseModel):
    """Request model for updating a function template."""

    id: str
    name: Optional[str] = None
    code: Optional[str] = None
    type: Optional[TemplateType] = None
    shared: Optional[bool] = None


class DeleteFunctionTemplateRequest(BaseModel):
    """Request model for deleting a function template."""

    id: str


class GetFunctionTemplateRequest(BaseModel):
    """Request model for getting a single function template."""

    id: str


@router.post("/data", response_model=BaseResponse)
async def get_function_templates(
    data: GetFunctionTemplatesRequest, current_user: User = Depends(get_current_user)
):
    """
    Retrieves a paginated list of function templates.
    """
    skip = (data.page - 1) * data.length
    query = FunctionTemplate.find(FunctionTemplate.app_id == data.appId)

    if data.function_type:
        query = query.find(
            FunctionTemplate.function_type == data.function_type,
        )

    data_list = await query.skip(skip).limit(data.length).to_list()
    total_count = await query.count()

    page_num = math.ceil(total_count / data.length) if data.length > 0 else 0
    return BaseResponse(
        code=0,
        msg="success",
        data={
            "data": data_list,
            "pageNum": page_num,
            "pageSize": data.length,
            "total": total_count,
        },
    )


@router.post("/create", response_model=BaseResponse)
async def create_function_template(
    data: CreateFunctionTemplateRequest, current_user: User = Depends(get_current_user)
):
    """
    Creates a new function template.
    """
    if await FunctionTemplate.find_one(FunctionTemplate.name == data.name):
        raise HTTPException(
            status_code=409, detail="Function template with this name already exists"
        )

    new_template = FunctionTemplate(
        app_id=data.appId,
        name=data.name,
        description=data.description,
        code=data.code,
        type=data.type,
        shared=data.shared,
    )
    await new_template.insert()

    return BaseResponse(
        code=0,
        msg="Function template created successfully",
        data={"id": str(new_template.id)},
    )


@router.post("/delete", response_model=BaseResponse)
async def delete_function_template(
    data: DeleteFunctionTemplateRequest, current_user: User = Depends(get_current_user)
):
    """
    Deletes a function template.
    """
    template = await FunctionTemplate.get(data.id)
    if not template:
        raise HTTPException(status_code=404, detail="Function template not found")

    await template.delete()

    return BaseResponse(code=0, msg="Function template deleted successfully", data={})


@router.post("/update", response_model=BaseResponse)
async def update_function_template(
    data: UpdateFunctionTemplateRequest, current_user: User = Depends(get_current_user)
):
    """
    Updates a function template.
    """
    template = await FunctionTemplate.get(data.id)
    if not template:
        raise HTTPException(status_code=404, detail="Function template not found")

    update_data = data.model_dump(exclude_unset=True, exclude={"id"})
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    await template.update(Set(update_data))

    return BaseResponse(code=0, msg="Function template updated successfully", data={})


@router.post("/info", response_model=BaseResponse)
async def get_function_template(
    data: GetFunctionTemplateRequest, current_user: User = Depends(get_current_user)
):
    """
    Retrieves information about a single function template.
    """
    template = await FunctionTemplate.get(data.id)
    if not template:
        raise HTTPException(status_code=404, detail="Function template not found")

    return BaseResponse(code=0, msg="success", data=template)
