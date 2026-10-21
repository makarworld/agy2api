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

    def test_gemini_exhausted_does_not_block_when_claude_has_quota(self):
        self.assertTrue(
            pool_manager.has_usable_model_quota({"gemini_5h": 0.0, "claude_5h": 0.79})
        )
        self.assertFalse(
            pool_manager.has_usable_model_quota({"gemini_5h": 0.0, "claude_5h": 0.0})
        )
        self.assertTrue(pool_manager.has_usable_model_quota({}))

    def test_apply_quota_cooldown_skips_when_claude_has_headroom(self):
        async def _run():
            with patch.object(pool_manager.account_store, "mark_account_rate_limited") as mark_rl, \
                patch.object(pool_manager.stats_store, "upsert_pool_account_state", new=AsyncMock()) as upsert:
                result = await pool_manager.apply_quota_cooldown(
                    "acc-1",
                    {
                        "gemini_5h": 0.0,
                        "claude_5h": 1.0,
                        "gemini_5h_reset": "2099-01-01T00:00:00Z",
                    },
                )
                self.assertIsNone(result)
                mark_rl.assert_not_called()
                upsert.assert_not_called()

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
