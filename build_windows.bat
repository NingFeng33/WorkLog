@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo Python 3 is required. Install it from https://www.python.org/downloads/windows/ and enable the py launcher.
  exit /b 1
)

py -3 -m pip install --upgrade pyinstaller
if errorlevel 1 exit /b 1

py -3 -m PyInstaller --noconfirm --clean --onefile --name WorkLog --add-data "static;static" app.py
if errorlevel 1 exit /b 1

if not exist "dist\data" mkdir "dist\data"
if exist "data\worklog.sqlite3" copy /y "data\worklog.sqlite3" "dist\data\worklog.sqlite3" >nul
if not exist "dist\Year Report" mkdir "dist\Year Report"

echo.
echo Build complete: %CD%\dist\WorkLog.exe
echo Copy the whole dist folder to the Windows computer and double-click WorkLog.exe.
echo Your database will be kept in dist\data\worklog.sqlite3.
endlocal
