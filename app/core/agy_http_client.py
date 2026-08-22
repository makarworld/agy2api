import json
import logging
import os
import time
import uuid
from typing import Any, AsyncIterator, List, Optional

import httpx

from app.core import oauth_refresh
from app.core import pool_manager
from app.core.cloudcode_common import LOAD_CODEASSIST_URL, STREAM_GENERATE_URL, cloudcode_headers
from app.core.http_tools_bridge import (
    anthropic_tools_to_gemini,
    extract_parts_from_response,
    messages_to_gemini_contents,
    tool_choice_to_gemini_mode,
)
from app.core.model_manager import resolve_http_model

logger = logging.getLogger(__name__)

SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]

_cached_project_id: Optional[str] = None


def _gemini_home() -> str:
    return os.path.expanduser("~/.gemini")


def _agent_request_id() -> str:
    return f"agent/{uuid.uuid4()}/{int(time.time() * 1000)}/{uuid.uuid4()}/1"


def _normalize_project_id(raw: Any) -> str:
    if isinstance(raw, dict):
        for key in ("projectId", "id", "name"):
            value = raw.get(key)
            if value:
                return str(value)
        raise RuntimeError(f"loadCodeAssist project object missing id: {raw}")
    if not raw:
        raise RuntimeError("loadCodeAssist response missing cloudaicompanionProject")
    return str(raw)


def _deep_find(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for value in obj.values():
            found = _deep_find(value, key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _deep_find(item, key)
            if found is not None:
                return found
    return None


async def _active_proxy() -> Optional[str]:
    return pool_manager.get_active_account_proxy()


async def get_access_token(*, gemini_home: Optional[str] = None, proxy: Optional[str] = None) -> str:
    home = gemini_home or _gemini_home()
    proxy = proxy if proxy is not None else await _active_proxy()
    await oauth_refresh.ensure_fresh_antigravity_token(
        home,
        proxy=proxy,
        pool_account_id=pool_manager.get_active_account_id(),
    )
    return oauth_refresh.read_access_token(home)


async def _get_project_id(access_token: str, *, proxy: Optional[str] = None) -> str:
    global _cached_project_id
    if _cached_project_id:
        return _cached_project_id

    async with httpx.AsyncClient(proxy=proxy, timeout=60.0) as client:
        response = await client.post(
            LOAD_CODEASSIST_URL,
            headers=cloudcode_headers(access_token),
            json={},
        )
    if response.status_code != 200:
        raise RuntimeError(f"loadCodeAssist failed (HTTP {response.status_code}): {response.text[:500]}")

    payload = response.json()
    project_raw = payload.get("cloudaicompanionProject") or _deep_find(payload, "cloudaicompanionProject")
    project = _normalize_project_id(project_raw)
    _cached_project_id = project
    return project


def _map_usage(usage_metadata: dict) -> dict:
    if not usage_metadata:
        return {}
    return {
        "input_tokens": usage_metadata.get("promptTokenCount", 0),
        "output_tokens": usage_metadata.get("candidatesTokenCount", 0),
        "thinking_tokens": usage_metadata.get("thoughtsTokenCount", 0),
        "cache_read_tokens": usage_metadata.get("cachedContentTokenCount", 0),
    }


def _generation_config(backend_model: str, thinking_level: Optional[str]) -> dict:
    gen_config: dict = {"maxOutputTokens": 8192}
    thinking_cfg: dict = {}

    if thinking_level:
        thinking_cfg["thinkingLevel"] = thinking_level
    if backend_model.startswith("gemini-3.") and "flash" in backend_model:
        thinking_cfg.setdefault("includeThoughts", True)
        thinking_cfg.setdefault("thinkingBudget", -1)
    elif thinking_level:
        thinking_cfg.setdefault("includeThoughts", False)

    if thinking_cfg:
        gen_config["thinkingConfig"] = thinking_cfg
    return gen_config


def _build_envelope(
    project_id: str,
    backend_model: str,
    contents: List[dict],
    thinking_level: Optional[str] = None,
    *,
    system: Optional[str] = None,
    tools: Optional[List[dict]] = None,
    tool_choice: Optional[Any] = None,
) -> dict:
    inner: dict = {
        "contents": contents,
        "generationConfig": _generation_config(backend_model, thinking_level),
        "safetySettings": SAFETY_SETTINGS,
        "sessionId": str(-abs(hash(uuid.uuid4()))),
    }

    if system:
        inner["systemInstruction"] = {"parts": [{"text": system}]}

    gemini_tools = anthropic_tools_to_gemini(tools)
    if gemini_tools:
        inner["tools"] = gemini_tools
        mode = tool_choice_to_gemini_mode(tool_choice)
        if mode:
            inner["toolConfig"] = {"functionCallingConfig": {"mode": mode}}

    return {
        "project": project_id,
        "requestId": _agent_request_id(),
        "model": backend_model,
        "userAgent": "antigravity",
        "requestType": "agent",
        "request": inner,
    }


async def stream_completion(
    messages: List[dict],
    system: Optional[str] = None,
    model: Optional[str] = None,
    *,
    tools: Optional[List[dict]] = None,
    tool_choice: Optional[Any] = None,
    proxy: Optional[str] = None,
) -> AsyncIterator[dict]:
    """Direct HTTP stream to Cloud Code Assist with Claude Code tools passthrough."""
    proxy = proxy if proxy is not None else await _active_proxy()
    access_token = await get_access_token(proxy=proxy)
    project_id = await _get_project_id(access_token, proxy=proxy)
    backend_model, thinking_level = resolve_http_model(model or "gemini-2.5-flash")

    contents = messages_to_gemini_contents(messages)
    if not contents:
        raise RuntimeError("No user/assistant messages to send")

    body = _build_envelope(
        project_id,
        backend_model,
        contents,
        thinking_level,
        system=system,
        tools=tools,
        tool_choice=tool_choice,
    )
    if model and model != backend_model:
        logger.info("[http] model %s -> backend %s", model, backend_model)

    full_text = ""
    final_usage: dict = {}
    all_tool_calls: List[dict] = []
    seen_tool_ids: set[str] = set()

    async with httpx.AsyncClient(proxy=proxy, timeout=300.0) as client:
        async with client.stream(
            "POST",
            STREAM_GENERATE_URL,
            headers=cloudcode_headers(access_token, streaming=True),
            json=body,
        ) as response:
            if response.status_code != 200:
                detail = (await response.aread()).decode(errors="replace")[:500]
                raise RuntimeError(f"streamGenerateContent failed (HTTP {response.status_code}): {detail}")

            async for line in response.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if not raw or raw == "[DONE]":
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                usage_meta = obj.get("usageMetadata") or (obj.get("response") or {}).get("usageMetadata")
                if usage_meta:
                    final_usage = _map_usage(usage_meta)

                delta_text, tool_calls = extract_parts_from_response(obj)
                if delta_text:
                    full_text += delta_text
                    yield {"delta": delta_text}

                new_calls = []
                for tc in tool_calls:
                    tc_id = tc.get("id", "")
                    if tc_id and tc_id in seen_tool_ids:
                        continue
                    if tc_id:
                        seen_tool_ids.add(tc_id)
                    new_calls.append(tc)
                    all_tool_calls.append(tc)
                if new_calls:
                    yield {"tool_calls": new_calls}

    stop_reason = "tool_use" if all_tool_calls else "end_turn"
    yield {
        "usage": final_usage,
        "text": full_text,
        "tool_calls": all_tool_calls,
        "stop_reason": stop_reason,
    }
