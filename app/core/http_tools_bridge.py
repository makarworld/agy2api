"""Anthropic tools <-> Gemini functionDeclarations conversion for HTTP transport."""
import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)
# Gemini functionDeclarations.parameters accept a small OpenAPI subset only.
_SCHEMA_ALLOWED_KEYS = frozenset({
    "type",
    "properties",
    "required",
    "items",
    "description",
    "enum",
})

_TYPE_MAP = {
    "object": "OBJECT",
    "string": "STRING",
    "integer": "INTEGER",
    "number": "NUMBER",
    "boolean": "BOOLEAN",
    "array": "ARRAY",
    "null": "NULL",
}


def _normalize_schema_type(value: Any) -> Any:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item.lower() != "null":
                mapped = _TYPE_MAP.get(item.lower())
                return mapped if mapped else item.upper()
        return "STRING"
    if isinstance(value, str):
        mapped = _TYPE_MAP.get(value.lower())
        return mapped if mapped else value.upper()
    return value


def _coerce_items_schema(value: Any) -> Optional[dict]:
    """Gemini Schema.items is a single object, not a JSON Schema tuple list."""
    if isinstance(value, dict):
        return _sanitize_json_schema_for_gemini(value)
    if isinstance(value, list):
        for entry in value:
            if isinstance(entry, dict):
                return _sanitize_json_schema_for_gemini(entry)
        return {"type": "STRING"}
    return None


def _sanitize_json_schema_for_gemini(schema: Any) -> Any:
    """Keep only Gemini-compatible schema fields; drop JSON Schema validation keywords."""
    if not isinstance(schema, dict):
        return schema

    for combiner in ("anyOf", "oneOf", "allOf"):
        options = schema.get(combiner)
        if isinstance(options, list) and options:
            candidates = [item for item in options if isinstance(item, dict)]
            if candidates:
                preferred = next(
                    (
                        item
                        for item in candidates
                        if item.get("type") not in (None, "null", "NULL")
                        or item.get("properties")
                    ),
                    candidates[0],
                )
                return _sanitize_json_schema_for_gemini(preferred)

    out: dict = {}
    for key, value in schema.items():
        if key not in _SCHEMA_ALLOWED_KEYS:
            continue
        if key == "type":
            out[key] = _normalize_schema_type(value)
        elif key == "properties" and isinstance(value, dict):
            out[key] = {
                prop_name: _sanitize_json_schema_for_gemini(prop_schema)
                for prop_name, prop_schema in value.items()
                if isinstance(prop_schema, dict)
            }
        elif key == "required" and isinstance(value, list):
            out[key] = [item for item in value if isinstance(item, str)]
        elif key == "items":
            coerced = _coerce_items_schema(value)
            if coerced is not None:
                out[key] = coerced
        elif key == "description" and isinstance(value, str):
            out[key] = value
        elif key == "enum" and isinstance(value, list):
            out[key] = value

    if "type" not in out and "properties" in out:
        out["type"] = "OBJECT"
    elif "type" not in out and "enum" in out:
        out.setdefault("type", "STRING")
    elif "type" not in out and "items" in out:
        out["type"] = "ARRAY"

    # Gemini rejects `items` unless the field type is ARRAY.
    if out.get("type") != "ARRAY":
        out.pop("items", None)
    elif "items" in out and not isinstance(out["items"], dict):
        out["items"] = {"type": "STRING"}

    return out


def http_debug_enabled() -> bool:
    return os.environ.get("AGY_HTTP_DEBUG", "").lower() in ("1", "true", "yes")


def thought_as_text_enabled(*, tools_present: bool = False) -> bool:
    env = os.environ.get("AGY_THOUGHT_AS_TEXT")
    if env is not None and str(env).strip() != "":
        return str(env).strip().lower() in ("1", "true", "yes")
    return tools_present


def tool_result_trim_enabled() -> bool:
    """When false, functionResponse tool results are sent to Gemini without length limits."""
    env = os.environ.get("AGY_HTTP_TRIM_TOOL_RESULTS")
    if env is None or str(env).strip() == "":
        return True
    return str(env).strip().lower() in ("1", "true", "yes")


