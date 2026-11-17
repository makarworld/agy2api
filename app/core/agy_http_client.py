import asyncio
import hashlib
import json
import logging
import os
import re
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
    extract_stream_parts_from_response,
    finalize_pending_tool_calls,
    http_debug_enabled,
    ingest_stream_tool_calls,
    messages_to_gemini_contents,
    parse_text_serialized_tool_call,
    summarize_sse_parts,
    thought_as_text_enabled,
    thought_text_wrappers,
    tool_choice_to_gemini_mode,
)
from app.core.model_manager import resolve_http_model
from app.core.request_tracer import record_attempt

logger = logging.getLogger(__name__)

_TITLE_PROMPT_MARKER = "write the title in russian"
_CLAUDE_CODE_SYSTEM_MARKERS = ("x-anthropic-billing-header:", "You are Claude Code")


class ProQuotaExhaustedError(RuntimeError):
    """All accounts rejected the local Pro quota."""


def _suppress_thought_text(system: Optional[str], messages: List[dict]) -> bool:
    payload = json.dumps({"system": system or "", "messages": messages}, ensure_ascii=False).lower()
    return _TITLE_PROMPT_MARKER in payload


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


def _agent_request_id(cascade_id: str, trajectory_id: str, step: int) -> str:
    return f"agent/{cascade_id}/{int(time.time() * 1000)}/{trajectory_id}/{step}"


_DEFAULT_ANTIGRAVITY_TOOLS: Optional[List[dict]] = None


def _get_default_antigravity_tools() -> List[dict]:
    global _DEFAULT_ANTIGRAVITY_TOOLS
    if _DEFAULT_ANTIGRAVITY_TOOLS is None:
        tools_path = os.path.join(os.path.dirname(__file__), "default_antigravity_tools.json")
        try:
            with open(tools_path, "r", encoding="utf-8") as f:
                _DEFAULT_ANTIGRAVITY_TOOLS = json.load(f)
        except Exception:
            _DEFAULT_ANTIGRAVITY_TOOLS = []
    return _DEFAULT_ANTIGRAVITY_TOOLS


def _stable_session_id(seed_key: Optional[str]) -> str:
    seed = seed_key or "default-antigravity-session"
    val = int(hashlib.sha256(seed.encode()).hexdigest()[:15], 16)
    signed_val = -((val % (2**62)) + 10**17)
    return str(signed_val)


_CONVERSATION_SESSIONS: dict[str, dict] = {}
_MAX_CONVERSATION_SESSIONS = 5000


def _get_or_create_session(messages: List[dict]) -> tuple[str, str, int, int]:
    """Returns (cascade_id, trajectory_id, step, request_seq) maintaining conversation continuity."""
    now = time.time()
    if len(_CONVERSATION_SESSIONS) > _MAX_CONVERSATION_SESSIONS:
        stale_keys = [k for k, v in _CONVERSATION_SESSIONS.items() if now - v.get("last_activity", 0) > 86400]
        for k in stale_keys:
            _CONVERSATION_SESSIONS.pop(k, None)

    session_key = ""
    if messages:
        first_msg = messages[0]
        raw_key = f"{first_msg.get('role')}:{str(first_msg.get('content', ''))[:300]}"
        session_key = hashlib.sha256(raw_key.encode("utf-8", errors="ignore")).hexdigest()[:16]

    if session_key and session_key in _CONVERSATION_SESSIONS:
        sess = _CONVERSATION_SESSIONS[session_key]
        sess["step"] += 1
        sess["request_seq"] += 1
        sess["last_activity"] = now
        return sess["cascade_id"], sess["trajectory_id"], sess["step"], sess["request_seq"]

    cascade_id = str(uuid.uuid4())
    trajectory_id = str(uuid.uuid4())
    step = 1
    request_seq = 1

    if session_key:
        _CONVERSATION_SESSIONS[session_key] = {
            "cascade_id": cascade_id,
            "trajectory_id": trajectory_id,
            "step": step,
            "request_seq": request_seq,
            "last_activity": now,
        }

    return cascade_id, trajectory_id, step, request_seq


