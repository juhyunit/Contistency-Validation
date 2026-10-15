"""집계표 분석(SM-01)과 계좌별 대사 계산(RC-01~04, 대사결과 시트)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

from recon.config import Config
from recon.models import DEPOSIT, ROW_NO, WITHDRAWAL
from recon.values import parse_date, parse_int

if TYPE_CHECKING:
    from recon.rules.context import RuleContext

RESULT_MATCH = "일치"
RESULT_MISMATCH = "불일치"
RESULT_EXCLUDED = "집계표 오류로 대사 제외"
RESULT_EXISTENCE = "계좌 존재 불일치"
RECONCILED_RESULTS = (RESULT_MATCH, RESULT_MISMATCH)

CAUSE_EXCLUDED_TXN = "제외 거래 있음"
CAUSE_REVIEW_TXN = "검토 거래 있음"
CAUSE_UNKNOWN = "원인 미상"
CAUSE_BALANCE = "잔액 등식 불일치"

NON_NEGATIVE_COLUMNS = ("deposit_count", "deposit_amount", "withdrawal_count", "withdrawal_amount")
BALANCE_COLUMNS = ("opening_balance", "closing_balance")

RECON_COLUMNS = (
    "account_no",
    "result",
    "diff_cause",
    "summary_row_no",
    "is_target",
    "in_summary",
    "txn_deposit_count",
    "sum_deposit_count",
    "deposit_count_diff",
    "txn_deposit_amount",
    "sum_deposit_amount",
    "deposit_amount_diff",
    "txn_withdrawal_count",
    "sum_withdrawal_count",
    "withdrawal_count_diff",
    "txn_withdrawal_amount",
    "sum_withdrawal_amount",
    "withdrawal_amount_diff",
    "opening_balance",
    "closing_balance",
    "expected_closing_balance",
    "balance_diff",
    "deposit_mismatch",
    "withdrawal_mismatch",
    "balance_mismatch",
)
RECON_INT_COLUMNS = tuple(
    c for c in RECON_COLUMNS if c not in ("account_no", "result", "diff_cause", "is_target", "in_summary")
    and not c.endswith("_mismatch")
)


@dataclass(frozen=True)
class SummaryRow:
    account_no: str
    row_no: int
    opening_balance: int
    deposit_count: int
    deposit_amount: int
    withdrawal_count: int
    withdrawal_amount: int
    closing_balance: int


@dataclass(frozen=True)
class SummaryProblem:
    key: str  # 계좌번호, 계좌번호가 없으면 "행 N"
    account_no: str
    row_no: int
    columns: tuple[str, ...]
    values: tuple[str, ...]
    reasons: tuple[str, ...]


@dataclass
class SummaryAnalysis:
    rows: dict[str, SummaryRow] = field(default_factory=dict)  # 대사 가능한 집계표 행
    problems: list[SummaryProblem] = field(default_factory=list)  # SM-01 대상

    @property
    def excluded_accounts(self) -> dict[str, SummaryProblem]:
        return {p.account_no: p for p in self.problems if p.account_no}


def analyze_summary(records: list[dict], base_date: date, config: Config) -> SummaryAnalysis:
    analysis = SummaryAnalysis()
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        if r["account_no"]:
            groups[r["account_no"]].append(r)
        else:
            analysis.problems.append(
                SummaryProblem(f"행 {r[ROW_NO]}", "", r[ROW_NO], ("account_no",), ("",), ("계좌번호 없음",))
            )

    for account_no, group in groups.items():
        found: dict[str, tuple[str, str]] = {}  # 사유 → (컬럼, 값). 중복 행에서 같은 사유는 한 번만 적는다
        if len(group) > 1:
            rows = ", ".join(str(g[ROW_NO]) for g in group)
            found[f"계좌 중복 행 ({rows}행)"] = ("account_no", account_no)
        for r in group:
            if parse_date(r["base_date"], config.date_format) != base_date:
                found.setdefault(f"base_date가 기준일({base_date})과 다름", ("base_date", r["base_date"]))
            for column in NON_NEGATIVE_COLUMNS + BALANCE_COLUMNS:
                number = parse_int(r[column])
                if number is None:
                    found.setdefault(f"{column} 숫자가 아님", (column, r[column]))
                elif number < 0 and column in NON_NEGATIVE_COLUMNS:
                    found.setdefault(f"{column} 음수", (column, r[column]))

        first = group[0]
        if found:
            analysis.problems.append(
                SummaryProblem(
                    account_no,
                    account_no,
                    first[ROW_NO],
                    tuple(column for column, _ in found.values()),
                    tuple(value for _, value in found.values()),
                    tuple(found),
                )
            )
        else:
            analysis.rows[account_no] = SummaryRow(
                account_no,
                first[ROW_NO],
                *(parse_int(first[c]) for c in ("opening_balance", *NON_NEGATIVE_COLUMNS, "closing_balance")),
            )
    analysis.problems.sort(key=lambda p: p.row_no)
    return analysis


def build_recon_rows(ctx: RuleContext) -> list[dict]:
    analysis = ctx.summary_analysis
    excluded = analysis.excluded_accounts
    tolerance = ctx.config.amount_tolerance

    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])  # 입금 건수·금액, 출금 건수·금액
    for r in ctx.clean_records():
        amount = parse_int(r["amount"])
        if amount is None:  # DQ-04를 끈 경우에만 생긴다
            continue
        if r["direction"] == DEPOSIT:
            totals[r["account_no"]][0] += 1
            totals[r["account_no"]][1] += amount
        elif r["direction"] == WITHDRAWAL:
            totals[r["account_no"]][2] += 1
            totals[r["account_no"]][3] += amount

    quarantined_accounts = {r["account_no"] for r in ctx.quarantined_records()}
    review_accounts = {
        r["account_no"]
        for r in ctx.txn_records
        if r[ROW_NO] in ctx.txn_warn_rows and r[ROW_NO] not in ctx.txn_error_rows
    }

    rows = []
    for account_no in sorted(ctx.target_accounts | set(analysis.rows) | set(excluded)):
        dep_count, dep_amount, wd_count, wd_amount = totals.get(account_no, [0, 0, 0, 0])
        summary = analysis.rows.get(account_no)
        row = dict.fromkeys(RECON_COLUMNS)
        row.update(
            account_no=account_no,
            diff_cause="",
            is_target=account_no in ctx.target_accounts,
            in_summary=summary is not None or account_no in excluded,
            txn_deposit_count=dep_count,
            txn_deposit_amount=dep_amount,
            txn_withdrawal_count=wd_count,
            txn_withdrawal_amount=wd_amount,
            deposit_mismatch=False,
            withdrawal_mismatch=False,
            balance_mismatch=False,
        )
        if account_no in excluded:
            row.update(result=RESULT_EXCLUDED, summary_row_no=excluded[account_no].row_no)
            rows.append(row)
            continue

        if summary is not None:
            expected_closing = summary.opening_balance + summary.deposit_amount - summary.withdrawal_amount
            row.update(
                summary_row_no=summary.row_no,
                sum_deposit_count=summary.deposit_count,
                sum_deposit_amount=summary.deposit_amount,
                sum_withdrawal_count=summary.withdrawal_count,
                sum_withdrawal_amount=summary.withdrawal_amount,
                deposit_count_diff=dep_count - summary.deposit_count,
                deposit_amount_diff=dep_amount - summary.deposit_amount,
                withdrawal_count_diff=wd_count - summary.withdrawal_count,
                withdrawal_amount_diff=wd_amount - summary.withdrawal_amount,
                opening_balance=summary.opening_balance,
                closing_balance=summary.closing_balance,
                expected_closing_balance=expected_closing,
                balance_diff=summary.closing_balance - expected_closing,
            )

        if summary is None or not row["is_target"]:
            row["result"] = RESULT_EXISTENCE
            rows.append(row)
            continue

        row["deposit_mismatch"] = row["deposit_count_diff"] != 0 or abs(row["deposit_amount_diff"]) > tolerance
        row["withdrawal_mismatch"] = (
            row["withdrawal_count_diff"] != 0 or abs(row["withdrawal_amount_diff"]) > tolerance
        )
        row["balance_mismatch"] = abs(row["balance_diff"]) > tolerance
        causes = []
        if row["deposit_mismatch"] or row["withdrawal_mismatch"]:
            if account_no in quarantined_accounts:
                causes.append(CAUSE_EXCLUDED_TXN)
            elif account_no in review_accounts:
                causes.append(CAUSE_REVIEW_TXN)
            else:
                causes.append(CAUSE_UNKNOWN)
        if row["balance_mismatch"]:
            causes.append(CAUSE_BALANCE)
        row["diff_cause"] = " / ".join(causes)
        row["result"] = RESULT_MISMATCH if causes else RESULT_MATCH
        rows.append(row)
    return rows
