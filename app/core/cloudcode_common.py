import os
import platform

CLOUDCODE_BASE = os.environ.get(
    "AGY_HTTP_CLOUDCODE_BASE",
    "https://daily-cloudcode-pa.googleapis.com",
)
QUOTA_PROJECT = os.environ.get("AGY_HTTP_QUOTA_PROJECT", "aicode-consumers")

LOAD_CODEASSIST_URL = f"{CLOUDCODE_BASE}/v1internal:loadCodeAssist"
QUOTA_SUMMARY_URL = f"{CLOUDCODE_BASE}/v1internal:retrieveUserQuotaSummary"
STREAM_GENERATE_URL = f"{CLOUDCODE_BASE}/v1internal:streamGenerateContent?alt=sse"

_OS_TYPE = "windows" if platform.system().lower() == "windows" else "linux"
_DEFAULT_USER_AGENT = (
    f"antigravity/cli/1.1.18 (aidev_client; os_type={_OS_TYPE}; "
    "arch=amd64; cl=968774718; auth_method=consumer)"
)
AGY_HTTP_USER_AGENT = os.environ.get("AGY_HTTP_USER_AGENT", _DEFAULT_USER_AGENT)


def cloudcode_headers(access_token: str, *, streaming: bool = False) -> dict:
    """Headers matching agy CLI (no Client-Metadata / X-Goog-Api-Client)."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "User-Agent": AGY_HTTP_USER_AGENT,
        "Accept-Encoding": "gzip",
    }
    if streaming:
        headers["Accept"] = "text/event-stream"
    return headers
