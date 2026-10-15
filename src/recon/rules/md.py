"""② 기준정보 정합성 (MD): 계좌 마스터·거래코드 마스터와 거래내역 비교.

DQ ERROR 행은 검사하지 않는다 (깨진 계좌번호가 MD-01을 중복으로 일으키지 않도록).
"""

from __future__ import annotations

from recon.models import CLOSED, ERROR, ROW_NO, SUSPENDED, TRANSACTIONS, WARN, WITHDRAWAL
from recon.rules.dq import txn_key
from recon.rules.registry import Finding, register
from recon.values import parse_datetime


@register("MD-01", "미등록 계좌", severity=ERROR, file_type=TRANSACTIONS)
def unknown_account(ctx):
    for r in ctx.md_records():
        if r["account_no"] not in ctx.accounts:
            yield Finding(r[ROW_NO], txn_key(r), "account_no", r["account_no"], "계좌 마스터에 없는 계좌")


@register("MD-02", "계좌 유효기간 외 거래", severity=ERROR, file_type=TRANSACTIONS)
def outside_account_period(ctx):
    for r in ctx.md_records():
        info = ctx.accounts.get(r["account_no"])
        parsed = parse_datetime(r["txn_dt"], ctx.config.txn_dt_format)
        if info is None or parsed is None:
            continue
        day = parsed.date()
        if day < info.open_date:
            yield Finding(r[ROW_NO], txn_key(r), "txn_dt", r["txn_dt"], f"개설일({info.open_date}) 이전 거래")
        elif info.status == CLOSED and info.close_date is not None and day > info.close_date:
            yield Finding(r[ROW_NO], txn_key(r), "txn_dt", r["txn_dt"], f"해지일({info.close_date}) 이후 거래")


@register("MD-03", "미등록·폐지 거래코드", severity=ERROR, file_type=TRANSACTIONS)
def unknown_or_inactive_code(ctx):
    for r in ctx.md_records():
        info = ctx.codes.get(r["txn_code"])
        if info is None:
            yield Finding(r[ROW_NO], txn_key(r), "txn_code", r["txn_code"], "거래코드 마스터에 없는 코드")
        elif not info.active:
            yield Finding(r[ROW_NO], txn_key(r), "txn_code", r["txn_code"], "폐지된 거래코드 (active_yn = N)")


@register("MD-04", "코드-방향 불일치", severity=ERROR, file_type=TRANSACTIONS)
def code_direction_mismatch(ctx):
    for r in ctx.md_records():
        info = ctx.codes.get(r["txn_code"])
        direction = r["direction"]
        if info is not None and direction in ctx.config.directions and direction != info.direction:
            yield Finding(
                r[ROW_NO],
                txn_key(r),
                "direction",
                direction,
                f"거래코드 {r['txn_code']}의 방향은 {info.direction}인데 거래는 {direction}",
            )


@register("MD-05", "지급정지 계좌 출금", severity=WARN, file_type=TRANSACTIONS)
def suspended_withdrawal(ctx):
    for r in ctx.md_records():
        info = ctx.accounts.get(r["account_no"])
        if info is not None and info.status == SUSPENDED and r["direction"] == WITHDRAWAL:
            yield Finding(r[ROW_NO], txn_key(r), "account_no", r["account_no"], "지급정지(SUSPENDED) 계좌 출금")
