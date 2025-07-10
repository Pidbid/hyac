# routers/services/storage.py
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.jwt_auth import get_current_user
from core.minio_manager import minio_manager
from models.applications_model import Application
from models.common_model import BaseResponse
from models.users_model import User

router = APIRouter(
    prefix="/storage",
    tags=["Storage Management"],
    responses={404: {"description": "Not found"}},
)


class BucketRequest(BaseModel):
    """Request model for bucket-related operations."""

    appId: str


class FolderRequest(BaseModel):
    """Request model for folder-related operations."""

    appId: str
    folder_name: str


class FileRequest(BaseModel):
    """Request model for file-related operations."""

    appId: str
    object_name: str


class ListObjectsRequest(BaseModel):
    """Request model for listing objects."""

    appId: str
    prefix: Optional[str] = "/"


@router.post("/create_folder", response_model=BaseResponse)
async def create_folder(
    data: FolderRequest, current_user: User = Depends(get_current_user)
):
    """
    Creates a new folder in the application's storage bucket.
    """
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    success = minio_manager.create_folder(data.appId.lower(), data.folder_name)
    if not success:
        return BaseResponse(code=500, msg="Failed to create folder")
    return BaseResponse(
        code=0, msg=f"Folder '{data.folder_name}' created successfully."
    )


@router.post("/delete_file", response_model=BaseResponse)
async def delete_file(
    data: FileRequest, current_user: User = Depends(get_current_user)
):
    """
    Deletes a file from the application's storage bucket.
    """
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    success = minio_manager.delete_object(data.appId.lower(), data.object_name)
    if not success:
        return BaseResponse(code=500, msg="Failed to delete file")
    return BaseResponse(code=0, msg=f"File '{data.object_name}' deleted successfully.")


@router.post("/delete_folder", response_model=BaseResponse)
async def delete_folder(
    data: FolderRequest, current_user: User = Depends(get_current_user)
):
    """
    Deletes a folder from the application's storage bucket.
    """
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    success = minio_manager.delete_folder(data.appId.lower(), data.folder_name)
    if not success:
        return BaseResponse(code=500, msg="Failed to delete folder")
    return BaseResponse(
        code=0, msg=f"Folder '{data.folder_name}' deleted successfully."
    )


@router.post("/upload_file", response_model=BaseResponse)
async def upload_file(
    appId: str = Form(...),
    object_name: str = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """
    Uploads a file to the application's storage bucket.
    """
    app = await Application.find_one(
        Application.app_id == appId, Application.users == current_user.username
    )
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(await file.read())
        temp_file_path = tmp.name

    success = minio_manager.upload_file(appId.lower(), object_name, temp_file_path)
    Path(temp_file_path).unlink()

    if not success:
        return BaseResponse(code=500, msg="File upload failed")

    return BaseResponse(
        code=0, msg="File uploaded successfully", data={"filename": file.filename}
    )


@router.post("/download_file")
async def download_file(
    data: FileRequest, current_user: User = Depends(get_current_user)
):
    """
    Downloads a file from the application's storage bucket.
    """
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    if not minio_manager.client:
        raise HTTPException(status_code=500, detail="MinIO client is not initialized")

    response = None
    try:
        response = minio_manager.client.get_object(data.appId.lower(), data.object_name)
        return StreamingResponse(
            response.stream(32 * 1024),
            headers={"Content-Disposition": f"attachment; filename={data.object_name}"},
        )
    except Exception as e:
        raise HTTPException(
            status_code=404, detail=f"File not found or download failed: {e}"
        )
    finally:
        if response:
            response.close()
            response.release_conn()


@router.post("/get_download_url", response_model=BaseResponse)
async def get_download_url(
    data: FileRequest, current_user: User = Depends(get_current_user)
):
    """
    Generates a presigned URL for downloading a file.
    """
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    url = minio_manager.get_download_url(data.appId.lower(), data.object_name)
    if not url:
        return BaseResponse(code=500, msg="Failed to generate download URL")

    return BaseResponse(
        code=0, msg="Download URL generated successfully", data={"url": url}
    )


@router.post("/list_objects", response_model=BaseResponse)
async def list_objects(
    data: ListObjectsRequest, current_user: User = Depends(get_current_user)
):
    """
    Lists objects (files and folders) in the application's storage bucket.
    """
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    objects = minio_manager.list_objects(data.appId.lower(), data.prefix)
    if objects is None:
        return BaseResponse(code=500, msg="Failed to list objects")

    return BaseResponse(code=0, msg="Objects listed successfully", data=objects)
