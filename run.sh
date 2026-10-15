#!/usr/bin/env sh
# 원클릭 실행 (macOS·Linux): 처음 한 번은 파이썬과 패키지를 자동으로 설치하고, 브라우저에 화면을 연다.
#   ./run.sh        (macOS에서 더블클릭하려면 run.command 이름으로 복사해서 쓰세요)
cd "$(dirname "$0")" || exit 1

if ! command -v uv >/dev/null 2>&1; then
  echo "uv가 설치되어 있지 않습니다. 아래 명령으로 설치한 뒤 터미널을 새로 열고 다시 실행하세요."
  echo ""
  echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
  echo ""
  exit 1
fi

echo "필요한 패키지를 확인하고 화면을 엽니다. 처음 실행은 1~2분 걸릴 수 있습니다."
echo "종료하려면 이 창에서 Ctrl+C를 누르세요."
exec uv run streamlit run app/streamlit_app.py
