@echo off
chcp 65001 >nul
rem 원클릭 실행 (Windows): 더블클릭하면 처음 한 번은 파이썬과 패키지를 자동으로 설치하고, 브라우저에 화면을 연다.
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
  echo uv가 설치되어 있지 않습니다. PowerShell에서 아래 명령으로 설치한 뒤 이 파일을 다시 실행하세요.
  echo.
  echo   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  echo.
  pause
  exit /b 1
)

echo 필요한 패키지를 확인하고 화면을 엽니다. 처음 실행은 1~2분 걸릴 수 있습니다.
echo 종료하려면 이 창을 닫거나 Ctrl+C를 누르세요.
uv run streamlit run app/streamlit_app.py
pause
