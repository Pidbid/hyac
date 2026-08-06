import unittest
from unittest.mock import AsyncMock, patch

from core import runtime_status_manager


class RuntimeStatusSynchronizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_status_sync_delegates_to_the_authoritative_reconciler(self):
        reconcile = AsyncMock()

        with patch.object(
            runtime_status_manager,
            "reconcile_running_apps",
            reconcile,
        ):
            await runtime_status_manager.sync_runtime_status()

        reconcile.assert_awaited_once_with()

    async def test_reconciler_failure_is_contained_for_the_scheduler(self):
        reconcile = AsyncMock(side_effect=RuntimeError("temporary failure"))
        with patch.object(
            runtime_status_manager,
            "reconcile_running_apps",
            reconcile,
        ):
            await runtime_status_manager.sync_runtime_status()

        reconcile.assert_awaited_once_with()


if __name__ == "__main__":
    unittest.main()
