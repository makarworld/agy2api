# Сравнение запросов AGY и agy2api

Источник HAR: `C:\Users\User\Downloads\HTTPToolkit_2026-09-16_16-23_agy_snap.har`.

## Исправленные расхождения

- User-Agent обновлён с `antigravity/cli/1.1.18` до HAR-версии `1.2.4`.
- `loadCodeAssist` теперь получает `{"metadata":{"ideType":"ANTIGRAVITY"}}`.
- Для `systemInstruction` добавлен `role: user`.
- Убран не наблюдавшийся в HAR `safetySettings`.
- Лимит вывода по умолчанию изменён с `8192` на `65536`.
- Thinking больше не отключается при наличии tools.
- Добавлены trajectory UUID, step index и HAR-подобные labels.
- `Accept: text/event-stream` убран: в HAR заголовок отсутствует.

## Оставшееся отличие

Image-запрос уже совпадал с HAR.

HAR использует дополнительные служебные запросы `fetchAdminControls`,
`fetchAvailableModels`, `fetchUserInfo`, `listExperiments`,
`recordTrajectoryAnalytics`, `writeTrajectoryAcls`. Они не являются частью
основного generate/stream контракта и в текущем патче не добавлялись.

SSE parsing совместим с наблюдаемым `data: {"response": ...}`.
