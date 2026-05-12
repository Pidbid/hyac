from collections.abc import Mapping, Sequence
from typing import Any


async def aggregate_to_list(
    document_model: type[Any], pipeline: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Run Beanie aggregation and return all documents as a list."""
    query = document_model.aggregate(list(pipeline))
    aggregate_cursor = await query.get_cursor()
    return await aggregate_cursor.to_list(length=None)
