"""Anthropic tools <-> Gemini functionDeclarations conversion for HTTP transport."""
import json
import uuid
from typing import Any, Dict, List, Optional, Tuple

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
    if isinstance(value, str):
        mapped = _TYPE_MAP.get(value.lower())
        return mapped if mapped else value.upper()
    return value


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
            out[key] = _sanitize_json_schema_for_gemini(value)
        elif key == "description" and isinstance(value, str):
            out[key] = value
        elif key == "enum" and isinstance(value, list):
            out[key] = value

    if "type" not in out and "properties" in out:
        out["type"] = "OBJECT"
    elif "type" not in out and "enum" in out:
        out.setdefault("type", "STRING")
    return out


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
        return f"toolu_{uuid.uuid4().hex[:24]}"
    if thought_sig:
        return f"call_{fc_id}|{thought_sig}"
    return f"call_{fc_id}"


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


def _tool_result_content_to_response(content: Any) -> dict:
    """Gemini functionResponse.response must stay simple — wrap MCP payloads as text."""
    text = _tool_result_text_blob(content)
    if not text:
        return {"result": ""}
    if len(text) > 32000:
        text = text[:32000] + "\n...[truncated]"
    return {"result": text}


def messages_to_gemini_contents(messages: List[dict]) -> List[dict]:
    name_map = _build_tool_name_map(messages)
    contents: List[dict] = []
    for msg in messages:
        role = msg.get("role", "user")
        if role == "system":
            continue

        tool_results = msg.get("tool_results")
        if tool_results and role == "user":
            response_parts: List[dict] = []
            for tr in tool_results:
                tool_use_id = tr.get("tool_use_id", "")
                fc_id, _ = decode_tool_id(tool_use_id)
                name = tr.get("name") or name_map.get(tool_use_id) or "tool_result"
                func_resp: dict = {
                    "name": name,
                    "response": _tool_result_content_to_response(tr.get("content")),
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


def extract_parts_from_response(obj: dict) -> Tuple[str, List[dict]]:
    """Extract visible text and tool_calls from a streamGenerateContent SSE object."""
    response = obj.get("response") or obj
    candidates = response.get("candidates") or []
    if not candidates:
        return "", []

    parts = candidates[0].get("content", {}).get("parts") or []
    text_chunks: List[str] = []
    tool_calls: List[dict] = []

    for part in parts:
        if not isinstance(part, dict):
            continue
        if part.get("thought"):
            continue
        if "text" in part and part["text"]:
            text_chunks.append(part["text"])
        if "functionCall" in part:
            fc = part["functionCall"] or {}
            name = fc.get("name", "")
            if not name:
                continue
            args = fc.get("args", {})
            if not isinstance(args, dict):
                args = {}
            fc_id = fc.get("id", "")
            thought_sig = part.get("thoughtSignature") or part.get("thought_signature") or ""
            tool_calls.append({
                "id": encode_tool_id(fc_id, thought_sig),
                "name": name,
                "input": args,
            })

    return "".join(text_chunks), tool_calls
