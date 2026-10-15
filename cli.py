"""명령행 실행. 화면(app)과 같은 pipeline.run_pipeline을 호출한다 (스케줄러 연결용).

예)
  python cli.py run --input-dir data/sample/injected --base-date 2026-10-15
  python cli.py run --input-dir data/fixed --base-date 2026-10-15 --parent-run-id 3
  python cli.py runs
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from recon.loader import read_input_dir  # noqa: E402
from recon.pipeline import run_pipeline  # noqa: E402
from recon.repository import Repository  # noqa: E402

STAT_LINES = (
    ("total_rows", "총 거래"),
    ("clean_rows", "정상"),
    ("quarantined_rows", "격리"),
    ("review_rows", "검토 대상"),
    ("accounts_matched", "대사 일치 계좌"),
    ("accounts_mismatched", "대사 불일치 계좌"),
    ("accounts_excluded", "집계표 오류로 대사 제외"),
    ("accounts_existence_mismatch", "계좌 존재 불일치"),
    ("unidentified_quarantined_rows", "계좌 미식별 격리"),
)


def _run(args: argparse.Namespace) -> int:
    if not args.input_dir.is_dir():
        print(f"입력 폴더가 없습니다: {args.input_dir}", file=sys.stderr)
        return 2
    result = run_pipeline(read_input_dir(args.input_dir), args.base_date, parent_run_id=args.parent_run_id)
    print(f"실행 #{result.run_id}: {result.status}")
    for warning in result.warnings:
        print(f"  경고: {warning}")
    if not result.succeeded:
        print(f"  원인: {result.error_message}")
        return 1
    stats = result.validation.stats
    for key, label in STAT_LINES:
        print(f"  {label}: {stats[key]:,}")
    counts = {k: v for k, v in result.validation.rule_counts.items() if v}
    print("  규칙별 오류: " + (", ".join(f"{k} {v}" for k, v in counts.items()) or "없음"))
    print(f"  보고서: {result.outputs.report}")
    return 0


def _runs(_: argparse.Namespace) -> int:
    runs = Repository().list_runs()
    if runs.empty:
        print("실행 이력이 없습니다.")
        return 0
    columns = ["run_id", "parent_run_id", "base_date", "status", "started_at", "finished_at", "error_message"]
    print(runs[columns].astype(object).fillna("").to_string(index=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="금융 데이터 검증·대사 자동화")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="입력 폴더의 파일 4개로 검증 실행")
    run.add_argument("--input-dir", type=Path, required=True,
                     help="transactions.csv, account_summary.xlsx, account_master.csv, txn_code_master.csv가 있는 폴더")
    run.add_argument("--base-date", type=date.fromisoformat, required=True, help="기준일 (YYYY-MM-DD)")
    run.add_argument("--parent-run-id", type=int, help="재처리일 때 이전 실행 번호")
    run.set_defaults(func=_run)

    runs = sub.add_parser("runs", help="실행 이력 보기")
    runs.set_defaults(func=_runs)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
