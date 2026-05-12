import sys
from pathlib import Path
from unittest import IsolatedAsyncioTestCase


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.beanie_compat import aggregate_to_list  # noqa: E402


class FakeCursor:
    def __init__(self, items):
        self.items = items

    async def to_list(self, length=None):
        return self.items


class AggregationQuery:
    async def get_cursor(self):
        return FakeCursor([{"tag": "beanie2"}])


class FunctionMetricDocument:
    @staticmethod
    def aggregate(pipeline):
        return AggregationQuery()


class AggregateToListTest(IsolatedAsyncioTestCase):
    async def test_returns_beanie2_aggregation_results(self):
        result = await aggregate_to_list(FunctionMetricDocument, [])

        self.assertEqual(result, [{"tag": "beanie2"}])