def _max_tool_result_chars(*, aggressive: bool = False, is_recent: bool = True) -> Optional[int]:
    if not tool_result_trim_enabled():
        return None
    if aggressive:
        return int(os.environ.get("AGY_HTTP_RETRY_TOOL_RESULT_CHARS", "4000"))
    if not is_recent:
        return int(os.environ.get("AGY_HTTP_OLD_TOOL_RESULT_CHARS", "4000"))
    return int(os.environ.get("AGY_HTTP_MAX_TOOL_RESULT_CHARS", "12000"))


def _trim_tool_result_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    logger.info("[http] trimmed tool result %s chars -> %s", len(text), limit)
    return text[:limit] + "\n...[truncated]"


def summarize_sse_parts(obj: dict) -> str:
    response = obj.get("response") or obj
    candidates = response.get("candidates") or []
    if not candidates:
        return "candidates=0"
    cand = candidates[0]
    parts = cand.get("content", {}).get("parts") or []
    flags = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        bits = []
        if part.get("thought"):
            bits.append("thought")
        if part.get("text"):
            bits.append("text")
        if part.get("functionCall"):
            bits.append("functionCall")
        flags.append("+".join(bits) or "empty")
    finish = cand.get("finishReason") or cand.get("finish_reason") or "?"
    return f"parts={len(parts)} [{', '.join(flags)}] finishReason={finish}"


def finalize_pending_tool_calls(pending: dict[str, dict]) -> List[dict]:
    """Emit any pending tool calls that accumulated a name during streaming."""
    finalized: List[dict] = []
    for key, tc in list(pending.items()):
        if not tc.get("name"):
            if http_debug_enabled() and tc.get("input"):
                logger.warning("[http] dropping unnamed pending tool call key=%s", key)
            continue
        finalized.append({k: v for k, v in tc.items() if not k.startswith("_")})
    return finalized


def anthropic_tools_to_gemini(tools: Optional[List[dict]]) -> Optional[List[dict]]:
    if not tools:
        return None
    decls: List[dict] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        name = tool.get("name")
        if not name:
            continue
        decl: dict = {
            "name": name,
            "description": tool.get("description", ""),
        }
        schema = tool.get("input_schema") or tool.get("parameters")
        if isinstance(schema, dict) and schema:
            decl["parameters"] = _sanitize_json_schema_for_gemini(schema)
        decls.append(decl)
    if not decls:
        return None
    return [{"functionDeclarations": decls}]


def tool_choice_to_gemini_mode(tool_choice: Any) -> Optional[str]:
    if tool_choice is None or tool_choice == "auto":
        return "AUTO"
    if tool_choice == "none":
        return "NONE"
    if tool_choice == "any":
        return "ANY"
    if isinstance(tool_choice, dict) and tool_choice.get("type") == "tool":
        return "ANY"
    return None


def encode_tool_id(fc_id: str = "", thought_sig: str = "") -> str:
    """Anthropic tool_use id envelope around Gemini functionCall.id (+ optional thoughtSignature)."""
    fc_id = (fc_id or "").strip()
    thought_sig = (thought_sig or "").strip()
    if not fc_id and not thought_sig:
        return ""
    if thought_sig:
        return f"call_{fc_id}|{thought_sig}"
    return f"call_{fc_id}"


def stream_tool_call_key(tc: dict) -> str:
    """Stable dedupe key for Gemini SSE chunks (backend ids may arrive late)."""
    name = (tc.get("name") or "").strip()
    idx = int(tc.get("_stream_index", 0))
    if name:
        return f"{name}@{idx}"
    tc_id = (tc.get("id") or "").strip()
    if tc_id and not tc_id.startswith("toolu_"):
        raw_fc, _ = decode_tool_id(tc_id)
        if raw_fc:
            return f"fc:{raw_fc}"
        return f"fc:{tc_id}"
    return f"idx:{idx}"


