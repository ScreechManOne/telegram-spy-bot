@echo off
cd /d "%~dp0.."
echo Запускаем Telegram Spy Bot...
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate
) else if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate
)
python bot.py
pause
