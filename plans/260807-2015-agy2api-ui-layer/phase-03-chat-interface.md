---
title: "Phase 3: Chat Interface"
status: todo
---

# Phase 3: Chat Interface

## Overview

Implement the main Chat UI for testing, styled like goclaw's chat window. It will support text messages, file/image uploads (converted to base64 data URIs), and communicate via `agy2api`'s `POST /v1/chat/completions` REST API instead of WebSocket.

## Requirements

- [x] Build `ChatPage`, `ChatThread`, and `ChatSidebar` components.
- [x] Implement an input area supporting drag-and-drop or file selection.
- [x] Convert selected images to Base64 data URIs locally.
- [x] Fetch streaming responses from `POST /v1/chat/completions` (using `stream: true` and Server-Sent Events).
- [x] Attach the API key from LocalStorage to the `Authorization` header.

## Implementation Steps

1. Create chat UI components inspired by `goclaw/ui/web/src/pages/chat`.
2. Implement file handling utility (`readAsDataURL`) for images.
3. Create a chat service that performs a `fetch` request to `/v1/chat/completions`.
4. Parse the SSE stream to display the model's response incrementally.
5. Store chat history locally or in state for the session.

## Todo

- [x] Chat layout and components.
- [x] Image to Base64 utility.
- [x] REST client for streaming chat completions.
- [x] End-to-end testing with a real model.

## Success Criteria

- User can type messages and attach images.
- System correctly streams the model's response.
- UI handles errors and loading states gracefully.
