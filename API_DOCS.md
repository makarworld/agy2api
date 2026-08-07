# API Documentation

This project provides an OpenAI-compatible REST API wrapper for the Google Antigravity (AGY) CLI.

Base URL: `http://localhost:8000`

## Authentication
All endpoints require a Bearer token in the `Authorization` header.
- **Header:** `Authorization: Bearer <AGY_API_KEY>`
- **Example:** `Authorization: Bearer sk-dummy`

---

## 1. List Models
Returns a list of available models. Currently returns hardcoded Gemini models.

**Endpoint:** `GET /v1/models`

**Response Example:**
```json
{
  "object": "list",
  "data": [
    {
      "id": "Gemini 3.6 Flash (High)",
      "object": "model",
      "created": 1786102824,
      "owned_by": "google"
    },
    {
      "id": "Gemini 3.1 Pro (High)",
      "object": "model",
      "created": 1786102824,
      "owned_by": "google"
    }
  ]
}
```

---

## 2. Chat Completions
Creates a model response for the given chat conversation. Supports text and images (via base64 data URIs).

**Endpoint:** `POST /v1/chat/completions`

**Request Body Example:**
```json
{
  "model": "Gemini 3.6 Flash (High)",
  "messages": [
    {
      "role": "user",
      "content": "Hello! What is your name?"
    }
  ],
  "temperature": 1.0,
  "stream": false
}
```

**Response Example:**
```json
{
  "id": "chatcmpl-0d1ea4851363",
  "object": "chat.completion",
  "created": 1786102866,
  "model": "Gemini 3.6 Flash (High)",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello! How can I help you with your coding or project today?"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0
  }
}
```

---

## 3. Image Generations
Creates an image given a prompt. It runs the AGY artist skills in the background.

**Endpoint:** `POST /v1/images/generations`

**Request Body Example:**
```json
{
  "prompt": "A cute orange cat playing with a ball of yarn",
  "n": 1,
  "size": "1024x1024",
  "response_format": "url"
}
```

**Response Example:**
```json
{
  "created": 1786102966,
  "data": [
    {
      "url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
      "b64_json": null
    }
  ]
}
```

---

## 4. Health Check
Endpoint to check if the server is running.

**Endpoint:** `GET /health`

**Response Example:**
```json
{
  "status": "ok",
  "message": "AGY wrapper is running"
}
```

---
*Note: Because this API is built using FastAPI, interactive Swagger UI documentation is automatically generated and accessible at `http://localhost:8000/docs`.*
