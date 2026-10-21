import os
import unittest
from unittest.mock import AsyncMock, patch

from app.core import account_verification
from app.core.account_verification import (
    _build_launcher_html,
    clear_verification_cache,
    extract_verification_url,
    handle_verification_error,
    open_verification_in_browser,
    resolve_account_email,
)


class TestAccountVerification(unittest.TestCase):
    def setUp(self):
        clear_verification_cache()

    def tearDown(self):
        clear_verification_cache()

    def test_extract_verification_url_exact_sample(self):
        sample = (
            "OAuth error: https://accounts.google.com/v3/signin/continue?"
            "plt=AKgnsbvTDr7PaKPFisxrOFqcxj1n1MWb_DKQ1O1-5bymTmpjL9KZKowEjk-yJ_I-AtRAUSYvKaLIB99Fp_AP3dAOfmF-cUIy24ayCqz9s0jXRBg5UD6fkB1CaKxjm67lb0Qg20gsxXJn"
            "&continue=https://developers.google.com/gemini-code-assist/auth/auth_success_gemini&sarp=1&scc=1&flowName=GlifWebSignIn&authuser"
        )
        url = extract_verification_url(sample)
        self.assertIsNotNone(url)
        self.assertTrue(url.startswith("https://accounts.google.com/v3/signin/continue?plt="))
        self.assertIn("flowName=GlifWebSignIn", url)
        self.assertIn("auth_success_gemini", url)

    def test_extract_verification_url_json_and_html_escaped(self):
        json_sample = (
            '{"error": "interaction_required", "url": "https:\\/\\/accounts.google.com\\/v3\\/signin\\/continue?'
            'plt=12345&amp;continue=https:\\/\\/developers.google.com&amp;sarp=1"}'
        )
        url = extract_verification_url(json_sample)
        self.assertIsNotNone(url)
        self.assertTrue(url.startswith("https://accounts.google.com/v3/signin/continue?plt=12345&continue="))
        self.assertNotIn(r"\/", url)
        self.assertNotIn("&amp;", url)

    def test_extract_verification_url_returns_none_for_normal_errors(self):
        self.assertIsNone(extract_verification_url("HTTP 429: Rate limit exceeded"))
        self.assertIsNone(extract_verification_url("Connection refused: 127.0.0.1:8000"))
        self.assertIsNone(extract_verification_url(""))
        self.assertIsNone(extract_verification_url(None))

    def test_resolve_account_email_from_url(self):
        url = "https://accounts.google.com/v3/signin/continue?plt=123&authuser=john.doe%40gmail.com"
        email = resolve_account_email(url=url)
        self.assertEqual(email, "john.doe@gmail.com")

        url_cap = "https://accounts.google.com/v3/signin/continue?plt=123&Email=alice%40work.com"
        email_cap = resolve_account_email(url=url_cap)
        self.assertEqual(email_cap, "alice@work.com")

    def test_resolve_account_email_fallback(self):
        email = resolve_account_email(account_id="acc-999")
        self.assertEqual(email, "acc-999")

        email_empty = resolve_account_email()
        self.assertEqual(email_empty, "Google")

    def test_launcher_html_generation(self):
        url = "https://accounts.google.com/v3/signin/continue?plt=abc&sarp=1"
        email = "user@test.org"
        html = _build_launcher_html(url, email)

        self.assertIn("Пройдите проверку чтобы аккаунт ", html)
        self.assertIn('"user@test.org"', html)
        self.assertIn("имел доступ к подписке", html)
        self.assertIn(f'window.location.href = "{url}";', html)
        self.assertIn('href="https://accounts.google.com/v3/signin/continue?plt=abc&amp;sarp=1"', html)

    @patch("subprocess.Popen")
    @patch("sys.platform", "win32")
    def test_open_verification_in_browser_launches_windows_cmd(self, mock_popen):
        url = "https://accounts.google.com/v3/signin/continue?plt=test1"
        email = "dev@example.com"

        opened = open_verification_in_browser(url, email=email, force=True)
        self.assertTrue(opened)
        mock_popen.assert_called_once()
        args, kwargs = mock_popen.call_args
        cmd = args[0]
        self.assertEqual(cmd[:3], ["cmd", "/c", "start"])
        self.assertEqual(cmd[3], "")
        html_file = cmd[4]
        self.assertTrue(os.path.exists(html_file))
        with open(html_file, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("dev@example.com", content)
        self.assertIn("test1", content)

    @patch("subprocess.Popen")
    def test_verification_debounce_prevents_duplicate_browser_open(self, mock_popen):
        url = "https://accounts.google.com/v3/signin/continue?plt=debounce_test"
        email = "repeat@example.com"

        # First call opens browser
        res1 = open_verification_in_browser(url, email=email)
        self.assertTrue(res1)
        self.assertEqual(mock_popen.call_count, 1)

        # Second call within debounce window is ignored
        res2 = open_verification_in_browser(url, email=email)
        self.assertFalse(res2)
        self.assertEqual(mock_popen.call_count, 1)

        # Force bypasses debounce
        res3 = open_verification_in_browser(url, email=email, force=True)
        self.assertTrue(res3)
        self.assertEqual(mock_popen.call_count, 2)

    @patch("app.core.account_verification.open_verification_in_browser")
    def test_handle_verification_error(self, mock_open):
        err = "OAuth refresh failed: https://accounts.google.com/v3/signin/continue?plt=xyz&flowName=GlifWebSignIn"
        url = handle_verification_error(err, account_id="my-acc", email="my-acc@gmail.com")
        self.assertIsNotNone(url)
        self.assertIn("plt=xyz", url)
        mock_open.assert_called_once_with(url, email="my-acc@gmail.com", account_id="my-acc", force=False)

    @patch("httpx.AsyncClient")
    def test_oauth_refresh_triggers_verification_and_raises(self, mock_client_cls):
        import asyncio
        from app.core import oauth_refresh

        async def _run():
            verify_url = "https://accounts.google.com/v3/signin/continue?plt=err123&flowName=GlifWebSignIn"
            mock_resp = AsyncMock()
            mock_resp.status_code = 400
            mock_resp.text = f"interaction_required: {verify_url}"

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            with patch("app.core.account_verification.open_verification_in_browser") as mock_open:
                with self.assertRaises(RuntimeError) as cm:
                    await oauth_refresh.refresh_google_token("bad_refresh", account_id="test_acc")
                self.assertIn("OAuth refresh failed", str(cm.exception))
                mock_open.assert_called_once()
                opened_url = mock_open.call_args[0][0]
                self.assertIn("plt=err123", opened_url)

        asyncio.run(_run())

    def test_pool_rotation_on_verification_failure(self):
        import asyncio
        from app.core import pool_manager

        async def _run():
            accounts = [
                {"id": "acc-1", "name": "Account One", "email": "acc1@gmail.com", "access_token": "tok-1"},
                {"id": "acc-2", "name": "Account Two", "email": "acc2@gmail.com", "access_token": "tok-2"},
            ]

            async def fake_select(exclude=frozenset(), model=None, session_hash=None):
                for a in accounts:
                    if a["id"] not in exclude:
                        return a
                return None

            verify_url = "https://accounts.google.com/v3/signin/continue?plt=rotate_me&flowName=GlifWebSignIn"

            async def fake_refresh(proxy=None, pool_account_id=None, raise_on_error=False):
                if pool_account_id == "acc-1":
                    raise RuntimeError(f"Interaction needed: {verify_url}")

            with (
                patch.object(pool_manager.account_store, "has_accounts", return_value=True),
                patch.object(
                    pool_manager.account_store,
                    "get_account_by_id",
                    side_effect=lambda aid: next((a for a in accounts if a["id"] == aid), None),
                ),
                patch.object(pool_manager, "select_next_healthy_account", side_effect=fake_select),
                patch.object(pool_manager, "_ensure_oauth_fresh", side_effect=fake_refresh),
                patch(
                    "app.core.oauth_refresh.read_sqlite_access_token",
                    side_effect=lambda aid: f"tok-{aid[-1]}",
                ),
                patch.object(pool_manager.stats_store, "set_active_account_id_db", new=AsyncMock()),
                patch.object(pool_manager.account_store, "mark_account_used"),
                patch.object(pool_manager, "mark_rate_limited", new=AsyncMock()) as mock_mark_rl,
                patch("app.core.account_verification.open_verification_in_browser") as mock_open,
            ):
                acc_id, proxy, token = await pool_manager.acquire_http_account()
                self.assertEqual(acc_id, "acc-2")
                self.assertEqual(token, "tok-2")
                mock_open.assert_called_once()
                self.assertIn("rotate_me", mock_open.call_args[0][0])
                mock_mark_rl.assert_called_once()
                self.assertEqual(mock_mark_rl.call_args[0][0], "acc-1")

        asyncio.run(_run())
