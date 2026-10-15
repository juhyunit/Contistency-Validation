"""MD 규칙: 기준정보 정합성."""

from __future__ import annotations

import pytest

from helpers import (
    ACC,
    ACC2,
    CLOSED_TODAY,
    CLOSED_YESTERDAY,
    OPENED_TODAY,
    OPENS_TOMORROW,
    SUSPENDED_ACC,
    hit_rows,
    hits,
    run,
    txn,
)


@pytest.mark.parametrize("account_no", ["999-99-999999", "111-11-111112"])
def test_md01_hits_unknown_account(account_no):
    assert hit_rows(run([txn(account_no=account_no)]), "MD-01") == [2]


@pytest.mark.parametrize("account_no", [ACC, ACC2])
def test_md01_accepts_registered_account(account_no):
    assert hit_rows(run([txn(account_no=account_no)]), "MD-01") == []


@pytest.mark.parametrize(
    ("account_no", "message"),
    [(CLOSED_YESTERDAY, "해지일(2026-10-14) 이후 거래"), (OPENS_TOMORROW, "개설일(2026-10-16) 이전 거래")],
)
def test_md02_hits_day_after_close_and_day_before_open(account_no, message):
    result = run([txn(account_no=account_no)])
    assert hit_rows(result, "MD-02") == [2]
    assert hits(result, "MD-02").loc[0, "message"] == message


@pytest.mark.parametrize("account_no", [CLOSED_TODAY, OPENED_TODAY, ACC])
def test_md02_accepts_close_day_and_open_day(account_no):
    assert hit_rows(run([txn(account_no=account_no)]), "MD-02") == []


@pytest.mark.parametrize(("code", "message"), [("X01", "거래코드 마스터에 없는 코드"), ("W06", "폐지된 거래코드")])
def test_md03_hits_unknown_and_inactive_code(code, message):
    result = run([txn(txn_code=code, direction="W")])
    assert hit_rows(result, "MD-03") == [2]
    assert hits(result, "MD-03").loc[0, "message"].startswith(message)


@pytest.mark.parametrize(("code", "direction"), [("D01", "D"), ("W01", "W")])
def test_md03_accepts_active_code(code, direction):
    assert hit_rows(run([txn(txn_code=code, direction=direction)]), "MD-03") == []


@pytest.mark.parametrize(("code", "direction"), [("D01", "W"), ("W01", "D")])
def test_md04_hits_direction_mismatch(code, direction):
    assert hit_rows(run([txn(txn_code=code, direction=direction)]), "MD-04") == [2]


@pytest.mark.parametrize(("code", "direction"), [("D02", "D"), ("W01", "W"), ("X01", "W")])
def test_md04_accepts_matching_direction_or_unknown_code(code, direction):
    # 마스터에 없는 코드는 MD-03만 걸리고 방향은 비교하지 않는다
    assert hit_rows(run([txn(txn_code=code, direction=direction)]), "MD-04") == []


def test_inactive_code_with_wrong_direction_records_both_md_errors():
    result = run([txn(txn_code="W06", direction="D")])
    assert hit_rows(result, "MD-03") == [2]
    assert hit_rows(result, "MD-04") == [2]


def test_md05_warns_on_suspended_withdrawal_and_keeps_row():
    result = run([txn(account_no=SUSPENDED_ACC, txn_code="W01", direction="W"),
                  txn(account_no=SUSPENDED_ACC, txn_code="W01", direction="W", amount="500")])
    assert hit_rows(result, "MD-05") == [2, 3]
    assert set(hits(result, "MD-05")["severity"]) == {"WARN"}
    assert len(result.clean) == 2


@pytest.mark.parametrize(
    "row",
    [
        {"account_no": SUSPENDED_ACC, "txn_code": "D01", "direction": "D"},
        {"account_no": ACC, "txn_code": "W01", "direction": "W"},
    ],
)
def test_md05_ignores_suspended_deposit_and_active_withdrawal(row):
    assert hit_rows(run([txn(**row)]), "MD-05") == []
