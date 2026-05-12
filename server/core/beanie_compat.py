from collections.abc import Mapping, Sequence
from inspect import isawaitable
from typing import Any


async def aggregate_to_list(
    document_model: type[Any], pipeline: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Run Beanie aggregation across Motor and PyMongo async cursor APIs."""
    query = document_model.aggregate(list(pipeline))
    # Beanie keeps this legacy property name even when backed by PyMongo async.
    aggregate_cursor = query.motor_cursor
    if isawaitable(aggregate_cursor):
        aggregate_cursor = await aggregate_cursor
    return await aggregate_cursor.to_list(length=None)
