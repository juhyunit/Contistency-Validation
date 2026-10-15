"""③ 집계표 검증 (SM): 대사 전에 집계표 자체의 중복·형식 오류를 찾는다."""

from __future__ import annotations

from recon.models import ACCOUNT_SUMMARY, ERROR
from recon.rules.registry import Finding, register


@register("SM-01", "집계표 자체 오류", severity=ERROR, file_type=ACCOUNT_SUMMARY)
def summary_problems(ctx):
    # 계좌당 1건만 기록하고, 해당 계좌는 RC-01~04 검사에서 모두 뺀다.
    for problem in ctx.summary_analysis.problems:
        yield Finding(
            problem.row_no,
            problem.key,
            ", ".join(problem.columns),
            ", ".join(problem.values),
            "; ".join(problem.reasons) + " → 대사 제외",
        )
