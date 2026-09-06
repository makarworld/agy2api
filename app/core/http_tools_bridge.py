"""Bridge and helpers for Cloud Code Assist HTTP transport tools passthrough."""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any, Optional, Tuple

from src.bot.utils import logger if False else logging.getLogger(__name__)

logger = logging.getLogger(__name__)

_GENERIC_CONTAINER_SCHEMA = {
    "type": "OBJECT",
    "properties": {},
}


def _coerce_items_schema(value: Any) -> Optional[dict]:
    """Gemini Schema.items is a single object, not a JSON Schema tuple list."""
    if isinstance(value, dict):
        return _sanitize_json_schema_for_gemini(value)
    if isinstance(value, list) and value:
        first = value[0]
        if isinstance(first, dict):
            return _sanitize_json_schema_for_gemini(first)
    return None


def _sanitize_json_schema_for_gemini(schema: Any) -> dict:
    if not isinstance(schema, dict):
        return dict(_GENERIC_CONTAINER_SCHEMA)

    out: dict[str, Any] = {}
    raw_type = schema.get("type")
    if isinstance(raw_type, str):
        norm_type = raw_type.upper()
        if norm_type in ("STRING", "INTEGER", "NUMBER", "BOOLEAN", "ARRAY", "OBJECT"):
            out["type"] = norm_type
        elif norm_type == "NULL":
            out["type"] = "STRING"
    elif isinstance(raw_type, list) and raw_type:
        first_scalar = next(
            (
                str(t).upper()
                for t in raw_type
                if str(t).upper() in ("STRING", "INTEGER", "NUMBER", "BOOLEAN", "ARRAY", "OBJECT")
            ),
            None,
        )
        out["type"] = first_scalar or "STRING"

    for key, value in schema.items():
        if key == "properties" and isinstance(value, dict):
            props = {}
            for prop_name, prop_schema in value.items():
                props[prop_name] = _sanitize_json_schema_for_gemini(prop_schema)
            out["properties"] = props
        elif key == "required" and isinstance(value, list):
            out["required"] = [str(item) for item in value if isinstance(item, str)]
        elif key == "items":
            coerced = _coerce_items_schema(value)
            if coerced is not None:
                out[key] = coerced
        elif key in ("description", "enum") and isinstance(value, (str, list)):
            out[key] = value

    if "type" not in out and "properties" in out:
        out["type"] = "OBJECT"
    if out.get("type") == "ARRAY" and "items" not in out:
        out["items"] = {"type": "STRING"}
    if "items" in out and "type" not in out:
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
    return False


def tool_result_trim_enabled() -> bool:
    """When false, functionResponse tool results are sent to Gemini without length limits."""
    env = os.environ.get("AGY_HTTP_TRIM_TOOL_RESULTS")
    if env is None or str(env).strip() == "":
        return True
    return str(env).strip().lower() in ("1", "true", "yes")


def _max_tool_result_chars(
    *, aggressive: bool = False, is_recent: bool = True
) -> Optional[int]:
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
            bits.append(f"text({len(part['text'])})")
        if part.get("functionCall"):
            fc = part["functionCall"]
            bits.append(f"call:{fc.get('name') or 'unnamed'}")
        if bits:
            flags.append("+".join(bits))
    return f"cand0[{','.join(flags)}]" if flags else "cand0[empty]"


def finalize_pending_tool_calls(pending: dict[str, dict]) -> list[dict]:
    """Emit any pending tool calls that accumulated a name during streaming."""
    finalized: list[dict] = []
    for key, tc in list(pending.items()):
        if not tc.get("name"):
            logger.warning("[http] dropping unnamed tool call key=%s", key)
            continue
        finalized.append(tc)
    pending.clear()
    return finalized


def anthropic_tools_to_gemini(tools: Optional[list[dict]]) -> Optional[list[dict]]:
    if not tools:
        return None
    decls: list[dict] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        name = tool.get("name")
        if not name:
            continue
        schema = tool.get("input_schema") or tool.get("parameters") or {}
        decl = {
            "name": str(name),
            "description": str(tool.get("description") or ""),
            "parameters": _sanitize_json_schema_for_gemini(schema),
        }
        decls.append(decl)
    return [{"functionDeclarations": decls}] if decls else None


def tool_choice_to_gemini_mode(tool_choice: Any) -> Optional[dict]:
    if not tool_choice:
        return None
    if isinstance(tool_choice, str):
        choice_type = tool_choice.lower()
        if choice_type in ("auto", "none"):
            return {"mode": choice_type.upper()}
        if choice_type in ("any", "required"):
            return {"mode": "ANY"}
        return None
    if isinstance(tool_choice, dict):
        ctype = str(tool_choice.get("type", "auto")).lower()
        if ctype == "tool":
            name = tool_choice.get("name")
            if name:
                return {
                    "mode": "ANY",
                    "allowedFunctionNames": [str(name)],
                }
            return {"mode": "ANY"}
        if ctype in ("any", "required"):
            return {"mode": "ANY"}
        if ctype == "none":
            return {"mode": "NONE"}
    return None


def encode_tool_id(call_id: str, thought_signature: str = "") -> str:
    """Pack call_id and thoughtSignature into tool_use.id for lossless passthrough."""
    cid = (call_id or "").strip()
    sig = (thought_signature or "").strip()
    if not sig:
        return cid or f"call_{os.urandom(8).hex()}"
    packed = json.dumps({"c": cid, "s": sig}, separators=(",", ":"))
    b64 = base64.urlsafe_b64encode(packed.encode()).decode().rstrip("=")
    return f"ccas_{b64}"


