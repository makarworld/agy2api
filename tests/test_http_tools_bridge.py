import json
import unittest

from app.core.http_tools_bridge import (
    anthropic_tools_to_gemini,
    decode_tool_id,
    encode_tool_id,
    extract_parts_from_response,
    messages_to_gemini_contents,
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
        text, tool_calls = extract_parts_from_response(obj)
        self.assertEqual(text, "")
        self.assertEqual(len(tool_calls), 1)
        self.assertEqual(tool_calls[0]["name"], "Bash")
        self.assertEqual(tool_calls[0]["input"]["command"], "pwd")
        self.assertTrue(tool_calls[0]["id"].startswith("call_fc1|"))

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
        text, tool_calls = extract_parts_from_response(obj)
        self.assertEqual(text, "I'll run it")
        self.assertEqual(len(tool_calls), 1)


if __name__ == "__main__":
    unittest.main()
