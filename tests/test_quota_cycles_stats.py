import time
import pytest
from app.core import stats_store


def test_account_quota_cycle_lifecycle_and_model_breakdown(tmp_path):
    db_file = str(tmp_path / "test_cycles.db")
    stats_store.init_db(db_file)

    acc = "acc_cycle_1"

    # 1. 100% quota triggers a new active cycle
    full_quota = {
        "gemini_5h": 1.0,
        "claude_5h": 1.0,
    }
    stats_store.on_quota_updated_sync(acc, full_quota)

    active = stats_store.get_account_active_cycle_sync(acc)
    assert active is not None
    assert active["is_active"] == 1
    assert active["fraction_spent"] == 0.0
    assert active["total_requests"] == 0

    # 2. Record requests with different models
    stats_store._record_request_sync(
        endpoint="openai-chat",
        model="claude-sonnet-4-6",
        pool_account=acc,
        prompt_tokens=1000,
        completion_tokens=200,
        cache_tokens=0,
        success=True,
        latency_ms=500,
        error_type=None,
    )
    stats_store._record_request_sync(
        endpoint="openai-chat",
        model="gemini-3.8-flash-high",
        pool_account=acc,
        prompt_tokens=500,
        completion_tokens=100,
        cache_tokens=0,
        success=True,
        latency_ms=200,
        error_type=None,
    )

    # 3. Quota check shows 5h dropped to 70% (30% spent)
    part_quota = {
        "gemini_5h": 0.70,
        "claude_5h": 1.0,
    }
    stats_store.on_quota_updated_sync(acc, part_quota)

    active = stats_store.get_account_active_cycle_sync(acc)
    assert active["total_requests"] == 2
    assert active["total_prompt_tokens"] == 1500
    assert active["total_completion_tokens"] == 300
    assert abs(active["fraction_spent"] - 0.30) < 0.01

    m_stats = active["model_stats"]
    assert "claude-sonnet-4-6" in m_stats
    assert m_stats["claude-sonnet-4-6"]["requests"] == 1
    assert m_stats["claude-sonnet-4-6"]["prompt_tokens"] == 1000
    assert m_stats["gemini-3.8-flash-high"]["requests"] == 1
    assert m_stats["gemini-3.8-flash-high"]["prompt_tokens"] == 500

    # 4. Quota resets to 100% -> Closes previous cycle and opens new one
    stats_store.on_quota_updated_sync(acc, full_quota)

    cycles = stats_store.get_account_quota_cycles_sync(acc, limit=10)
    assert len(cycles) == 2
    # The older closed cycle
    closed = [c for c in cycles if c["is_active"] == 0][0]
    assert closed["total_requests"] == 2
    assert closed["total_prompt_tokens"] == 1500

    # The new active cycle
    new_active = [c for c in cycles if c["is_active"] == 1][0]
    assert new_active["total_requests"] == 0
    assert new_active["total_prompt_tokens"] == 0
