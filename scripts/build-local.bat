@echo off
REM Local build and test script for repr CLI (Windows)

echo ========================================
echo Repr CLI - Local Build ^& Test Script
echo ========================================
echo.

REM Check Python version
echo Checking Python version...
python --version
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Python not found
    exit /b 1
)
echo.

REM Install dependencies
echo Installing dependencies...
python -m pip install --upgrade pip >nul 2>&1
pip install pyinstaller >nul 2>&1
pip install -e . >nul 2>&1
echo Dependencies installed
echo.

REM Build binary
echo Building binary with PyInstaller...
if exist repr.spec (
    pyinstaller repr.spec --clean
) else (
    echo repr.spec not found, using inline build
    pyinstaller --onefile ^
        --name repr ^
        --console ^
        --hidden-import=repr ^
        --collect-all=typer ^
        --collect-all=rich ^
        --collect-all=pygments ^
        repr/cli.py
)
echo Binary built
echo.

REM Test binary
echo Testing binary...
if not exist dist\repr.exe (
    echo ERROR: Binary not found in dist\repr.exe
    exit /b 1
)

echo Running: dist\repr.exe --help
dist\repr.exe --help >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Binary failed
    exit /b 1
)
echo Binary works!
echo.

REM Show binary info
echo Binary Information:
echo   Location: %CD%\dist\repr.exe
for %%I in (dist\repr.exe) do echo   Size: %%~zI bytes
echo.

REM Final instructions
echo Build complete!
echo.
echo To test the binary:
echo   dist\repr.exe --help
echo   dist\repr.exe config --json
echo.
echo To install, add to PATH or copy to:
echo   C:\Windows\System32\repr.exe
echo   or
echo   C:\Program Files\repr\repr.exe
echo.








































