import json
import os
import unittest
from unittest import mock

from app.core.http_tools_bridge import (
    anthropic_tools_to_gemini,
    decode_tool_id,
    encode_tool_id,
    extract_parts_from_response,
    finalize_pending_tool_calls,
    ingest_stream_tool_calls,
    merge_stream_tool_call,
    messages_to_gemini_contents,
    stream_tool_call_key,
    tool_choice_to_gemini_mode,
)


class TestHttpToolsBridge(unittest.TestCase):
    def test_anthropic_tools_to_gemini(self):
        tools = [
            {
                "name": "Bash",
                "description": "Run bash",
                "input_schema": {
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                },
            }
        ]
        gemini = anthropic_tools_to_gemini(tools)
        self.assertIsNotNone(gemini)
        decl = gemini[0]["functionDeclarations"][0]
        self.assertEqual(decl["name"], "Bash")
        self.assertEqual(decl["parameters"]["type"], "OBJECT")

    def test_strips_json_schema_meta_fields(self):
        tools = [
            {
                "name": "Bash",
                "description": "Run bash",
                "input_schema": {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "shell command",
                            "default": "ls",
                        },
                        "value": {
                            "type": "number",
                            "exclusiveMinimum": 0,
                            "minimum": 0,
                        },
                    },
                    "required": ["command"],
                },
            }
        ]
        decl = anthropic_tools_to_gemini(tools)[0]["functionDeclarations"][0]
        params = decl["parameters"]
        self.assertNotIn("$schema", params)
        self.assertNotIn("additionalProperties", params)
        self.assertEqual(params["type"], "OBJECT")
        self.assertEqual(params["properties"]["command"]["type"], "STRING")
        self.assertNotIn("default", params["properties"]["command"])
        self.assertNotIn("exclusiveMinimum", params["properties"]["value"])
        self.assertNotIn("minimum", params["properties"]["value"])
        self.assertEqual(params["properties"]["value"]["type"], "NUMBER")
        self.assertEqual(params["required"], ["command"])

    def test_tuple_items_array_collapses_to_single_schema(self):
        tools = [
            {
                "name": "TupleItems",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "a": {"type": "string"},
                        "b": {"type": "integer"},
                        "value": {
                            "type": "array",
                            "items": [{"type": "string"}],
                        },
                    },
                },
            }
        ]
        value = anthropic_tools_to_gemini(tools)[0]["functionDeclarations"][0]["parameters"]["properties"]["value"]
        self.assertEqual(value["type"], "ARRAY")
        self.assertIsInstance(value["items"], dict)
        self.assertEqual(value["items"]["type"], "STRING")
        self.assertNotIsInstance(value["items"], list)

    def test_strips_items_from_non_array_types(self):
        tools = [
            {
                "name": "BadSchema",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "count": {"type": "integer"},
                        "tags": {
                            "type": "string",
                            "items": {"type": "string"},
                        },
                    },
                },
            }
        ]
        params = anthropic_tools_to_gemini(tools)[0]["functionDeclarations"][0]["parameters"]
        tags = params["properties"]["tags"]
        self.assertEqual(tags["type"], "STRING")
        self.assertNotIn("items", tags)

    def test_keeps_items_for_array_types(self):
        tools = [
            {
                "name": "ListTool",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
            }
        ]
        tags = anthropic_tools_to_gemini(tools)[0]["functionDeclarations"][0]["parameters"]["properties"]["tags"]
        self.assertEqual(tags["type"], "ARRAY")
        self.assertEqual(tags["items"]["type"], "STRING")

    def test_array_union_type_keeps_items(self):
        tools = [
            {
                "name": "UnionTool",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "values": {
                            "type": ["array", "null"],
                            "items": {"type": "number"},
                        },
                    },
                },
            }
        ]
        values = anthropic_tools_to_gemini(tools)[0]["functionDeclarations"][0]["parameters"]["properties"]["values"]
        self.assertEqual(values["type"], "ARRAY")
        self.assertEqual(values["items"]["type"], "NUMBER")

    def test_anyof_unions_collapse_to_first_object_branch(self):
        tools = [
            {
                "name": "Tool",
                "input_schema": {
                    "anyOf": [
                        {"type": "null"},
                        {
                            "type": "object",
                            "properties": {"x": {"type": "string"}},
                        },
                    ]
                },
            }
        ]
        params = anthropic_tools_to_gemini(tools)[0]["functionDeclarations"][0]["parameters"]
        self.assertEqual(params["type"], "OBJECT")
        self.assertIn("x", params["properties"])

    def test_tool_choice_modes(self):
        self.assertEqual(tool_choice_to_gemini_mode("auto"), "AUTO")
        self.assertEqual(tool_choice_to_gemini_mode("none"), "NONE")
        self.assertEqual(tool_choice_to_gemini_mode("any"), "ANY")
        self.assertEqual(tool_choice_to_gemini_mode({"type": "tool", "name": "Bash"}), "ANY")

    def test_tool_result_to_function_response(self):
        messages = [
            {
                "role": "user",
                "tool_results": [
                    {
                        "tool_use_id": "call_fc123|sig",
                        "content": '{"stdout": "ok"}',
                        "name": "Bash",
                    }
                ],
                "content": "",
            }
        ]
        contents = messages_to_gemini_contents(messages)
        self.assertEqual(len(contents), 1)
        self.assertEqual(contents[0]["role"], "user")
        part = contents[0]["parts"][0]["functionResponse"]
        self.assertEqual(part["name"], "Bash")
        self.assertEqual(part["id"], "fc123")
        self.assertIn("ok", part["response"]["result"])

    def test_assistant_tool_calls_to_function_call(self):
        messages = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "call_abc|sig", "name": "Bash", "input": {"command": "ls"}},
                ],
            }
        ]
        contents = messages_to_gemini_contents(messages)
        part = contents[0]["parts"][0]
        self.assertEqual(part["functionCall"]["name"], "Bash")
        self.assertEqual(part["functionCall"]["id"], "abc")
        self.assertEqual(part["thoughtSignature"], "sig")

    def test_extract_function_call_from_response(self):
        obj = {
            "response": {
                "candidates": [{
                    "content": {
                        "parts": [{
                            "functionCall": {"name": "Bash", "args": {"command": "pwd"}, "id": "fc1"},
                            "thoughtSignature": "sig",
                        }],
                    },
                }],
            },
        }
        text, tool_calls, _ = extract_parts_from_response(obj)
        self.assertEqual(text, "")
        self.assertEqual(len(tool_calls), 1)
        self.assertEqual(tool_calls[0]["name"], "Bash")
        self.assertEqual(tool_calls[0]["input"]["command"], "pwd")
        self.assertTrue(tool_calls[0]["id"].startswith("call_fc1|"))

    def test_encode_without_backend_id_returns_empty(self):
        self.assertEqual(encode_tool_id(), "")

    def test_stream_tool_call_key_stable_without_backend_id(self):
        tc = {"id": "", "name": "Task", "_stream_index": 0}
        self.assertEqual(stream_tool_call_key(tc), "Task@0")
        self.assertEqual(stream_tool_call_key(tc), stream_tool_call_key(tc))

    def test_stream_tool_call_key_stable_when_id_arrives_later(self):
        early = {"id": "", "name": "Read", "_stream_index": 0}
        late = {"id": "call_call_3506260|sig", "name": "Read", "_stream_index": 0}
        self.assertEqual(stream_tool_call_key(early), stream_tool_call_key(late))

    def test_extract_dedupes_duplicate_function_calls_in_one_chunk(self):
        obj = {
            "response": {
                "candidates": [{
                    "content": {
                        "parts": [
                            {
                                "functionCall": {
                                    "id": "call_1",
                                    "name": "Read",
                                    "args": {"file_path": "/a.py"},
                                },
                            },
                            {
                                "functionCall": {
                                    "id": "call_1",
                                    "name": "Read",
                                    "args": {"file_path": "/a.py"},
                                },
                            },
                        ],
                    },
                }],
            },
        }
        _, tool_calls, _ = extract_parts_from_response(obj)
        self.assertEqual(len(tool_calls), 1)

    def test_merge_stream_tool_call_prefers_richer_args(self):
        prev = {"id": "", "name": "Task", "input": {"description": "Plan"}}
        curr = {"id": "", "name": "Task", "input": {"description": "Plan", "prompt": "full"}}
        merged = merge_stream_tool_call(prev, curr)
        self.assertEqual(merged["input"]["prompt"], "full")

    def test_stream_chunks_same_tool_dedupe_by_key(self):
        chunks = [
            {"response": {"candidates": [{"content": {"parts": [{"functionCall": {"name": "Task", "args": {"description": "Plan"}}}]}}]}},
            {"response": {"candidates": [{"content": {"parts": [{"functionCall": {"name": "Task", "args": {"description": "Plan", "prompt": "x"}}}]}}]}},
        ]
        pending: dict = {}
        emitted = 0
        for obj in chunks:
            _, tool_calls, _ = extract_parts_from_response(obj)
            emitted += len(ingest_stream_tool_calls(tool_calls, pending))
        self.assertEqual(emitted, 1)
        self.assertEqual(pending["Task@0"]["input"]["prompt"], "x")

    def test_stream_partial_args_merge_into_named_call(self):
        chunks = [
            {"response": {"candidates": [{"content": {"parts": [{"functionCall": {"name": "Read", "args": {}}}]}}]}},
            {"response": {"candidates": [{"content": {"parts": [{"functionCall": {"args": {"file_path": "/a.py"}}}]}}]}},
        ]
        pending: dict = {}
        emitted = 0
        for obj in chunks:
            _, tool_calls, _ = extract_parts_from_response(obj)
            emitted += len(ingest_stream_tool_calls(tool_calls, pending))
        self.assertEqual(emitted, 1)
        self.assertEqual(pending["Read@0"]["input"]["file_path"], "/a.py")

    def test_extract_keeps_function_call_inside_thought_part(self):
        obj = {
            "response": {
                "candidates": [{
                    "content": {
                        "parts": [{
                            "thought": True,
                            "functionCall": {"name": "Bash", "args": {"command": "ls"}},
                        }],
                    },
                }],
            },
        }
        text, tool_calls, _ = extract_parts_from_response(obj)
        self.assertEqual(text, "")
        self.assertEqual(len(tool_calls), 1)
        self.assertEqual(tool_calls[0]["name"], "Bash")

    def test_encode_decode_gemini_prefixed_id(self):
        encoded = encode_tool_id("call_2235145", "sig")
        self.assertEqual(encoded, "call_call_2235145|sig")
        fc_id, sig = decode_tool_id(encoded)
        self.assertEqual(fc_id, "call_2235145")
        self.assertEqual(sig, "sig")

    def test_tool_result_resolves_name_from_assistant_history(self):
        messages = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_call_2235145|sig",
                        "name": "ListMcpResourcesTool",
                        "input": {},
                    }
                ],
            },
            {
                "role": "user",
                "tool_results": [
                    {
                        "tool_use_id": "call_call_2235145|sig",
                        "content": [{"type": "text", "text": "[mcp] cursor-ide-browser"}],
                    }
                ],
                "content": "",
            },
        ]
        contents = messages_to_gemini_contents(messages)
        self.assertEqual(contents[0]["role"], "model")
        self.assertEqual(contents[1]["role"], "user")
        func_resp = contents[1]["parts"][0]["functionResponse"]
        self.assertEqual(func_resp["name"], "ListMcpResourcesTool")
        self.assertEqual(func_resp["id"], "call_2235145")
        self.assertIn("cursor-ide-browser", func_resp["response"]["result"])

    def test_extract_text_and_tool_calls(self):
        obj = {
            "response": {
                "candidates": [{
                    "content": {
                        "parts": [
                            {"text": "I'll run it"},
                            {"functionCall": {"name": "Bash", "args": {"command": "ls"}}},
                        ],
                    },
                }],
            },
        }
        text, tool_calls, _ = extract_parts_from_response(obj)
        self.assertEqual(text, "I'll run it")
        self.assertEqual(len(tool_calls), 1)

    def test_thought_text_fallback_when_no_visible_output(self):
        obj = {
            "response": {
                "candidates": [{
                    "content": {
                        "parts": [{"thought": True, "text": "internal reasoning"}],
                    },
                }],
            },
        }
        text, tool_calls, _ = extract_parts_from_response(obj, allow_thought_text=True)
        self.assertEqual(text, "internal reasoning")
        self.assertEqual(tool_calls, [])

    def test_thought_text_not_used_without_flag(self):
        obj = {
            "response": {
                "candidates": [{
                    "content": {
                        "parts": [{"thought": True, "text": "hidden"}],
                    },
                }],
            },
        }
        text, tool_calls, _ = extract_parts_from_response(obj, allow_thought_text=False)
        self.assertEqual(text, "")
        self.assertEqual(tool_calls, [])

    def test_finalize_emits_pending_named_tool_call(self):
        pending = {
            "Bash@0": {
                "id": "call_fc1|",
                "name": "Bash",
                "input": {"command": "ls"},
                "_stream_index": 0,
            }
        }
        out = finalize_pending_tool_calls(pending)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["name"], "Bash")
        self.assertNotIn("_stream_index", out[0])

    def test_finalize_after_partial_stream_merge(self):
        chunks = [
            {"response": {"candidates": [{"content": {"parts": [{"functionCall": {"name": "Read", "args": {}}}]}}]}},
            {"response": {"candidates": [{"content": {"parts": [{"functionCall": {"args": {"file_path": "/a.py"}}}]}}]}},
        ]
        pending: dict = {}
        for obj in chunks:
            _, tool_calls, _ = extract_parts_from_response(obj)
            ingest_stream_tool_calls(tool_calls, pending)
        out = finalize_pending_tool_calls(pending)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["name"], "Read")
        self.assertEqual(out[0]["input"]["file_path"], "/a.py")

    def test_trim_tool_result_exceeds_limit(self):
        with mock.patch.dict(os.environ, {"AGY_HTTP_MAX_TOOL_RESULT_CHARS": "100"}):
            long_content = "x" * 200
            messages = [
                {
                    "role": "user",
                    "tool_results": [
                        {
                            "tool_use_id": "call_fc1|sig",
                            "content": long_content,
                            "name": "Read",
                        }
                    ],
                    "content": "",
                }
            ]
            contents = messages_to_gemini_contents(messages)
            result = contents[0]["parts"][0]["functionResponse"]["response"]["result"]
            self.assertIn("truncated", result)
            self.assertLess(len(result), 200)

    def test_trim_disabled_sends_full_tool_result(self):
        with mock.patch.dict(
            os.environ,
            {"AGY_HTTP_TRIM_TOOL_RESULTS": "false", "AGY_HTTP_MAX_TOOL_RESULT_CHARS": "100"},
        ):
            long_content = "z" * 500
            messages = [
                {
                    "role": "user",
                    "tool_results": [
                        {
                            "tool_use_id": "call_fc1|sig",
                            "content": long_content,
                            "name": "Read",
                        }
                    ],
                    "content": "",
                }
            ]
            contents = messages_to_gemini_contents(messages)
            result = contents[0]["parts"][0]["functionResponse"]["response"]["result"]
            self.assertEqual(result, long_content)
            self.assertNotIn("truncated", result)

    def test_old_tool_results_trimmed_more_aggressively(self):
        with mock.patch.dict(
            os.environ,
            {"AGY_HTTP_MAX_TOOL_RESULT_CHARS": "12000", "AGY_HTTP_OLD_TOOL_RESULT_CHARS": "50"},
        ):
            long_content = "y" * 200
            messages = [
                {
                    "role": "user",
                    "tool_results": [{"tool_use_id": "call_a|", "content": long_content, "name": "Read"}],
                    "content": "",
                },
                {"role": "assistant", "content": "ok"},
                {
                    "role": "user",
                    "tool_results": [{"tool_use_id": "call_b|", "content": "short", "name": "Read"}],
                    "content": "",
                },
            ]
            contents = messages_to_gemini_contents(messages)
            old_result = contents[0]["parts"][0]["functionResponse"]["response"]["result"]
            recent_result = contents[2]["parts"][0]["functionResponse"]["response"]["result"]
            self.assertIn("truncated", old_result)
            self.assertEqual(recent_result, "short")


if __name__ == "__main__":
    unittest.main()
