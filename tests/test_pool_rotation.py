import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from app.core import pool_manager


class TestPoolRotationReasons(unittest.TestCase):
    def test_rotation_log_reason_helpers_are_available(self):
        self.assertTrue(callable(pool_manager.mark_rate_limited))

    def test_model_cooldown_does_not_block_other_models(self):
        async def _run():
            pool_manager._MODEL_COOLDOWNS.clear()
            with patch.object(pool_manager, "list_accounts", return_value=[{"id": "acc-1"}]), \
                patch.object(pool_manager.stats_store, "get_pool_account_state", new=AsyncMock(return_value={})):
                await pool_manager.mark_rate_limited("acc-1", 60, model="gemini-pro-agent")
                self.assertIsNone(await pool_manager.select_next_healthy_account(model="gemini-pro-agent"))
                self.assertIsNotNone(await pool_manager.select_next_healthy_account(model="gemini-3.8-flash-high"))

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
