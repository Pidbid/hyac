# routers/services/database.py
import math
from datetime import datetime
from typing import Literal, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from pymongo import ASCENDING, DESCENDING, TEXT
from pymongo.errors import PyMongoError

from core.database_dynamic import dynamic_db
from core.jwt_auth import get_current_user
from core.utils import mongodb_result_serializer
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


class IndexField(BaseModel):
    """Request model for one index field."""

    field: str
    direction: Literal["asc", "desc", "text"]


class GetCollectionIndexesRequest(BaseModel):
    """Request model for getting indexes from a collection."""

    appId: str
    colName: str


class CreateIndexRequest(BaseModel):
    """Request model for creating an index."""

    appId: str
    colName: str
    keys: List[IndexField]
    unique: bool = False
    sparse: bool = False
    expireAfterSeconds: int | None = None


class DropIndexRequest(BaseModel):
    """Request model for dropping an index."""

    appId: str
    colName: str
    indexName: str


class UpdateIndexRequest(CreateIndexRequest):
    """Request model for replacing an index."""

    oldIndexName: str


INDEX_DIRECTION_MAP = {
    "asc": ASCENDING,
    "desc": DESCENDING,
    "text": TEXT,
}


async def validate_database_access(app_id: str, username: str):
    """Validate that the current user can manage the app database."""
    app = await Application.find_one(
        Application.app_id == app_id, Application.users == username
    )
    if not app:
        raise HTTPException(
            status_code=404, detail="Application not found or permission denied"
        )
    return app


async def validate_collection_exists(app_id: str, col_name: str):
    """Validate that a collection exists in the app database."""
    collections = await dynamic_db.app_collections(app_id)
    if col_name not in collections:
        raise APIException(code=404, msg="Collection not found")


def build_index_keys(keys: List[IndexField]):
    """Convert frontend index fields into a PyMongo index key specification."""
    if not keys:
        raise APIException(code=400, msg="Index keys cannot be empty")

    index_keys = []
    for item in keys:
        field = item.field.strip()
        if not field:
            raise APIException(code=400, msg="Index field cannot be empty")
        if field.startswith("$") or "\x00" in field:
            raise APIException(code=400, msg="Invalid index field name")
        index_keys.append((field, INDEX_DIRECTION_MAP[item.direction]))

    return index_keys


def build_index_options(data: CreateIndexRequest):
    """Build safe PyMongo index options from request data."""
    options = {}
    if data.unique:
        options["unique"] = True
    if data.sparse:
        options["sparse"] = True
    if data.expireAfterSeconds is not None:
        if data.expireAfterSeconds < 0:
            raise APIException(code=400, msg="TTL seconds must be greater than or equal to 0")
        if len(data.keys) != 1:
            raise APIException(code=400, msg="TTL indexes only support a single field")
        options["expireAfterSeconds"] = data.expireAfterSeconds

    return options


def normalize_index_keys(index: dict):
    """Return user-facing index keys from MongoDB index metadata."""
    keys = []
    weights = index.get("weights", {})

    for field, direction in index.get("key", {}).items():
        if field == "_fts":
            keys.extend((weighted_field, TEXT) for weighted_field in weights)
            continue
        if field == "_ftsx":
            continue
        keys.append((field, direction))

    return keys


def serialize_index_key_direction(direction):
    """Serialize a PyMongo index direction for the frontend."""
    if direction == ASCENDING:
        return "asc"
    if direction == DESCENDING:
        return "desc"
    if direction == TEXT:
        return "text"
    return str(direction)


def serialize_index(index: dict):
    """Serialize MongoDB index metadata for the frontend."""
    keys = [
        {"field": field, "direction": serialize_index_key_direction(direction)}
        for field, direction in normalize_index_keys(index)
    ]

    return {
        "name": index.get("name", ""),
        "keys": keys,
        "unique": bool(index.get("unique", False)),
        "sparse": bool(index.get("sparse", False)),
        "expireAfterSeconds": index.get("expireAfterSeconds"),
        "isDefault": index.get("name") == "_id_",
    }


