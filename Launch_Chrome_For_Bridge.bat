@echo off
REM Find and launch Chrome with remote debugging for Universal LLM Bridge

echo ==========================================
echo   Chrome Launcher for LLM Bridge
echo ==========================================
echo.

REM Check common Chrome locations
set CHROME_PATH=""

if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
    set CHROME_PATH="C:\Program Files\Google\Chrome\Application\chrome.exe"
    echo Found Chrome at: C:\Program Files\Google\Chrome\Application\
)

if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" (
    set CHROME_PATH="C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    echo Found Chrome at: C:\Program Files (x86)\Google\Chrome\Application\
)

if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" (
    set CHROME_PATH="%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
    echo Found Chrome at: %LOCALAPPDATA%\Google\Chrome\Application\
)

if %CHROME_PATH%=="" (
    echo ERROR: Could not find Chrome!
    echo.
    echo Please manually locate chrome.exe and update this script.
    echo Common locations:
    echo   - C:\Program Files\Google\Chrome\Application\chrome.exe
    echo   - C:\Program Files (x86)\Google\Chrome\Application\chrome.exe
    echo.
    pause
    exit /b 1
)

echo.
echo Starting Chrome with remote debugging enabled...
echo Port: 9222
echo.
echo Once Chrome opens:
echo   1. Log into your LLM (Grok, ChatGPT, Claude, etc.)
echo   2. In the Universal LLM Bridge GUI, check "Use Existing Chrome"
echo   3. Click Connect
echo.
echo Press any key to launch Chrome...
pause > nul

%CHROME_PATH% --remote-debugging-port=9222

echo.
echo Chrome closed. Press any key to exit...
pause
