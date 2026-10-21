import time
import pytest
from app.core import oauth_refresh, pool_manager, stats_store


def test_cached_quota_persistence_and_restore(tmp_path):
    db_file = str(tmp_path / "test_stats.db")
    stats_store.init_db(db_file)

    test_quota = {
        "gemini_5h": 0.85,
        "gemini_weekly": 0.95,
        "claude_5h": 1.0,
        "claude_weekly": 1.0,
        "gemini_5h_reset": "2026-10-06T18:00:00Z",
    }
    stats_store.save_cached_account_quota_sync("acc_test_1", test_quota, time.time())

    # Verify DB has cached quota
    state = stats_store.get_pool_account_state_sync("acc_test_1")
    assert state is not None
    assert state["last_quota_check_ts"] > 0

    restored = stats_store.get_cached_account_quota_db_sync("acc_test_1")
    assert restored["gemini_5h"] == 0.85


def test_should_refresh_account_quota_logic(tmp_path):
    db_file = str(tmp_path / "test_stats.db")
    stats_store.init_db(db_file)

    now = time.time()
    # Case 1: No usage, reset time in future -> Should NOT refresh
    stats_store._upsert_pool_account_state_sync(
        "acc_idle",
        last_used_ts=now - 500,
        last_quota_check_ts=now - 100,
        cached_quota_json='{"gemini_5h": 0.5, "gemini_5h_reset": "2030-01-01T00:00:00Z"}',
    )
    assert not pool_manager.should_refresh_account_quota("acc_idle")

    # Case 2: Had usage since last check -> SHOULD refresh
    stats_store._upsert_pool_account_state_sync(
        "acc_active",
        last_used_ts=now - 50,
        last_quota_check_ts=now - 200,
        cached_quota_json='{"gemini_5h": 0.9, "gemini_5h_reset": "2030-01-01T00:00:00Z"}',
    )
    assert pool_manager.should_refresh_account_quota("acc_active")

    # Case 3: Limit reached reset time in past -> SHOULD refresh
    stats_store._upsert_pool_account_state_sync(
        "acc_reset_due",
        last_used_ts=now - 500,
        last_quota_check_ts=now - 300,
        cached_quota_json='{"gemini_5h": 0.4, "gemini_5h_reset": "2020-01-01T00:00:00Z"}',
    )
    assert pool_manager.should_refresh_account_quota("acc_reset_due")
