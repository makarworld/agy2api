# AGY2API - API Documentation

This project provides an OpenAI-compatible REST API wrapper for the Google Antigravity (AGY) CLI.

Base URL: `http://localhost:8000` (hoặc domain của bạn)

## Authentication
Tất cả các endpoint (ngoại trừ `/health`) đều yêu cầu token Bearer trong header `Authorization`.
- **Header:** `Authorization: Bearer <AGY_API_KEY>`
- **Ví dụ:** `Authorization: Bearer sk-agy-secret-123`
*(Bạn cấu hình key này trong file `.env`)*

---

## 1. List Models
Lấy danh sách các AI model đang được hỗ trợ. Hiện tại mặc định trả về Gemini 3.6 Flash và Gemini 3.1 Pro.

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
    }
  ]
}
```

---

## 2. Chat Completions (Hỗ trợ Đa phương thức - Multimodal)
Gửi yêu cầu chat hoặc yêu cầu phân tích file/hình ảnh đến mô hình. Tương thích chuẩn OpenAI Chat API.

**Endpoint:** `POST /v1/chat/completions`

### Trường hợp 1: Chat Text bình thường
**Request Body:**
```json
{
  "model": "Gemini 3.6 Flash (High)",
  "messages": [
    {
      "role": "user",
      "content": "Viết cho tôi một hàm Python tính Fibonacci"
    }
  ]
}
```

### Trường hợp 2: Gửi File/Hình ảnh (Test đa phương thức)
Để cho model phân tích ảnh hoặc file, bạn có thể truyền nội dung file dưới dạng `Base64 Data URI` trong mảng `content`, tương tự cách OpenAI Vision API hoạt động.

**Request Body:**
```json
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
        "content": "Đây là một bức ảnh về một chú mèo cam đang chơi cuộn len..."
      },
      "finish_reason": "stop"
    }
  ]
}
```

---

## 3. Image Generations
Tạo hình ảnh AI dựa trên prompt văn bản (Text-to-Image). Hệ thống sẽ chạy lệnh gọi tính năng Artist của AGY ở background.

**Endpoint:** `POST /v1/images/generations`

**Request Body Example:**
```json
{
  "prompt": "A cute orange cat playing with a ball of yarn, cartoon style",
  "n": 1,
  "response_format": "url"
}
```
*(Ghi chú: Nếu bạn để `response_format` là `b64_json`, API sẽ trả về dữ liệu hình ảnh dạng Base64 thuần túy. Nếu để `url`, API sẽ tự bọc nó dưới dạng Data URI `data:image/png;base64,...` để tương thích frontend).*

**Response Example:**
```json
{
  "created": 1786102966,
  "data": [
    {
      "url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAA...",
      "b64_json": null
    }
  ]
}
```

---

## 4. Text-to-Speech (Audio Generations)
Tạo tệp âm thanh từ văn bản sử dụng chuẩn OpenAI (hiện tại hỗ trợ qua engine CapCut).

**Endpoint:** `POST /v1/audio/speech`

**Request Body Example:**
```json
{
  "model": "tts-1",
  "input": "Xin chào thế giới!",
  "voice": "alloy",
  "response_format": "mp3",
  "speed": 1.0
}
```

**Response:**
Trả về một luồng (streaming) nội dung âm thanh nhị phân (`audio/mpeg`).

---

## 5. Speech-to-Text (Audio Transcriptions)
Chuyển đổi file âm thanh thành văn bản / phụ đề.

**Endpoint:** `POST /v1/audio/transcriptions` (Sử dụng `multipart/form-data`)

**Request Parameters:**
- `file`: Tệp âm thanh cần upload.
- `model`: (Tuỳ chọn) Ví dụ: `whisper-1`.
- `language`: (Tuỳ chọn) Ví dụ: `en-US`, `zh-CN`.
- `response_format`: Định dạng trả về (`json`, `text`, `srt`, `vtt`).

**Response Example (nếu response_format="json"):**
```json
{
  "text": "Xin chào thế giới!"
}
```

---

## 6. List Voices
Lấy danh sách tất cả các giọng đọc (voices) khả dụng từ CapCut để dùng cho `/v1/audio/speech`.

**Endpoint:** `GET /v1/audio/voices`

**Response Example:**
```json
{
  "voices": [
    {
      "voice_type": "BV074_streaming",
      "display_name": "Tiếng Anh (Mỹ)",
      "resource_id": "...",
      "lang": "en"
    }
  ]
}
```

---

## 7. Get System Logs
Đọc nội dung log mới nhất của hệ thống AGY Wrapper (chỉ khả dụng nếu bạn chạy backend bằng systemd). Rất hữu ích để debug hoặc theo dõi frontend.

**Endpoint:** `GET /v1/logs?lines=100`

**Response Example:**
```json
{
  "logs": "Aug 07 20:45:53 clawbot uvicorn[805378]: INFO: Application startup complete.\n..."
}
```

---

## 5. Health Check
Endpoint dùng để kiểm tra uptime của backend.

**Endpoint:** `GET /health` (Không yêu cầu API Key)

**Response Example:**
```json
{
  "status": "ok",
  "message": "AGY wrapper is running"
}
```

---
*Mẹo: API được xây dựng bằng FastAPI, nên bạn cũng có thể mở trực tiếp **`http://localhost:8000/docs`** trên trình duyệt để xem giao diện Swagger UI tương tác trực tiếp.*
