import json
import os
import tempfile
import unittest

from app.core.request_tracer import (
    get_current_trace,
    record_attempt,
    start_trace,
)
from app.core import stats_store


class TestRequestTracer(unittest.IsolatedAsyncioTestCase):
    def test_trace_lifecycle_and_rotation(self):
        trace = start_trace()
        self.assertIs(get_current_trace(), trace)

        # Attempt 1: fails on account 1
        record_attempt(
            raw_request={"model": "gemini-flash", "attempt": 1},
            raw_response={"error": "rate limited"},
            response_status=429,
            pool_account="acc_1",
        )
        self.assertEqual(trace.attempt_count, 1)
        self.assertEqual(trace.pool_account, "acc_1")
        self.assertEqual(trace.response_status, 429)

        # Attempt 2: succeeds on account 2
        record_attempt(
            raw_request={"model": "gemini-flash", "attempt": 2},
            raw_response={"candidates": [{"content": "hello"}]},
            response_status=200,
            pool_account="acc_2",
        )
        self.assertEqual(trace.attempt_count, 2)
        # Should record the LAST attempt
        self.assertEqual(trace.pool_account, "acc_2")
        self.assertEqual(trace.response_status, 200)
        self.assertIn('"attempt": 2', trace.raw_request_str)
        self.assertIn('"hello"', trace.raw_response_str)

    async def test_stats_store_records_raw_fields(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = os.path.join(tmp_dir, "test_stats.db")
            stats_store.init_db(db_path)

            req_obj = {"project": "test", "request": {"contents": [{"text": "prompt"}]}}
            resp_obj = {"candidates": [{"content": {"parts": [{"text": "response"}]}}]}

            await stats_store.record_request(
                endpoint="anthropic-chat",
                model="claude-sonnet-4-6",
                pool_account="acc_test",
                prompt_tokens=10,
                completion_tokens=20,
                cache_tokens=0,
                success=True,
                latency_ms=150,
                error_type=None,
                chat_id="chat_123",
                chat_title="Test Chat",
                prompt_preview="prompt",
                response_preview="response",
                raw_request=json.dumps(req_obj),
                raw_response=json.dumps(resp_obj),
                response_status=200,
            )

            reqs = await stats_store.get_requests_list(limit=10)
            self.assertEqual(reqs["total"], 1)
            row = reqs["requests"][0]
            self.assertEqual(row["response_status"], 200)
            self.assertEqual(row["pool_account"], "acc_test")
            self.assertIn('"project": "test"', row["raw_request"])
            self.assertIn('"response"', row["raw_response"])

            # Test pruning
            pruned = await stats_store.prune_old_request_previews(retention_seconds=0)
            self.assertEqual(pruned, 1)
            reqs_after = await stats_store.get_requests_list(limit=10)
            row_after = reqs_after["requests"][0]
            self.assertIsNone(row_after["raw_request"])
            self.assertIsNone(row_after["raw_response"])
            self.assertIsNone(row_after["prompt_preview"])
