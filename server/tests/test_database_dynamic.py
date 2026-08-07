import sys
from pathlib import Path
from unittest import IsolatedAsyncioTestCase


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.database_dynamic import DynamicDB  # noqa: E402


class FakeAsyncCursor:
    def __init__(self, items):
        self._items = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._items)
        except StopIteration as error:
            raise StopAsyncIteration from error


class FakeCollection:
    def __init__(self, indexes):
        self.indexes = indexes
        self.list_indexes_awaited = False

    async def list_indexes(self):
        self.list_indexes_awaited = True
        return FakeAsyncCursor(self.indexes)


class FakeDatabase:
    def __init__(self, collection):
        self.collection = collection

    def __getitem__(self, _name):
        return self.collection


class DynamicDatabaseTests(IsolatedAsyncioTestCase):
    async def test_awaits_pymongo_async_list_indexes_before_iteration(self):
        expected = [
            {"name": "_id_", "key": {"_id": 1}},
            {"name": "name_1", "key": {"name": 1}},
        ]
        collection = FakeCollection(expected)
        database = object.__new__(DynamicDB)
        database.app_db = lambda _app_id: FakeDatabase(collection)

        indexes = await database.app_collection_indexes("app", "items")

        self.assertTrue(collection.list_indexes_awaited)
        self.assertEqual(expected, indexes)