def stream_tool_call_key(tc: dict) -> str:
    """Stable per-call aggregation key across SSE chunks."""
    fc_id, sig = decode_tool_id(tc.get("id", ""))
    if fc_id:
        return f"id:{fc_id}"
    idx = tc.get("_stream_index")
    if idx is not None:
        return f"idx:{idx}"
    name = (tc.get("name") or "").strip()
    if name:
        return f"name:{name}"
    return f"raw:{tc.get('id', '')}"


def merge_stream_tool_call(target: dict, incoming: dict) -> None:
    """Accumulate incoming delta chunks into target tool call object."""
    if incoming.get("name") and not target.get("name"):
        target["name"] = incoming["name"]
    raw_id = incoming.get("id", "")
    fc_id, sig = decode_tool_id(raw_id)
    if fc_id or sig:
        cur_fc_id, cur_sig = decode_tool_id(target.get("id", ""))
        merged_fc_id = fc_id or cur_fc_id
        merged_sig = sig or cur_sig
        target["id"] = encode_tool_id(merged_fc_id, merged_sig)
    elif raw_id and not target.get("id"):
        target["id"] = raw_id

    new_input = incoming.get("input")
    if isinstance(new_input, dict) and new_input:
        cur_input = target.get("input")
        if not isinstance(cur_input, dict):
            target["input"] = {}
        target["input"].update(new_input)


def ingest_stream_tool_calls(
    tool_calls: list[dict],
    pending_tool_calls: dict[str, dict],
) -> list[dict]:
    """Merge newly extracted tool calls into pending accumulator and return completed calls."""
    ready: list[dict] = []
    for tc in tool_calls:
        key = stream_tool_call_key(tc)
        target = pending_tool_calls.get(key)
        if target is None:
            target = {
                "id": tc.get("id", ""),
                "name": tc.get("name", ""),
                "input": tc.get("input", {}) if isinstance(tc.get("input"), dict) else {},
            }
            pending_tool_calls[key] = target
        else:
            merge_stream_tool_call(target, tc)

        # If name is resolved, we consider this tool call formed and can emit it
        if target.get("name") and key in pending_tool_calls:
            ready.append(dict(target))
            del pending_tool_calls[key]

    return ready


def decode_tool_id(packed_id: str) -> Tuple[str, str]:
    """Unpack call_id and thoughtSignature from encoded tool_use.id."""
    if not packed_id or not packed_id.startswith("ccas_"):
        return packed_id or "", ""
    raw = packed_id[len("ccas_") :]
    rem = len(raw) % 4
    if rem:
        raw += "=" * (4 - rem)
    try:
        decoded = base64.urlsafe_b64decode(raw.encode()).decode()
        data = json.loads(decoded)
        return str(data.get("c") or ""), str(data.get("s") or "")
    except Exception:
        return packed_id, ""


def _tool_result_content_to_response(content: Any) -> Any:
    if isinstance(content, str):
        try:
            return json.loads(content)
        except Exception:
            return content
    if isinstance(content, (dict, list)):
        return content
    return str(content)


def messages_to_gemini_contents(
    messages: list[dict],
    *,
    trim_aggressive: bool = False,
) -> list[dict]:
    """Convert OpenAI/Anthropic messages list into Gemini contents structure."""
    contents: list[dict] = []
    total_msgs = len(messages)

    for idx, msg in enumerate(messages):
        role = msg.get("role", "user")
        is_recent = (total_msgs - idx) <= 3
        api_role = "model" if role in ("assistant", "model") else "user"

        parts: list[dict] = []

        # Tool calls from assistant
        tool_calls = msg.get("tool_calls") or []
        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            name = tc.get("name") or (tc.get("function") or {}).get("name")
            args = tc.get("input") or (tc.get("function") or {}).get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            if name:
                fc_part: dict[str, Any] = {
                    "functionCall": {
                        "name": str(name),
                        "args": args if isinstance(args, dict) else {},
                    }
                }
                parts.append(fc_part)

        # Tool result from tool role
        if role == "tool":
            name = msg.get("name", "tool")
            content = msg.get("content", "")
            resp_val = _tool_result_content_to_response(content)
            if isinstance(resp_val, str):
                limit = _max_tool_result_chars(aggressive=trim_aggressive, is_recent=is_recent)
                if limit:
                    resp_val = _trim_tool_result_text(resp_val, limit)
            parts.append(
                {
                    "functionResponse": {
                        "name": str(name),
                        "response": {"result": resp_val},
                    }
                }
            )

        # Multimodal image parts
        images = msg.get("images") or []
        for img in images:
            if isinstance(img, dict) and "data" in img:
                parts.append(
                    {
                        "inlineData": {
                            "mimeType": img.get("mime_type", "image/png"),
                            "data": img["data"],
                        }
                    }
                )

        text = msg.get("content", "")
        if isinstance(text, str) and text:
            parts.append({"text": text})

        if parts:
            contents.append({"role": api_role, "parts": parts})

    return contents


def extract_parts_from_response(
    obj: dict,
    *,
    allow_thought_text: bool = False,
) -> Tuple[str, list[dict], Optional[str]]:
    """Extract visible text and tool_calls from a streamGenerateContent SSE object."""
    response = obj.get("response") or obj
    candidates = response.get("candidates") or []
    if not candidates:
        return "", [], None

    parts = candidates[0].get("content", {}).get("parts") or []
    finish_reason = candidates[0].get("finishReason") or candidates[0].get("finish_reason")
    text_chunks: list[str] = []
    thought_chunks: list[str] = []
    tool_calls: list[dict] = []
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
