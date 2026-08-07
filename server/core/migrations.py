"""Idempotent data migrations required by security releases."""

from datetime import datetime, timezone
from hashlib import sha256

from pymongo import ASCENDING
from pymongo.errors import OperationFailure

from core.database import mongodb_manager
from core.environment_contract import RESERVED_ENV_KEYS


SECURITY_MIGRATION = "security-boundary-v1"
RESERVED_ENV_MIGRATION = "reserved-environment-v2"
LIFECYCLE_REVISION_MIGRATION = "lifecycle-revision-v3"
RUNTIME_AUTHORITY_MIGRATION = "runtime-authority-v4"
SETTINGS_REVISION_MIGRATION = "settings-revisions-v5"
TASK_PUBLICATION_MIGRATION = "task-publication-v6"
RUNTIME_CLEANUP_OWNERSHIP_MIGRATION = "runtime-cleanup-ownership-v7"
FUNCTION_AUTH_DEFAULT_MIGRATION = "function-auth-default-v8"


def _username_index_keys(index: dict) -> list[tuple[str, int]]:
    keys = index.get("key", [])
    return list(keys.items()) if isinstance(keys, dict) else list(keys)


def _legacy_username(document: dict, reserved: set[str]) -> str:
    seed = f"{document.get('username')!r}:{document['_id']}"
    digest = sha256(seed.encode("utf-8")).hexdigest()[:16]
    base = f"legacy-disabled-{digest}"
    candidate = base
    suffix = 0
    while candidate in reserved:
        suffix += 1
        candidate = f"{base}-{suffix}"
    return candidate


async def run_pre_beanie_migrations() -> None:
    """Normalize legacy identities and install the manual unique username index."""
    users_collection = mongodb_manager.db["users"]
    documents = await (
        users_collection.find({}, projection={"username": 1})
        .sort("_id", ASCENDING)
        .to_list(length=None)
    )
    reserved = {
        username
        for document in documents
        if isinstance((username := document.get("username")), str)
        and bool(username.strip())
    }
    seen: set[str] = set()
    now = datetime.now(timezone.utc)

    for document in documents:
        username = document.get("username")
        is_valid = isinstance(username, str) and bool(username.strip())
        if is_valid and username not in seen:
            seen.add(username)
            continue

        replacement = _legacy_username(document, reserved | seen)
        identity_filter: dict = {"_id": document["_id"]}
        if "username" not in document:
            identity_filter["username"] = {"$exists": False}
        elif username is None:
            identity_filter["username"] = {"$exists": True, "$eq": None}
        else:
            identity_filter["username"] = username
        result = await users_collection.update_one(
            identity_filter,
            {
                "$set": {
                    "username": replacement,
                    "disabled": True,
                    "refresh_token_hash": None,
                    "updated_at": now,
                },
                "$unset": {"refresh_token": ""},
                "$inc": {"token_version": 1},
            },
        )
        if result.matched_count == 0:
            current = await users_collection.find_one(
                {"_id": document["_id"]},
                projection={
                    "username": 1,
                    "disabled": 1,
                    "refresh_token": 1,
                    "refresh_token_hash": 1,
                },
            )
            if (
                current is None
                or current.get("username") != replacement
                or current.get("disabled") is not True
                or current.get("refresh_token_hash") is not None
                or "refresh_token" in current
            ):
                raise RuntimeError(
                    "Concurrent legacy username migration produced an "
                    "unexpected identity state"
                )
        reserved.add(replacement)
        seen.add(replacement)

    indexes = await users_collection.index_information()
    has_unique_username_index = False
    for name, index in indexes.items():
        if _username_index_keys(index) != [("username", ASCENDING)]:
            continue
        if index.get("unique") is True:
            has_unique_username_index = True
        else:
            try:
                await users_collection.drop_index(name)
            except OperationFailure as exc:
                if exc.code != 27:
                    raise

    if not has_unique_username_index:
        await users_collection.create_index(
            [("username", ASCENDING)],
            unique=True,
            name="username_unique",
        )