_HAR_MODEL_ENUMS = {
    "gemini-3.8-flash-high": "MODEL_PLACEHOLDER_M318",
    "gemini-3.8-flash-low": "MODEL_PLACEHOLDER_M320",
    "gemini-3.7-flash-high": "MODEL_PLACEHOLDER_M298",
    "gemini-3.7-flash-low": "MODEL_PLACEHOLDER_M300",
    "gemini-3.6-flash-high": "MODEL_PLACEHOLDER_M71",
    "gemini-3.6-flash-low": "MODEL_PLACEHOLDER_M73",
    "gemini-3.1-pro-low": "MODEL_PLACEHOLDER_M36",
    "gemini-pro-agent": "MODEL_PLACEHOLDER_M16",
    "gpt-oss-120b-medium": "MODEL_OPENAI_GPT_OSS_120B_MEDIUM",
    "claude-opus-4-6-thinking": "MODEL_PLACEHOLDER_M26",
    "claude-sonnet-4-6": "MODEL_PLACEHOLDER_M35",
}


def _model_enum(model: str) -> str:
    return _HAR_MODEL_ENUMS.get(model.lower(), model)


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
            json={"metadata": {"ideType": "ANTIGRAVITY"}},
        )
    if response.status_code == 401 and not _auth_retried:
        logger.warning("[http] loadCodeAssist 401 — forcing OAuth refresh and retrying")
        access_token = await _refresh_after_401(access_token, account_id=account_id, proxy=proxy)
        return await _get_project_id(access_token, account_id=account_id, proxy=proxy, _auth_retried=True)
    if response.status_code != 200:
        from app.core.account_verification import handle_verification_error

        handle_verification_error(response.text, account_id=account_id)
        raise RuntimeError(f"loadCodeAssist failed (HTTP {response.status_code}): {response.text}")

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


def _is_model_capacity_error(status_code: int, detail: str) -> bool:
    lowered = detail.lower()
    return status_code == 503 and ("no capacity available" in lowered or "service is currently unavailable" in lowered)


def _map_usage(usage_metadata: dict) -> dict:
    if not usage_metadata:
        return {}
    # promptTokenCount is total input; cachedContentTokenCount is a subset (not additive).
    prompt_total = usage_metadata.get("promptTokenCount", 0)
    cache_read = usage_metadata.get("cachedContentTokenCount", 0)
    body = {
        "input_tokens": prompt_total,
        "output_tokens": usage_metadata.get("candidatesTokenCount", 0),
        "thinking_tokens": usage_metadata.get("thoughtsTokenCount", 0),
        "cache_read_tokens": cache_read,
        "total_tokens": prompt_total
        + usage_metadata.get("candidatesTokenCount", 0)
        + usage_metadata.get("thoughtsTokenCount", 0),
    }
    return body


