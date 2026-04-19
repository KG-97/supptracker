@echo off
REM SuppTracker Backend Launcher
REM Starts the FastAPI backend on http://localhost:8000

cd /d %~dp0
echo Starting SuppTracker backend on http://localhost:8000 ...
python -m uvicorn app:app --reload --port 8000
pause
