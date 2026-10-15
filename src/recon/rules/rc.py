"""③ 거래-집계 대사 (RC): 정상 거래를 계좌별로 합산해 집계표와 비교한다.

SM-01로 제외된 계좌는 검사하지 않고, RC-01(계좌 존재 불일치) 계좌는 RC-02~04를 검사하지 않는다.
"""

from __future__ import annotations

from recon.models import ACCOUNT_SUMMARY, ERROR
from recon.reconcile import RESULT_EXISTENCE, RECONCILED_RESULTS
from recon.rules.registry import Finding, register


@register("RC-01", "계좌 존재 불일치", severity=ERROR, file_type=ACCOUNT_SUMMARY)
def account_existence(ctx):
    for row in ctx.recon_rows:
        if row["result"] != RESULT_EXISTENCE:
            continue
        account_no = row["account_no"]
        if row["is_target"]:
            message = "집계 대상 계좌가 집계표에 없음"
        elif account_no not in ctx.accounts:
            message = "집계표에 있으나 계좌 마스터에 없는 계좌"
        else:
            info = ctx.accounts[account_no]
            message = (
                f"집계표에 있으나 기준일에 유효하지 않은 계좌 "
                f"(status {info.status}, 개설일 {info.open_date}, 해지일 {info.close_date or '-'})"
            )
        yield Finding(row["summary_row_no"], account_no, "account_no", account_no, message)


def _flow_finding(row: dict, kind: str, label: str) -> Finding:
    txn_count, sum_count = row[f"txn_{kind}_count"], row[f"sum_{kind}_count"]
    txn_amount, sum_amount = row[f"txn_{kind}_amount"], row[f"sum_{kind}_amount"]
    return Finding(
        row["summary_row_no"],
        row["account_no"],
        f"{kind}_count, {kind}_amount",
        f"{sum_count}, {sum_amount}",
        f"{label} 불일치: 거래 {txn_count}건 {txn_amount:,}원 / 집계표 {sum_count}건 {sum_amount:,}원",
    )


@register("RC-02", "입금 불일치", severity=ERROR, file_type=ACCOUNT_SUMMARY)
def deposit_mismatch(ctx):
    for row in ctx.recon_rows:
        if row["result"] in RECONCILED_RESULTS and row["deposit_mismatch"]:
            yield _flow_finding(row, "deposit", "입금")


@register("RC-03", "출금 불일치", severity=ERROR, file_type=ACCOUNT_SUMMARY)
def withdrawal_mismatch(ctx):
    for row in ctx.recon_rows:
        if row["result"] in RECONCILED_RESULTS and row["withdrawal_mismatch"]:
            yield _flow_finding(row, "withdrawal", "출금")


@register("RC-04", "잔액 등식 불일치", severity=ERROR, file_type=ACCOUNT_SUMMARY)
def balance_equation(ctx):
    # 집계표 자체 검증: 기초 + 입금 − 출금 = 기말
    for row in ctx.recon_rows:
        if row["result"] in RECONCILED_RESULTS and row["balance_mismatch"]:
            yield Finding(
                row["summary_row_no"],
                row["account_no"],
                "closing_balance",
                str(row["closing_balance"]),
                f"잔액 등식 불일치: 기초 {row['opening_balance']:,} + 입금 {row['sum_deposit_amount']:,} "
                f"− 출금 {row['sum_withdrawal_amount']:,} = {row['expected_closing_balance']:,}, "
                f"집계표 기말 {row['closing_balance']:,}",
            )
