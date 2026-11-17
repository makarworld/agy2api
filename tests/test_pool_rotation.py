import asyncio
import time
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from app.core import pool_manager


class TestPoolRotationReasons(unittest.TestCase):
    def test_rotation_log_reason_helpers_are_available(self):
        self.assertTrue(callable(pool_manager.mark_rate_limited))

    def test_model_cooldown_does_not_block_other_models(self):
        async def _run():
            pool_manager._MODEL_COOLDOWNS.clear()
            with (
                patch.object(pool_manager, "list_accounts", return_value=[{"id": "acc-1"}]),
                patch.object(pool_manager.stats_store, "get_pool_account_state", new=AsyncMock(return_value={})),
            ):
                await pool_manager.mark_rate_limited("acc-1", 60, model="gemini-pro-agent")
                self.assertIsNone(await pool_manager.select_next_healthy_account(model="gemini-pro-agent"))
                self.assertIsNotNone(await pool_manager.select_next_healthy_account(model="gemini-3.8-flash-high"))

        asyncio.run(_run())

    def test_gemini_exhausted_does_not_block_when_claude_has_quota(self):
        self.assertTrue(pool_manager.has_usable_model_quota({"gemini_5h": 0.0, "claude_5h": 0.79}))
        self.assertFalse(pool_manager.has_usable_model_quota({"gemini_5h": 0.0, "claude_5h": 0.0}))
        self.assertTrue(pool_manager.has_usable_model_quota({}))

    def test_apply_quota_cooldown_skips_when_claude_has_headroom(self):
        async def _run():
            with (
                patch.object(pool_manager.account_store, "mark_account_rate_limited") as mark_rl,
                patch.object(pool_manager.stats_store, "upsert_pool_account_state", new=AsyncMock()) as upsert,
            ):
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

    def test_oauth_network_failure_does_not_place_model_in_cooldown_and_uses_existing_token(self):
        async def _run():
            pool_manager._MODEL_COOLDOWNS.clear()
            acc = {"id": "acc-1", "access_token": "fallback-token-xyz"}
            with (
                patch.object(pool_manager.account_store, "has_accounts", return_value=True),
                patch.object(pool_manager.account_store, "get_all_accounts", return_value=[acc]),
                patch.object(pool_manager.account_store, "get_account_by_id", return_value=acc),
                patch.object(pool_manager, "select_next_healthy_account", new=AsyncMock(return_value=acc)),
                patch.object(
                    pool_manager, "_ensure_oauth_fresh", side_effect=RuntimeError("All connection attempts failed")
                ),
                patch.object(pool_manager.stats_store, "set_active_account_id_db", new=AsyncMock()),
                patch.object(pool_manager.account_store, "mark_account_used"),
            ):
                acc_id, proxy, token = await pool_manager.acquire_http_account(model="gemini-3.8-flash-high")
                self.assertEqual(acc_id, "acc-1")
                self.assertEqual(token, "fallback-token-xyz")
                # Model must NOT be in _MODEL_COOLDOWNS
                self.assertNotIn("gemini-3.8-flash-high", pool_manager._MODEL_COOLDOWNS.get("acc-1", {}))

        asyncio.run(_run())

    def test_clear_model_cooldowns_resets_state(self):
        pool_manager._MODEL_COOLDOWNS.clear()
        pool_manager._MODEL_COOLDOWNS["acc-1"] = {"gemini-3.8-flash-high": 9999999999.0}
        self.assertIn("gemini-3.8-flash-high", pool_manager.get_account_model_cooldowns("acc-1"))

        pool_manager.clear_model_cooldowns("acc-1", model="gemini-3.8-flash-high")
        self.assertEqual(pool_manager.get_account_model_cooldowns("acc-1"), {})

    def test_current_session_matches_pool_by_refresh_token(self):
        with (
            patch.object(pool_manager, "_read_gemini_credentials", return_value=("live-rt", "user@example.com")),
            patch.object(pool_manager.account_store, "find_account_by_refresh_token", return_value={"id": "acc-found"}),
        ):
            matched = pool_manager.current_session_matches_pool()
            self.assertEqual(matched, "acc-found")

    def test_current_session_matches_pool_by_email_fallback(self):
        with (
            patch.object(pool_manager, "_read_gemini_credentials", return_value=(None, "user@example.com")),
            patch.object(pool_manager, "_find_account_by_email", return_value={"id": "acc-by-email"}),
        ):
            matched = pool_manager.current_session_matches_pool()
            self.assertEqual(matched, "acc-by-email")

    def test_delete_account_cleans_runtime_state_and_switches_active(self):
        async def _run():
            pool_manager._active_account_id = "acc-to-delete"
            pool_manager._MODEL_COOLDOWNS["acc-to-delete"] = {"gemini-pro": 999999.0}
            pool_manager._SESSION_AFFINITY["hash1"] = ("acc-to-delete", 999999.0)

            with (
                patch.object(pool_manager.account_store, "delete_account") as mock_del_acc,
                patch.object(
                    pool_manager,
                    "_load_manifest",
                    return_value={"accounts": [{"id": "acc-to-delete"}, {"id": "acc-remaining"}]},
                ),
                patch.object(pool_manager, "_save_manifest") as mock_save,
                patch.object(pool_manager, "list_accounts", return_value=[{"id": "acc-remaining"}]),
                patch.object(pool_manager.stats_store, "delete_pool_account_state", new=AsyncMock()) as mock_del_state,
                patch.object(pool_manager.stats_store, "set_active_account_id_db", new=AsyncMock()) as mock_set_active,
            ):
                await pool_manager.delete_account("acc-to-delete")

                mock_del_acc.assert_called_once_with("acc-to-delete")
                mock_del_state.assert_called_once_with("acc-to-delete")
                self.assertNotIn("acc-to-delete", pool_manager._MODEL_COOLDOWNS)
                self.assertNotIn("hash1", pool_manager._SESSION_AFFINITY)
                self.assertEqual(pool_manager.get_active_account_id(), "acc-remaining")
                mock_set_active.assert_called_once_with("acc-remaining")

        asyncio.run(_run())

    def test_acquire_http_account_refresh_failure_uses_fallback_with_multi_accounts(self):
        async def _run():
            now = time.time()
            acc1 = {
                "id": "acc-1",
                "access_token": "token-1",
                "token_expiry": now + 1800,
                "proxy": None,
            }
            acc2 = {
                "id": "acc-2",
                "access_token": "token-2",
                "token_expiry": now + 1800,
                "proxy": None,
            }
            with (
                patch.object(pool_manager.account_store, "has_accounts", return_value=True),
                patch.object(pool_manager, "select_next_healthy_account", new=AsyncMock(return_value={"id": "acc-1"})),
                patch.object(pool_manager.account_store, "get_account_by_id", return_value=acc1),
                patch.object(pool_manager.account_store, "get_all_accounts", return_value=[acc1, acc2]),
                patch.object(pool_manager.account_store, "mark_account_used"),
                patch.object(pool_manager.stats_store, "set_active_account_id_db", new=AsyncMock()),
                patch.object(
                    pool_manager,
                    "_ensure_oauth_fresh",
                    new=AsyncMock(side_effect=httpx.ConnectError("Network timeout")),
                ),
            ):
                account_id, proxy, token = await pool_manager.acquire_http_account()
                # Should stay on acc-1 using its valid fallback token, not rotating to acc-2!
                self.assertEqual(account_id, "acc-1")
                self.assertEqual(token, "token-1")

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
