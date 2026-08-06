import os
from copy import deepcopy
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from pymongo.errors import OperationFailure


os.environ.setdefault("DEV_MODE", "true")
os.environ.setdefault("SECRET_KEY", "test-secret-key-with-at-least-32-characters")

from core import migrations
from models.users_model import User


class _Cursor:
    def __init__(self, documents):
        self.documents = documents

    def sort(self, field, direction):
        reverse = direction < 0
        self.documents.sort(key=lambda item: item[field], reverse=reverse)
        return self

    async def to_list(self, length=None):
        return deepcopy(self.documents if length is None else self.documents[:length])


class _UserCollection:
    def __init__(
        self,
        documents,
        *,
        create_error=None,
        drop_error=None,
        concurrent_repair=False,
    ):
        self.documents = deepcopy(documents)
        self.indexes = {
            "_id_": {"key": [("_id", 1)], "unique": True},
            "username_1": {"key": [("username", 1)]},
        }
        self.create_error = create_error
        self.drop_error = drop_error
        self.concurrent_repair = concurrent_repair
        self.update_queries = []
        self.find_one_queries = []

    def find(self, *_args, **_kwargs):
        return _Cursor(self.documents)

    @staticmethod
    def _matches(document, query):
        for field, expected in query.items():
            if isinstance(expected, dict) and "$exists" in expected:
                if (field in document) is not expected["$exists"]:
                    return False
                if "$eq" in expected and document.get(field) != expected["$eq"]:
                    return False
            elif document.get(field) != expected:
                return False
        return True

    @staticmethod
    def _apply_update(document, update):
        for field, value in update.get("$set", {}).items():
            document[field] = value
        for field in update.get("$unset", {}):
            document.pop(field, None)
        for field, amount in update.get("$inc", {}).items():
            document[field] = document.get(field, 0) + amount

    async def update_one(self, query, update):
        self.update_queries.append(deepcopy(query))
        document = next(
            (item for item in self.documents if self._matches(item, query)),
            None,
        )
        if self.concurrent_repair:
            self.concurrent_repair = False
            rival_document = next(
                item for item in self.documents if item["_id"] == query["_id"]
            )
            self._apply_update(rival_document, update)
            return SimpleNamespace(matched_count=0)
        if document is None:
            return SimpleNamespace(matched_count=0)
        self._apply_update(document, update)
        return SimpleNamespace(matched_count=1)

    async def find_one(self, query, projection=None):
        self.find_one_queries.append(deepcopy(query))
        document = next(
            (item for item in self.documents if self._matches(item, query)),
            None,
        )
        if document is None:
            return None
        if projection is None:
            return deepcopy(document)
        return {
            key: deepcopy(value)
            for key, value in document.items()
            if key == "_id" or projection.get(key)
        }

    async def index_information(self):
        return deepcopy(self.indexes)

    async def drop_index(self, name):
        self.indexes.pop(name)
        if self.drop_error is not None:
            error = self.drop_error
            self.drop_error = None
            raise error

    async def create_index(self, keys, *, unique, name):
        if self.create_error is not None:
            raise self.create_error
        self.indexes[name] = {"key": list(keys), "unique": unique}
        return name


