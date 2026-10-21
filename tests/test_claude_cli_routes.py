import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.claude_cli_routes import (
    find_claude_binary,
    read_current_gclaude_model,
)
from app.main import app


class TestClaudeCliRoutes(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.auth_headers = {"Authorization": "Bearer test-master-key"}

    def test_find_claude_binary_when_available(self):
        with patch("shutil.which", return_value="C:/bin/claude.exe"):
            found = find_claude_binary()
            self.assertIsNotNone(found)
            self.assertTrue(found.endswith("claude.exe"))

    def test_find_claude_binary_when_absent(self):
        with (
            patch("shutil.which", return_value=None),
            patch("os.path.isfile", return_value=False),
        ):
            self.assertIsNone(find_claude_binary())

    def test_get_status_endpoint(self):
        with (
            patch("app.api.claude_cli_routes.find_claude_binary", return_value="C:/Users/User/bin/claude.exe"),
            patch("app.core.key_manager._get_master_keys", return_value={"test-master-key"}),
        ):
            res = self.client.get("/v1/claude-cli/status", headers=self.auth_headers)
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data["installed"])
            self.assertIn("install_guide", data)
            self.assertIn("powershell", data["install_guide"])
            self.assertIn("npm", data["install_guide"])
            self.assertEqual(data["default_model"], "max-gem")

    def test_setup_claude_cli_creates_bat_and_sh_files(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with (
                patch("app.api.claude_cli_routes.get_user_bin_dir", return_value=tmp_dir),
                patch("app.core.key_manager._get_master_keys", return_value={"test-master-key"}),
            ):
                payload = {
                    "model": "max-gem",
                    "api_key": "sk-agy-custom-token-999",
                    "launch": False,
                }
                res = self.client.post("/v1/claude-cli/setup", json=payload, headers=self.auth_headers)
                self.assertEqual(res.status_code, 200)

                bat_path = os.path.join(tmp_dir, "gclaude.bat")
                sh_path = os.path.join(tmp_dir, "gclaude")

                self.assertTrue(os.path.exists(bat_path))
                self.assertTrue(os.path.exists(sh_path))

                with open(bat_path, "r", encoding="utf-8") as f:
                    bat_content = f.read()

                self.assertIn("ANTHROPIC_AUTH_TOKEN=sk-agy-custom-token-999", bat_content)
                self.assertIn("claude --model max-gem %*", bat_content)
                self.assertIn("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1", bat_content)
                self.assertIn("CLAUDE_CODE_AUTO_COMPACT_WINDOW=1000000", bat_content)
                self.assertIn("CLAUDE_CODE_EFFORT_LEVEL=max", bat_content)
                self.assertIn("ANTHROPIC_MODEL=max-gem", bat_content)
                self.assertIn("ANTHROPIC_DEFAULT_OPUS_MODEL=max-gem", bat_content)
                self.assertIn("ANTHROPIC_DEFAULT_SONNET_MODEL=max-gem", bat_content)
                self.assertIn("ANTHROPIC_DEFAULT_HAIKU_MODEL=max-gem", bat_content)
                self.assertIn("ANTHROPIC_DEFAULT_FABLE_MODEL=max-gem", bat_content)
                self.assertIn("CLAUDE_CODE_SUBAGENT_MODEL=max-gem", bat_content)
                self.assertIn("ANTHROPIC_BASE_URL=", bat_content)

                with open(sh_path, "r", encoding="utf-8") as f:
                    sh_content = f.read()

                self.assertIn('export ANTHROPIC_AUTH_TOKEN="sk-agy-custom-token-999"', sh_content)
                self.assertIn('export CLAUDE_CODE_AUTO_COMPACT_WINDOW="1000000"', sh_content)
                self.assertIn('export CLAUDE_CODE_EFFORT_LEVEL="max"', sh_content)
                self.assertIn('export ANTHROPIC_MODEL="max-gem"', sh_content)
                self.assertIn('export ANTHROPIC_DEFAULT_OPUS_MODEL="max-gem"', sh_content)
                self.assertIn('exec claude --model "max-gem" "$@"', sh_content)

                # Check read_current_gclaude_model helper
                with patch("app.api.claude_cli_routes.get_gclaude_bat_path", return_value=bat_path):
                    self.assertEqual(read_current_gclaude_model(), "max-gem")

    def test_setup_claude_cli_creates_backup_before_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with (
                patch("app.api.claude_cli_routes.get_user_bin_dir", return_value=tmp_dir),
                patch("app.core.key_manager._get_master_keys", return_value={"test-master-key"}),
            ):
                # 1. First setup
                res1 = self.client.post(
                    "/v1/claude-cli/setup",
                    json={"model": "max-gem", "api_key": "tok-1"},
                    headers=self.auth_headers,
                )
                self.assertEqual(res1.status_code, 200)

                # 2. Second setup with different model
                res2 = self.client.post(
                    "/v1/claude-cli/setup",
                    json={"model": "claude-sonnet-4-6", "api_key": "tok-2"},
                    headers=self.auth_headers,
                )
                self.assertEqual(res2.status_code, 200)

                bat_path = os.path.join(tmp_dir, "gclaude.bat")
                bak_path = os.path.join(tmp_dir, "gclaude.bat.bak")

                self.assertTrue(os.path.exists(bak_path))
                with open(bak_path, "r", encoding="utf-8") as f:
                    bak_content = f.read()
                self.assertIn("claude --model max-gem %*", bak_content)

                with open(bat_path, "r", encoding="utf-8") as f:
                    new_content = f.read()
                self.assertIn("claude --model claude-sonnet-4-6 %*", new_content)

    @patch("subprocess.Popen")
    @patch("sys.platform", "win32")
    def test_setup_claude_cli_launches_cmd_when_requested(self, mock_popen):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with (
                patch("app.api.claude_cli_routes.get_user_bin_dir", return_value=tmp_dir),
                patch("app.core.key_manager._get_master_keys", return_value={"test-master-key"}),
            ):
                res = self.client.post(
                    "/v1/claude-cli/setup",
                    json={"model": "max-gem", "launch": True},
                    headers=self.auth_headers,
                )
                self.assertEqual(res.status_code, 200)
                data = res.json()
                self.assertTrue(data["launched"])
                mock_popen.assert_called_once()
                cmd = mock_popen.call_args[0][0]
                self.assertEqual(cmd, ["cmd", "/c", "start", "cmd", "/k", "gclaude"])
