from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union

class Message(BaseModel):
    role: str = Field(..., description="The role of the messages author, e.g. user, assistant, or system")
    content: Union[str, List[Dict[str, Any]]] = Field(..., description="The contents of the message. Can be a string or an array of content parts (for multimodal inputs like images).")

class ChatCompletionRequest(BaseModel):
    model: str = Field(..., description="ID of the model to use, e.g. 'Gemini 3.6 Flash (High)'")
    messages: List[Message]
    temperature: Optional[float] = Field(1.0, description="Sampling temperature")
    stream: Optional[bool] = Field(False, description="Whether to stream back partial progress")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "model": "Gemini 3.6 Flash (High)",
                    "messages": [
                        {
                            "role": "user",
                            "content": "Viết cho tôi một hàm Python tính Fibonacci"
                        }
                    ]
                },
                {
                    "model": "Gemini 3.6 Flash (High)",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Trong bức ảnh này có những gì?"
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD..."
                                    }
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    }

class ChoiceMessage(BaseModel):
    role: str = "assistant"
    content: str

class Choice(BaseModel):
    index: int = 0
    message: ChoiceMessage
    finish_reason: str = "stop"

class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Choice]
    usage: Usage

class Model(BaseModel):
    id: str
    object: str = "model"
    created: int
    owned_by: str = "google"

class ModelList(BaseModel):
    object: str = "list"
    data: List[Model]
