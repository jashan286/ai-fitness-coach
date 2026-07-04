@echo off
title AI Fitness Coach
cd /d "%~dp0"

if not exist venv (
    echo Creating virtual environment for the first time... please wait.
    python -m venv venv
)

call venv\Scripts\activate.bat

echo Checking required packages...
pip install -r requirements.txt --quiet

echo.
echo Starting AI Fitness Coach...
echo Your browser will open automatically once the server is ready.
echo To stop the app, close this window or press Ctrl+C.
echo.

python app.py

pause
