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

    def test_default_agent_has_labels_tools_and_stable_session_id(self):
        body1 = _build_envelope(
            "my-project",
            "gemini-3.7-flash-high",
            [{"role": "user", "parts": [{"text": "hello"}]}],
            account_id="acc-123",
        )
        body2 = _build_envelope(
            "my-project",
            "gemini-3.7-flash-high",
            [{"role": "user", "parts": [{"text": "hello 2"}]}],
            account_id="acc-123",
        )

        req1 = body1["request"]
        # Stable session ID across same account
        self.assertEqual(body1["userAgent"], "antigravity")
        self.assertEqual(body1["requestType"], "agent")
        self.assertTrue(req1["sessionId"].startswith("-"))
        self.assertEqual(req1["sessionId"], body2["request"]["sessionId"])

        # Default 17 Antigravity tools attached
        self.assertIn("tools", req1)
        self.assertEqual(len(req1["tools"]), 17)

        # Labels generated and present
        self.assertIn("labels", req1)
        labels = req1["labels"]
        self.assertEqual(labels["model_enum"], "MODEL_PLACEHOLDER_M298")
        self.assertEqual(labels["last_step_index"], "0")
        self.assertIn("trajectory_id", labels)
        self.assertIn("request_id", labels)

    def test_checkpoint_request_type(self):
        body = _build_envelope(
            "my-project",
            "gemini-3.7-flash-high",
            [{"role": "user", "parts": [{"text": "title"}]}],
            request_type="checkpoint",
        )
        self.assertEqual(body["requestType"], "checkpoint")
        self.assertTrue(body["requestId"].startswith("checkpoint/"))
        self.assertNotIn("labels", body["request"])
        self.assertNotIn("tools", body["request"])


if __name__ == "__main__":
    unittest.main()
