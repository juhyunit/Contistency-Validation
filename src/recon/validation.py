"""검증 엔진: DQ → MD → SM → RC 순서로 규칙을 실행하고 결과표를 만든다.

파일 읽기·DB·보고서와 분리되어 있어 테스트에서 데이터만 넣고 바로 돌릴 수 있다.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date

import pandas as pd

from recon.config import Config
from recon.loader import InputData
from recon.models import ERROR, FILE_TYPES, ISSUE_COLUMNS, ROW_NO, TRANSACTIONS, TXN_COLUMNS, WARN, Issue
from recon.reconcile import (
    RECON_COLUMNS,
    RECON_INT_COLUMNS,
    RESULT_EXCLUDED,
    RESULT_EXISTENCE,
    RESULT_MATCH,
    RESULT_MISMATCH,
)
from recon.rules.context import RuleContext
from recon.rules.registry import STAGE_NAMES, STAGES, all_rules, run_stage

QUARANTINE_EXTRA_COLUMNS = ("error_rules", "error_messages")


@dataclass
class ValidationResult:
    issues: pd.DataFrame  # ISSUE_COLUMNS
    recon: pd.DataFrame  # RECON_COLUMNS
    clean: pd.DataFrame  # row_no + 거래내역 컬럼
    quarantine: pd.DataFrame  # row_no + 거래내역 컬럼 + 오류 사유
    stats: dict[str, int]
    rule_counts: dict[str, int]

    @property
    def review(self) -> pd.DataFrame:
        return self.issues[self.issues["severity"] == WARN].reset_index(drop=True)


def validate(
    data: InputData,
    base_date: date,
    config: Config,
    logger: logging.Logger | None = None,
) -> ValidationResult:
    log = logger or logging.getLogger(__name__)
    ctx = RuleContext(data, base_date, config)
    issues: list[Issue] = []
    for stage in STAGES:
        log.info("%s(%s) 단계 시작", stage, STAGE_NAMES[stage])
        found = run_stage(stage, ctx)
        if stage == "DQ":
            ctx.finish_dq()
        issues.extend(found)
        errors = sum(1 for i in found if i.severity == ERROR)
        log.info("%s 단계 종료: ERROR %d건, WARN %d건", stage, errors, len(found) - errors)

    recon = _recon_frame(ctx.recon_rows)
    issues_frame = _issues_frame(issues)
    clean, quarantine = _split_transactions(data.transactions, issues)

    results = Counter(row["result"] for row in ctx.recon_rows)
    quarantined = ctx.quarantined_records()
    stats = {
        "total_rows": len(ctx.txn_records),
        "clean_rows": len(clean),
        "quarantined_rows": len(quarantine),
        "review_rows": len(ctx.txn_warn_rows - ctx.txn_error_rows),
        "error_issues": int((issues_frame["severity"] == ERROR).sum()),
        "warn_issues": int((issues_frame["severity"] == WARN).sum()),
        "accounts_matched": results[RESULT_MATCH],
        "accounts_mismatched": results[RESULT_MISMATCH],
        "accounts_excluded": results[RESULT_EXCLUDED],
        "accounts_existence_mismatch": results[RESULT_EXISTENCE],
        # 계좌번호가 깨졌거나 마스터에 없어 어느 계좌에도 연결할 수 없는 격리 행
        "unidentified_quarantined_rows": sum(1 for r in quarantined if r["account_no"] not in ctx.accounts),
    }
    counts = Counter(i.rule_id for i in issues)
    rule_counts = {rule.rule_id: counts.get(rule.rule_id, 0) for rule in all_rules()}
    log.info("정상 %d건, 격리 %d건, 검토 %d건", stats["clean_rows"], stats["quarantined_rows"], stats["review_rows"])
    return ValidationResult(issues_frame, recon, clean, quarantine, stats, rule_counts)


def _issues_frame(issues: list[Issue]) -> pd.DataFrame:
    order = {rule.rule_id: i for i, rule in enumerate(all_rules())}
    ordered = sorted(
        issues,
        key=lambda i: (
            FILE_TYPES.index(i.file_type),
            i.row_no is None,
            i.row_no or 0,
            order[i.rule_id],
            i.column_name,
            i.record_key,
        ),
    )
    frame = pd.DataFrame([asdict(i) for i in ordered], columns=list(ISSUE_COLUMNS))
    frame["row_no"] = frame["row_no"].astype("Int64")
    return frame


def _recon_frame(rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=list(RECON_COLUMNS))
    for column in RECON_INT_COLUMNS:
        frame[column] = frame[column].astype("Int64")
    for column in ("is_target", "in_summary", "deposit_mismatch", "withdrawal_mismatch", "balance_mismatch"):
        frame[column] = frame[column].astype(bool)
    return frame


def _split_transactions(transactions: pd.DataFrame, issues: list[Issue]) -> tuple[pd.DataFrame, pd.DataFrame]:
    reasons: dict[int, list[Issue]] = {}
    for issue in issues:
        if issue.file_type == TRANSACTIONS and issue.severity == ERROR and issue.row_no is not None:
            reasons.setdefault(issue.row_no, []).append(issue)
    columns = [ROW_NO, *TXN_COLUMNS]
    is_error = transactions[ROW_NO].isin(list(reasons))
    clean = transactions.loc[~is_error, columns].reset_index(drop=True)
    quarantine = transactions.loc[is_error, columns].reset_index(drop=True)
    quarantine["error_rules"] = [
        ", ".join(dict.fromkeys(i.rule_id for i in reasons[int(n)])) for n in quarantine[ROW_NO]
    ]
    quarantine["error_messages"] = [" | ".join(i.message for i in reasons[int(n)]) for n in quarantine[ROW_NO]]
    return clean, quarantine
