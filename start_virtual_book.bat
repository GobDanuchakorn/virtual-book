@echo off
cd /d "%~dp0"
start "Virtual Book Server" /min python.exe app.py
timeout /t 3 >nul
start "" "http://127.0.0.1:5055"
