import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core import oauth_refresh
from app.core.cloudcode_common import LOAD_CODEASSIST_URL, STREAM_GENERATE_URL, QUOTA_PROJECT, cloudcode_headers
from app.core.agy_http_client import _build_envelope, _get_project_id
import httpx


async def main():
    token = oauth_refresh.read_access_token()
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(LOAD_CODEASSIST_URL, headers=cloudcode_headers(token), json={})
        print("loadCodeAssist", r.status_code)
        payload = r.json()
        print("cloudaicompanionProject:", payload.get("cloudaicompanionProject"))

    project_id = await _get_project_id(token)
    print("cached project_id:", project_id)
    print("QUOTA_PROJECT:", QUOTA_PROJECT)

    contents = [{"role": "user", "parts": [{"text": "say hi"}]}]
    body_wrong = _build_envelope(project_id, "gemini-3.7-flash-high", contents)
    body_right = _build_envelope(QUOTA_PROJECT, "gemini-3.7-flash-high", contents)

    async with httpx.AsyncClient(timeout=60) as c:
        for label, body in [("wrong_project", body_wrong), ("quota_project", body_right)]:
            r = await c.post(
                STREAM_GENERATE_URL,
                headers=cloudcode_headers(token, streaming=True),
                json=body,
            )
            print(f"{label} status={r.status_code}")
            print(r.text[:500])
            print("---")


if __name__ == "__main__":
    asyncio.run(main())
