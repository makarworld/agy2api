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
from app.core.cloudcode_common import (
    GENERATE_CONTENT_URL,
    LOAD_CODEASSIST_URL,
    STREAM_GENERATE_URL,
    cloudcode_headers,
)
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

# Keyed by pool account id ("" when the pool is disabled) -- the Cloud Code project
# is per-Google-account, so a single global cache leaks one account's project to another.
_cached_project_ids: dict[str, str] = {}


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
    from app.core import account_store

    account_id = pool_manager.get_active_account_id()
    proxy = proxy if proxy is not None else await _active_proxy()
    if account_id and account_store.get_account_by_id(account_id):
        await oauth_refresh.ensure_fresh_sqlite_account(account_id, proxy=proxy, force=force)
        return oauth_refresh.read_sqlite_access_token(account_id)

    home = gemini_home or _gemini_home()
    await oauth_refresh.ensure_fresh_antigravity_token(
        home,
        proxy=proxy,
        pool_account_id=account_id,
        force=force,
    )
    return oauth_refresh.read_access_token(home)


async def _refresh_after_401(
    access_token: str,
    *,
    account_id: Optional[str] = None,
    proxy: Optional[str] = None,
) -> str:
    """Invalidate verify cache, force refresh, return a new access token."""
    oauth_refresh.invalidate_verify_cache(access_token)
    _cached_project_ids.pop(account_id or "", None)
    return await get_access_token(proxy=proxy, force=True)


async def _get_project_id(
    access_token: str,
    *,
    account_id: Optional[str] = None,
    proxy: Optional[str] = None,
    _auth_retried: bool = False,
) -> str:
    cache_key = account_id or ""
    cached = _cached_project_ids.get(cache_key)
    if cached:
        return cached

    async with httpx.AsyncClient(**httpx_client_kwargs(proxy=proxy, timeout=60.0)) as client:
        response = await client.post(
            LOAD_CODEASSIST_URL,
            headers=cloudcode_headers(access_token),
            json={},
        )
    if response.status_code == 401 and not _auth_retried:
        logger.warning("[http] loadCodeAssist 401 — forcing OAuth refresh and retrying")
        access_token = await _refresh_after_401(access_token, account_id=account_id, proxy=proxy)
        return await _get_project_id(access_token, account_id=account_id, proxy=proxy, _auth_retried=True)
    if response.status_code != 200:
        raise RuntimeError(f"loadCodeAssist failed (HTTP {response.status_code}): {response.text[:500]}")

    payload = response.json()
    project_raw = payload.get("cloudaicompanionProject") or _deep_find(payload, "cloudaicompanionProject")
    project = _normalize_project_id(project_raw)
    _cached_project_ids[cache_key] = project
    return project


def _is_rate_limited(status_code: int, detail: str) -> bool:
    if status_code in (429, 403):
        return True
    lowered = detail.lower()
    return any(sig in lowered for sig in pool_manager.RATE_LIMIT_SIGNALS)


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
    thought_as_text: Optional[bool] = None,
) -> AsyncIterator[dict]:
    """Direct HTTP stream to Cloud Code Assist with Claude Code tools passthrough."""
    excluded: set[str] = set()
    account_id, pool_proxy, access_token = await pool_manager.acquire_http_account()
    proxy = proxy if proxy is not None else pool_proxy
    if not access_token:
        access_token = await get_access_token(proxy=proxy)
    project_id = await _get_project_id(access_token, account_id=account_id, proxy=proxy)
    backend_model, thinking_level = resolve_http_model(model or "gemini-2.5-flash")
    tools_present = bool(anthropic_tools_to_gemini(tools))
    allow_thought_text = thought_as_text_enabled(tools_present=tools_present, param_override=thought_as_text)
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
        rate_limit_detail: Optional[str] = None
        in_think_block = False

        async with httpx.AsyncClient(**httpx_client_kwargs(proxy=proxy, timeout=300.0)) as client:
            try:
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
                        access_token = await _refresh_after_401(access_token, account_id=account_id, proxy=proxy)
                        auth_retried = True
                        retried_auth = True
                    elif response.status_code != 200:
                        detail = (await response.aread()).decode(errors="replace")[:500]
                        if account_id and _is_rate_limited(response.status_code, detail):
                            rate_limit_detail = detail
                        else:
                            if account_id:
                                await pool_manager.mark_failure(account_id)
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

                            # Wrap thinking text in <think>...</think> when thought_as_text is enabled
                            candidates = (obj.get("response") or obj).get("candidates") or []
                            parts = candidates[0].get("content", {}).get("parts") if candidates else []
                            is_thought_chunk = bool(parts and isinstance(parts[0], dict) and parts[0].get("thought"))

                            if delta_text:
                                if allow_thought_text:
                                    if is_thought_chunk and not in_think_block:
                                        in_think_block = True
                                        yield {"delta": "<think>\n"}
                                        full_text += "<think>\n"
                                    elif not is_thought_chunk and in_think_block:
                                        in_think_block = False
                                        yield {"delta": "\n</think>\n\n"}
                                        full_text += "\n</think>\n\n"

                                full_text += delta_text
                                yield {"delta": delta_text}

                            new_calls = ingest_stream_tool_calls(tool_calls, pending_tool_calls)
                            if new_calls:
                                yield {"tool_calls": new_calls}
            except (
                httpx.ConnectError,
                httpx.ConnectTimeout,
                httpx.ReadError,
                httpx.ReadTimeout,
                httpx.RemoteProtocolError,
            ) as net_err:
                logger.warning("[http] network/connection error on account %s: %s", account_id, net_err)
                if account_id:
                    excluded.add(account_id)
                    try:
                        account_id, proxy, access_token = await pool_manager.acquire_http_account(exclude=excluded)
                        project_id = await _get_project_id(access_token, account_id=account_id, proxy=proxy)
                        continue
                    except Exception:
                        pass
                raise

        if in_think_block:
            in_think_block = False
            yield {"delta": "\n</think>\n\n"}
            full_text += "\n</think>\n\n"

        if rate_limit_detail is not None:
            cooldown = int(os.environ.get("AGY_POOL_COOLDOWN_SECONDS", "3600"))
            await pool_manager.mark_rate_limited(account_id, cooldown)
            excluded.add(account_id)
            logger.warning("[http] account %s rate-limited, rotating: %s", account_id, rate_limit_detail[:200])
            account_id, proxy, access_token = await pool_manager.acquire_http_account(exclude=excluded)
            project_id = await _get_project_id(access_token, account_id=account_id, proxy=proxy)
            continue

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

        if account_id:
            await pool_manager.mark_success(account_id)

        stop_reason = "tool_use" if all_tool_calls else "end_turn"
        yield {
            "usage": final_usage,
            "text": full_text,
            "tool_calls": all_tool_calls,
            "stop_reason": stop_reason,
        }
        return


