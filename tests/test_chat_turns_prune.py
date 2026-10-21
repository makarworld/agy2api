import os
import pytest
from app.core import stats_store


def test_prune_chat_turns_preserves_counts_and_tokens(tmp_path):
    db_file = str(tmp_path / "test_prune.db")
    stats_store.init_db(db_file)

    chat_id = "test_chat_heavy"
    # Insert 15 turns
    for i in range(15):
        stats_store._record_request_sync(
            endpoint="anthropic-chat",
            model="claude-sonnet-4-6",
            pool_account="acc_1",
            prompt_tokens=100,
            completion_tokens=50,
            cache_tokens=0,
            success=True,
            latency_ms=100,
            error_type=None,
            chat_id=chat_id,
            chat_title="Heavy Chat",
            prompt_preview=f"Prompt turn {i} " + "A" * 500,
            response_preview=f"Response turn {i} " + "B" * 500,
            raw_request='{"messages": "large JSON ' + "X" * 1000 + '"}',
            raw_response='{"content": "large JSON ' + "Y" * 1000 + '"}',
        )

    # Verify initial state: 15 turns
    summary_before = stats_store._get_summary_sync(None)
    assert summary_before["totals"]["requests"] == 15
    assert summary_before["totals"]["prompt_tokens"] == 1500
    assert summary_before["totals"]["completion_tokens"] == 750

    chats_before = stats_store._get_chats_grouped_sync(limit=10)
    assert chats_before["total"] == 1
    assert chats_before["chats"][0]["total_requests"] == 15
    assert chats_before["chats"][0]["prompt_tokens"] == 1500

    # Prune keeping only the latest 5 turns
    pruned_count = stats_store.prune_chat_turns_sync(max_turns_to_keep=5)
    assert pruned_count == 10

    # 1. Row count and token totals must NOT change!
    summary_after = stats_store._get_summary_sync(None)
    assert summary_after["totals"]["requests"] == 15
    assert summary_after["totals"]["prompt_tokens"] == 1500
    assert summary_after["totals"]["completion_tokens"] == 750

    # 2. Chat total turns must NOT change!
    chats_after = stats_store._get_chats_grouped_sync(limit=10)
    assert chats_after["chats"][0]["total_requests"] == 15
    assert chats_after["chats"][0]["prompt_tokens"] == 1500

    # 3. Old turns have payloads cleared, new turns have full payloads intact
    all_reqs = stats_store._get_chat_requests_sync(chat_id)
    assert len(all_reqs) == 15
    # The first 10 requests (oldest) must have raw_request == None
    for r in all_reqs[:10]:
        assert r["raw_request"] is None
        assert r["raw_response"] is None
        assert r["prompt_preview"] == "[Turn payload pruned]"

    # The last 5 requests (newest) must retain raw_request
    for r in all_reqs[10:]:
        assert r["raw_request"] is not None
        assert r["raw_response"] is not None
        assert "Prompt turn" in r["prompt_preview"]
