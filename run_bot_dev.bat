@echo off
echo 🔄 Starting Apteka Bot with AUTO-RELOAD...
echo    (Bot will restart automatically when you edit files)
echo.
cd /d %~dp0
set PYTHONPATH=%cd%\src
.venv\Scripts\watchfiles --filter python ".venv\Scripts\python src/bot/telegram_bot.py" src
pause
