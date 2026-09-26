# Account avatars isolation & Stream error aborts

> **日期**: 2026-09-26  
> **作者**: abuztrade  
> **来源**: cursor:mcp  
> **对话**: MCP remember

---

**上下文**: Исправление бага с дублированием аватарок последнего аккаунта и устранение ложных успешных ответов с текстом Error: вместо обрыва стрима

**内容**: 1. Аватарки и имена аккаунтов:
- В SQLite таблицу accounts добавлены колонки name и picture с авто-миграцией в init_accounts_table().
- В pool_manager.sync_back_credentials добавлена строгая проверка: синхронизировать ~/.gemini в папку аккаунта разрешено ТОЛЬКО если get_active_account_id() == account_id. Ранее он вызывался при фоновых операциях и затирал папки чужих аккаунтов кредами последнего активного.
- В pool_manager._extract_account_jwt убран фоллбэк на ~/.gemini для не-активных аккаунтов при AGY_POOL_ENABLED=false.
- В complete_oauth_flow и refresh сохраняются name и picture в БД и манифест.

2. Обрыв соединений при ошибках стриминга вместо генерации текста 'Error:':
- В app/api/routes.py (OpenAI стриминг) убран блок yield chunk с Error: и finish_reason='stop'. Теперь при любом исключении или piece.get('error') делается raise, вызывая обрыв HTTP стрима.
- В app/api/anthropic_routes.py в стриминге убран yield content_block_delta с текстом ошибки и фиктивный message_stop/end_turn. При любой ошибке выбрасывается raise.
- В non-streaming эндпоинте Anthropic убран возврат HTTP 200 с текстом Error: - теперь возвращается HTTPException(502/503).
