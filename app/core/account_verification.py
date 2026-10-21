import hashlib
import html
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, Optional
import urllib.parse

logger = logging.getLogger(__name__)

_VERIFICATION_URL_RE = re.compile(r"https://accounts\.google\.com/(?:[a-zA-Z0-9_\-\.]+/)*signin/continue[^\s\"'<>\\,]+")
_VERIFICATION_FALLBACK_RE = re.compile(
    r"https://accounts\.google\.com/[^\s\"'<>\\,]*(?:plt=[a-zA-Z0-9_\-]+|flowName=GlifWebSignIn)[^\s\"'<>\\,]*"
)

# Debounce cache to prevent spawning multiple browser windows/tabs for the same check (TTL = 10 min)
_OPENED_URLS_CACHE: Dict[str, float] = {}
_DEBOUNCE_TTL_SECONDS = int(os.environ.get("AGY_VERIFY_DEBOUNCE_SECONDS", "600"))


def clear_verification_cache() -> None:
    """Test helper: clears debounce cache."""
    _OPENED_URLS_CACHE.clear()


def extract_verification_url(text: Any) -> Optional[str]:
    """Search for Google signin/continue verification URL in text, error message, or payload."""
    if not text:
        return None
    raw_str = str(text)

    # Unescape JSON-escaped slashes and HTML entities
    cleaned = raw_str.replace(r"\/", "/")
    cleaned = html.unescape(cleaned)

    match = _VERIFICATION_URL_RE.search(cleaned) or _VERIFICATION_FALLBACK_RE.search(cleaned)
    if not match:
        return None

    url = match.group(0).strip()
    # Strip trailing punctuation often found in error logs / JSON
    url = re.sub(r"[\)\]\}\'\"\.\,]+$", "", url)
    return url


def resolve_account_email(account_id: Optional[str] = None, url: Optional[str] = None) -> str:
    """Best-effort resolution of the account email for display in alerts and logs."""
    if account_id:
        try:
            from app.core import account_store

            db_acc = account_store.get_account_by_id(account_id)
            if db_acc and db_acc.get("email"):
                return str(db_acc["email"]).strip()
        except Exception:
            pass

        try:
            from app.core import pool_manager

            manifest_acc = pool_manager._find_account(account_id)
            if manifest_acc and manifest_acc.get("email"):
                return str(manifest_acc["email"]).strip()
        except Exception:
            pass

    if url:
        try:
            parsed = urllib.parse.urlparse(url)
            qs = urllib.parse.parse_qs(parsed.query)
            for key in ("Email", "email", "authuser"):
                val = qs.get(key, [None])[0]
                if val and "@" in val:
                    return val.strip()
        except Exception:
            pass

    return account_id or "Google"


def _build_launcher_html(url: str, email: str) -> str:
    escaped_url = html.escape(url, quote=True)
    escaped_email = html.escape(email)
    json_email = json.dumps(email, ensure_ascii=False)
    json_url = json.dumps(url)

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>Проверка аккаунта {escaped_email}</title>
</head>
<body style="margin:0;padding:40px;background:#0f172a;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#f8fafc;">
  <div style="max-width:560px;margin:40px auto;background:#1e293b;border-radius:12px;padding:28px;box-shadow:0 8px 24px rgba(0,0,0,0.3);border:1px solid #334155;">
    <h2 style="margin-top:0;font-size:20px;color:#38bdf8;">Требуется проверка аккаунта</h2>
    <p style="font-size:15px;line-height:1.6;color:#e2e8f0;">
      Пройдите проверку, чтобы аккаунт <b>{escaped_email}</b> имел доступ к подписке.
    </p>
    <div style="margin-top:20px;">
      <a href="{escaped_url}" style="display:inline-block;padding:12px 24px;background:#2563eb;color:#fff;text-decoration:none;border-radius:8px;font-weight:600;font-size:14px;">Перейти к проверке Google</a>
    </div>
  </div>
  <script>
    try {{
      alert("Пройдите проверку чтобы аккаунт " + {json_email} + " имел доступ к подписке");
    }} catch (e) {{}}
    window.location.href = {json_url};
  </script>
</body>
</html>
"""


def open_verification_in_browser(
    url: str,
    email: Optional[str] = None,
    account_id: Optional[str] = None,
    *,
    force: bool = False,
) -> bool:
    """Launch the verification URL in the default browser with an alert.

    Uses an intermediate local HTML launcher that displays an alert
    alert("Пройдите проверку чтобы аккаунт {email} имел доступ к подписке")
    and redirects to the Google signin/continue URL.
    """
    resolved_email = email or resolve_account_email(account_id, url)
    cache_key = f"{resolved_email}:{url}"
    now = time.time()

    if not force and _OPENED_URLS_CACHE.get(cache_key, 0.0) > now:
        logger.info(f"[verification] Аккаунт {resolved_email} нуждается в проверке (уже открыто в браузере): {url}")
        return False

    _OPENED_URLS_CACHE[cache_key] = now + _DEBOUNCE_TTL_SECONDS
    logger.warning(f"[verification] Аккаунт {resolved_email} нуждается в проверке: {url}")

    # If disabled by env var (e.g. headless CI/test environments)
    if os.environ.get("AGY_VERIFY_DISABLE_BROWSER", "").lower() in ("1", "true", "yes"):
        return True

    launcher_path: Optional[str] = None
    try:
        slug = re.sub(r"[^a-zA-Z0-9_\-]+", "_", resolved_email)
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:8]
        filename = f"agy_verify_{slug}_{digest}.html"
        launcher_path = os.path.join(tempfile.gettempdir(), filename)
        with open(launcher_path, "w", encoding="utf-8") as f:
            f.write(_build_launcher_html(url, resolved_email))
    except Exception as exc:
        logger.warning(f"[verification] Failed creating launcher HTML: {exc}")
        launcher_path = None

    target = launcher_path or url

    try:
        if sys.platform == "win32":
            # Use cmd /c start "" <target> to open default browser non-blocking
            subprocess.Popen(["cmd", "/c", "start", "", target], shell=True)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", target])
        else:
            subprocess.Popen(["xdg-open", target])
        return True
    except Exception as exc:
        logger.warning(f"[verification] Failed to launch browser for {resolved_email}: {exc}")
        return False


def handle_verification_error(
    error_text_or_exception: Any,
    account_id: Optional[str] = None,
    email: Optional[str] = None,
    *,
    force: bool = False,
) -> Optional[str]:
    """Inspect error/response for Google verification URL; if present, open in browser and log."""
    url = extract_verification_url(error_text_or_exception)
    if not url:
        return None

    resolved_email = email or resolve_account_email(account_id, url)
    open_verification_in_browser(url, email=resolved_email, account_id=account_id, force=force)
    return url
