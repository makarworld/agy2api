# Архитектурный аудит и план рефакторинга agy2api

**Дата:** 16.09.2026  
**Проект:** AGY2API (FastAPI шлюз к Google Antigravity / Cloud Code Assist)  
**Анализ выполнен в соответствии со стилем:** ponytail (минимальный достаточный код, YAGNI, высокая надежность)

---

## 1. Резюме (Executive Summary)

Кодовая база (~11 000 строк Python) успешно решает задачу проксирования запросов OpenAI/Anthropic в Google CloudCode API с пулом аккаунтов. Однако проект накопил серьезный технический долг в результате эволюции от локального CLI-враппера к распределенному HTTP-шлюзу с веб-панелью.

### Главные риски:
1. **Split-Brain SQLite (Критический):** `stats_store.py` и `account_store.py` пишут в **две разные базы данных** (`app/data/stats.db` и `data/stats.db`).
2. **Dual Source of Truth для аккаунтов:** Состояние пула одновременно размазано по `manifest.json`, SQLite-таблице `accounts` и in-memory переменным.
3. **Mid-stream retry data corruption:** При обрыве соединения посередине стриминга ротация аккаунта перезапускает генерацию с начала, отдавая клиенту дублированный или поврежденный текст.
4. **God-модули:** `pool_manager.py` (1177 строк) и `oauth_refresh.py` (1026 строк) нарушают SRP и объединяют до 6 не связанных зон ответственности.
5. **Мертвый / чужеродный код:** Подсистемы `warm`/`cli` процессов (`agy_session_pool.py`), заброшенный `cloudcode_lifecycle.py` и 1400 строк встроенной сторонней библиотеки `capcut_tts_api`.

---

## 2. Детальный разбор дефектов и антипаттернов

### 2.1. Критические дефекты (High / Critical Severity)

#### 🔴 Дефект 1: Рассинхронизация баз данных (Split-Brain SQLite)
- **Файлы:** `app/core/stats_store.py:77` и `app/core/account_store.py:10-12`, `app/main.py:64-66`.
- **Проблема:**
  - `stats_store.py` по умолчанию открывает `"app/data/stats.db"` (относительный путь от CWD) и читает переменную `AGY_STATS_DB_PATH`.
  - `account_store.py` открывает `os.path.join(..., "data", "stats.db")` (абсолютный путь) и читает переменную `AGY_DB_PATH`.
  - `key_manager.py` использует `stats_store._conn()`.
- **Последствия:** В системе одновременно создаются и живут две независимые SQLite базы. Статистика запросов и API-ключи пишутся в `app/data/stats.db`, а аккаунты пула — в `data/stats.db`. Бэкапы, миграции и деплой в Docker приводят к потере одной из баз.
- **Решение:** Создать единую точку конфигурации БД (`app/core/db.py`) с одной переменной окружения `AGY_DB_PATH` и общим подключением/пулом.

#### 🔴 Дефект 2: Двойной источник правды пула аккаунтов
- **Файлы:** `app/core/pool_manager.py` и `app/core/account_store.py`.
- **Проблема:**
  - В `pool_manager.py`: `_load_manifest()`, `_save_manifest()`, `_account_model_cooldowns` (in-memory dict), `_session_account_pins` (in-memory dict).
  - В `account_store.py`: методы `select_next_healthy_account()`, `mark_account_rate_limited()`, `mark_account_healthy()`.
  - В `pool_manager.acquire_http_account()` происходит вызов `account_store.select_next_healthy_account()`, но алгоритм выбора в `account_store` не учитывает per-model cooldowns (`_account_model_cooldowns`), живущие в памяти `pool_manager`.
- **Последствия:** Гонки состояний, невозможность масштабирования (несколько воркеров Uvicorn видят разные кулдауны), лишняя синхронизация `sync_all_account_sources()` на старте и при каждом чихе.
- **Решение:** Сделать SQLite единственным источником правды для аккаунтов и их кулдаунов. Убрать дублирующие методы выбора из `account_store`, оставить их в едином менеджере.

#### 🔴 Дефект 3: Повреждение данных при mid-stream ротации
- **Файл:** `app/core/agy_http_client.py:540-572` (генератор `stream_completion`).
- **Проблема:**
  - Если в процессе стриминга после `yield {"delta": delta_text}` возникает `httpx.ReadTimeout` или `RemoteProtocolError`, блок `except` перехватывает ошибку, ротирует аккаунт (`acquire_http_account`) и выполняет `continue`.
  - Цикл начинает генерацию заново (`step=1, request_seq=1`) с нового аккаунта.
- **Последствия:** Клиент (OpenAI SDK, Cursor, Claude Code) уже получил первые N токенов. После `continue` генератор начинает стримить ответ с самого начала, отдавая повтор текста или ломая синтаксис JSON tool calls.
- **Решение:** Вести флаг `yielded_any_chunks: bool`. Если хотя бы один токен был отправлен клиенту — запретить повторный старт стрима; выбрасывать исключение или разрывать соединение для штатного retry на стороне клиента.

---

### 2.2. Архитектурная связанность и God-модули (Medium Severity)

#### 🟠 God Object 1: `app/core/pool_manager.py` (1177 строк)
Модуль перегружен несвязанными задачами:
1. Хранение аккаунтов (манифест + БД).
2. Запуск системных окон терминала (`launch_login_terminal`).
3. Интерактивная OAuth-авторизация (PKCE, генерация URL, вебхук ожидания кода).
4. Запуск CLI подпроцессов (`execute_agy`, `_run_subprocess`).
5. Git-синхронизация пула (`git_pull`, `git_commit_and_push`).
6. Sticky-сессии и хэширование промптов (`compute_prompt_prefix_hash`).

