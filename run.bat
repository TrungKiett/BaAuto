@echo off
echo Dang khoi dong Web Automator Studio...
cd /d "%~dp0"
start http://localhost:5000
.\.venv\Scripts\python.exe app.py
pause
