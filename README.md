<div align="center">

# AGY2API

**Универсальный шлюз (Gateway) для работы с Google Antigravity & Cloud Code Assist (Gemini 3.7 / Flash Thinking) через форматы OpenAI и Anthropic API.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-Supported-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

</div>

> [!TIP]
> **AGY2API** позволяет подключить **Claude Code**, **Cursor**, **Cline**, **Chatbox**, **SillyTavern** и любые другие клиенты к безлимитному пулу Google-аккаунтов с автоматической ротацией при превышении квот (Rate Limit 429), поддержкой прокси для каждого аккаунта и встроенным веб-дашбордом.

---

## 🚀 Пошаговая инструкция по установке (с нуля)

### Вариант 1: Запуск на Windows (самый простой)

#### Шаг 1. Установите программы (если еще не стоят)
1. **Python 3.10+**: [Скачать с python.org](https://www.python.org/downloads/) *(Обязательно поставьте галочку "Add Python to PATH" при установке!)*
2. **Node.js 18+**: [Скачать с nodejs.org](https://nodejs.org/) *(LTS версия)*
3. **Git**: [Скачать с git-scm.com](https://git-scm.com/)

#### Шаг 2. Скачайте проект и откройте консоль
Откройте терминал (Command Prompt / PowerShell / Git Bash) и выполните:
```bash
git clone https://github.com/makarworld/agy2api.git
cd agy2api
```

#### Шаг 3. Установите зависимости и соберите веб-панель
```bash
# 1. Создание виртуального окружения Python
python -m venv .venv

# 2. Активация окружения (для Windows cmd/bash):
call .venv\Scripts\activate
# (если используете PowerShell: .venv\Scripts\Activate.ps1)

# 3. Установка Python библиотек
pip install -r requirements.txt

# 4. Сборка веб-интерфейса (UI)
cd ui
npm install
npm run build
cd ..
```

#### Шаг 4. Настройка файла `.env`
Скопируйте файл примера настроек:
```bash
copy .env.example .env
```
Откройте файл `.env` в блокноте и проверьте основные параметры (можно оставить как есть):
```ini
AGY_API_KEY=sk-my-super-secret-key-123
ANTHROPIC_COMPAT_API_KEY=sk-my-super-secret-key-123
ADMIN_PASSWORD=my-admin-password
AGY_POOL_ENABLED=true
AGY_TRANSPORT=http
ANTIGRAVITY_CLIENT_ID=your-google-client-id-here.apps.googleusercontent.com
ANTIGRAVITY_CLIENT_SECRET=your-google-client-secret-here
AGY_FORCE_MODEL=max-gem
```

#### Шаг 5. Запуск сервера
Дважды кликните по файлу **`start.bat`** или выполните в консоли:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
После запуска откройте браузер: **http://localhost:8000** (Пароль для входа: значение `ADMIN_PASSWORD` из `.env`).

---

### Вариант 2: Запуск на Linux / macOS

```bash
# 1. Клонирование
git clone https://github.com/makarworld/agy2api.git
cd agy2api

# 2. Python venv & pip
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Сборка UI
cd ui && npm install && npm run build && cd ..

# 4. Конфиг
cp .env.example .env

# 5. Запуск
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

### Вариант 3: Запуск через Docker

```bash
git clone https://github.com/makarworld/agy2api.git
cd agy2api
cp .env.example .env
docker compose up -d --build
```

---

## 🔑 Как добавить Google аккаунты в пул (в 1 клик)

Для работы **НЕ требуется** локальный `agy CLI` или терминалы авторизации.

1. Откройте в браузере веб-интерфейс: **`http://localhost:8000/`**
2. В боковом меню перейдите в раздел **`Account Pool`**.
3. В блоке **"Add Account via Google OAuth"**:
   - (Опционально) Укажите имя аккаунта (например `main`, `work`, `acc2`).
   - (Опционально) Укажите прокси для этого аккаунта (например `http://user:pass@ip:port` или `socks5://ip:port`).
   - Нажмите кнопку **`Generate Login Link`**.
4. Нажмите синюю кнопку **`Open Google Sign-In`** (или скопируйте ссылку и откройте в браузере, где выполнен вход в нужный Google-аккаунт).
5. Войдите в Google аккаунт и разрешите доступ. В конце страница выдаст код (или покажет адрес вида `https://antigravity.google/oauth-callback?code=4/0ATsMZq...`).
6. Скопируйте этот код (или всю строку URL) и вставьте в поле **`Paste Authorization Code or Redirect URL`**.
7. Нажмите кнопку **`Connect Account`**.
8. **Готово!** Аккаунт мгновенно добавлен в пул, проверен и готов к обработке запросов. Вы можете повторить это для 5, 10 или 20 аккаунтов.

---

## 🔌 Подключение к AI клиентам

### 1. Claude Code
Задайте переменные окружения и запустите `claude`:

**В Linux / macOS / Git Bash:**
```bash
export ANTHROPIC_BASE_URL="http://localhost:8000/anthropic/v1"
export ANTHROPIC_API_KEY="sk-my-super-secret-key-123"
claude
```

**В Windows CMD:**
```cmd
set ANTHROPIC_BASE_URL=http://localhost:8000/anthropic/v1
set ANTHROPIC_API_KEY=sk-my-super-secret-key-123
claude
```

**В Windows PowerShell:**
```powershell
$env:ANTHROPIC_BASE_URL="http://localhost:8000/anthropic/v1"
$env:ANTHROPIC_API_KEY="sk-my-super-secret-key-123"
claude
```

---

### 2. Cursor IDE
1. Откройте **Settings** → **Cursor Settings** → вкладка **Models**.
2. Включите переключатель **OpenAI API Key** и укажите ключ: `sk-my-super-secret-key-123`.
3. Нажмите **Override OpenAI Base URL** и введите:
   ```
   http://localhost:8000/v1
   ```
4. В списке моделей добавьте кастомную модель: `max-gem` (или `gemini-3.7-flash-high`).
5. Отключите другие модели и выберите `max-gem` в чате / автокомплите.

---

### 3. Cline (расширение для VS Code)
1. Откройте настройки Cline (шестерёнка в панели расширения).
2. **API Provider**: выберите `OpenAI Compatible` (или `Anthropic`).
3. **Base URL**: `http://localhost:8000/v1` (для OpenAI) или `http://localhost:8000/anthropic/v1` (для Anthropic).
4. **API Key**: `sk-my-super-secret-key-123`.
5. **Model ID**: `max-gem`.

---

## ⚙️ Настройки `.env` (Справочник)

| Параметр | По умолчанию | Описание |
| :--- | :--- | :--- |
| `AGY_API_KEY` | `sk-...` | Секретный ключ для доступа к вашему OpenAI эндпоинту |
| `ANTHROPIC_COMPAT_API_KEY` | `sk-...` | Секретный ключ для Anthropic эндпоинта (`/anthropic/v1`) |
| `ADMIN_PASSWORD` | `...` | Пароль для входа в веб-панель `http://localhost:8000` |
| `AGY_TRANSPORT` | `http` | Режим работы: `http` (прямой Cloud Code Assist), `warm` (фоновые сессии), `cli` (вызов процесса) |
| `AGY_POOL_ENABLED` | `true` | Включение автоматической ротации пула аккаунтов |
| `AGY_FORCE_MODEL` | `max-gem` | Принудительно направлять все запросы в Gemini 3.7 Flash Thinking |
| `AGY_GOOGLE_PROXY` | ` ` | Глобальный прокси для запросов к Google (если страна под санкциями) |

---

## ❓ Частые вопросы и ошибки (Troubleshooting)

**В: Ошибка `Rate Limit / Quota Exceeded (429)` в клиенте?**
> О: Если в пуле добавлено несколько аккаунтов (`AGY_POOL_ENABLED=true`), сервер сам переключится на следующий свободный аккаунт. Добавьте больше аккаунтов через вкладку `Account Pool`.

**В: Запросы к Google блокируются по региону (Location not supported)?**
> О: Укажите прокси в `.env` (`AGY_GOOGLE_PROXY=http://user:pass@ip:port`) либо задайте индивидуальный прокси при добавлении аккаунта в веб-панели.

**В: Как обновить веб-панель после правок кода?**
> О: Перейдите в папку `ui` и выполните `npm run build`.

---

## 📄 Лицензия

MIT License — свободное использование и модификация.
