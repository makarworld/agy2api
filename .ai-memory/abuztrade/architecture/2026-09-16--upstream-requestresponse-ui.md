# Трейсинг и отображение Upstream Request/Response в UI

> **日期**: 2026-09-16  
> **作者**: abuztrade  
> **来源**: cursor:mcp  
> **对话**: MCP remember

---

**上下文**: Пользователь попросил отображать сырой исходящий запрос с компактными промптами (...) и ответ со статусом во вкладке Request рядом с Raw JSON.

**内容**: Добавлен механизм трейсинга исходящих upstream-запросов и ответов (app/core/request_tracer.py). В SQLite-таблицу requests добавлены поля raw_request, raw_response, response_status с автомиграцией в stats_store.py. При ротации аккаунтов в пуле сохраняется последний выполненный запрос и ответ. В UI (requests-page.tsx) добавлена вкладка Request рядом с Raw JSON с интерактивным скрытием промптов (...) и раскрытием по клику, а также блоком Response со статусом ниже.

**理由**: ContextVar позволяет прозрачно пробрасывать тело запроса и ответа через асинхронные генераторы без модификации сигнатур внешних вызовов. Хранение последнего запроса решает задачу отладки при ротации аккаунтов.

**排除方案**: Хранение промежуточных попыток в отдельной таблице; логирование в файл вместо SQLite.

**影响**: app/core/request_tracer.py, app/core/stats_store.py, app/core/agy_http_client.py, app/api/routes.py, app/api/anthropic_routes.py, ui/src/pages/requests-page.tsx, ui/src/hooks/use-requests.ts