def merge_stream_tool_call(previous: dict, current: dict) -> dict:
    """Keep the richer of two snapshots of the same streamed functionCall."""
    prev_input = previous.get("input") if isinstance(previous.get("input"), dict) else {}
    curr_input = current.get("input") if isinstance(current.get("input"), dict) else {}
    merged = dict(previous)
    merged.update(current)
    if len(json.dumps(curr_input, sort_keys=True)) >= len(json.dumps(prev_input, sort_keys=True)):
        merged["input"] = curr_input
    else:
        merged["input"] = prev_input
    if not merged.get("name") and previous.get("name"):
        merged["name"] = previous["name"]
    if not merged.get("id") and previous.get("id"):
        merged["id"] = previous["id"]
    return merged


def ingest_stream_tool_calls(
    tool_calls: List[dict],
    pending: dict[str, dict],
) -> List[dict]:
    """Merge streamed functionCall snapshots; return new calls ready to emit."""
    new_calls: List[dict] = []
    for tc in tool_calls:
        name = (tc.get("name") or "").strip()
        idx = int(tc.get("_stream_index", 0))

        if not name:
            match_key = None
            for pk, pv in pending.items():
                if pv.get("_stream_index") == idx:
                    match_key = pk
                    break
            if match_key is None:
                match_key = f"partial@{idx}"
            had_name = bool((pending.get(match_key) or {}).get("name"))
            merged = merge_stream_tool_call(pending.get(match_key, {}), tc) if match_key in pending else tc
            pending[match_key] = merged
            if merged.get("name"):
                proper_key = stream_tool_call_key(merged)
                if proper_key != match_key:
                    pending.pop(match_key, None)
                    pending[proper_key] = merged
                if not had_name:
                    new_calls.append({k: v for k, v in merged.items() if not k.startswith("_")})
            continue

        key = stream_tool_call_key(tc)
        previous = pending.get(key)
        if previous is not None:
            had_name = bool(previous.get("name"))
            merged = merge_stream_tool_call(previous, tc)
            pending[key] = merged
            if not had_name and merged.get("name"):
                new_calls.append({k: v for k, v in merged.items() if not k.startswith("_")})
            continue

        pending[key] = tc
        new_calls.append({k: v for k, v in tc.items() if not k.startswith("_")})
    return new_calls


def decode_tool_id(tool_use_id: str) -> Tuple[str, str]:
    if not tool_use_id:
        return "", ""
    if tool_use_id.startswith("call_"):
        raw = tool_use_id[5:]
        if "|" in raw:
            fc_id, sig = raw.split("|", 1)
            return fc_id, sig
        return raw, ""
    return "", ""


def _build_tool_name_map(messages: List[dict]) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        for tc in msg.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            tool_id = tc.get("id", "")
            name = tc.get("name", "")
            if tool_id and name:
                mapping[tool_id] = name
    return mapping


def _tool_result_text_blob(content: Any) -> str:
    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(block.get("text", ""))
        return "\n".join(t for t in texts if t)
    if isinstance(content, dict):
        return json.dumps(content, ensure_ascii=False)
    return str(content) if content is not None else ""


def _tool_result_content_to_response(content: Any, *, max_chars: Optional[int] = None) -> dict:
    """Gemini functionResponse.response must stay simple — wrap MCP payloads as text."""
    text = _tool_result_text_blob(content)
    if not text:
        return {"result": ""}
    limit = max_chars if max_chars is not None else _max_tool_result_chars(is_recent=True)
    if limit is not None and len(text) > limit:
        text = _trim_tool_result_text(text, limit)
    return {"result": text}


