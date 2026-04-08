@echo off
REM Quick start script for CloudCostGuardEnv (Windows)

echo CloudCostGuardEnv - Quick Start
echo ================================
echo.

REM Check if venv exists
if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
)

REM Activate venv
call .venv\Scripts\activate.bat

REM Install dependencies if needed
echo Installing dependencies...
uv pip install -r server/requirements.txt -q

REM Start the server
echo.
echo Starting server on http://localhost:8000
echo ================================
echo.
python -m uvicorn server.app:app --host 0.0.0.0 --port 8000 --reload

pause