def build_index_restore_args(index: dict):
    """Build PyMongo create_index args from an existing MongoDB index document."""
    keys = normalize_index_keys(index)

    options = {}
    for option_key in [
        "name",
        "unique",
        "sparse",
        "expireAfterSeconds",
        "partialFilterExpression",
        "collation",
        "weights",
        "default_language",
        "language_override",
        "textIndexVersion",
        "2dsphereIndexVersion",
        "bits",
        "min",
        "max",
        "bucketSize",
        "wildcardProjection",
        "hidden",
    ]:
        if option_key in index:
            options[option_key] = index[option_key]

    return keys, options


def find_index_by_name(indexes: list[dict], index_name: str):
    """Find an index document by name."""
    return next((index for index in indexes if index.get("name") == index_name), None)


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
            "data": mongodb_result_serializer(documents),
            "pageNum": page_num,
            "pageSize": data.length,
            "total": total_count,
        },
    )


@router.post("/indexes", response_model=BaseResponse)
async def get_collection_indexes(
    data: GetCollectionIndexesRequest, current_user=Depends(get_current_user)
):
    """
    Retrieves indexes from a specific collection.
    """
    await validate_database_access(data.appId, current_user.username)
    await validate_collection_exists(data.appId, data.colName)

    indexes = await dynamic_db.app_collection_indexes(data.appId, data.colName)
    return BaseResponse(
        code=0,
        msg="Indexes retrieved successfully",
        data={"data": [serialize_index(index) for index in indexes]},
    )


@router.post("/create_index", response_model=BaseResponse)
async def create_index(data: CreateIndexRequest, current_user=Depends(get_current_user)):
    """
    Creates an index on a specific collection.
    """
    await validate_database_access(data.appId, current_user.username)
    await validate_collection_exists(data.appId, data.colName)

    index_keys = build_index_keys(data.keys)
    index_options = build_index_options(data)
    try:
        index_name = await dynamic_db.app_create_collection_index(
            data.appId, data.colName, index_keys, **index_options
        )
    except PyMongoError as e:
        raise APIException(code=400, msg=str(e))

    return BaseResponse(
        code=0,
        msg="Index created successfully",
        data={"indexName": index_name},
    )


@router.post("/drop_index", response_model=BaseResponse)
async def drop_index(data: DropIndexRequest, current_user=Depends(get_current_user)):
    """
    Drops an index from a specific collection.
    """
    await validate_database_access(data.appId, current_user.username)
    await validate_collection_exists(data.appId, data.colName)
    if data.indexName == "_id_":
        raise APIException(code=400, msg="Cannot drop the default _id_ index")

    try:
        await dynamic_db.app_drop_collection_index(
            data.appId, data.colName, data.indexName
        )
    except PyMongoError as e:
        raise APIException(code=400, msg=str(e))

    return BaseResponse(code=0, msg="Index dropped successfully", data={})


@router.post("/update_index", response_model=BaseResponse)
async def update_index(data: UpdateIndexRequest, current_user=Depends(get_current_user)):
    """
    Replaces an index by dropping the old index and creating a new one.
    """
    await validate_database_access(data.appId, current_user.username)
    await validate_collection_exists(data.appId, data.colName)
    if data.oldIndexName == "_id_":
        raise APIException(code=400, msg="Cannot modify the default _id_ index")

    index_keys = build_index_keys(data.keys)
    index_options = build_index_options(data)
    indexes = await dynamic_db.app_collection_indexes(data.appId, data.colName)
    old_index = find_index_by_name(indexes, data.oldIndexName)
    if not old_index:
        raise APIException(code=404, msg="Index not found")

    restore_keys, restore_options = build_index_restore_args(old_index)
    old_index_dropped = False
    try:
        await dynamic_db.app_drop_collection_index(
            data.appId, data.colName, data.oldIndexName
        )
        old_index_dropped = True
        index_name = await dynamic_db.app_create_collection_index(
            data.appId, data.colName, index_keys, **index_options
        )
    except PyMongoError as e:
        if old_index_dropped:
            try:
                await dynamic_db.app_create_collection_index(
                    data.appId, data.colName, restore_keys, **restore_options
                )
            except PyMongoError as restore_error:
                raise APIException(
                    code=500,
                    msg=f"Index update failed and original index restore failed: {restore_error}",
                )
            raise APIException(code=400, msg=f"{e}; original index restored")
        raise APIException(code=400, msg=str(e))

    return BaseResponse(
        code=0,
        msg="Index updated successfully",
        data={"indexName": index_name},
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

    return BaseResponse(code=0, msg="Document deleted successfully", data=data.docId)


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
        data=data.docId,
    )