def messages_to_gemini_contents(
    messages: List[dict],
    *,
    trim_aggressive: bool = False,
) -> List[dict]:
    name_map = _build_tool_name_map(messages)
    contents: List[dict] = []

    tool_result_indices = [
        idx for idx, msg in enumerate(messages)
        if msg.get("role") == "user" and msg.get("tool_results")
    ]
    last_tool_result_idx = tool_result_indices[-1] if tool_result_indices else -1

    for msg_idx, msg in enumerate(messages):
        role = msg.get("role", "user")
        if role == "system":
            continue

        tool_results = msg.get("tool_results")
        if tool_results and role == "user":
            is_recent = msg_idx == last_tool_result_idx
            max_chars = (
                _max_tool_result_chars(aggressive=trim_aggressive, is_recent=is_recent)
                if tool_result_trim_enabled()
                else None
            )
            response_parts: List[dict] = []
            for tr in tool_results:
                tool_use_id = tr.get("tool_use_id", "")
                fc_id, _ = decode_tool_id(tool_use_id)
                name = tr.get("name") or name_map.get(tool_use_id) or "tool_result"
                func_resp: dict = {
                    "name": name,
                    "response": _tool_result_content_to_response(tr.get("content"), max_chars=max_chars),
                }
                if fc_id:
                    func_resp["id"] = fc_id
                response_parts.append({"functionResponse": func_resp})

            user_parts: List[dict] = list(response_parts)
            text = msg.get("content")
            if text:
                user_parts.append({"text": text})
            if user_parts:
                contents.append({"role": "user", "parts": user_parts})
            continue

        if role == "assistant":
            parts: List[dict] = []
            text = msg.get("content")
            if text:
                parts.append({"text": text})
            for tc in msg.get("tool_calls") or []:
                if not isinstance(tc, dict):
                    continue
                name = tc.get("name", "")
                if not name:
                    continue
                args = tc.get("input", {})
                if not isinstance(args, dict):
                    args = {}
                fc_id, thought_sig = decode_tool_id(tc.get("id", ""))
                fc_part: dict = {"name": name, "args": args}
                if fc_id:
                    fc_part["id"] = fc_id
                part: dict = {"functionCall": fc_part}
                if thought_sig:
                    part["thoughtSignature"] = thought_sig
                parts.append(part)
            if parts:
                contents.append({"role": "model", "parts": parts})
            continue

        api_role = "model" if role == "assistant" else "user"
        text = msg.get("content", "")
        if text:
            contents.append({"role": api_role, "parts": [{"text": text}]})
    return contents


def extract_parts_from_response(
    obj: dict,
    *,
    allow_thought_text: bool = False,
) -> Tuple[str, List[dict], Optional[str]]:
    """Extract visible text and tool_calls from a streamGenerateContent SSE object."""
    response = obj.get("response") or obj
    candidates = response.get("candidates") or []
    if not candidates:
        return "", [], None

    parts = candidates[0].get("content", {}).get("parts") or []
    finish_reason = candidates[0].get("finishReason") or candidates[0].get("finish_reason")
    text_chunks: List[str] = []
    thought_chunks: List[str] = []
    tool_calls: List[dict] = []
    seen_call_keys: set[str] = set()

    for part_idx, part in enumerate(parts):
        if not isinstance(part, dict):
            continue
        is_thought = bool(part.get("thought"))
        if "text" in part and part["text"]:
            if is_thought:
                thought_chunks.append(part["text"])
            else:
                text_chunks.append(part["text"])
        if "functionCall" not in part:
            continue

        fc = part["functionCall"] or {}
        name = (fc.get("name") or "").strip()
        args = fc.get("args", {})
        if not isinstance(args, dict):
            args = {}
        fc_id = fc.get("id", "")
        thought_sig = part.get("thoughtSignature") or part.get("thought_signature") or ""
        if not name and not args and not fc_id:
            continue
        tc = {
            "id": encode_tool_id(fc_id, thought_sig),
            "name": name,
            "input": args,
            "_stream_index": part_idx,
        }
        dedupe_key = fc_id or (f"{name}@{part_idx}" if name else f"partial@{part_idx}")
        if dedupe_key in seen_call_keys:
            continue
        seen_call_keys.add(dedupe_key)
        tool_calls.append(tc)

    if not text_chunks and not tool_calls and thought_chunks and allow_thought_text:
        text_chunks = thought_chunks

    if finish_reason and not text_chunks and not tool_calls:
        logger.warning("[http] empty stream chunk finishReason=%s", finish_reason)

    return "".join(text_chunks), tool_calls, finish_reason