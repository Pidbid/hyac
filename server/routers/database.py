# routers/services/database.py
import math
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.database_dynamic import dynamic_db
from core.jwt_auth import get_current_user
from core.utils import motor_result_serializer
from models.applications_model import Application
from models.common_model import BaseResponse
from core.exceptions import APIException

router = APIRouter(
    prefix="/database",
    tags=["Database Management"],
    responses={404: {"description": "Database not found"}},
)


class GetCollectionRequest(BaseModel):
    """Request model for getting collections."""

    appId: str


class GetCollectionDocumentsRequest(BaseModel):
    """Request model for getting documents from a collection."""

    appId: str
    colName: str
    page: int
    length: int


class InsertDocumentRequest(BaseModel):
    """Request model for inserting a document."""

    appId: str
    colName: str
    docData: dict


class CreateCollectionRequest(BaseModel):
    """Request model for creating a collection."""

    appId: str
    colName: str


class DeleteCollectionRequest(BaseModel):
    """Request model for deleting a collection."""

    appId: str
    colName: str


class ClearCollectionRequest(BaseModel):
    """Request model for clearing a collection."""

    appId: str
    colName: str


class DeleteDocumentByIdRequest(BaseModel):
    """Request model for deleting a document by its ID."""

    appId: str
    colName: str
    docId: str


class DeleteDocumentsByIdsRequest(BaseModel):
    """Request model for deleting documents by their IDs."""

    appId: str
    colName: str
    docIds: List[str]


class UpdateDocumentByIdRequest(BaseModel):
    """Request model for updating a document by its ID."""

    appId: str
    colName: str
    docId: str
    docData: dict


@router.post("/collections", response_model=BaseResponse)
async def get_collections(
    data: GetCollectionRequest, current_user=Depends(get_current_user)
):
    """
    Retrieves the list of collections for a given application.
    """
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        raise HTTPException(
            status_code=404, detail="Application not found or permission denied"
        )

    # This logic seems to be synchronizing a config collection with actual collections.
    app_collections_config = await dynamic_db.app_db(data.appId)["__config__"].find_one(
        {}
    )
    real_collections = await dynamic_db.app_collections(data.appId)
    if app_collections_config and len(real_collections) > 0:
        if set(app_collections_config.get("collections", [])) != set(real_collections):
            await dynamic_db.app_db(data.appId)["__config__"].find_one_and_update(
                {"create_by": "system"},
                {"$set": {"collections": real_collections}},
            )
        if "__config__" in real_collections:
            real_collections.remove("__config__")
        return BaseResponse(
            code=0,
            msg="Collections retrieved successfully",
            data={"data": real_collections},
        )
    elif not app_collections_config and len(real_collections) > 0:
        insert_data = {
            "create_at": datetime.now(),
            "update_at": datetime.now(),
            "create_by": "system",
            "collections": real_collections,
        }
        await dynamic_db.app_insert_document(data.appId, "__config__", insert_data)
        return BaseResponse(
            code=0,
            msg="Collections retrieved successfully",
            data={"data": real_collections},
        )
    else:
        return BaseResponse(code=0, msg="No collections found", data={"data": []})


@router.post("/documents", response_model=BaseResponse)
async def get_collection_documents(
    data: GetCollectionDocumentsRequest, current_user=Depends(get_current_user)
):
    """
    Retrieves documents from a specific collection with pagination.
    """
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        raise HTTPException(
            status_code=404, detail="Application not found or permission denied"
        )

    total_count = await dynamic_db.app_collection_documents_counts(
        data.appId, data.colName
    )
    documents = await dynamic_db.app_collection_documents(
        data.appId, data.colName, data.page, data.length
    )

    page_num = math.ceil(total_count / data.length) if data.length > 0 else 0

    return BaseResponse(
        code=0,
        msg="Documents retrieved successfully",
        data={
            "data": motor_result_serializer(documents),
            "pageNum": page_num,
            "pageSize": data.length,
            "total": total_count,
        },
    )


@router.post("/create_collection", response_model=BaseResponse)
async def create_collection(
    data: CreateCollectionRequest, current_user=Depends(get_current_user)
):
    """
    Creates a new collection in the application's database.
    """
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        raise HTTPException(
            status_code=404, detail="Application not found or permission denied"
        )

    existing_collections = await dynamic_db.app_collections(data.appId)
    if data.colName in existing_collections:
        return BaseResponse(
            code=409, msg="Collection with this name already exists", data={}
        )

    # Logic to manage a '__config__' collection.
    if not existing_collections:
        insert_data = {
            "create_at": datetime.now(),
            "update_at": datetime.now(),
            "create_by": "system",
            "collections": [data.colName],
        }
        await dynamic_db.app_insert_document(data.appId, "__config__", insert_data)
    else:
        await dynamic_db.app_db(data.appId)["__config__"].find_one_and_update(
            {"create_by": "system"},
            {"$push": {"collections": data.colName}},
        )

    # Create a dummy document to ensure collection is created.
    await dynamic_db.app_db(data.appId)[data.colName].insert_one({"_init": True})
    await dynamic_db.app_db(data.appId)[data.colName].delete_one({"_init": True})

    return BaseResponse(
        code=0,
        msg="Collection created successfully",
        data={"collection_name": data.colName},
    )


