# 금융 데이터 검증·대사 자동화

하루치 계좌 거래내역을 받아 세 단계를 자동으로 수행하는 도구입니다. 결과는 엑셀 보고서, 정상·격리 거래 CSV, 실행 이력(DB)으로 남습니다.

- **품질 검증 (DQ-01~07):** 빈 값, 형식 오류, 중복을 찾습니다.
- **기준정보 정합성 (MD-01~05):** 계좌 마스터·거래코드 마스터와 거래내역을 대조합니다.
- **집계표 검증·대사 (SM-01, RC-01~04):** 계좌별 거래 합계를 집계표와 비교합니다.

설계와 규칙은 [docs/설계서.md](docs/설계서.md), [docs/업무규칙서.md](docs/업무규칙서.md), [docs/데이터사전.md](docs/데이터사전.md)에 있습니다.

## 실행하기

### 1. 원클릭 실행 (권장)

[uv](https://docs.astral.sh/uv/)만 한 번 설치하면 됩니다. 파이썬과 패키지는 처음 실행할 때 uv가 알아서 설치합니다.

| OS | uv 설치 (한 번만) | 실행 |
|---|---|---|
| Windows | PowerShell에서 `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 \| iex"` | `run.bat` 더블클릭 |
| macOS·Linux | 터미널에서 `curl -LsSf https://astral.sh/uv/install.sh \| sh` | `./run.sh` |

실행하면 브라우저에 화면이 열립니다(`http://localhost:8501`). 실행 파일이 없으면 **실행** 탭에서 **샘플 데이터로 실행**을 누르세요. 오류를 심어 둔 합성 데이터로 결과를 볼 수 있습니다.

### 2. 명령행

```bash
uv run python tools/generate_data.py          # data/sample/clean, data/sample/injected 생성
uv run python cli.py run --input-dir data/sample/injected --base-date 2026-10-15
uv run python cli.py run --input-dir data/fixed --base-date 2026-10-15 --parent-run-id 1   # 재처리
uv run python cli.py runs                     # 실행 이력
uv run python tools/evaluate.py               # 정답 대비 재현율·오탐 (통과 못 하면 종료 코드 1)
```

입력 폴더에는 다음 이름의 파일 4개가 있어야 합니다: `transactions.csv`, `account_summary.xlsx`, `account_master.csv`, `txn_code_master.csv`. 이 중 하나라도 없으면 실행은 FAILED로 기록됩니다.

### 3. 웹 데모 (Streamlit Community Cloud)

설치 없이 링크로 보여 주고 싶을 때 씁니다.

1. [share.streamlit.io](https://share.streamlit.io)에서 GitHub 계정으로 로그인합니다.
2. **Create app**을 누르고 이 저장소와 브랜치를 고릅니다. Main file path에는 `app/streamlit_app.py`를 입력합니다.
3. 의존성은 `requirements.txt`로 설치됩니다.

**주의할 점**
- **실제 금융 데이터는 올리지 마세요.** 공개 서버이므로 합성 데이터(샘플 버튼)만 쓰는 데모 용도입니다.
- **데이터가 지워질 수 있습니다.** 앱이 재시작되면 SQLite 실행 이력과 보고서 파일이 사라질 수 있습니다.

## 출력 위치

모든 출력은 `data/` 아래에 쌓이며, 이 폴더는 git에 올라가지 않습니다.

| 경로 | 내용 |
|---|---|
| `data/recon.db` | 실행 이력 DB (SQLite). `DATABASE_URL` 환경변수로 PostgreSQL 등으로 바꿀 수 있음 |
| `data/archive/` | 업로드 원본 보관 (`SHA-256 앞 16자_파일명`) |
| `data/output/run_{번호}/` | `report_{번호}.xlsx`, `clean_transactions.csv`, `quarantine_transactions.csv`, `run.log` |
| `data/sample/` | `tools/generate_data.py`로 만든 합성 데이터와 정답 파일 |

`data/` 위치는 `RECON_DATA_DIR` 환경변수로 바꿀 수 있습니다. 정규식, 금액 허용오차, 규칙 사용 여부는 [config/rules.yaml](config/rules.yaml)에서 바꿉니다.

## 구조

```mermaid
flowchart LR
    UI["app/streamlit_app.py<br/>화면"] --> P
    CLI["cli.py<br/>명령행·스케줄러"] --> P
    P["pipeline.py<br/>실행 순서·상태"] --> L["loader.py<br/>읽기·해시·스키마"]
    P --> V["validation.py<br/>DQ→MD→SM→RC"]
    V --> R["rules/<br/>17개 규칙 (레지스트리)"]
    V --> RC["reconcile.py<br/>계좌별 대사"]
    P --> RP["reporter.py<br/>엑셀·CSV"]
    P --> DB["repository.py<br/>DB"]
```

```
config/rules.yaml          # 정규식, 허용오차, 규칙 on/off
src/recon/
  loader.py                # 파일 읽기, 인코딩·스키마 확인, 해시, 원본 보관
  rules/                   # registry.py(등록·실행), dq.py, md.py, sm.py, rc.py, context.py
  reconcile.py             # 집계표 분석, 계좌별 대사 계산
  validation.py            # 단계별 실행, 정상·격리 분리
  pipeline.py              # 전체 실행 순서, run 상태 관리
  reporter.py              # 엑셀·CSV 출력
  repository.py            # DB 저장·조회
  synthetic.py             # 합성 데이터 + 오류 주입
  evaluation.py            # 정답 대비 재현율·오탐 계산
app/streamlit_app.py       # 화면 (실행, 결과 요약, 상세, 실행 이력)
cli.py                     # 명령행 실행
tools/generate_data.py     # 합성 데이터 생성
tools/evaluate.py          # 평가 (CI에서 사용)
tests/                     # 단위·경계값·통합·실패 상황 테스트
```

## 개발

```bash
uv sync                    # 의존성 설치 (.venv)
uv run pytest              # 테스트
```

- **CI:** main에 push하면 GitHub Actions(`.github/workflows/ci.yml`)가 테스트, 합성 데이터 생성, 평가를 차례로 실행합니다.
- **의존성 변경:** 의존성을 바꾼 뒤에는 `uv lock`을 실행하고, 아래 명령으로 `requirements.txt`를 다시 만드세요.

  ```bash
  uv export --no-dev --no-hashes --no-header --no-annotate --format requirements-txt > requirements.txt
  ```
