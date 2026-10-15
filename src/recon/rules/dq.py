"""① 품질 검증 (DQ): 거래내역 파일 하나 안의 누락·형식·중복 오류."""

from __future__ import annotations

from collections import defaultdict

from recon.models import ERROR, ROW_NO, TRANSACTIONS, TXN_COLUMNS, TXN_REQUIRED, WARN
from recon.rules.registry import Finding, register
from recon.values import parse_datetime, parse_int


def txn_key(record: dict) -> str:
    """오류목록의 키. txn_id가 비어 있으면 행번호로 표시한다."""
    return record["txn_id"] or f"행 {record[ROW_NO]}"


@register("DQ-01", "필수값 누락", severity=ERROR, file_type=TRANSACTIONS)
def required_values(ctx):
    # 값은 읽을 때 앞뒤 공백을 지웠으므로 공백뿐인 값도 빈 값이 된다.
    for r in ctx.txn_records:
        for column in TXN_REQUIRED:
            if r[column] == "":
                yield Finding(r[ROW_NO], txn_key(r), column, "", f"필수값 누락: {column}")


@register("DQ-02", "계좌번호 형식", severity=ERROR, file_type=TRANSACTIONS)
def account_no_format(ctx):
    for r in ctx.txn_records:
        value = r["account_no"]
        if value and not ctx.config.account_no_pattern.fullmatch(value):
            yield Finding(r[ROW_NO], txn_key(r), "account_no", value, "계좌번호 형식 오류 (형식: 123-45-678901)")


@register("DQ-03", "거래일시 형식·범위", severity=ERROR, file_type=TRANSACTIONS)
def txn_datetime(ctx):
    fmt = ctx.config.txn_dt_format
    for r in ctx.txn_records:
        value = r["txn_dt"]
        if not value:
            continue
        parsed = parse_datetime(value, fmt)
        if parsed is None:
            yield Finding(r[ROW_NO], txn_key(r), "txn_dt", value, f"거래일시 형식 오류 (형식: {fmt})")
        elif parsed.date() != ctx.base_date:
            yield Finding(r[ROW_NO], txn_key(r), "txn_dt", value, f"거래일이 기준일({ctx.base_date})과 다름")


@register("DQ-04", "금액 형식", severity=ERROR, file_type=TRANSACTIONS)
def amount_format(ctx):
    for r in ctx.txn_records:
        value = r["amount"]
        if not value:
            continue
        amount = parse_int(value)
        if amount is None:
            yield Finding(r[ROW_NO], txn_key(r), "amount", value, "금액이 정수가 아님")
        elif amount <= 0:
            yield Finding(r[ROW_NO], txn_key(r), "amount", value, "금액이 0 이하")


@register("DQ-05", "입출금 구분 값", severity=ERROR, file_type=TRANSACTIONS)
def direction_value(ctx):
    allowed = ctx.config.directions
    for r in ctx.txn_records:
        value = r["direction"]
        if value and value not in allowed:
            yield Finding(r[ROW_NO], txn_key(r), "direction", value, f"입출금 구분 값 오류 (허용: {', '.join(allowed)})")


@register("DQ-06", "거래번호 중복", severity=ERROR, file_type=TRANSACTIONS)
def duplicate_txn_id(ctx):
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in ctx.txn_records:
        if r["txn_id"]:
            groups[r["txn_id"]].append(r)
    for txn_id, rows in groups.items():
        if len(rows) < 2:
            continue
        first = rows[0]
        content = tuple(first[c] for c in TXN_COLUMNS)
        if all(tuple(r[c] for c in TXN_COLUMNS) == content for r in rows[1:]):
            # 내용이 같으면 같은 거래가 두 번 들어온 것: 첫 건만 남긴다.
            for r in rows[1:]:
                yield Finding(r[ROW_NO], txn_id, "txn_id", txn_id, f"거래번호 중복: 내용 동일, {first[ROW_NO]}행만 유지")
        else:
            # 내용이 다르면 어느 쪽이 맞는지 판단할 수 없으므로 전부 격리한다.
            for r in rows:
                yield Finding(r[ROW_NO], txn_id, "txn_id", txn_id, f"거래번호 중복: 내용 상이, {len(rows)}건 전부 격리")


@register("DQ-07", "의심 중복", severity=WARN, file_type=TRANSACTIONS)
def suspected_duplicate(ctx):
    # DQ ERROR 행은 대사에 쓰이지 않으므로 비교 대상에서 뺀다.
    # 먼저 나온 행을 기준으로 두고 뒤에 나온 행을 검토 대상으로 올린다 (둘 다 대사에는 포함).
    first_seen: dict[tuple, dict] = {}
    for r in ctx.txn_records:
        if r[ROW_NO] in ctx.txn_error_rows:
            continue
        amount = parse_int(r["amount"])
        if amount is None:
            continue
        key = (r["account_no"], r["txn_dt"], r["txn_code"], amount)
        first = first_seen.setdefault(key, r)
        if first is not r:
            yield Finding(
                r[ROW_NO],
                txn_key(r),
                "txn_id",
                r["txn_id"],
                f"의심 중복: {first[ROW_NO]}행(txn_id {first['txn_id']})과 계좌·일시·코드·금액 동일",
            )