def _generation_config(
    backend_model: str,
    thinking_level: Optional[str],
    *,
    tools_present: bool = False,
    max_output_tokens: int = 65536,
) -> dict:
    lower_model = backend_model.lower()
    if lower_model.startswith("claude-"):
        max_output_tokens, default_budget = 64000, 1024
    elif lower_model == "gpt-oss-120b-medium":
        max_output_tokens, default_budget = 32768, 8192
    elif lower_model == "gemini-pro-agent":
        max_output_tokens, default_budget = 65535, 10001
    elif lower_model.endswith("-low"):
        default_budget = 1000
    elif lower_model.endswith("-medium"):
        default_budget = 4000
    else:
        default_budget = -1
    gen_config: dict = {"maxOutputTokens": max_output_tokens}
    thinking_cfg: dict = {}

    is_pro = "pro" in lower_model
    is_gemini_3 = lower_model.startswith("gemini-3.") or "gemini-3" in lower_model

    if thinking_level == "zero":
        thinking_cfg["includeThoughts"] = False
        thinking_cfg["thinkingBudget"] = 0
    elif thinking_level and lower_model.startswith("gemini-"):
        default_budget = {"low": 1000, "medium": 4000, "high": -1}.get(thinking_level, default_budget)
    elif thinking_level:
        thinking_cfg["thinkingLevel"] = thinking_level

    if is_pro:
        # Gemini Pro models only work in thinking mode and reject budget 0.
        thinking_cfg.setdefault("includeThoughts", True)
        thinking_cfg.setdefault("thinkingBudget", default_budget)
    elif thinking_level:
        # Explicit thinking level requested (e.g. high/medium/low for flash)
        thinking_cfg.setdefault("includeThoughts", True)
        thinking_cfg.setdefault("thinkingBudget", default_budget)
    elif is_gemini_3 and "flash" in lower_model:
        # Gemini 3.x Flash without explicit level (auto/default)
        thinking_cfg.setdefault("includeThoughts", True)
        thinking_cfg.setdefault("thinkingBudget", default_budget)
    elif tools_present:
        # Legacy/base models with tools -> disable thinking for speed
        thinking_cfg["includeThoughts"] = True
        thinking_cfg["thinkingBudget"] = default_budget

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
    max_output_tokens: int = 65536,
    trajectory_id: Optional[str] = None,
    cascade_id: Optional[str] = None,
    step: int = 1,
    request_seq: int = 1,
    account_id: Optional[str] = None,
    request_type: str = "agent",
) -> dict:
    gemini_tools = anthropic_tools_to_gemini(tools)
    if not gemini_tools and request_type == "agent":
        default_tools = _get_default_antigravity_tools()
        if default_tools:
            gemini_tools = default_tools

    session_id = _stable_session_id(account_id or project_id)
    inner: dict = {
        "contents": contents,
        "generationConfig": _generation_config(
            backend_model,
            thinking_level,
            tools_present=bool(gemini_tools),
            max_output_tokens=max_output_tokens,
        ),
        "sessionId": session_id,
    }

    if system and any(marker in system for marker in _CLAUDE_CODE_SYSTEM_MARKERS):
        # Cloud Code masks rejection of Claude Code's identity system prompt as HTTP 429.
        # Agy carries client context in user contents, which preserves it without rejection.
        inner["contents"] = [{"role": "user", "parts": [{"text": system}]}] + contents
    elif system:
        inner["systemInstruction"] = {"role": "user", "parts": [{"text": system}]}

    if gemini_tools:
        inner["tools"] = gemini_tools
        mode = tool_choice_to_gemini_mode(tool_choice)
        if mode:
            inner["toolConfig"] = {"functionCallingConfig": {"mode": mode}}

    traj_id = trajectory_id or str(uuid.uuid4())
    casc_id = cascade_id or str(uuid.uuid4())

    if request_type == "checkpoint":
        req_id = f"checkpoint/{traj_id}"
    else:
        req_id = _agent_request_id(casc_id, traj_id, step)

    body = {
        "project": project_id,
        "requestId": req_id,
        "model": backend_model,
        "userAgent": "antigravity",
        "requestType": request_type,
        "request": inner,
    }

    if request_type == "agent":
        labels: dict[str, str] = {
            "last_step_index": str(max(0, step - 1)),
            "model_enum": _model_enum(backend_model),
            "request_id": f"{traj_id}-{request_seq}",
            "trajectory_id": traj_id,
            "used_claude": str(backend_model.lower().startswith("claude-")).lower(),
            "used_claude_conservative": str(backend_model.lower().startswith("claude-")).lower(),
            "used_non_gemini_model": str(not backend_model.lower().startswith("gemini-")).lower(),
        }
        if step > 1:
            labels["last_execution_id"] = f"{traj_id}-{max(0, request_seq - 1)}"
        body["request"]["labels"] = labels
    return body


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
    parts_summary = summarize_sse_parts(last_sse_obj) if last_sse_obj else "n/a"
    logger.warning(
        f"[http][debug] empty stream finishReason={finish_reason} "
        f"usage={final_usage or usage_meta} pending={len(pending_tool_calls)} "
        f"unnamed_keys={unnamed} parts={parts_summary}"
    )
    if last_sse_obj:
        logger.warning(f"[http][debug] last_sse={json.dumps(last_sse_obj)[:2000]}")


def _log_http_request(url: str, body: dict) -> None:
    if http_debug_enabled():
        logger.warning(f"[http][debug] REQUEST url={url} json={json.dumps(body, ensure_ascii=False)}")


def _log_http_response(url: str, status: int, body: str) -> None:
    if http_debug_enabled():
        logger.warning(f"[http][debug] RESPONSE url={url} status={status} body={body}")