IMAGE_SYSTEM_INSTRUCTION = (
    "You are an AI image generator. Generate images based on user descriptions. "
    "Focus on creating high-quality, visually appealing images that match the user's request."
)
DEFAULT_IMAGE_MODEL = os.environ.get("AGY_IMAGE_MODEL", "gemini-3.1-flash-image")


def _image_request_id() -> str:
    return f"image_gen/{int(time.time() * 1000)}/{uuid.uuid4()}/2"


def _parse_aspect_ratio(prompt: str, size: Optional[str] = None) -> str:
    if size:
        normalized = size.strip().replace("x", ":")
        if normalized in {"1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"}:
            return normalized
    lowered = prompt.lower()
    for ratio in ("21:9", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "5:4", "4:5", "1:1"):
        if ratio in lowered or ratio.replace(":", "/") in lowered or ratio.replace(":", "x") in lowered:
            return ratio
    return "1:1"


def _build_image_request(
    prompt: str,
    project_id: str,
    model: str,
    aspect_ratio: str,
    reference_parts: Optional[List[dict]] = None,
) -> dict:
    parts: List[dict] = list(reference_parts or [])
    parts.append({"text": prompt})
    return {
        "project": project_id,
        "requestId": _image_request_id(),
        "request": {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "candidateCount": 1,
                "imageConfig": {"aspectRatio": aspect_ratio},
            },
        },
        "model": model,
        "userAgent": "antigravity",
        "requestType": "image_gen",
    }


def _extract_image_from_json(data: dict) -> dict:
    candidates = (data.get("response") or data).get("candidates") or []
    for candidate in candidates:
        for part in candidate.get("content", {}).get("parts") or []:
            inline = part.get("inlineData") or {}
            b64_data = inline.get("data")
            if b64_data:
                return {
                    "mime_type": inline.get("mimeType", "image/jpeg"),
                    "data": b64_data,
                }
    raise RuntimeError(f"No image data returned by the model: {str(data)[:300]}")


async def generate_image(
    prompt: str,
    *,
    model: Optional[str] = None,
    size: Optional[str] = None,
    reference_parts: Optional[List[dict]] = None,
    proxy: Optional[str] = None,
) -> dict:
    """Generate an image via Cloud Code Assist image models (pure HTTP POST generateContent)."""
    excluded: set[str] = set()
    backend_model = model or DEFAULT_IMAGE_MODEL
    aspect_ratio = _parse_aspect_ratio(prompt, size=size)

    while True:
        account_id, pool_proxy, access_token = await pool_manager.acquire_http_account(exclude=excluded)
        account_proxy = proxy if proxy is not None else pool_proxy
        if not access_token:
            access_token = await get_access_token(proxy=account_proxy)
        project_id = await _get_project_id(access_token, account_id=account_id, proxy=account_proxy)
        body = _build_image_request(prompt, project_id, backend_model, aspect_ratio, reference_parts)
        headers = cloudcode_headers(access_token, streaming=False)

        async with httpx.AsyncClient(**httpx_client_kwargs(proxy=account_proxy, timeout=300.0)) as client:
            response = await client.post(GENERATE_CONTENT_URL, headers=headers, json=body)
            if response.status_code == 401:
                access_token = await _refresh_after_401(access_token, account_id=account_id, proxy=account_proxy)
                headers = cloudcode_headers(access_token, streaming=False)
                response = await client.post(GENERATE_CONTENT_URL, headers=headers, json=body)

            if response.status_code != 200:
                detail = response.text[:500]
                if account_id and _is_rate_limited(response.status_code, detail):
                    cooldown = int(os.environ.get("AGY_POOL_COOLDOWN_SECONDS", "3600"))
                    await pool_manager.mark_rate_limited(account_id, cooldown)
                    excluded.add(account_id)
                    logger.warning("[image] account %s rate-limited, rotating: %s", account_id, detail[:200])
                    continue
                raise RuntimeError(f"image generation failed (HTTP {response.status_code}): {detail}")

            image = _extract_image_from_json(response.json())

        if account_id:
            await pool_manager.mark_success(account_id)
        return image