class UserIdentityMigrationTests(IsolatedAsyncioTestCase):
    async def test_raw_migration_renames_duplicates_and_installs_unique_index(self):
        collection = _UserCollection(
            [
                {
                    "_id": 1,
                    "username": "duplicate",
                    "disabled": False,
                    "refresh_token_hash": "first-refresh",
                    "token_version": 2,
                },
                {
                    "_id": 2,
                    "username": "duplicate",
                    "disabled": False,
                    "refresh_token_hash": "second-refresh",
                    "token_version": 4,
                },
                {
                    "_id": 3,
                    "username": "unique-user",
                    "disabled": False,
                    "refresh_token_hash": "third-refresh",
                    "token_version": 1,
                },
            ]
        )
        database = {"users": collection}

        with patch.object(migrations.mongodb_manager, "db", database):
            await migrations.run_pre_beanie_migrations()
            first_result = deepcopy(collection.documents)
            await migrations.run_pre_beanie_migrations()

        self.assertEqual(first_result, collection.documents)
        self.assertEqual(len(collection.documents), 3)
        usernames = [item["username"] for item in collection.documents]
        self.assertEqual(len(usernames), len(set(usernames)))
        self.assertEqual(collection.documents[0]["username"], "duplicate")
        duplicate = next(item for item in collection.documents if item["_id"] == 2)
        self.assertNotEqual(duplicate["username"], "duplicate")
        self.assertTrue(duplicate["disabled"])
        self.assertIsNone(duplicate["refresh_token_hash"])
        self.assertEqual(duplicate["token_version"], 5)
        self.assertNotIn("username_1", collection.indexes)
        unique_indexes = [
            index
            for index in collection.indexes.values()
            if index.get("key") == [("username", 1)] and index.get("unique") is True
        ]
        self.assertEqual(len(unique_indexes), 1)

    async def test_raw_migration_index_failure_is_fatal(self):
        collection = _UserCollection(
            [{"_id": 1, "username": "operator"}],
            create_error=RuntimeError("cannot create unique index"),
        )
        with patch.object(migrations.mongodb_manager, "db", {"users": collection}):
            with self.assertRaisesRegex(RuntimeError, "cannot create unique index"):
                await migrations.run_pre_beanie_migrations()

    async def test_raw_migration_tolerates_concurrent_index_drop(self):
        collection = _UserCollection(
            [{"_id": 1, "username": "operator"}],
            drop_error=OperationFailure("index not found", code=27),
        )

        with patch.object(migrations.mongodb_manager, "db", {"users": collection}):
            await migrations.run_pre_beanie_migrations()

        unique_indexes = [
            index
            for index in collection.indexes.values()
            if index.get("key") == [("username", 1)]
            and index.get("unique") is True
        ]
        self.assertEqual(len(unique_indexes), 1)

    async def test_raw_migration_repairs_duplicates_with_identity_cas(self):
        collection = _UserCollection(
            [
                {"_id": 1, "username": "duplicate"},
                {"_id": 2, "username": "duplicate", "token_version": 7},
            ]
        )

        with patch.object(migrations.mongodb_manager, "db", {"users": collection}):
            await migrations.run_pre_beanie_migrations()

        self.assertEqual(
            collection.update_queries,
            [{"_id": 2, "username": "duplicate"}],
        )

    async def test_raw_migration_accepts_identical_concurrent_repair(self):
        collection = _UserCollection(
            [
                {"_id": 1, "username": "duplicate"},
                {"_id": 2, "username": "duplicate", "token_version": 7},
            ],
            concurrent_repair=True,
        )

        with patch.object(migrations.mongodb_manager, "db", {"users": collection}):
            await migrations.run_pre_beanie_migrations()

        repaired = next(item for item in collection.documents if item["_id"] == 2)
        self.assertEqual(repaired["token_version"], 8)
        self.assertEqual(collection.find_one_queries, [{"_id": 2}])

    async def test_security_v1_does_not_enable_legacy_users(self):
        class Collection:
            def __init__(self):
                self.calls = []

            async def find_one(self, _query):
                return None

            async def update_many(self, query, update):
                self.calls.append((query, update))

            async def insert_one(self, _document):
                return None

        collections = {
            name: Collection()
            for name in ("settings", "users", "applications", "functions", "tasks")
        }
        with patch.object(migrations.mongodb_manager, "db", collections):
            await migrations.run_security_migrations()

        user_update = collections["users"].calls[0][1]
        self.assertNotIn("disabled", user_update["$set"])

    def test_beanie_model_does_not_manage_the_raw_unique_index(self):
        self.assertFalse(getattr(User.Settings, "indexes", []))


if __name__ == "__main__":
    import unittest

    unittest.main()
