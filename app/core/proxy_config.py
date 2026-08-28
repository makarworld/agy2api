import logging
import os
from typing import Any, Optional
from urllib.parse import quote, urlparse

logger = logging.getLogger(__name__)

_ENV_KEYS = ("AGY_GOOGLE_PROXY", "AGY_PROXY")
_LOCAL_PROXY_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _normalize_proxy_url(proxy: str) -> str:
    proxy = proxy.strip()
    if not proxy:
        return proxy
    if "://" not in proxy:
        proxy = f"http://{proxy}"
    return proxy


def _encode_proxy_credentials(proxy: str) -> str:
    """Percent-encode userinfo so httpx gets a valid proxy URL."""
    if "://" not in proxy:
        return proxy
    scheme, rest = proxy.split("://", 1)
    if "@" not in rest:
        return proxy
    userinfo, hostport = rest.rsplit("@", 1)
    if ":" not in userinfo:
        return proxy
    username, password = userinfo.split(":", 1)
    if "%" in username or "%" in password:
        return proxy
    return (
        f"{scheme}://{quote(username, safe='')}:{quote(password, safe='')}@{hostport}"
    )


def env_google_proxy() -> Optional[str]:
    for key in _ENV_KEYS:
        value = os.environ.get(key, "").strip()
        if value:
            return _encode_proxy_credentials(_normalize_proxy_url(value))
    return None


def get_google_proxy(account_proxy: Optional[str] = None) -> Optional[str]:
    """Per-account pool proxy wins; otherwise default fallback to AGY_GOOGLE_PROXY from env."""
    if account_proxy and str(account_proxy).strip():
        return _encode_proxy_credentials(
            _normalize_proxy_url(str(account_proxy).strip())
        )
    env_proxy = env_google_proxy()
    if env_proxy:
        return env_proxy
    return None


def _proxy_hostname(proxy: Optional[str]) -> str:
    if not proxy:
        return ""
    normalized = _normalize_proxy_url(proxy.strip())
    return (urlparse(normalized).hostname or "").lower()


def is_local_proxy(proxy: Optional[str]) -> bool:
    return _proxy_hostname(proxy) in _LOCAL_PROXY_HOSTS


def ssl_verify_enabled(proxy: Optional[str] = None) -> bool:
    """Whether httpx should verify TLS certs (disable for localhost MITM proxies)."""
    for key in ("AGY_SSL_VERIFY", "AGY_HTTP_SSL_VERIFY"):
        value = os.environ.get(key)
        if value is not None and str(value).strip() != "":
            return str(value).strip().lower() not in ("0", "false", "no", "off")
    if is_local_proxy(proxy):
        return False
    return True


def httpx_client_kwargs(
    *,
    proxy: Optional[str] = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Shared kwargs for httpx.AsyncClient used by Google/OAuth HTTP transport."""
    kwargs: dict[str, Any] = {"timeout": timeout}
    if proxy:
        kwargs["proxy"] = proxy
    if not ssl_verify_enabled(proxy):
        kwargs["verify"] = False
    return kwargs
