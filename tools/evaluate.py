"""정답 대비 재현율·오탐 계산. 재현율 100%, 오탐 0건이 아니면 종료 코드 1 (CI 실패).

  python tools/evaluate.py                                   # data/sample/injected를 검증하고 평가
  python tools/evaluate.py --run-id 5 --data-dir data/sample/injected   # 이미 실행한 결과를 평가
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from recon.evaluation import evaluate  # noqa: E402
from recon.loader import read_input_dir  # noqa: E402
from recon.pipeline import run_pipeline  # noqa: E402
from recon.repository import Repository  # noqa: E402
from recon.synthetic import ANSWER_FILE_NAME, DEFAULT_BASE_DATE  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="정답 파일 대비 재현율·오탐 계산")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data" / "sample" / "injected")
    parser.add_argument("--base-date", type=date.fromisoformat, default=DEFAULT_BASE_DATE)
    parser.add_argument("--run-id", type=int, help="이미 실행한 결과를 평가 (생략하면 data-dir로 새로 실행)")
    args = parser.parse_args(argv)

    answer_path = args.data_dir / ANSWER_FILE_NAME
    if not answer_path.is_file():
        print(f"정답 파일이 없습니다: {answer_path} (먼저 tools/generate_data.py 실행)", file=sys.stderr)
        return 2
    answer = pd.read_csv(answer_path, dtype=str, keep_default_na=False, encoding="utf-8-sig")

    if args.run_id is not None:
        issues = Repository().get_issues(args.run_id)
        run_label = f"실행 #{args.run_id}"
    else:
        result = run_pipeline(read_input_dir(args.data_dir), args.base_date)
        if not result.succeeded:
            print(f"실행 #{result.run_id} 실패: {result.error_message}", file=sys.stderr)
            return 1
        issues = result.validation.issues
        run_label = f"실행 #{result.run_id}"

    ev = evaluate(issues, answer)
    print(f"{run_label} 평가")
    print(ev.per_rule.to_string(index=False, formatters={"recall": "{:.0%}".format}))
    print(f"전체 재현율 {ev.recall:.1%} ({ev.detected}/{ev.injected}), 오탐 {len(ev.false_positives)}건, "
          f"예상된 연쇄 {len(ev.cascades)}건")
    if not ev.missed.empty:
        print("\n탐지하지 못한 주입 오류:")
        print(ev.missed.to_string(index=False))
    if not ev.false_positives.empty:
        print("\n오탐:")
        print(ev.false_positives[["rule_id", "row_no", "record_key", "message"]].to_string(index=False))
    print("결과: " + ("통과" if ev.passed else "실패"))
    return 0 if ev.passed else 1


if __name__ == "__main__":
    sys.exit(main())