def _estimate_content_tokens(content: dict) -> int:
    """Rough token estimate for a single Gemini content entry.

    Uses ~3 chars/token (conservative) because the real tokenizer often
    produces more tokens than a naive chars÷4 estimate.
    """
    total = 0
    for part in content.get("parts", []):
        if "text" in part:
            total += len(part["text"])
        elif "inlineData" in part:
            # base64 data is ~1.37x the raw bytes; token cost is much lower
            # than text but still significant
            total += len(part["inlineData"].get("data", "")) // 2
        elif "functionCall" in part:
            total += len(json.dumps(part["functionCall"].get("args", {})))
            total += len(part["functionCall"].get("name", ""))
        elif "functionResponse" in part:
            total += len(json.dumps(part["functionResponse"].get("response", {})))
            total += len(part["functionResponse"].get("name", ""))
    return total // 3


_PROMPT_TOO_LONG_RE = re.compile(r"prompt is too long:\s*(\d+)\s*tokens?\s*>\s*(\d+)\s*maximum")


def _trim_contents_to_limit(
    contents: List[dict],
    max_tokens: int,
    *,
    system: Optional[str] = None,
    tools: Optional[List[dict]] = None,
) -> List[dict]:
    """Drop oldest contents (keeping at least the last message) to fit under max_tokens.

    After trimming, strips orphaned functionResponse parts from the new first
    user message (their matching functionCall was in a dropped model message).
    """
    overhead = 0
    if system:
        overhead += len(system) // 4
    if tools:
        overhead += len(json.dumps(tools)) // 4

    total = overhead + sum(_estimate_content_tokens(c) for c in contents)
    if total <= max_tokens:
        return contents

    logger.warning(
        "[http] prompt too large ~%d tokens (limit %d), trimming oldest messages",
        total,
        max_tokens,
    )

    # Always keep at least the last content entry
    trimmed = list(contents)
    running = total
    while len(trimmed) > 1 and running > max_tokens:
        removed = trimmed.pop(0)
        running -= _estimate_content_tokens(removed)

    # Ensure first message is from user (Gemini requirement)
    while len(trimmed) > 1 and trimmed[0].get("role") != "user":
        removed = trimmed.pop(0)
        running -= _estimate_content_tokens(removed)

    # Strip orphaned functionResponse/functionCall pairs iteratively.
    # Removing a model entry can orphan the next user's functionResponse;
    # removing that user entry can leave a model entry at position 0 (invalid).
    # Loop until stable.
    cleaned = list(trimmed)
    changed = True
    while changed:
        changed = False

        # Collect all functionCall ids/names in remaining model entries
        available_fc_ids: set[str] = set()
        for entry in cleaned:
            if entry.get("role") != "model":
                continue
            for part in entry.get("parts", []):
                fc = part.get("functionCall")
                if fc and fc.get("id"):
                    available_fc_ids.add(fc["id"])

        # Strip orphaned functionResponse parts from user entries
        new_cleaned: List[dict] = []
        for entry in cleaned:
            if entry.get("role") != "user":
                new_cleaned.append(entry)
                continue
            kept_parts = []
            for part in entry.get("parts", []):
                fr = part.get("functionResponse")
                if fr:
                    fr_id = fr.get("id", "")
                    if fr_id and fr_id not in available_fc_ids:
                        changed = True
                        continue  # orphaned
                kept_parts.append(part)
            if kept_parts:
                new_cleaned.append({**entry, "parts": kept_parts})
            else:
                changed = True  # entire entry dropped
        cleaned = new_cleaned

        # Ensure first message is from user (Gemini requirement)
        while len(cleaned) > 1 and cleaned[0].get("role") != "user":
            cleaned.pop(0)
            changed = True

    # Final safety: if cleaned is empty, keep at least the last original content
    if not cleaned:
        # Take last user message, strip any functionResponse parts
        last = contents[-1]
        text_parts = [p for p in last.get("parts", []) if "text" in p]
        cleaned = [{**last, "parts": text_parts}] if text_parts else [{"role": "user", "parts": [{"text": ""}]}]

    final_tokens = overhead + sum(_estimate_content_tokens(c) for c in cleaned)
    logger.info(
        "[http] trimmed prompt to ~%d tokens (%d/%d contents kept)",
        final_tokens,
        len(cleaned),
        len(contents),
    )
    return cleaned


