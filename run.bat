@echo off
echo Stopping old bot processes...
taskkill /IM python.exe /F >nul 2>&1
timeout /t 2 /nobreak >nul
cd /d "%~dp0"
echo Starting bot...
python main.py
pause
