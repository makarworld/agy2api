import json
import logging
import os
import time
import uuid
from typing import Any, AsyncIterator, List, Optional

import httpx

from app.core.proxy_config import httpx_client_kwargs
from app.core import oauth_refresh
from app.core import pool_manager
from app.core.cloudcode_common import LOAD_CODEASSIST_URL, STREAM_GENERATE_URL, cloudcode_headers
from app.core.http_tools_bridge import (
    anthropic_tools_to_gemini,
    extract_parts_from_response,
    finalize_pending_tool_calls,
    http_debug_enabled,
    ingest_stream_tool_calls,
    messages_to_gemini_contents,
    summarize_sse_parts,
    thought_as_text_enabled,
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


async def get_access_token(
    *,
    gemini_home: Optional[str] = None,
    proxy: Optional[str] = None,
    force: bool = False,
) -> str:
    home = gemini_home or _gemini_home()
    proxy = proxy if proxy is not None else await _active_proxy()
    await oauth_refresh.ensure_fresh_antigravity_token(
        home,
        proxy=proxy,
        pool_account_id=pool_manager.get_active_account_id(),
        force=force,
    )
    return oauth_refresh.read_access_token(home)


async def _refresh_after_401(
    access_token: str,
    *,
    proxy: Optional[str] = None,
) -> str:
    """Invalidate verify cache, force refresh, return a new access token."""
    oauth_refresh.invalidate_verify_cache(access_token)
    global _cached_project_id
    _cached_project_id = None
    return await get_access_token(proxy=proxy, force=True)


async def _get_project_id(
    access_token: str,
    *,
    proxy: Optional[str] = None,
    _auth_retried: bool = False,
) -> str:
    global _cached_project_id
    if _cached_project_id:
        return _cached_project_id

    async with httpx.AsyncClient(**httpx_client_kwargs(proxy=proxy, timeout=60.0)) as client:
        response = await client.post(
            LOAD_CODEASSIST_URL,
            headers=cloudcode_headers(access_token),
            json={},
        )
    if response.status_code == 401 and not _auth_retried:
        logger.warning("[http] loadCodeAssist 401 — forcing OAuth refresh and retrying")
        access_token = await _refresh_after_401(access_token, proxy=proxy)
        return await _get_project_id(access_token, proxy=proxy, _auth_retried=True)
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
    # promptTokenCount is total input; cachedContentTokenCount is a subset (not additive).
    prompt_total = usage_metadata.get("promptTokenCount", 0)
    cache_read = usage_metadata.get("cachedContentTokenCount", 0)
    return {
        "input_tokens": prompt_total,
        "output_tokens": usage_metadata.get("candidatesTokenCount", 0),
        "thinking_tokens": usage_metadata.get("thoughtsTokenCount", 0),
        "cache_read_tokens": cache_read,
        "total_tokens": prompt_total
        + usage_metadata.get("candidatesTokenCount", 0)
        + usage_metadata.get("thoughtsTokenCount", 0),
    }


def _generation_config(
    backend_model: str,
    thinking_level: Optional[str],
    *,
    tools_present: bool = False,
    max_output_tokens: int = 8192,
) -> dict:
    gen_config: dict = {"maxOutputTokens": max_output_tokens}
    thinking_cfg: dict = {}

    if thinking_level:
        thinking_cfg["thinkingLevel"] = thinking_level
    if backend_model.startswith("gemini-3.") and "flash" in backend_model and not tools_present:
        thinking_cfg.setdefault("includeThoughts", True)
        thinking_cfg.setdefault("thinkingBudget", -1)
    elif tools_present:
        thinking_cfg["includeThoughts"] = False
        thinking_cfg["thinkingBudget"] = 0
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
    max_output_tokens: int = 8192,
) -> dict:
    gemini_tools = anthropic_tools_to_gemini(tools)
    inner: dict = {
        "contents": contents,
        "generationConfig": _generation_config(
            backend_model,
            thinking_level,
            tools_present=bool(gemini_tools),
            max_output_tokens=max_output_tokens,
        ),
        "safetySettings": SAFETY_SETTINGS,
        "sessionId": str(-abs(hash(uuid.uuid4()))),
    }

    if system:
        inner["systemInstruction"] = {"parts": [{"text": system}]}

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


