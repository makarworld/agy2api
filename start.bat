@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
call .venv\Scripts\activate.bat
start "" http://127.0.0.1:26767
python scripts\run_server.py
