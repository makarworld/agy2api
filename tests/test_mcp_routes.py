import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from app.main import app
from app.core.security import API_KEY


class TestMcpRoutes(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.headers = {"Authorization": f"Bearer {API_KEY}"}

    def test_mcp_unauthorized(self):
        resp = self.client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        self.assertEqual(resp.status_code, 401)

    def test_mcp_initialize(self):
        resp = self.client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": "1", "method": "initialize"},
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("jsonrpc"), "2.0")
        self.assertEqual(data.get("id"), "1")
        self.assertIn("serverInfo", data.get("result", {}))

    def test_mcp_tools_list(self):
        resp = self.client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": "2", "method": "tools/list"},
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        tools = resp.json().get("result", {}).get("tools", [])
        tool_names = [t["name"] for t in tools]
        self.assertIn("get_stats_summary", tool_names)
        self.assertIn("get_recent_errors", tool_names)
        self.assertIn("get_requests", tool_names)
        self.assertIn("get_pool_accounts_and_limits", tool_names)

    def test_mcp_tools_call_get_stats_summary(self):
        resp = self.client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": "3",
                "method": "tools/call",
                "params": {"name": "get_stats_summary", "arguments": {}},
            },
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        content = resp.json().get("result", {}).get("content", [])
        self.assertTrue(len(content) > 0)
        parsed = json.loads(content[0]["text"])
        self.assertIn("uptime_seconds", parsed)
        self.assertIn("totals", parsed)

    def test_mcp_tools_call_get_pool_accounts_and_limits(self):
        resp = self.client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": "4",
                "method": "tools/call",
                "params": {"name": "get_pool_accounts_and_limits", "arguments": {}},
            },
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        content = resp.json().get("result", {}).get("content", [])
        self.assertTrue(len(content) > 0)
        parsed = json.loads(content[0]["text"])
        self.assertIn("accounts", parsed)


if __name__ == "__main__":
    unittest.main()
