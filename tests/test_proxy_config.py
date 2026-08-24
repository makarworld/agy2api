import os
import unittest

from app.core.proxy_config import (
    env_google_proxy,
    get_google_proxy,
    httpx_client_kwargs,
    ssl_verify_enabled,
)


class TestProxyConfig(unittest.TestCase):
    def setUp(self):
        self._env = os.environ.copy()
        for key in ("AGY_GOOGLE_PROXY", "AGY_PROXY"):
            os.environ.pop(key, None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)

    def test_env_proxy_adds_http_scheme(self):
        os.environ["AGY_GOOGLE_PROXY"] = "user:pass@1.2.3.4:8080"
        self.assertEqual(env_google_proxy(), "http://user:pass@1.2.3.4:8080")

    def test_env_proxy_overrides_account_proxy(self):
        os.environ["AGY_GOOGLE_PROXY"] = "http://env-proxy:3128"
        self.assertEqual(get_google_proxy("http://account-proxy:3128"), "http://env-proxy:3128")

    def test_account_proxy_used_when_env_missing(self):
        self.assertEqual(get_google_proxy("socks5://acc:1080"), "socks5://acc:1080")

    def test_ssl_verify_disabled_for_localhost_proxy_by_default(self):
        self.assertFalse(ssl_verify_enabled("http://127.0.0.1:8888"))
        self.assertFalse(ssl_verify_enabled("http://localhost:8000"))

    def test_ssl_verify_explicit_env_overrides_localhost(self):
        os.environ["AGY_SSL_VERIFY"] = "true"
        self.assertTrue(ssl_verify_enabled("http://127.0.0.1:8888"))

    def test_httpx_client_kwargs_disable_verify_for_local_proxy(self):
        kwargs = httpx_client_kwargs(proxy="http://localhost:8888", timeout=10.0)
        self.assertFalse(kwargs["verify"])
        self.assertEqual(kwargs["proxy"], "http://localhost:8888")


if __name__ == "__main__":
    unittest.main()
