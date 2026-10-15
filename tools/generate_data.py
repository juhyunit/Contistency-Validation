"""합성 데이터 생성: 깨끗한 데이터(clean/)와 오류 주입 데이터(injected/ + 정답 파일).

  python tools/generate_data.py                  # data/sample 아래에 생성
  python tools/generate_data.py --seed 7 --out-dir data/sample7
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from recon.synthetic import ANSWER_FILE_NAME, DEFAULT_BASE_DATE, DEFAULT_SEED, generate_datasets  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="합성 데이터 생성과 오류 주입")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "data" / "sample")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--base-date", type=date.fromisoformat, default=DEFAULT_BASE_DATE)
    args = parser.parse_args(argv)

    clean, injected = generate_datasets(args.seed, args.base_date)
    clean.write(args.out_dir / "clean")
    injected.write(args.out_dir / "injected")

    per_rule = Counter(rule for rule, _ in {(a["expected_rule"], a["error_id"]) for a in injected.answer})
    print(f"기준일 {args.base_date}, 시드 {args.seed}")
    print(f"깨끗한 데이터: {args.out_dir / 'clean'} (거래 {len(clean.transactions):,}건, 집계 계좌 {len(clean.summary)}개)")
    print(f"오류 주입 데이터: {args.out_dir / 'injected'} (거래 {len(injected.transactions):,}건)")
    print(f"정답 파일: {args.out_dir / 'injected' / ANSWER_FILE_NAME} (오류 {sum(per_rule.values())}건)")
    print("  " + ", ".join(f"{rule} {count}" for rule, count in sorted(per_rule.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
