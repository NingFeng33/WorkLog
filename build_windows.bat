
@echo off
setlocal
cd /d "%~dp0"

echo ==============================
echo WorkLog Windows Builder
echo ==============================

REM Check Python
where python >nul 2>nul
if errorlevel 1 (
    echo Python is not installed or not in PATH.
    pause
    exit /b 1
)

REM Create virtual environment if missing
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 exit /b 1
)

REM Use project virtual environment
call ".venv\Scripts\activate.bat"

REM Upgrade pip
python -m pip install --upgrade pip

REM Install requirements
if exist "requirements.txt" (
    python -m pip install -r requirements.txt
    if errorlevel 1 exit /b 1
)

REM Install PyInstaller
python -m pip install pyinstaller
if errorlevel 1 exit /b 1

REM Build EXE
python -m PyInstaller --noconfirm --clean --onefile ^
    --name WorkLog ^
    --add-data "static;static" ^
    app.py

if errorlevel 1 (
    echo BUILD FAILED!
    pause
    exit /b 1
)

REM Prepare distribution folders
if not exist "dist\data" mkdir "dist\data"

if exist "data\worklog.sqlite3" (
    if not exist "dist\data\worklog.sqlite3" (
        copy "data\worklog.sqlite3" "dist\data\worklog.sqlite3"
    )
)

if not exist "dist\Year Report" mkdir "dist\Year Report"

echo.
echo ==============================
echo BUILD COMPLETED!
echo ==============================
echo EXE: dist\WorkLog.exe

pause
endlocal
