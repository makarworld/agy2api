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

class SpeechRequest(BaseModel):
    model: str = Field(..., description="ID của model (vd: 'tts-1', 'tts-1-hd')")
    input: str = Field(..., description="Đoạn văn bản cần chuyển thành giọng nói.")
    voice: str = Field("alloy", description="Giọng đọc cần sử dụng. (vd: 'alloy', 'BV074_streaming')")
    response_format: Optional[str] = Field("mp3", description="Định dạng trả về. Mặc định là mp3.")
    speed: Optional[float] = Field(1.0, description="Tốc độ đọc (0.25 đến 4.0). Mặc định là 1.0.")

    model_config = {
        "json_schema_extra": {
            "example": {
                "model": "tts-1",
                "input": "Xin chào thế giới!",
                "voice": "alloy",
                "response_format": "mp3",
                "speed": 1.0
            }
        }
    }
