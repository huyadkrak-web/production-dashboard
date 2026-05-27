@echo off
cd /d "%~dp0backend"
start cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000"
timeout /t 5
start "" "http://localhost:5173"
exit