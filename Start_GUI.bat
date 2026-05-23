@echo off
REM Universal LLM Bridge - Windows Launcher
REM Simply double-click this file to start the GUI

echo ==========================================
echo   Universal LLM Bridge - GUI Launcher
echo ==========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found!
    echo Please install Python 3.10 or higher from:
    echo https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

REM Check if package is installed
python -c "import webui_bridge" >nul 2>&1
if errorlevel 1 (
    echo Installing Universal LLM Bridge...
    pip install -e ".[gui]"
    if errorlevel 1 (
        echo Installation failed!
        pause
        exit /b 1
    )
)

REM Check if Playwright is installed
python -c "from playwright.sync_api import sync_playwright" >nul 2>&1
if errorlevel 1 (
    echo Installing Playwright browsers...
    playwright install chromium
)

echo Starting GUI...
echo.
echo The web browser will open automatically.
echo If it doesn't, navigate to: http://localhost:8501
echo.

python run_gui.py

pause
