import asyncio
import json
import os
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, patch

from app.core import oauth_refresh
from app.core.agy_runner import with_heartbeat


class TestOAuthRefresh(unittest.TestCase):
    def setUp(self):
        self._env = os.environ.copy()
        os.environ["ANTIGRAVITY_CLIENT_ID"] = "test-client-id"
        os.environ["ANTIGRAVITY_CLIENT_SECRET"] = "test-client-secret"
        os.environ["AGY_OAUTH_REFRESH_ENABLED"] = "true"
        os.environ["AGY_OAUTH_REFRESH_SKEW_SECONDS"] = "120"
        oauth_refresh.clear_active_credential_cache()
        for key in ("AGY_ACCESS_TOKEN", "AGY_BEARER_TOKEN"):
            os.environ.pop(key, None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)

    def test_parse_expiry_rfc3339(self):
        ts = oauth_refresh.parse_expiry("2026-05-20T17:19:27.123456789Z")
        self.assertGreater(ts, 0)

    def test_ensure_fresh_skips_valid_token(self):
        async def _run():
            with tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, "antigravity-cli", "antigravity-oauth-token")
                os.makedirs(os.path.dirname(path), exist_ok=True)
                data = {
                    "auth_method": "consumer",
                    "token": {
                        "access_token": "valid-token",
                        "refresh_token": "refresh-abc",
                        "expiry": oauth_refresh._format_expiry_rfc3339(3600),
                    },
                }
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f)

                with patch("app.core.oauth_refresh.verify_access_token", new_callable=AsyncMock, return_value=False):
                    with patch("app.core.oauth_refresh.refresh_google_token", new_callable=AsyncMock) as mock_refresh:
                        refreshed = await oauth_refresh.ensure_fresh_antigravity_token(tmp)
                        self.assertFalse(refreshed)
                        mock_refresh.assert_not_called()

        asyncio.run(_run())

    def test_ensure_fresh_refreshes_expired_token(self):
        async def _run():
            with tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, "antigravity-cli", "antigravity-oauth-token")
                os.makedirs(os.path.dirname(path), exist_ok=True)
                data = {
                    "auth_method": "consumer",
                    "token": {
                        "access_token": "stale-token",
                        "refresh_token": "refresh-abc",
                        "expiry": "2020-01-01T00:00:00.000000Z",
                    },
                }
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f)

                mock_response = {
                    "access_token": "new-access",
                    "refresh_token": "refresh-abc",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                }
                with patch("app.core.oauth_refresh.verify_access_token", new_callable=AsyncMock, return_value=False):
                    with patch(
                        "app.core.oauth_refresh.refresh_google_token",
                        new_callable=AsyncMock,
                        return_value=mock_response,
                    ):
                        refreshed = await oauth_refresh.ensure_fresh_antigravity_token(tmp)
                        self.assertTrue(refreshed)

                with open(path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                self.assertEqual(saved["token"]["access_token"], "new-access")
                self.assertEqual(saved["token"]["refresh_token"], "refresh-abc")

        asyncio.run(_run())

    def test_ensure_fresh_skips_valid_oauth_creds_json(self):
        async def _run():
            with tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, "oauth_creds.json")
                data = {
                    "access_token": "valid-token",
                    "refresh_token": "refresh-abc",
                    "scope": "openid",
                    "token_type": "Bearer",
                    "id_token": "eyJ-test",
                    "expiry_date": int((time.time() + 3600) * 1000),
                }
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f)

                with patch("app.core.oauth_refresh.verify_access_token", new_callable=AsyncMock, return_value=False):
                    with patch("app.core.oauth_refresh.refresh_google_token", new_callable=AsyncMock) as mock_refresh:
                        refreshed = await oauth_refresh.ensure_fresh_credentials(tmp)
                        self.assertFalse(refreshed)
                        mock_refresh.assert_not_called()

        asyncio.run(_run())

    def test_ensure_fresh_refreshes_expired_oauth_creds_json(self):
        async def _run():
            with tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, "oauth_creds.json")
                data = {
                    "access_token": "stale-token",
                    "refresh_token": "refresh-abc",
                    "scope": "openid cloud-platform",
                    "token_type": "Bearer",
                    "id_token": "eyJ-preserve",
                    "expiry_date": 1,
                }
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f)

                with patch("app.core.oauth_refresh.verify_access_token", new_callable=AsyncMock, return_value=False):
                    with patch(
                        "app.core.oauth_refresh.refresh_google_token",
                        new_callable=AsyncMock,
                        return_value={
                            "access_token": "new-access",
                            "refresh_token": "refresh-abc",
                            "token_type": "Bearer",
                            "expires_in": 3600,
                            "scope": "openid cloud-platform",
                            "id_token": "eyJ-new",
                        },
                    ):
                        refreshed = await oauth_refresh.ensure_fresh_credentials(tmp)
                        self.assertTrue(refreshed)

                with open(path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                self.assertEqual(saved["access_token"], "new-access")
                self.assertEqual(saved["refresh_token"], "refresh-abc")
                self.assertEqual(saved["scope"], "openid cloud-platform")
                self.assertEqual(saved["id_token"], "eyJ-new")
                self.assertGreater(saved["expiry_date"], int(time.time() * 1000))

        asyncio.run(_run())

    def test_verify_access_token_ok(self):
        async def _run():
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response
            with patch("httpx.AsyncClient", return_value=mock_client):
                ok = await oauth_refresh.verify_access_token("ya29.test-token")
                self.assertTrue(ok)

        asyncio.run(_run())

    def test_verify_access_token_unauthorized(self):
        async def _run():
            mock_response = AsyncMock()
            mock_response.status_code = 401
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response
            with patch("httpx.AsyncClient", return_value=mock_client):
                ok = await oauth_refresh.verify_access_token("ya29.bad-token")
                self.assertFalse(ok)

        asyncio.run(_run())

    def test_ensure_fresh_refresh_fails_verify_ok(self):
        async def _run():
            with tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, "oauth_creds.json")
                data = {
                    "access_token": "still-valid",
                    "refresh_token": "refresh-abc",
                    "expiry_date": 1,
                }
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f)

                with patch(
                    "app.core.oauth_refresh.verify_access_token",
                    new_callable=AsyncMock,
                    side_effect=[True, True, True],
                ):
                    with patch(
                        "app.core.oauth_refresh.refresh_google_token",
                        new_callable=AsyncMock,
                        side_effect=RuntimeError("invalid_grant"),
                    ) as mock_refresh:
                        refreshed = await oauth_refresh.ensure_fresh_credentials(tmp)
                        self.assertFalse(refreshed)
                        mock_refresh.assert_called_once()

        asyncio.run(_run())

    def test_ensure_fresh_refresh_fails_verify_fails_raises(self):
        async def _run():
            with tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, "oauth_creds.json")
                data = {
                    "access_token": "dead-token",
                    "refresh_token": "refresh-abc",
                    "expiry_date": 1,
                }
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f)

                with patch(
                    "app.core.oauth_refresh.verify_access_token",
                    new_callable=AsyncMock,
                    return_value=False,
                ):
                    with patch(
                        "app.core.oauth_refresh.refresh_google_token",
                        new_callable=AsyncMock,
                        side_effect=RuntimeError("invalid_grant"),
                    ):
                        with self.assertRaises(RuntimeError):
                            await oauth_refresh.ensure_fresh_credentials(tmp)

        asyncio.run(_run())

    def test_ensure_fresh_stale_expiry_still_refreshes_despite_verify_cache(self):
        async def _run():
            with tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, "oauth_creds.json")
                data = {
                    "access_token": "live-token",
                    "refresh_token": "refresh-abc",
                    "expiry_date": 1,
                }
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f)

                oauth_refresh._verify_cache[oauth_refresh._access_token_suffix("live-token")] = time.time() + 600

                mock_response = {
                    "access_token": "refreshed-access",
                    "refresh_token": "refresh-abc",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                }
                with patch(
                    "app.core.oauth_refresh.verify_access_token",
                    new_callable=AsyncMock,
                    return_value=True,
                ):
                    with patch(
                        "app.core.oauth_refresh.refresh_google_token",
                        new_callable=AsyncMock,
                        return_value=mock_response,
                    ) as mock_refresh:
                        refreshed = await oauth_refresh.ensure_fresh_credentials(tmp)
                        self.assertTrue(refreshed)
                        mock_refresh.assert_called_once()

                with open(path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                self.assertEqual(saved["access_token"], "refreshed-access")

        asyncio.run(_run())

    def test_invalidate_verify_cache(self):
        token_a = "ya29.a" + "x" * 20
        token_b = "ya29.b" + "y" * 20
        key_a = oauth_refresh._access_token_suffix(token_a)
        key_b = oauth_refresh._access_token_suffix(token_b)
        oauth_refresh._verify_cache[key_a] = time.time() + 600
        oauth_refresh._verify_cache[key_b] = time.time() + 600
        oauth_refresh.invalidate_verify_cache(token_a)
        self.assertNotIn(key_a, oauth_refresh._verify_cache)
        self.assertIn(key_b, oauth_refresh._verify_cache)
        oauth_refresh.invalidate_verify_cache()
        self.assertEqual(oauth_refresh._verify_cache, {})

    def test_force_refresh_bypasses_valid_expiry(self):
        async def _run():
            with tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, "oauth_creds.json")
                future_ms = int((time.time() + 7200) * 1000)
                data = {
                    "access_token": "valid-token",
                    "refresh_token": "refresh-abc",
                    "expiry_date": future_ms,
                }
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f)

                mock_response = {
                    "access_token": "forced-access",
                    "refresh_token": "refresh-abc",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                }
                with patch(
                    "app.core.oauth_refresh.verify_access_token",
                    new_callable=AsyncMock,
                    return_value=True,
                ):
                    with patch(
                        "app.core.oauth_refresh.refresh_google_token",
                        new_callable=AsyncMock,
                        return_value=mock_response,
                    ) as mock_refresh:
                        refreshed = await oauth_refresh.ensure_fresh_credentials(tmp, force=True)
                        self.assertTrue(refreshed)
                        mock_refresh.assert_called_once()

        asyncio.run(_run())

    def test_read_access_token_from_oauth_creds_json_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "oauth_creds.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"access_token": "from-oauth-creds", "refresh_token": "r"}, f)
            self.assertEqual(oauth_refresh.read_access_token(tmp), "from-oauth-creds")

    def test_discovery_prefers_antigravity_when_both_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            agy_path = os.path.join(tmp, "antigravity-cli", "antigravity-oauth-token")
            os.makedirs(os.path.dirname(agy_path), exist_ok=True)
            with open(agy_path, "w", encoding="utf-8") as f:
                json.dump({"token": {"access_token": "agy-token"}}, f)
            with open(os.path.join(tmp, "oauth_creds.json"), "w", encoding="utf-8") as f:
                json.dump({"access_token": "gemini-token"}, f)
            self.assertEqual(oauth_refresh.read_access_token(tmp), "agy-token")

    def test_discover_verified_prefers_working_oauth_creds(self):
        async def _run():
            with tempfile.TemporaryDirectory() as tmp:
                agy_path = os.path.join(tmp, "antigravity-cli", "antigravity-oauth-token")
                os.makedirs(os.path.dirname(agy_path), exist_ok=True)
                with open(agy_path, "w", encoding="utf-8") as f:
                    json.dump({"token": {"access_token": "dead-agy-token"}}, f)
                oauth_path = os.path.join(tmp, "oauth_creds.json")
                with open(oauth_path, "w", encoding="utf-8") as f:
                    json.dump({"access_token": "live-gemini-token"}, f)

                async def fake_verify(token, **kwargs):
                    return token == "live-gemini-token"

                with patch("app.core.oauth_refresh.verify_access_token", side_effect=fake_verify):
                    discovered = await oauth_refresh.discover_verified_credential_file(tmp)
                    self.assertEqual(discovered[0], oauth_path)
                    self.assertEqual(oauth_refresh.read_access_token(tmp), "live-gemini-token")

        asyncio.run(_run())

    def test_env_access_token_override_patches_disk(self):
        async def _run():
            with tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, "oauth_creds.json")
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "access_token": "stale-token",
                            "refresh_token": "keep-refresh",
                            "expiry_date": 1,
                        },
                        f,
                    )

                os.environ["AGY_ACCESS_TOKEN"] = "env-live-token"
                with patch(
                    "app.core.oauth_refresh.verify_access_token",
                    new_callable=AsyncMock,
                    return_value=True,
                ):
                    refreshed = await oauth_refresh.ensure_fresh_credentials(tmp)
                    self.assertTrue(refreshed)

                with open(path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                self.assertEqual(saved["access_token"], "env-live-token")
                self.assertEqual(saved["refresh_token"], "keep-refresh")
                self.assertEqual(oauth_refresh.read_access_token(tmp), "env-live-token")

        asyncio.run(_run())

    def test_cloudcode_headers_match_agy(self):
        from app.core.cloudcode_common import cloudcode_headers

        headers = cloudcode_headers("ya29.test")
        self.assertEqual(headers["Authorization"], "Bearer ya29.test")
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertIn("antigravity/cli", headers["User-Agent"])
        self.assertEqual(headers["Accept-Encoding"], "gzip")
        self.assertNotIn("Client-Metadata", headers)
        self.assertNotIn("X-Goog-Api-Client", headers)

        stream_headers = cloudcode_headers("ya29.test", streaming=True)
        self.assertEqual(stream_headers["Accept"], "text/event-stream")

    def test_strips_refresh_token_whitespace(self):
        view = oauth_refresh._normalize_token_view(
            {"refresh_token": "  tok-abc  ", "access_token": "a", "expiry_date": 1},
            "gemini_flat",
        )
        self.assertEqual(view["refresh_token"], "tok-abc")

    def test_decodes_url_encoded_refresh_token(self):
        encoded = "1%2F%2F0cWzy9OdjWMKOCgYIARAAGAwSNwF-L9IraMsn9CknfIoNh8nH-yogmECZTzpJQL6eb7MtQdCXek4qFANis9sMdyTiBEB0Qcp1gkM"
        view = oauth_refresh._normalize_token_view(
            {"refresh_token": encoded, "access_token": "a", "expiry_date": 1},
            "gemini_flat",
        )
        self.assertTrue(view["refresh_token"].startswith("1//"))
        self.assertTrue(view["refresh_token"].endswith("cp1gkM"))

    def test_refresh_google_token_decodes_encoded_refresh(self):
        async def _run():
            encoded = "1%2F%2F0cWzy9OdjWMKOCgYIARAAGAwSNwF-L9IraMsn9CknfIoNh8nH-yogmECZTzpJQL6eb7MtQdCXek4qFANis9sMdyTiBEB0Qcp1gkM"
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json = lambda: {
                "access_token": "new-access",
                "expires_in": 3600,
                "token_type": "Bearer",
            }

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            with patch("httpx.AsyncClient", return_value=mock_client):
                await oauth_refresh.refresh_google_token(encoded)
                sent_refresh = mock_client.post.call_args.kwargs["data"]["refresh_token"]
                self.assertTrue(sent_refresh.startswith("1//"))
                self.assertNotIn("%2F", sent_refresh)

        asyncio.run(_run())

    def test_skips_refresh_when_expiry_still_valid(self):
        future_ms = int((time.time() + 7200) * 1000)
        view = oauth_refresh._normalize_token_view(
            {"access_token": "valid", "refresh_token": "rt", "expiry_date": future_ms},
            "gemini_flat",
        )
        self.assertFalse(oauth_refresh._needs_refresh_from_view(view))

    def test_refresh_google_token_http_error(self):
        async def _run():
            mock_response = AsyncMock()
            mock_response.status_code = 400
            mock_response.text = "invalid_grant"

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            with patch("httpx.AsyncClient", return_value=mock_client):
                with self.assertRaises(RuntimeError):
                    await oauth_refresh.refresh_google_token("bad-refresh")

        asyncio.run(_run())

    def test_refresh_preserves_refresh_token_on_rotation(self):
        async def _run():
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json = lambda: {
                "access_token": "rotated-access",
                "expires_in": 3600,
                "token_type": "Bearer",
            }

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            with patch("httpx.AsyncClient", return_value=mock_client):
                result = await oauth_refresh.refresh_google_token("original-refresh")
                self.assertEqual(result["refresh_token"], "original-refresh")

        asyncio.run(_run())


class TestWithHeartbeat(unittest.TestCase):
    def test_yields_none_on_idle(self):
        async def slow_gen():
            await asyncio.sleep(0.05)
            yield {"delta": "hi"}

        async def _run():
            results = []
            async for item in with_heartbeat(slow_gen(), interval=0.01):
                results.append(item)
            self.assertIn(None, results)
            self.assertEqual(results[-1], {"delta": "hi"})

        asyncio.run(_run())

    def test_no_ping_when_chunks_arrive_quickly(self):
        async def fast_gen():
            yield {"delta": "a"}
            yield {"delta": "b"}

        async def _run():
            results = []
            async for item in with_heartbeat(fast_gen(), interval=1.0):
                results.append(item)
            self.assertNotIn(None, results)
            self.assertEqual(len(results), 2)

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
