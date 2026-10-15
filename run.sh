#!/usr/bin/env sh
# 원클릭 실행 (macOS·Linux): 처음 한 번은 파이썬과 패키지를 자동으로 설치하고, 브라우저에 화면을 연다.
#   ./run.sh        (macOS에서 더블클릭하려면 이 파일을 run.command 이름으로 복사해서 쓰세요)
cd "$(dirname "$0")" || exit 1

if [ ! -f pyproject.toml ] || [ ! -f app/streamlit_app.py ]; then
  echo "[!] run.sh는 압축을 푼 프로젝트 폴더 안에서 실행해야 합니다."
  echo "    GitHub에서 Code > Download ZIP으로 전체를 받아 압축을 푼 뒤 다시 실행하세요."
  exit 1
fi

UV=""
if command -v uv >/dev/null 2>&1; then
  UV="uv"
elif [ -x "$HOME/.local/bin/uv" ]; then
  UV="$HOME/.local/bin/uv"   # 설치 직후 PATH에 아직 없을 때
else
  echo "[!] uv가 설치되어 있지 않습니다. 아래 명령으로 설치한 뒤 다시 실행하세요."
  echo ""
  echo "    curl -LsSf https://astral.sh/uv/install.sh | sh"
  echo ""
  exit 1
fi

echo "[1/2] 파이썬과 패키지를 준비합니다. 처음에는 약 150MB를 받느라 1~3분 걸릴 수 있습니다."
"$UV" sync --no-dev || { echo "[!] 패키지 준비에 실패했습니다. 위 메시지를 확인하세요."; exit 1; }

echo ""
echo "[2/2] 화면을 엽니다: http://localhost:8501"
echo "      이 창을 열어 둔 채로 사용하고, 끝내려면 Ctrl+C를 누르세요."
exec "$UV" run --no-dev streamlit run app/streamlit_app.py
