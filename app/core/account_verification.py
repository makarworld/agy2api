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
    json_url = json.dumps(url)

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Проверка аккаунта {escaped_email}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 20px;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      background: #090d16;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      color: #f8fafc;
    }}
    .modal {{
      width: 100%;
      max-width: 540px;
      background: #151d2f;
      border: 1px solid #293548;
      border-radius: 16px;
      padding: 32px 28px;
      box-shadow: 0 20px 40px -10px rgba(0, 0, 0, 0.6);
      text-align: center;
      animation: popIn 0.25s cubic-bezier(0.16, 1, 0.3, 1);
    }}
    @keyframes popIn {{
      from {{ opacity: 0; transform: scale(0.95); }}
      to {{ opacity: 1; transform: scale(1); }}
    }}
    .icon-badge {{
      width: 56px;
      height: 56px;
      margin: 0 auto 18px;
      background: rgba(56, 189, 248, 0.12);
      border: 1px solid rgba(56, 189, 248, 0.25);
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      color: #38bdf8;
      font-size: 26px;
    }}
    h2 {{
      margin: 0 0 10px;
      font-size: 21px;
      font-weight: 700;
      color: #ffffff;
    }}
    .desc {{
      font-size: 14px;
      line-height: 1.6;
      color: #94a3b8;
      margin: 0 0 20px;
    }}
    .desc b {{
      color: #e2e8f0;
      word-break: break-all;
    }}
    .url-box {{
      width: 100%;
      background: #0b1120;
      border: 1px solid #1e293b;
      border-radius: 8px;
      padding: 10px 14px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 11px;
      color: #64748b;
      margin-bottom: 22px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      user-select: all;
    }}
    .btn-row {{
      display: flex;
      gap: 12px;
    }}
    .btn {{
      flex: 1;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      padding: 13px 20px;
      border-radius: 10px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      text-decoration: none;
      transition: all 0.15s ease;
      border: none;
    }}
    .btn-copy {{
      background: #1e293b;
      color: #f1f5f9;
      border: 1px solid #334155;
    }}
    .btn-copy:hover {{
      background: #27354a;
      border-color: #475569;
    }}
    .btn-copy.copied {{
      background: #064e3b;
      border-color: #059669;
      color: #34d399;
    }}
    .btn-open {{
      background: #2563eb;
      color: #ffffff;
      box-shadow: 0 4px 14px rgba(37, 99, 235, 0.4);
    }}
    .btn-open:hover {{
      background: #1d4ed8;
    }}
    .toast {{
      margin-top: 14px;
      font-size: 12px;
      color: #34d399;
      min-height: 18px;
      transition: opacity 0.2s;
    }}
  </style>
</head>
<body>
  <div class="modal">
    <div class="icon-badge">🔒</div>
    <h2>Требуется проверка аккаунта</h2>
    <p class="desc">
      Пройдите проверку, чтобы аккаунт <b>{escaped_email}</b> имел доступ к подписке.
    </p>

    <div class="url-box" id="urlBox" title="{escaped_url}">{escaped_url}</div>

    <div class="btn-row">
      <button class="btn btn-copy" id="copyBtn" onclick="copyLink()">
        <span id="copyIcon">📋</span>
        <span id="copyText">Скопировать</span>
      </button>

      <button class="btn btn-open" id="openBtn" onclick="openLink()">
        <span>↗</span>
        <span>Открыть</span>
      </button>
    </div>

    <div class="toast" id="toast"></div>
  </div>

  <script>
    const verifyUrl = {json_url};

    function copyLink() {{
      const btn = document.getElementById('copyBtn');
      const text = document.getElementById('copyText');
      const icon = document.getElementById('copyIcon');
      const toast = document.getElementById('toast');

      const performCopy = () => {{
        btn.classList.add('copied');
        text.innerText = 'Скопировано!';
        icon.innerText = '✓';
        toast.innerText = 'Ссылка скопирована в буфер обмена';
        setTimeout(() => {{
          btn.classList.remove('copied');
          text.innerText = 'Скопировать';
          icon.innerText = '📋';
          toast.innerText = '';
        }}, 3000);
      }};

      if (navigator.clipboard && navigator.clipboard.writeText) {{
        navigator.clipboard.writeText(verifyUrl).then(performCopy).catch(fallbackCopy);
      }} else {{
        fallbackCopy();
      }}

      function fallbackCopy() {{
        try {{
          const ta = document.createElement('textarea');
          ta.value = verifyUrl;
          ta.style.position = 'fixed';
          ta.style.opacity = '0';
          document.body.appendChild(ta);
          ta.select();
          document.execCommand('copy');
          document.body.removeChild(ta);
          performCopy();
        }} catch (e) {{
          toast.innerText = 'Не удалось скопировать, выделите ссылку вручную';
        }}
      }}
    }}

    function openLink() {{
      window.location.href = verifyUrl;
    }}
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