def _log_empty_stream_debug(
    *,
    finish_reason: Optional[str],
    final_usage: dict,
    pending_tool_calls: dict[str, dict],
    last_sse_obj: Optional[dict],
) -> None:
    if not http_debug_enabled():
        return
    unnamed = [k for k, v in pending_tool_calls.items() if not v.get("name")]
    usage_meta = (last_sse_obj or {}).get("usageMetadata") or {}
    logger.warning(
        "[http][debug] empty stream finishReason=%s usage=%s pending=%s unnamed_keys=%s parts=%s",
        finish_reason,
        final_usage or usage_meta,
        len(pending_tool_calls),
        unnamed,
        summarize_sse_parts(last_sse_obj) if last_sse_obj else "n/a",
    )
    if last_sse_obj:
        logger.warning("[http][debug] last_sse=%s", json.dumps(last_sse_obj)[:2000])


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
    tools_present = bool(anthropic_tools_to_gemini(tools))
    allow_thought_text = thought_as_text_enabled(tools_present=tools_present)
    max_output_tokens = int(os.environ.get("AGY_HTTP_MAX_OUTPUT_TOKENS", "8192"))

    trim_aggressive = False
    retried_empty = False
    auth_retried = False

    while True:
        contents = messages_to_gemini_contents(messages, trim_aggressive=trim_aggressive)
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
            max_output_tokens=max_output_tokens,
        )
        if model and model != backend_model and not retried_empty:
            logger.info("[http] model %s -> backend %s", model, backend_model)

        full_text = ""
        final_usage: dict = {}
        pending_tool_calls: dict[str, dict] = {}
        last_finish_reason: Optional[str] = None
        last_sse_obj: Optional[dict] = None
        retried_auth = False

        async with httpx.AsyncClient(**httpx_client_kwargs(proxy=proxy, timeout=300.0)) as client:
            async with client.stream(
                "POST",
                STREAM_GENERATE_URL,
                headers=cloudcode_headers(access_token, streaming=True),
                json=body,
            ) as response:
                if response.status_code == 401 and not auth_retried:
                    detail = (await response.aread()).decode(errors="replace")[:200]
                    logger.warning(
                        "[http] streamGenerateContent 401 — forcing OAuth refresh and retrying: %s",
                        detail,
                    )
                    access_token = await _refresh_after_401(access_token, proxy=proxy)
                    auth_retried = True
                    retried_auth = True
                elif response.status_code != 200:
                    detail = (await response.aread()).decode(errors="replace")[:500]
                    raise RuntimeError(f"streamGenerateContent failed (HTTP {response.status_code}): {detail}")
                else:
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

                        last_sse_obj = obj
                        usage_meta = obj.get("usageMetadata") or (obj.get("response") or {}).get("usageMetadata")
                        if usage_meta:
                            final_usage = _map_usage(usage_meta)

                        delta_text, tool_calls, finish_reason = extract_parts_from_response(
                            obj,
                            allow_thought_text=allow_thought_text,
                        )
                        if finish_reason:
                            last_finish_reason = finish_reason
                        if delta_text:
                            full_text += delta_text
                            yield {"delta": delta_text}

                        new_calls = ingest_stream_tool_calls(tool_calls, pending_tool_calls)
                        if new_calls:
                            yield {"tool_calls": new_calls}

        if retried_auth:
            continue

        all_tool_calls = finalize_pending_tool_calls(pending_tool_calls)
        if not full_text and not all_tool_calls:
            _log_empty_stream_debug(
                finish_reason=last_finish_reason,
                final_usage=final_usage,
                pending_tool_calls=pending_tool_calls,
                last_sse_obj=last_sse_obj,
            )
            retry_reasons = {None, "STOP", "MAX_TOKENS", "MALFORMED_FUNCTION_CALL"}
            if not retried_empty and last_finish_reason in retry_reasons:
                logger.warning(
                    "[http] empty response finishReason=%s — retrying with aggressive trim",
                    last_finish_reason,
                )
                retried_empty = True
                trim_aggressive = True
                max_output_tokens = min(max_output_tokens * 2, 16384)
                continue

            error_msg = f"Gemini returned empty response (finishReason={last_finish_reason or 'unknown'})"
            logger.error("[http] %s", error_msg)
            empty_as_empty_content = (
                os.environ.get("AGY_HTTP_EMPTY_AS_EMPTY_CONTENT", "true").lower() in ("true", "1", "yes")
                if last_finish_reason == "STOP"
                else os.environ.get("AGY_HTTP_EMPTY_AS_EMPTY_CONTENT", "false").lower() in ("true", "1", "yes")
            )
            if empty_as_empty_content:
                logger.info("[http] returning empty content [] with stop_reason=end_turn")
                yield {
                    "usage": final_usage,
                    "text": "",
                    "tool_calls": [],
                    "stop_reason": "end_turn",
                }
                return

            yield {
                "usage": final_usage,
                "text": "",
                "tool_calls": [],
                "stop_reason": "error",
                "error": error_msg,
            }
            return

        stop_reason = "tool_use" if all_tool_calls else "end_turn"
        yield {
            "usage": final_usage,
            "text": full_text,
            "tool_calls": all_tool_calls,
            "stop_reason": stop_reason,
        }
        return
