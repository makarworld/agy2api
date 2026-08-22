from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union


class AnthropicMessage(BaseModel):
    role: str
    content: Union[str, List[Dict[str, Any]]]


class AnthropicMessagesRequest(BaseModel):
    model: str
    max_tokens: Optional[int] = 4096
    messages: List[AnthropicMessage]
    system: Optional[Union[str, List[Dict[str, Any]]]] = None
    stream: Optional[bool] = False
    temperature: Optional[float] = None
    stop_sequences: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "model": "claude-sonnet-5",
                    "max_tokens": 1024,
                    "messages": [
                        {"role": "user", "content": "Hello, Claude"}
                    ]
                }
            ]
        }
    }


class AnthropicUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class AnthropicContentBlock(BaseModel):
    type: str = "text"
    text: str


class AnthropicMessageResponse(BaseModel):
    id: str
    type: str = "message"
    role: str = "assistant"
    model: str
    content: List[AnthropicContentBlock]
    stop_reason: Optional[str] = "end_turn"
    stop_sequence: Optional[str] = None
    usage: AnthropicUsage
