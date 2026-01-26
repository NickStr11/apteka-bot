@echo off
echo 🤖 Launching Apteka Bot...
set PYTHONPATH=%PYTHONPATH%;%cd%\src
if not exist .venv (
    echo ❌ .venv directory not found. Please create it first.
    pause
    exit /b
)
call .venv\Scripts\activate
python src\bot\telegram_bot.py
pause
