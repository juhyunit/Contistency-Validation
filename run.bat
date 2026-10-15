@echo off
setlocal
title Recon - financial data validation
rem One-click launcher for Windows. ASCII only on purpose: cmd.exe misreads UTF-8 text
rem in batch files on some systems, which can make the window close without a message.
cd /d "%~dp0"

echo ============================================================
echo   Recon - financial data validation and reconciliation
echo ============================================================
echo.

rem 1) This file only works inside the extracted project folder.
if not exist "pyproject.toml" goto not_extracted
if not exist "app\streamlit_app.py" goto not_extracted

rem 2) Find uv. A fresh install may not be on PATH until you sign out, so check the default folder too.
set "UV="
where uv >nul 2>nul && set "UV=uv"
if not defined UV if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV=%USERPROFILE%\.local\bin\uv.exe"
if not defined UV goto no_uv

echo [1/2] Preparing Python and packages...
echo       The first run downloads about 150 MB and can take 1-3 minutes.
"%UV%" sync --no-dev
if errorlevel 1 goto failed

echo.
echo [2/2] Starting the app. Your browser opens at http://localhost:8501
echo       Keep this window open while you use the app. Close it to stop.
echo.
"%UV%" run --no-dev streamlit run app/streamlit_app.py
if errorlevel 1 goto failed
goto end

:not_extracted
echo [!] run.bat must be started from inside the extracted project folder.
echo     It looks like it was opened on its own or from inside a ZIP file.
echo.
echo     1. On GitHub, click "Code" and then "Download ZIP".
echo     2. Right-click the ZIP file and choose "Extract All".
echo     3. Open the extracted folder and double-click run.bat.
echo.
pause
exit /b 1

:no_uv
echo [!] uv is not installed. Open PowerShell and run:
echo.
echo     powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
echo.
echo     Then close this window and double-click run.bat again.
echo.
pause
exit /b 1

:failed
echo.
echo [!] Something went wrong. Please read the messages above.
echo     If you ask for help, send a screenshot of this window.
echo.
pause
exit /b 1

:end
endlocal
