@echo off
chcp 65001 > nul

echo Checking Python installation...
python --version
if errorlevel 1 (
    echo.
    echo ERROR: Python not found!
    echo Please install Python from python.org
    pause
    exit /b 1
)

echo.
echo Installing dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERROR: Failed to install dependencies!
    pause
    exit /b 1
)

echo.
echo ========================================
echo Starting bot...
echo Press Ctrl+C to stop
echo ========================================
echo.
python bot.py
pause
