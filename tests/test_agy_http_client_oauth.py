import asyncio
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core import agy_http_client


class TestAgyHttpClientOAuthRetry(unittest.TestCase):
    def setUp(self):
        self._account_patch = patch.object(
            agy_http_client.pool_manager,
            "acquire_http_account",
            new_callable=AsyncMock,
            return_value=(None, None, None),
        )
        self._account_patch.start()

    def tearDown(self):
        self._account_patch.stop()

    def test_503_no_capacity_is_model_capacity_error_not_account_rate_limit(self):
        self.assertTrue(
            agy_http_client._is_model_capacity_error(
                503,
                '{"message":"No capacity available for model gemini-3.8-flash-high"}',
            )
        )
        self.assertFalse(agy_http_client._is_rate_limited(503, "No capacity available"))

    def test_title_prompt_suppresses_thought_text(self):
        self.assertTrue(
            agy_http_client._suppress_thought_text(
                "Write the title in Russian. Keep technical terms and code identifiers in their original form.",
                [],
            )
        )
        self.assertFalse(agy_http_client._suppress_thought_text("普通のプロンプト", []))

    def test_get_project_id_retries_on_401(self):
        async def _run():
            responses = [
                MagicMock(status_code=401, text="Unauthorized"),
                MagicMock(
                    status_code=200, text='{"cloudaicompanionProject":"proj-123"}'
                ),
            ]
            responses[1].json = lambda: {"cloudaicompanionProject": "proj-123"}

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post = AsyncMock(side_effect=responses)

            agy_http_client._cached_project_id = None
            with patch("httpx.AsyncClient", return_value=mock_client):
                with patch.object(
                    agy_http_client,
                    "_refresh_after_401",
                    new_callable=AsyncMock,
                    return_value="new-token",
                ) as mock_refresh:
                    project = await agy_http_client._get_project_id("old-token")
                    self.assertEqual(project, "proj-123")
                    mock_refresh.assert_called_once_with(
                        "old-token", account_id=None, proxy=None
                    )
                    self.assertEqual(mock_client.post.call_count, 2)

        asyncio.run(_run())

    def test_stream_completion_retries_on_401(self):
        async def _run():
            unauthorized = MagicMock(status_code=401)
            unauthorized.aread = AsyncMock(return_value=b"Unauthorized")

            ok_response = MagicMock(status_code=200)
            ok_response.aiter_lines = lambda: _async_lines(
                ['data: {"candidates":[{"content":{"parts":[{"text":"hi"}]}}]}']
            )

            stream_ctx = AsyncMock()
            stream_ctx.__aenter__ = AsyncMock(side_effect=[unauthorized, ok_response])
            stream_ctx.__aexit__ = AsyncMock(return_value=False)

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.stream = MagicMock(return_value=stream_ctx)

            with patch("httpx.AsyncClient", return_value=mock_client):
                with patch.object(
                    agy_http_client,
                    "get_access_token",
                    new_callable=AsyncMock,
                    return_value="token-a",
                ):
                    with patch.object(
                        agy_http_client,
                        "_get_project_id",
                        new_callable=AsyncMock,
                        return_value="proj-1",
                    ):
                        with patch.object(
                            agy_http_client,
                            "_refresh_after_401",
                            new_callable=AsyncMock,
                            return_value="token-b",
                        ) as mock_refresh:
                            chunks = []
                            async for item in agy_http_client.stream_completion(
                                [{"role": "user", "content": "hello"}]
                            ):
                                chunks.append(item)

            mock_refresh.assert_called_once()
            self.assertTrue(
                any(c.get("delta") == "hi" for c in chunks if isinstance(c, dict))
            )

        asyncio.run(_run())

    def test_stream_completion_retries_empty_then_succeeds(self):
        async def _run():
            empty_response = MagicMock(status_code=200)
            empty_response.aiter_lines = lambda: _async_lines(
                [
                    'data: {"candidates":[{"content":{"parts":[]},"finishReason":"MAX_TOKENS"}]}'
                ]
            )

            ok_response = MagicMock(status_code=200)
            ok_response.aiter_lines = lambda: _async_lines(
                [
                    'data: {"response":{"candidates":[{"content":{"parts":[{"text":"retry ok"}]}}]}}'
                ]
            )

            stream_ctxs = []
            for resp in (empty_response, ok_response):
                ctx = AsyncMock()
                ctx.__aenter__ = AsyncMock(return_value=resp)
                ctx.__aexit__ = AsyncMock(return_value=False)
                stream_ctxs.append(ctx)

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.stream = MagicMock(side_effect=stream_ctxs)

            with patch("httpx.AsyncClient", return_value=mock_client):
                with patch.object(
                    agy_http_client,
                    "get_access_token",
                    new_callable=AsyncMock,
                    return_value="token-a",
                ):
                    with patch.object(
                        agy_http_client,
                        "_get_project_id",
                        new_callable=AsyncMock,
                        return_value="proj-1",
                    ):
                        chunks = []
                        async for item in agy_http_client.stream_completion(
                            [{"role": "user", "content": "hello"}]
                        ):
                            chunks.append(item)

            self.assertEqual(mock_client.stream.call_count, 2)
            final = [c for c in chunks if "usage" in c][-1]
            self.assertEqual(final.get("text"), "retry ok")
            self.assertEqual(final.get("stop_reason"), "end_turn")

        asyncio.run(_run())

    def test_stream_completion_empty_after_retry_yields_error(self):
        async def _run():
            empty_response = MagicMock(status_code=200)
            empty_response.aiter_lines = lambda: _async_lines(
                [
                    'data: {"candidates":[{"content":{"parts":[]},"finishReason":"STOP"}]}'
                ]
            )

            stream_ctx = AsyncMock()
            stream_ctx.__aenter__ = AsyncMock(return_value=empty_response)
            stream_ctx.__aexit__ = AsyncMock(return_value=False)

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.stream = MagicMock(return_value=stream_ctx)

            with patch.dict(os.environ, {"AGY_HTTP_EMPTY_AS_EMPTY_CONTENT": "false"}):
                with patch("httpx.AsyncClient", return_value=mock_client):
                    with patch.object(
                        agy_http_client,
                        "get_access_token",
                        new_callable=AsyncMock,
                        return_value="token-a",
                    ):
                        with patch.object(
                            agy_http_client,
                            "_get_project_id",
                            new_callable=AsyncMock,
                            return_value="proj-1",
                        ):
                            chunks = []
                            async for item in agy_http_client.stream_completion(
                                [{"role": "user", "content": "hello"}]
                            ):
                                chunks.append(item)

            self.assertEqual(mock_client.stream.call_count, 2)
            final = [c for c in chunks if "usage" in c][-1]
            self.assertEqual(final.get("stop_reason"), "error")
            self.assertIn("empty response", final.get("error", "").lower())

        asyncio.run(_run())

    def test_stream_completion_empty_stop_reason_returns_end_turn_when_flag_enabled(
        self,
    ):
        async def _run():
            empty_response = MagicMock(status_code=200)
            empty_response.aiter_lines = lambda: _async_lines(
                [
                    'data: {"candidates":[{"content":{"parts":[]},"finishReason":"STOP"}]}'
                ]
            )

            stream_ctx = AsyncMock()
            stream_ctx.__aenter__ = AsyncMock(return_value=empty_response)
            stream_ctx.__aexit__ = AsyncMock(return_value=False)

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.stream = MagicMock(return_value=stream_ctx)

            with patch.dict(os.environ, {"AGY_HTTP_EMPTY_AS_EMPTY_CONTENT": "true"}):
                with patch("httpx.AsyncClient", return_value=mock_client):
                    with patch.object(
                        agy_http_client,
                        "get_access_token",
                        new_callable=AsyncMock,
                        return_value="token-a",
                    ):
                        with patch.object(
                            agy_http_client,
                            "_get_project_id",
                            new_callable=AsyncMock,
                            return_value="proj-1",
                        ):
                            chunks = []
                            async for item in agy_http_client.stream_completion(
                                [{"role": "user", "content": "hello"}]
                            ):
                                chunks.append(item)

            self.assertEqual(mock_client.stream.call_count, 2)
            final = [c for c in chunks if "usage" in c][-1]
            self.assertEqual(final.get("stop_reason"), "end_turn")
            self.assertEqual(final.get("text"), "")
            self.assertEqual(final.get("tool_calls"), [])
            self.assertNotIn("error", final)

        asyncio.run(_run())


async def _async_lines(lines):
    for line in lines:
        yield line


if __name__ == "__main__":
    unittest.main()