async def stream_completion(
    messages: List[dict],
    system: Optional[str] = None,
    model: Optional[str] = None,
    *,
    tools: Optional[List[dict]] = None,
    tool_choice: Optional[Any] = None,
    proxy: Optional[str] = None,
    thought_as_text: Optional[bool] = None,
    thinking_level_override: Optional[str] = None,
) -> AsyncIterator[dict]:
    """Direct HTTP stream to Cloud Code Assist with Claude Code tools passthrough."""
    excluded: set[str] = set()
    backend_model, thinking_level = resolve_http_model(model or "gemini-2.5-flash")
    if thinking_level_override is not None and "pro" not in backend_model.lower():
        thinking_level = "zero" if thinking_level_override == "0" else thinking_level_override
    while True:
        try:
            account_id, pool_proxy, access_token = await pool_manager.acquire_http_account(
                exclude=excluded, model=backend_model
            )
        except RuntimeError as exc:
            if backend_model == "gemini-pro-agent":
                raise ProQuotaExhaustedError("Все лимиты Pro закончились. Переключите модель на другую.") from exc
            raise
        effective_proxy = proxy if proxy is not None else pool_proxy
        if not access_token:
            access_token = await get_access_token(proxy=effective_proxy)
        try:
            project_id = await _get_project_id(access_token, account_id=account_id, proxy=effective_proxy)
            proxy = effective_proxy
            break
        except Exception as exc:
            from app.core.account_verification import handle_verification_error

            handle_verification_error(exc, account_id=account_id)
            if account_id:
                excluded.add(account_id)
                logger.warning(
                    f"[http] _get_project_id failed for account={account_id}, rotating to next account: {exc}"
                )
                continue
            raise
    tools_present = bool(anthropic_tools_to_gemini(tools))
    allow_thought_text = thought_as_text_enabled(tools_present=tools_present, param_override=thought_as_text)
    if _suppress_thought_text(system, messages):
        allow_thought_text = False
    thought_prefix_raw, thought_suffix_raw = thought_text_wrappers()
    thought_prefix = thought_prefix_raw.replace("\\n", "\n")
    thought_suffix = thought_suffix_raw.replace("\\n", "\n")
    max_output_tokens = int(os.environ.get("AGY_HTTP_MAX_OUTPUT_TOKENS") or "65536")
    is_checkpoint = _suppress_thought_text(system, messages)
    request_type = "checkpoint" if is_checkpoint else "agent"
    cascade_id, trajectory_id, step, request_seq = _get_or_create_session(messages)

    max_input_tokens = int(os.environ.get("AGY_HTTP_MAX_INPUT_TOKENS", "950000"))
    trim_aggressive = False
    retried_empty = False
    auth_retried = False
    yielded_any_content = False
    prompt_too_long_retries = 0
    net_retries = 0

    while True:
        contents = messages_to_gemini_contents(messages, trim_aggressive=trim_aggressive)
        if not contents:
            raise RuntimeError("No user/assistant messages to send")

        contents = _trim_contents_to_limit(contents, max_input_tokens, system=system, tools=tools)

        body = _build_envelope(
            project_id,
            backend_model,
            contents,
            thinking_level,
            system=system,
            tools=tools,
            tool_choice=tool_choice,
            max_output_tokens=max_output_tokens,
            trajectory_id=trajectory_id,
            cascade_id=cascade_id,
            step=step,
            request_seq=request_seq,
            account_id=account_id,
            request_type=request_type,
        )
        if model and model != backend_model and not retried_empty:
            logger.info(f"[http] model {model} -> backend {backend_model}")

        full_text = ""
        final_usage: dict = {}
        pending_tool_calls: dict[str, dict] = {}
        last_finish_reason: Optional[str] = None
        last_sse_obj: Optional[dict] = None
        retried_auth = False
        rate_limit_detail: Optional[str] = None
        prompt_too_long_retry = False
        serialized_text_buffer = ""
        buffering_serialized_text = False

        thought_buffer = ""
        trailing_ws = ""
        text_stream_started = False

        def _flush_thoughts() -> list[dict]:
            nonlocal thought_buffer
            if not allow_thought_text or not thought_buffer.strip():
                thought_buffer = ""
                return []
            cleaned = re.sub(r"[\r\n]+", " ", thought_buffer).strip()
            thought_buffer = ""
            if not cleaned:
                return []
            formatted = f"{thought_prefix}{cleaned}{thought_suffix}"
            return [{"delta": formatted}]

        def _process_visible_text(text: str) -> list[dict]:
            nonlocal trailing_ws, text_stream_started
            if not text:
                return []
            out = _flush_thoughts()
            if not text_stream_started:
                text = text.lstrip()
                if not text:
                    return out
                text_stream_started = True
            combined = trailing_ws + text
            trailing_ws = ""
            stripped = combined.rstrip(" \t\r\n")
            if stripped:
                trailing_ws = combined[len(stripped) :]
                out.append({"delta": stripped})
            else:
                trailing_ws = combined
            return out

        record_attempt(raw_request=body, pool_account=account_id)

        async with httpx.AsyncClient(**httpx_client_kwargs(proxy=proxy, timeout=300.0)) as client:
            try:
                _log_http_request(STREAM_GENERATE_URL, body)
                debug_response_lines: list[str] = []
                async with client.stream(
                    "POST",
                    STREAM_GENERATE_URL,
                    headers=cloudcode_headers(access_token, streaming=True),
                    json=body,
                ) as response:
                    if response.status_code == 401 and not auth_retried:
                        detail = (await response.aread()).decode(errors="replace")[:200]
                        record_attempt(
                            raw_request=body,
                            response_status=401,
                            raw_response=detail,
                            pool_account=account_id,
                        )
                        logger.warning(
                            f"[http] streamGenerateContent 401 — forcing OAuth refresh and retrying: {detail}"
                        )
                        access_token = await _refresh_after_401(access_token, account_id=account_id, proxy=proxy)
                        auth_retried = True
                        retried_auth = True
                    elif response.status_code != 200:
                        detail = (await response.aread()).decode(errors="replace")
                        from app.core.account_verification import handle_verification_error

                        handle_verification_error(detail, account_id=account_id)
                        record_attempt(
                            raw_request=body,
                            response_status=response.status_code,
                            raw_response=detail,
                            pool_account=account_id,
                        )
                        _log_http_response(STREAM_GENERATE_URL, response.status_code, detail)
                        if _is_model_capacity_error(response.status_code, detail):
                            logger.warning(
                                "[http] model service unavailable; retrying without account rotation: "
                                f"model={backend_model} reason=model_capacity endpoint=streamGenerateContent"
                            )
                            raise RuntimeError(f"streamGenerateContent failed (HTTP {response.status_code}): {detail}")
                        if account_id and _is_rate_limited(response.status_code, detail):
                            rate_limit_detail = detail
                        elif (
                            response.status_code == 400
                            and "prompt is too long" in detail
                            and prompt_too_long_retries < 3
                        ):
                            m = _PROMPT_TOO_LONG_RE.search(detail)
                            if m:
                                upstream_limit = int(m.group(2))
                                # Use the real upstream limit with 10% margin
                                max_input_tokens = int(upstream_limit * 0.85)
                            else:
                                # Halve our estimate if we can't parse the real count
                                max_input_tokens = max_input_tokens // 2
                            prompt_too_long_retries += 1
                            prompt_too_long_retry = True
                            logger.warning(
                                "[http] prompt too long (attempt %d/3), reducing limit to %d tokens and retrying",
                                prompt_too_long_retries,
                                max_input_tokens,
                            )
                        else:
                            if account_id and response.status_code >= 500:
                                await pool_manager.mark_failure(account_id)
                            raise RuntimeError(f"streamGenerateContent failed (HTTP {response.status_code}): {detail}")
                    else:
                        async for line in response.aiter_lines():
                            if http_debug_enabled():
                                debug_response_lines.append(line)
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

                            (
                                delta_text,
                                thought_chunk,
                                tool_calls,
                                finish_reason,
                            ) = extract_stream_parts_from_response(
                                obj,
                                allow_thought_text=allow_thought_text,
                            )
                            if finish_reason:
                                last_finish_reason = finish_reason

                            if thought_chunk:
                                thought_buffer += thought_chunk

                            if delta_text:
                                if tools_present and (
                                    buffering_serialized_text
                                    or (not full_text and delta_text.lstrip().startswith(("{", "[", "```")))
                                ):
                                    buffering_serialized_text = True
                                    serialized_text_buffer += delta_text
                                    full_text += delta_text
                                    continue

                                for item in _process_visible_text(delta_text):
                                    full_text += item["delta"]
                                    yield item
                                    yielded_any_content = True

                            new_calls = ingest_stream_tool_calls(tool_calls, pending_tool_calls)
                            if new_calls:
                                for item in _flush_thoughts():
                                    full_text += item["delta"]
                                    yield item
                                    yielded_any_content = True
                                yield {"tool_calls": new_calls}
                                yielded_any_content = True
                        _log_http_response(
                            STREAM_GENERATE_URL,
                            response.status_code,
                            "\n".join(debug_response_lines),
                        )
            except (
                httpx.ConnectError,
                httpx.ConnectTimeout,
                httpx.ReadError,
                httpx.ReadTimeout,
                httpx.RemoteProtocolError,
            ) as net_err:
                record_attempt(
                    raw_request=body,
                    response_status=0,
                    raw_response=f"NetworkError: {type(net_err).__name__}: {net_err}",
                    pool_account=account_id,
                )
                if yielded_any_content:
                    logger.error(
                        f"[http] network error after stream started (account={account_id}). Dropping stream to trigger clean client retry: {net_err}"
                    )
                    raise RuntimeError(f"Network error mid-stream ({type(net_err).__name__}): {net_err}") from net_err

                # Network error before any content was yielded:
                # Do NOT rotate account! Network glitches are transient host/proxy/upstream network issues,
                # not an account fault. Rotating accounts burns valid accounts and breaks session affinity.
                if not yielded_any_content and net_retries < 2:
                    net_retries += 1
                    sleep_s = 0.5 * net_retries
                    logger.warning(
                        f"[http] Network error on account={account_id} ({type(net_err).__name__}: {net_err}), retrying on SAME account in {sleep_s}s (attempt {net_retries}/2)"
                    )
                    await asyncio.sleep(sleep_s)
                    continue

                logger.error(
                    f"[http] Network error on account={account_id} ({type(net_err).__name__}: {net_err}) after {net_retries} retries"
                )
                raise RuntimeError(
                    f"Upstream network error ({type(net_err).__name__}): {net_err} (account: {account_id or 'none'})"
                ) from net_err

        for item in _flush_thoughts():
            full_text += item["delta"]
            yield item
            yielded_any_content = True
        full_text = full_text.strip()

        if rate_limit_detail is not None:
            cooldown = int(os.environ.get("AGY_POOL_MODEL_COOLDOWN_SECONDS", "60"))
            previous_account_id = account_id
            await pool_manager.mark_rate_limited(account_id, cooldown, model=backend_model)
            excluded.add(account_id)
            logger.warning(
                f"[http] rotating account={account_id} model={backend_model} endpoint=streamGenerateContent "
                f"reason=account_rate_limit cooldown={cooldown}s next=select: {rate_limit_detail}"
            )
            try:
                account_id, proxy, access_token = await pool_manager.acquire_http_account(
                    exclude=excluded, model=backend_model
                )
            except RuntimeError as exc:
                if backend_model == "gemini-pro-agent":
                    raise ProQuotaExhaustedError("Все лимиты Pro закончились. Переключите модель на другую.") from exc
                raise
            logger.info(
                f"[http] rotation complete previous={previous_account_id} next={account_id} model={backend_model} "
                "endpoint=streamGenerateContent reason=account_rate_limit"
            )
            project_id = await _get_project_id(access_token, account_id=account_id, proxy=proxy)
            continue

        if prompt_too_long_retry:
            # Re-enter the loop — contents will be re-trimmed with the lowered max_input_tokens
            continue

        if retried_auth:
            step += 2
            request_seq += 1
            continue

        all_tool_calls = finalize_pending_tool_calls(pending_tool_calls)
        if full_text and not all_tool_calls:
            parsed_text, parsed_calls = parse_text_serialized_tool_call(full_text)
            if parsed_calls:
                full_text = parsed_text
                all_tool_calls = parsed_calls
                if parsed_text and not yielded_any_content:
                    for item in _process_visible_text(parsed_text):
                        yield item
                        yielded_any_content = True
            elif serialized_text_buffer:
                buffering_serialized_text = False
                clean_serialized = serialized_text_buffer.strip()
                if clean_serialized:
                    yield {"delta": clean_serialized}
                    full_text = clean_serialized
        full_text = full_text.strip()
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
                    f"[http] empty response finishReason={last_finish_reason} — retrying with aggressive trim"
                )
                retried_empty = True
                step += 2
                request_seq += 1
                trim_aggressive = True
                max_output_tokens = min(max_output_tokens * 2, 16384)
                continue

            error_msg = f"Gemini returned empty response (finishReason={last_finish_reason or 'unknown'})"
            logger.error(f"[http] {error_msg}")
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
            await pool_manager.mark_success(account_id, model=backend_model)

        candidate_parts = []
        if full_text:
            candidate_parts.append({"text": full_text})
        if all_tool_calls:
            for tc in all_tool_calls:
                candidate_parts.append({"functionCall": {"name": tc.get("name"), "args": tc.get("input", {})}})

        raw_resp_obj = {
            "candidates": [
                {
                    "content": {
                        "role": "model",
                        "parts": candidate_parts or [{"text": ""}],
                    },
                    "finishReason": last_finish_reason or "STOP",
                }
            ],
            "usageMetadata": final_usage or (last_sse_obj or {}).get("usageMetadata", {}),
        }
        record_attempt(
            raw_request=body,
            response_status=200,
            raw_response=raw_resp_obj,
            pool_account=account_id,
        )

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
        account_proxy = pool_proxy if pool_proxy is not None else proxy
        if not access_token:
            access_token = await get_access_token(proxy=account_proxy)
        project_id = await _get_project_id(access_token, account_id=account_id, proxy=account_proxy)
        body = _build_image_request(prompt, project_id, backend_model, aspect_ratio, reference_parts)
        headers = cloudcode_headers(access_token, streaming=False)

        record_attempt(raw_request=body, pool_account=account_id)

        async with httpx.AsyncClient(**httpx_client_kwargs(proxy=account_proxy, timeout=300.0)) as client:
            response = await client.post(GENERATE_CONTENT_URL, headers=headers, json=body)
            if response.status_code == 401:
                access_token = await _refresh_after_401(access_token, account_id=account_id, proxy=account_proxy)
                headers = cloudcode_headers(access_token, streaming=False)
                response = await client.post(GENERATE_CONTENT_URL, headers=headers, json=body)

            if response.status_code != 200:
                detail = response.text
                from app.core.account_verification import handle_verification_error

                handle_verification_error(detail, account_id=account_id)
                record_attempt(
                    raw_request=body,
                    response_status=response.status_code,
                    raw_response=detail,
                    pool_account=account_id,
                )
                if _is_model_capacity_error(response.status_code, detail):
                    logger.warning(
                        "[image] model service unavailable; retrying without account rotation: "
                        f"model={backend_model} reason=model_capacity"
                    )
                    raise RuntimeError(f"image generation failed (HTTP {response.status_code}): {detail}")
                if account_id and _is_rate_limited(response.status_code, detail):
                    cooldown = int(os.environ.get("AGY_POOL_COOLDOWN_SECONDS", "3600"))
                    await pool_manager.mark_rate_limited(account_id, cooldown)
                    excluded.add(account_id)
                    logger.warning(
                        f"[image] rotating account={account_id} reason=account_rate_limit next=select: {detail}"
                    )
                    continue
                raise RuntimeError(f"image generation failed (HTTP {response.status_code}): {detail}")

            resp_json = response.json()
            record_attempt(
                raw_request=body,
                response_status=200,
                raw_response=resp_json,
                pool_account=account_id,
            )
            image = _extract_image_from_json(resp_json)

        if account_id:
            await pool_manager.mark_success(account_id, model=backend_model)
        return image
