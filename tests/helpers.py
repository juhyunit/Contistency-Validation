"""규칙 테스트용 작은 입력 데이터 만들기."""

from __future__ import annotations

from datetime import date
from itertools import count

import pandas as pd

from recon.config import Config, load_config
from recon.loader import InputData
from recon.models import (
    ACCOUNT_MASTER_COLUMNS,
    DEPOSIT,
    ROW_NO,
    SUMMARY_COLUMNS,
    TXN_CODE_MASTER_COLUMNS,
    TXN_COLUMNS,
)
from recon.validation import ValidationResult, validate
from recon.values import parse_int

BASE = date(2026, 10, 15)

ACC = "111-11-111111"  # ACTIVE, 2020-01-01 개설
ACC2 = "012-22-222222"  # ACTIVE, 앞자리 0
CLOSED_TODAY = "333-33-333333"  # CLOSED, 기준일 해지 (당일 거래 정상)
CLOSED_YESTERDAY = "444-44-444444"  # CLOSED, 기준일 전날 해지 (기준일 거래는 해지일 다음날)
OPENED_TODAY = "555-55-555555"  # ACTIVE, 기준일 개설 (당일 거래 정상)
OPENS_TOMORROW = "666-66-666666"  # ACTIVE, 기준일 다음날 개설 (기준일 거래는 개설일 전날)
SUSPENDED_ACC = "777-77-777777"  # SUSPENDED

ACCOUNTS = [
    {"account_no": ACC, "product_code": "P01", "status": "ACTIVE", "open_date": "2020-01-01", "close_date": ""},
    {"account_no": ACC2, "product_code": "P01", "status": "ACTIVE", "open_date": "2021-05-05", "close_date": ""},
    {"account_no": CLOSED_TODAY, "product_code": "P02", "status": "CLOSED", "open_date": "2019-03-01", "close_date": "2026-10-15"},
    {"account_no": CLOSED_YESTERDAY, "product_code": "P02", "status": "CLOSED", "open_date": "2019-03-01", "close_date": "2026-10-14"},
    {"account_no": OPENED_TODAY, "product_code": "P03", "status": "ACTIVE", "open_date": "2026-10-15", "close_date": ""},
    {"account_no": OPENS_TOMORROW, "product_code": "P03", "status": "ACTIVE", "open_date": "2026-10-16", "close_date": ""},
    {"account_no": SUSPENDED_ACC, "product_code": "P01", "status": "SUSPENDED", "open_date": "2018-01-01", "close_date": ""},
]
TARGETS = (ACC, ACC2, CLOSED_TODAY, OPENED_TODAY, SUSPENDED_ACC)  # 기준일에 유효한 계좌

CODES = [
    {"txn_code": "D01", "txn_name": "현금입금", "direction": "D", "active_yn": "Y"},
    {"txn_code": "D02", "txn_name": "계좌이체입금", "direction": "D", "active_yn": "Y"},
    {"txn_code": "W01", "txn_name": "현금출금", "direction": "W", "active_yn": "Y"},
    {"txn_code": "W06", "txn_name": "자동이체출금(폐지)", "direction": "W", "active_yn": "N"},
]

_ids = count(1)


def txn(**overrides) -> dict:
    """정상 입금 거래 1건. 바꾸고 싶은 컬럼만 넘긴다. 기본값끼리는 시각이 달라 의심 중복이 생기지 않는다."""
    n = next(_ids)
    row = {
        "txn_id": f"T{n:08d}",
        "txn_dt": f"2026-10-15 {9 + n // 3600 % 14:02d}:{n // 60 % 60:02d}:{n % 60:02d}",
        "account_no": ACC,
        "txn_code": "D01",
        "direction": "D",
        "amount": "10000",
        "channel": "ATM",
        "branch_code": "",
    }
    row.update(overrides)
    return row


def summary_row(account_no: str, opening: int = 0, dep=(0, 0), wd=(0, 0), closing: int | None = None, **overrides) -> dict:
    closing = opening + dep[1] - wd[1] if closing is None else closing
    row = {
        "base_date": BASE.isoformat(),
        "account_no": account_no,
        "opening_balance": str(opening),
        "deposit_count": str(dep[0]),
        "deposit_amount": str(dep[1]),
        "withdrawal_count": str(wd[0]),
        "withdrawal_amount": str(wd[1]),
        "closing_balance": str(closing),
    }
    row.update({k: str(v) for k, v in overrides.items()})
    return row


def consistent_summary(txns: list[dict], opening: int = 1_000_000) -> list[dict]:
    """거래를 그대로 합산한 집계표 (집계 대상 계좌 전부, 거래 0건 계좌는 0)."""
    totals = {acc: [0, 0, 0, 0] for acc in TARGETS}
    for t in txns:
        amount = parse_int(t["amount"])
        if t["account_no"] not in totals or amount is None:
            continue
        offset = 0 if t["direction"] == DEPOSIT else 2
        totals[t["account_no"]][offset] += 1
        totals[t["account_no"]][offset + 1] += amount
    return [summary_row(acc, opening, (v[0], v[1]), (v[2], v[3])) for acc, v in totals.items()]


def _frame(rows: list[dict], columns) -> pd.DataFrame:
    # loader와 같게 모든 값을 문자열로 만들고 앞뒤 공백을 지운다.
    records = [{ROW_NO: i, **{c: str(r.get(c, "")).strip() for c in columns}} for i, r in enumerate(rows, start=2)]
    return pd.DataFrame.from_records(records, columns=[ROW_NO, *columns])


def make_data(txns: list[dict], summary: list[dict] | None = None, accounts=None, codes=None) -> InputData:
    return InputData(
        transactions=_frame(txns, TXN_COLUMNS),
        account_summary=_frame(consistent_summary(txns) if summary is None else summary, SUMMARY_COLUMNS),
        account_master=_frame(ACCOUNTS if accounts is None else accounts, ACCOUNT_MASTER_COLUMNS),
        txn_code_master=_frame(CODES if codes is None else codes, TXN_CODE_MASTER_COLUMNS),
    )


def run(txns: list[dict], summary: list[dict] | None = None, config: Config | None = None, **kwargs) -> ValidationResult:
    return validate(make_data(txns, summary, **kwargs), BASE, config or load_config())


def hits(result: ValidationResult, rule_id: str) -> pd.DataFrame:
    return result.issues[result.issues["rule_id"] == rule_id].reset_index(drop=True)


def hit_rows(result: ValidationResult, rule_id: str) -> list[int]:
    return [int(n) for n in hits(result, rule_id)["row_no"]]


def hit_keys(result: ValidationResult, rule_id: str) -> list[str]:
    return list(hits(result, rule_id)["record_key"])
