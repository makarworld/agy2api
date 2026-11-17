import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from fastapi.testclient import TestClient

from app.core.security import API_KEY
from app.main import app


class TestApiEndpoints(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.headers = {"Authorization": f"Bearer {API_KEY}"}

    def test_get_models(self):
        resp = self.client.get("/v1/models", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("data", data)
        self.assertTrue(len(data["data"]) > 0)
        self.assertEqual(data["object"], "list")

    @patch("app.api.routes.run_completion", new_callable=AsyncMock)
    def test_chat_completions_non_stream(self, mock_run):
        mock_run.return_value = {
            "text": "Hello world from AGY!",
            "usage": {
                "input_tokens": 10,
                "output_tokens": 5,
                "total_tokens": 15,
                "cache_read_tokens": 0,
            },
            "tool_calls": [],
            "stop_reason": "stop",
        }

        payload = {
            "model": "gemini-2.5-flash",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": False,
        }
        resp = self.client.post("/v1/chat/completions", json=payload, headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["object"], "chat.completion")
        self.assertEqual(len(data["choices"]), 1)
        self.assertEqual(data["choices"][0]["message"]["content"], "Hello world from AGY!")
        self.assertEqual(data["choices"][0]["finish_reason"], "stop")
        self.assertEqual(data["usage"]["completion_tokens"], 5)
        self.assertEqual(data["usage"]["prompt_tokens"], 10)

    @patch("app.api.routes.stream_agy_completion")
    def test_chat_completions_stream(self, mock_stream):
        async def fake_stream(*args, **kwargs):
            yield {"delta": "Hello "}
            yield {"delta": "stream!"}
            yield {"usage": {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7}}

        mock_stream.side_effect = fake_stream

        payload = {
            "model": "gemini-2.5-flash",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": True,
        }
        resp = self.client.post("/v1/chat/completions", json=payload, headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        lines = [line.strip() for line in resp.text.split("\n") if line.strip().startswith("data: ")]
        self.assertTrue(len(lines) >= 3)
        self.assertEqual(lines[-1], "data: [DONE]")

    @patch("app.api.anthropic_routes.run_completion", new_callable=AsyncMock)
    def test_anthropic_messages_endpoint(self, mock_run):
        mock_run.return_value = {
            "text": "Anthropic-compatible response",
            "usage": {
                "input_tokens": 12,
                "output_tokens": 4,
                "total_tokens": 16,
                "cache_read_tokens": 0,
            },
            "tool_calls": [],
            "stop_reason": "end_turn",
        }

        payload = {
            "model": "claude-3-5-sonnet",
            "messages": [{"role": "user", "content": "Hello Claude"}],
            "max_tokens": 1024,
        }
        resp = self.client.post(
            "/anthropic/v1/messages",
            json=payload,
            headers={
                "x-api-key": API_KEY,
                "anthropic-version": "2023-06-01",
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["type"], "message")
        self.assertEqual(data["role"], "assistant")
        self.assertEqual(data["content"][0]["text"], "Anthropic-compatible response")
        self.assertEqual(data["usage"]["input_tokens"], 12)
        self.assertEqual(data["usage"]["output_tokens"], 4)

    @patch("app.api.anthropic_routes.run_completion", new_callable=AsyncMock)
    def test_anthropic_non_stream_tool_calls_no_dict_text_leak(self, mock_run):
        mock_run.return_value = {
            "text": "",
            "usage": {
                "input_tokens": 100,
                "output_tokens": 15,
                "thinking_tokens": 0,
                "total_tokens": 115,
                "cache_read_tokens": 0,
            },
            "tool_calls": [
                {
                    "id": "toolu_123",
                    "name": "Read",
                    "input": {"file_path": "test.py"},
                }
            ],
            "stop_reason": "tool_use",
        }

        payload = {
            "model": "claude-3-5-sonnet",
            "messages": [{"role": "user", "content": "Read test.py"}],
            "max_tokens": 1024,
            "stream": False,
        }
        resp = self.client.post(
            "/anthropic/v1/messages",
            json=payload,
            headers={
                "x-api-key": API_KEY,
                "anthropic-version": "2023-06-01",
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["stop_reason"], "tool_use")
        # Must NOT contain a text block with Python dictionary representation
        self.assertEqual(len(data["content"]), 1)
        self.assertEqual(data["content"][0]["type"], "tool_use")
        self.assertEqual(data["content"][0]["name"], "Read")

    def test_audio_voices_endpoint(self):
        resp = self.client.get("/v1/audio/voices", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("voices", data)

    @patch("app.core.pool_manager.acquire_http_account", new_callable=AsyncMock)
    @patch("app.core.agy_http_client.get_access_token", new_callable=AsyncMock)
    @patch("app.core.agy_http_client._get_project_id", new_callable=AsyncMock)
    def test_stream_completion_midstream_error_aborts(self, mock_proj, mock_token, mock_acquire):
        from app.core.agy_http_client import stream_completion

        mock_acquire.return_value = ("test-acc", None, "test-token")
        mock_token.return_value = "test-token"
        mock_proj.return_value = "test-proj"

        async def run_test():
            class MockResponse:
                status_code = 200

                async def aiter_lines(self):
                    yield 'data: {"response": {"candidates": [{"content": {"parts": [{"text": "First part"}]}}]}}'
                    raise httpx.ReadError("Simulated connection drop")

            class MockStreamContext:
                async def __aenter__(self):
                    return MockResponse()

                async def __aexit__(self, exc_type, exc_val, exc_tb):
                    pass

            class MockClientInstance:
                def stream(self, *args, **kwargs):
                    return MockStreamContext()

                async def __aenter__(self):
                    return self

                async def __aexit__(self, exc_type, exc_val, exc_tb):
                    pass

            with patch("httpx.AsyncClient", return_value=MockClientInstance()):
                chunks = []
                with self.assertRaises(RuntimeError) as ctx:
                    async for piece in stream_completion(
                        messages=[{"role": "user", "content": "hello"}],
                        model="gemini-2.5-flash",
                    ):
                        chunks.append(piece)

                self.assertIn("Network error mid-stream", str(ctx.exception))
                self.assertTrue(len(chunks) >= 1)
                self.assertEqual(chunks[0]["delta"], "First part")

        import asyncio

        asyncio.run(run_test())

    @patch("app.core.pool_manager.acquire_http_account", new_callable=AsyncMock)
    @patch("app.core.agy_http_client.get_access_token", new_callable=AsyncMock)
    @patch("app.core.agy_http_client._get_project_id", new_callable=AsyncMock)
    def test_stream_completion_network_retry_before_content(self, mock_proj, mock_token, mock_acquire):
        from app.core.agy_http_client import stream_completion

        mock_acquire.side_effect = [
            ("test-acc", None, "test-token"),
            RuntimeError("All pool accounts are rate-limited or unhealthy"),
        ]
        mock_token.return_value = "test-token"
        mock_proj.return_value = "test-proj"

        async def run_test():
            attempt = 0

            class MockResponse:
                status_code = 200

                async def aiter_lines(self):
                    yield 'data: {"response": {"candidates": [{"content": {"parts": [{"text": "Success after retry"}]}}]}}'

            class MockStreamContext:
                def __init__(self, should_fail):
                    self.should_fail = should_fail

                async def __aenter__(self):
                    if self.should_fail:
                        raise httpx.ConnectError("Connection refused")
                    return MockResponse()

                async def __aexit__(self, exc_type, exc_val, exc_tb):
                    pass

            class MockClientInstance:
                def stream(self, *args, **kwargs):
                    nonlocal attempt
                    attempt += 1
                    return MockStreamContext(should_fail=(attempt == 1))

                async def __aenter__(self):
                    return self

                async def __aexit__(self, exc_type, exc_val, exc_tb):
                    pass

            with (
                patch("httpx.AsyncClient", return_value=MockClientInstance()),
                patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            ):
                chunks = []
                async for piece in stream_completion(
                    messages=[{"role": "user", "content": "hello"}],
                    model="gemini-2.5-flash",
                ):
                    chunks.append(piece)

                self.assertEqual(attempt, 2)
                mock_sleep.assert_called_once()
                self.assertTrue(any(c.get("delta") == "Success after retry" for c in chunks))

        import asyncio

        asyncio.run(run_test())

    @patch("app.api.routes.stream_agy_completion")
    def test_chat_completions_stream_midstream_error_raises(self, mock_stream):
        async def failing_stream(*args, **kwargs):
            yield {"delta": "Hello "}
            raise httpx.ReadError("Simulated midstream connection drop")

        mock_stream.side_effect = failing_stream

        payload = {
            "model": "gemini-2.5-flash",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": True,
        }
        with self.assertRaises(Exception):
            self.client.post("/v1/chat/completions", json=payload, headers=self.headers)

    @patch("app.api.anthropic_routes.stream_agy_completion")
    def test_anthropic_stream_midstream_error_raises(self, mock_stream):
        async def failing_stream(*args, **kwargs):
            yield {"delta": "Hello "}
            raise httpx.ReadError("Simulated midstream connection drop")

        mock_stream.side_effect = failing_stream

        payload = {
            "model": "claude-3-5-sonnet",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": True,
        }
        with self.assertRaises(Exception):
            self.client.post(
                "/anthropic/v1/messages",
                json=payload,
                headers={"x-api-key": API_KEY, "anthropic-version": "2023-06-01"},
            )

    @patch("app.api.anthropic_routes.run_completion", new_callable=AsyncMock)
    def test_anthropic_non_stream_error_returns_502(self, mock_run):
        mock_run.side_effect = RuntimeError("Upstream connection failure")

        payload = {
            "model": "claude-3-5-sonnet",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": False,
        }
        resp = self.client.post(
            "/anthropic/v1/messages",
            json=payload,
            headers={"x-api-key": API_KEY, "anthropic-version": "2023-06-01"},
        )
        self.assertEqual(resp.status_code, 502)

    def test_build_messages_cleans_orphaned_raw_json_tool_calls(self):
        from unittest.mock import MagicMock
        from app.api.anthropic_routes import _build_messages
        from app.core.file_handler import TempFileManager

        file_mgr = TempFileManager()
        msg1 = MagicMock(role="user", content="Hello")
        msg2 = MagicMock(role="assistant", content='{"name": "Bash", "input": {"command": "pwd"}}')
        msg3 = MagicMock(role="user", content="Next command please")

        normalized, _, _ = _build_messages(None, [msg1, msg2, msg3], file_mgr)
        self.assertEqual(len(normalized), 2)
        self.assertEqual(normalized[0]["role"], "user")
        self.assertEqual(normalized[1]["role"], "user")
        self.assertEqual(normalized[1]["content"], "Next command please")

    def test_build_messages_restores_raw_json_tool_calls_when_results_follow(self):
        from unittest.mock import MagicMock
        from app.api.anthropic_routes import _build_messages
        from app.core.file_handler import TempFileManager

        file_mgr = TempFileManager()
        msg1 = MagicMock(role="user", content="Run pwd")
        msg2 = MagicMock(role="assistant", content='{"name": "Bash", "input": {"command": "pwd"}}')
        msg3 = MagicMock(
            role="user",
            content=[{"type": "tool_result", "tool_use_id": "call_1", "content": "/home/user", "name": "Bash"}],
        )

        normalized, _, _ = _build_messages(None, [msg1, msg2, msg3], file_mgr)
        self.assertEqual(len(normalized), 3)
        self.assertEqual(normalized[1]["role"], "assistant")
        self.assertEqual(normalized[1]["content"], "")
        self.assertEqual(len(normalized[1]["tool_calls"]), 1)
        self.assertEqual(normalized[1]["tool_calls"][0]["name"], "Bash")
        self.assertEqual(normalized[1]["tool_calls"][0]["input"], {"command": "pwd"})

    @patch("app.api.anthropic_routes.stream_agy_completion")
    def test_anthropic_stream_start_error_returns_sse_error_event(self, mock_stream):
        async def failing_stream_at_start(*args, **kwargs):
            raise RuntimeError("All pool accounts are rate-limited or unhealthy (acc-1 (status=exhausted))")
            yield {"delta": "never"}

        mock_stream.side_effect = failing_stream_at_start

        payload = {
            "model": "claude-3-5-sonnet",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": True,
        }
        resp = self.client.post(
            "/anthropic/v1/messages",
            json=payload,
            headers={"x-api-key": API_KEY, "anthropic-version": "2023-06-01"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("event: error", resp.text)
        self.assertIn("All pool accounts are rate-limited", resp.text)


if __name__ == "__main__":
    unittest.main()
