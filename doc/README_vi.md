<div align="center">

# AGY2API

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](../LICENSE)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/fastapi-0.100%2B-green.svg)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/docker-supported-blue.svg)](https://www.docker.com/)
[![Google Antigravity](https://img.shields.io/badge/Google-Antigravity_CLI-4285F4?logo=google&logoColor=white)](https://antigravity.google/product/antigravity-cli)

**Một dịch vụ API tương thích hoàn toàn với OpenAI, đóng vai trò là Wrapper cho Google Antigravity (AGY) CLI**

[English (Tiếng Anh)](../README.md)

</div>

## ✨ Tính năng Cốt lõi

- 🔄 **Tương thích OpenAI API** - Tích hợp mượt mà với các công cụ như Cursor, Chatbox, Cline, và SillyTavern.
- 🖼️ **Hỗ trợ Đa phương thức (Multimodal)** - Tự động trích xuất file và hình ảnh base64 từ payload của OpenAI, ghi vào thư mục tạm và truyền cho ngữ cảnh của `agy`.
- 🎨 **Tạo Hình ảnh** - Hỗ trợ API tạo ảnh `/v1/images/generations`.
- 🎙️ **Tạo Âm thanh** - Hỗ trợ Text-to-Speech (TTS) thông qua `/v1/audio/speech` (Dựa trên mã nguồn [capcut-tts-api](https://github.com/K07VN/capcut-tts-api)).
- 🛡️ **Thực thi An toàn** - Triển khai hook AGY PreToolUse (`safety_gate.py`) để chặn các lệnh shell nguy hiểm.
- 🚀 **Hỗ trợ Daemon** - Chạy ẩn mượt mà thông qua systemd hoặc Docker.
- 📱 **Giao diện Quản lý (UI)** - Tích hợp Web UI để xem log và quản lý API key.

## 🚀 Hướng dẫn Nhanh

### Yêu cầu
- Python 3.8+ hoặc Docker & Docker Compose
- [Google Antigravity (`agy`) CLI](https://antigravity.google/product/antigravity-cli) đã được cài đặt.

### Cách 1: Triển khai với Docker (Khuyên dùng)

```bash
# Clone dự án
git clone https://github.com/truongqv12/agy2api.git
cd agy2api

# Khởi chạy dịch vụ
docker-compose up -d

# Xem log
docker-compose logs -f
```

### Cách 2: Triển khai Local (Môi trường ảo)

```bash
# Clone dự án
git clone https://github.com/truongqv12/agy2api.git
cd agy2api

# Tạo và kích hoạt môi trường ảo (venv)
python -m venv .venv
source .venv/bin/activate  # Trên Windows dùng `.venv\Scripts\activate`

# Cài đặt thư viện
pip install -r requirements.txt

# Cấu hình API Key
export AGY_API_KEY="your-secret-key"

# Khởi chạy dịch vụ
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Triển khai bằng Systemd
1. Copy file `agy-wrapper.service` vào thư mục `~/.config/systemd/user/`.
2. Chỉnh sửa đường dẫn trong file service cho phù hợp.
3. Chạy lệnh `systemctl --user daemon-reload`
4. Chạy lệnh `systemctl --user enable --now margin`

## 🛡️ Hook An toàn (Safety Hooks)

Để bật chế độ bảo vệ (safety gate) cho môi trường `agy` ở local, bạn hãy link hoặc copy file `hooks.json` vào `~/.gemini/config/hooks.json` hoặc `.agents/hooks.json`.

## 🔌 Các Endpoint Chính
- `GET /health`
- `GET /v1/models`
- `POST /v1/chat/completions`
- `POST /v1/images/generations`
- `POST /v1/audio/speech`
- `GET /v1/audio/voices`
- `GET /api/keys` / `POST /api/keys`
- `GET /api/logs`

Để xem hướng dẫn chi tiết, vui lòng đọc [Tài liệu API](../API_DOCS.md).

## ⚙️ Sử dụng với Cursor

Trong phần **Cursor Settings > Models**:
1. Ghi đè (Override) trường OpenAI API Base URL thành `http://localhost:8000/v1`
2. Nhập `AGY_API_KEY` của bạn.
3. Thêm tên model tuỳ chỉnh (Ví dụ: `Gemini 3.6 Flash (High)`).