#### 🟠 God Object 2: `app/core/oauth_refresh.py` (1026 строк)
Модуль называется `oauth_refresh`, но внутри него:
1. Запросы квот пользователя в CloudCode (`retrieve_account_quota`, `retrieve_user_quota`).
2. Парсинг моделей квот (`_parse_quota_buckets`).
3. Кэш квот в памяти (`_quota_cache`).
4. Поддержка legacy-форматов файлов учетных записей Gemini CLI.
5. Логика OAuth refresh токенов Google.

#### 🟠 Раздутый роутер: `app/api/routes.py` (898 строк)
В одном роутере смешаны:
- OpenAI `/v1/chat/completions` (стриминг, тулы, маппинг ролей, think-теги).
- OpenAI `/v1/images/generations` (генерация картинок + парсинг соотношений сторон).
- OpenAI `/v1/audio/speech`, `/v1/audio/voices`, `/v1/audio/transcriptions`.
- Системный эндпоинт `/logs/tail`.

---

### 2.3. Мертвый код и лишние абстракции (Low / Cleanup Severity)

1. **`app/core/agy_session_pool.py` (249 строк) + `_stream_cli` / `_stream_warm` в `agy_runner.py`:**
   - Полноценный пул долгоживущих процессов `agy` CLI с таймерами простоя, сборщиком мусора (`_gc_task`) и блокировками.
   - В современной архитектуре шлюз работает по HTTP (`AGY_TRANSPORT=http`), так как только HTTP поддерживает актуальные фичи CloudCode. CLI-пул висит мертвым грузом.
2. **`app/core/cloudcode_lifecycle.py`:**
   - Лежит untracked файлом, реализует эндпоинты `fetchAvailableModels`, `loadCodeAssist`, `retrieveUserQuotaSummary`. При этом `oauth_refresh` реализует свои вызовы, а `model_manager` возвращает пустой список в HTTP-режиме вместо вызова `fetchAvailableModels`.
3. **Вендорный `app/capcut_tts_api/` (1400+ строк):**
   - Полный код библиотеки CapCut TTS вместе с CLI-интерфейсом (`cli.py`), генератором подписей и загрузчиком. Не относится к ядру проекта.

---

### 2.4. Производительность и параллелизм

1. **Избыточный оверхед в `stats_store._conn()`:**
   - На каждый запрос к SQLite выполняется `conn.execute("SELECT 1 FROM pool_account_state LIMIT 1")`.
   - При высокой нагрузке это создает лишние системные вызовы и блокировки диска.
2. **Синхронный `sqlite3` в async-обработчиках FastAPI:**
   - Операции `account_store.get_account_by_id`, `upsert_account`, `key_manager.validate_and_consume_key` вызываются синхронно в event loop без переноса в пул потоков (`run_in_threadpool`).
3. **In-memory state без персистентности:**
   - Кулдауны моделей, лимиты sliding window в `key_manager` сбрасываются при перезапуске сервера.

---

### 2.5. Пробелы в тестировании

- В проекте 13 тест-файлов, но они покрывают исключительно изолированные функции (`test_token_stats`, `test_http_tools_bridge`, `test_auto_classifier`).
- **0 тестов** на эндпоинты `routes.py`, `anthropic_routes.py`, `accounts_routes.py`.
- Логика конвертации SSE в форматы OpenAI/Anthropic, обработка 429 кодов и ротация аккаунтов на уровне API не тестируются.

---

## 3. Практический план рефакторинга (Action Plan)

### Этап 1: Устранение критических дефектов (1-2 дня)
1. **Унификация БД SQLite:**
   - Создать `app/core/db.py`: определить единственный путь к `stats.db` через `os.environ.get("AGY_DB_PATH", "data/stats.db")`.
   - Переключить `stats_store.py`, `account_store.py` и `key_manager.py` на общий `db.py`.
   - Убрать дублирующую проверку `SELECT 1 FROM ...` в `_conn()`.
2. **Защита mid-stream ротации:**
   - В `app/core/agy_http_client.py`: добавить проверку `yielded_any_chunks`. При возникновении сетевой ошибки после начала стриминга — прерывать генератор с явным исключением, не допуская задвоения данных.
3. **Единый источник правды для аккаунтов:**
   - Зафиксировать таблицу `accounts` в SQLite как единственный источник правды.
   - Перенести per-model cooldowns в таблицу SQLite или единый менеджер.

### Этап 2: Декомпозиция и наведение порядка (2-3 дня)
1. **Разгрузка `pool_manager.py`:**
   - Вынести интерактивную авторизацию в `app/core/oauth_flow.py`.
   - Вынести Git автосинхронизацию в `app/core/pool_git_sync.py`.
2. **Разгрузка `oauth_refresh.py`:**
   - Интегрировать `app/core/cloudcode_lifecycle.py` для вызовов квот и моделей.
   - Оставить в `oauth_refresh.py` только логику обновления токенов Google.
3. **Модуляризация роутов:**
   - Создать `app/api/audio_routes.py` (CapCut TTS), `app/api/image_routes.py` (картинки), `app/api/system_routes.py` (логи).
   - В `app/api/routes.py` оставить только Chat Completions и Models.

### Этап 3: Удаление мертвого кода и оптимизация (1 день)
1. Удалить `app/core/agy_session_pool.py` и неиспользуемые ветки `_stream_cli` / `_stream_warm`.
2. Очистить `app/capcut_tts_api/cli.py` и изолировать адаптер TTS.

### Этап 4: Тестирование API (1-2 дня)
1. Написать интеграционные тесты с `TestClient` для:
   - `/v1/chat/completions` (non-stream & stream).
   - `/anthropic/v1/messages` (non-stream & stream).
   - Ротации при 429 и автообновления токена при 401.
