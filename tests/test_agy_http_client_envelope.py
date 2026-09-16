import unittest

from app.core.agy_http_client import _build_envelope


class TestAgyHttpClientEnvelope(unittest.TestCase):
    def test_claude_code_system_is_sent_as_user_context(self):
        body = _build_envelope(
            "project",
            "gemini-3.8-flash-high",
            [{"role": "user", "parts": [{"text": "hello"}]}],
            system="x-anthropic-billing-header: test; You are Claude Code",
        )

        request = body["request"]
        self.assertNotIn("systemInstruction", request)
        self.assertEqual(request["contents"][0]["role"], "user")
        self.assertIn("You are Claude Code", request["contents"][0]["parts"][0]["text"])
        self.assertEqual(request["contents"][1]["parts"][0]["text"], "hello")


if __name__ == "__main__":
    unittest.main()