@router.post("/delete_collection", response_model=BaseResponse)
async def delete_collection(
    data: DeleteCollectionRequest, current_user=Depends(get_current_user)
):
    """
    Deletes a collection from the application's database.
    """
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        raise HTTPException(status_code=403, detail="Permission denied")

    doc_count = await dynamic_db.app_collection_documents_counts(
        data.appId, data.colName
    )
    if doc_count != 0:
        return BaseResponse(
            code=406,
            msg="Cannot delete a non-empty collection. Please clear it first.",
            data={},
        )

    await dynamic_db.app_db(data.appId)["__config__"].find_one_and_update(
        {"create_by": "system"},
        {"$pull": {"collections": data.colName}},
    )
    await dynamic_db.app_db(data.appId)[data.colName].drop()

    return BaseResponse(code=0, msg="Collection deleted successfully", data={})


@router.post("/clear_collection", response_model=BaseResponse)
async def clear_collection(
    data: ClearCollectionRequest, current_user=Depends(get_current_user)
):
    """
    Clears all documents from a collection.
    """
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        raise HTTPException(status_code=403, detail="Permission denied")

    collections = await dynamic_db.app_collections(data.appId)
    if data.colName not in collections:
        return BaseResponse(code=404, msg="Collection not found", data={})

    await dynamic_db.app_db(data.appId)[data.colName].delete_many({})
    return BaseResponse(code=0, msg="Collection cleared successfully", data={})


@router.post("/insert_document", response_model=BaseResponse)
async def insert_document(
    data: InsertDocumentRequest, current_user=Depends(get_current_user)
):
    """
    Inserts a new document into a collection.
    """
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        raise HTTPException(
            status_code=404, detail="Application not found or permission denied"
        )

    insert_result = await dynamic_db.app_insert_document(
        data.appId, data.colName, data.docData
    )

    return BaseResponse(
        code=0,
        msg="Document inserted successfully",
        data={"inserted_id": str(insert_result.inserted_id)},
    )


@router.post("/delete_document", response_model=BaseResponse)
async def delete_document(
    data: DeleteDocumentByIdRequest, current_user=Depends(get_current_user)
):
    """
    Deletes a document from a collection by its ID.
    """
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        raise HTTPException(
            status_code=404, detail="Application not found or permission denied"
        )

    delete_response = await dynamic_db.app_delete_document_by_id(
        data.appId, data.colName, data.docId
    )
    if delete_response.deleted_count == 0:
        return BaseResponse(
            code=404, msg="Document not found", data={"doc_id": data.docId}
        )

    return BaseResponse(
        code=0, msg="Document deleted successfully", data=delete_response.raw_result
    )


@router.post("/delete_documents", response_model=BaseResponse)
async def delete_documents(
    data: DeleteDocumentsByIdsRequest, current_user=Depends(get_current_user)
):
    """
    Deletes multiple documents from a collection by their IDs.
    """
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        raise HTTPException(
            status_code=404, detail="Application not found or permission denied"
        )
    try:
        delete_response = await dynamic_db.app_delete_documents_by_ids(
            data.appId, data.colName, data.docIds
        )
    except ValueError as e:
        raise APIException(code=400, msg=str(e))

    if delete_response.deleted_count == 0:
        return BaseResponse(
            code=404, msg="No documents found to delete", data={"doc_ids": data.docIds}
        )

    return BaseResponse(
        code=0, msg=f"Successfully deleted {delete_response.deleted_count} documents."
    )


@router.post("/update_document", response_model=BaseResponse)
async def update_document(
    data: UpdateDocumentByIdRequest, current_user=Depends(get_current_user)
):
    """
    Updates a document in a collection by its ID.
    """
    app = await Application.find_one(
        Application.app_id == data.appId, Application.users == current_user.username
    )
    if not app:
        raise HTTPException(
            status_code=404, detail="Application not found or permission denied"
        )

    if "_id" in data.docData:
        del data.docData["_id"]

    update_response = await dynamic_db.app_update_document_by_id(
        data.appId, data.colName, data.docId, data.docData
    )

    if update_response.matched_count == 0:
        return BaseResponse(
            code=404, msg="Document not found to update", data={"doc_id": data.docId}
        )

    return BaseResponse(
        code=0,
        msg="Document updated successfully",
        data=update_response.raw_result,
    )