async def run_security_migrations() -> None:
    settings_collection = mongodb_manager.db["settings"]
    if not await settings_collection.find_one({"name": SECURITY_MIGRATION}):
        now = datetime.now(timezone.utc)
        await mongodb_manager.db["users"].update_many(
            {},
            {
                "$unset": {"refresh_token": ""},
                "$set": {
                    "refresh_token_hash": None,
                    "token_version": 1,
                },
            },
        )
        await mongodb_manager.db["applications"].update_many(
            {"cors.allow_origins": "*", "cors.allow_credentials": True},
            {"$set": {"cors.allow_credentials": False}},
        )
        await mongodb_manager.db["functions"].update_many(
            {},
            [
                {
                    "$set": {
                        "memory_limit": {
                            "$min": [
                                4096,
                                {
                                    "$max": [
                                        128,
                                        {"$ifNull": ["$memory_limit", 128]},
                                    ]
                                },
                            ]
                        },
                        "timeout": {
                            "$min": [
                                300,
                                {
                                    "$max": [
                                        1,
                                        {"$ifNull": ["$timeout", 5]},
                                    ]
                                },
                            ]
                        },
                    }
                }
            ],
        )
        await mongodb_manager.db["tasks"].update_many(
            {},
            [
                {
                    "$set": {
                        "app_id": {"$ifNull": ["$app_id", "$payload.app_id"]},
                        "attempts": {"$ifNull": ["$attempts", 0]},
                        "lease_owner": None,
                        "lease_expires_at": None,
                        "next_attempt_at": None,
                        "last_error": {"$ifNull": ["$last_error", None]},
                    }
                }
            ],
        )
        await mongodb_manager.db["tasks"].update_many(
            {"status": "running", "lease_expires_at": None},
            {"$set": {"lease_expires_at": now}},
        )
        await settings_collection.insert_one(
            {
                "name": SECURITY_MIGRATION,
                "data": {"completed": True},
                "create_at": now,
                "update_at": now,
            }
        )

    if not await settings_collection.find_one(
        {"name": RESERVED_ENV_MIGRATION}
    ):
        now = datetime.now(timezone.utc)
        await mongodb_manager.db["applications"].update_many(
            {
                "environment_variables.key": {
                    "$in": sorted(RESERVED_ENV_KEYS)
                }
            },
            {
                "$pull": {
                    "environment_variables": {
                        "key": {"$in": sorted(RESERVED_ENV_KEYS)}
                    }
                }
            },
        )
        await settings_collection.insert_one(
            {
                "name": RESERVED_ENV_MIGRATION,
                "data": {"completed": True},
                "create_at": now,
                "update_at": now,
            }
        )

    if not await settings_collection.find_one(
        {"name": LIFECYCLE_REVISION_MIGRATION}
    ):
        now = datetime.now(timezone.utc)
        await mongodb_manager.db["applications"].update_many(
            {"lifecycle_revision": {"$exists": False}},
            {"$set": {"lifecycle_revision": 0}},
        )
        await settings_collection.insert_one(
            {
                "name": LIFECYCLE_REVISION_MIGRATION,
                "data": {"completed": True},
                "create_at": now,
                "update_at": now,
            }
        )

    if not await settings_collection.find_one(
        {"name": RUNTIME_AUTHORITY_MIGRATION}
    ):
        now = datetime.now(timezone.utc)
        applications_collection = mongodb_manager.db["applications"]
        for field, default in (
            ("runtime_generation", 0),
            ("runtime_token_hash", None),
            ("lifecycle_completed_task_id", None),
        ):
            await applications_collection.update_many(
                {field: {"$exists": False}},
                {"$set": {field: default}},
            )
        await settings_collection.insert_one(
            {
                "name": RUNTIME_AUTHORITY_MIGRATION,
                "data": {"completed": True},
                "create_at": now,
                "update_at": now,
            }
        )

    if not await settings_collection.find_one(
        {"name": SETTINGS_REVISION_MIGRATION}
    ):
        now = datetime.now(timezone.utc)
        applications_collection = mongodb_manager.db["applications"]
        for field in (
            "environment_revision",
            "cors_revision",
            "notification_revision",
            "ai_config_revision",
        ):
            await applications_collection.update_many(
                {field: {"$exists": False}},
                {"$set": {field: 0}},
            )
        await settings_collection.insert_one(
            {
                "name": SETTINGS_REVISION_MIGRATION,
                "data": {"completed": True},
                "create_at": now,
                "update_at": now,
            }
        )

    if not await settings_collection.find_one(
        {"name": TASK_PUBLICATION_MIGRATION}
    ):
        now = datetime.now(timezone.utc)
        tasks_collection = mongodb_manager.db["tasks"]
        for field in (
            "published_at",
            "published_status",
            "published_lifecycle_revision",
            "published_runtime_generation",
        ):
            await tasks_collection.update_many(
                {field: {"$exists": False}},
                {"$set": {field: None}},
            )
        await settings_collection.insert_one(
            {
                "name": TASK_PUBLICATION_MIGRATION,
                "data": {"completed": True},
                "create_at": now,
                "update_at": now,
            }
        )

    if not await settings_collection.find_one(
        {"name": RUNTIME_CLEANUP_OWNERSHIP_MIGRATION}
    ):
        now = datetime.now(timezone.utc)
        applications_collection = mongodb_manager.db["applications"]
        for field in (
            "runtime_cleanup_task_id",
            "runtime_cleanup_lease_owner",
            "runtime_cleanup_lease_expires_at",
        ):
            await applications_collection.update_many(
                {field: {"$exists": False}},
                {"$set": {field: None}},
            )
        await settings_collection.insert_one(
            {
                "name": RUNTIME_CLEANUP_OWNERSHIP_MIGRATION,
                "data": {"completed": True},
                "create_at": now,
                "update_at": now,
            }
        )

    if not await settings_collection.find_one(
        {"name": FUNCTION_AUTH_DEFAULT_MIGRATION}
    ):
        now = datetime.now(timezone.utc)
        await mongodb_manager.db["functions"].update_many(
            {"requires_auth": {"$exists": False}},
            {"$set": {"requires_auth": True}},
        )
        await settings_collection.insert_one(
            {
                "name": FUNCTION_AUTH_DEFAULT_MIGRATION,
                "data": {"completed": True},
                "create_at": now,
                "update_at": now,
            }
        )
