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


if __name__ == "__main__":
    unittest.main()
