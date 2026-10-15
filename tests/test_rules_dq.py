"""DQ 규칙: 규칙마다 걸려야 하는 경우와 걸리면 안 되는 경우를 2개 이상씩."""

from __future__ import annotations

import pytest

from helpers import ACC, ACC2, hit_rows, hits, run, txn


# ---------------------------------------------------------------- DQ-01 필수값 누락


@pytest.mark.parametrize(
    "bad",
    [{"amount": ""}, {"txn_id": "   "}, {"account_no": "　"}, {"txn_dt": ""}, {"direction": ""}, {"txn_code": ""}],
)
def test_dq01_hits_blank_or_whitespace_only_required_value(bad):
    result = run([txn(), txn(**bad)])
    assert hit_rows(result, "DQ-01") == [3]
    assert hits(result, "DQ-01").loc[0, "column_name"] == next(iter(bad))


@pytest.mark.parametrize("ok", [{}, {"channel": "", "branch_code": ""}, {"amount": " 5000 "}])
def test_dq01_ignores_complete_rows_and_blank_optional_columns(ok):
    assert hit_rows(run([txn(**ok)]), "DQ-01") == []


def test_dq01_blank_value_is_not_double_reported_as_format_error():
    result = run([txn(amount="", account_no="", txn_dt="")])
    assert len(hits(result, "DQ-01")) == 3
    assert result.issues["rule_id"].tolist().count("DQ-04") == 0
    assert result.issues["rule_id"].tolist().count("DQ-02") == 0


# ---------------------------------------------------------------- DQ-02 계좌번호 형식


@pytest.mark.parametrize(
    "account_no",
    [
        "12345678901",  # 하이픈 없음
        "1234567890",  # 엑셀이 숫자로 바꿔 앞자리 0이 사라진 값
        "123-45-67890",  # 자릿수 부족
        "12-345-678901",  # 하이픈 위치
        "１２３-45-678901",  # 전각 숫자
        "123-45-678901-1",
    ],
)
def test_dq02_hits_malformed_account_numbers(account_no):
    assert hit_rows(run([txn(account_no=account_no)]), "DQ-02") == [2]


@pytest.mark.parametrize("account_no", [ACC, ACC2, " 111-11-111111 "])
def test_dq02_accepts_well_formed_numbers_including_leading_zero(account_no):
    assert hit_rows(run([txn(account_no=account_no)]), "DQ-02") == []


# ---------------------------------------------------------------- DQ-03 거래일시


@pytest.mark.parametrize(
    "txn_dt",
    ["2026-10-14 23:59:59", "2026-10-16 00:00:00", "2026/10/15 10:00:00", "2026-10-15 9:00:00", "2026-10-15", "어제"],
)
def test_dq03_hits_unparsable_or_other_day(txn_dt):
    assert hit_rows(run([txn(txn_dt=txn_dt)]), "DQ-03") == [2]


@pytest.mark.parametrize("txn_dt", ["2026-10-15 00:00:00", "2026-10-15 23:59:59", "2026-10-15 12:34:56"])
def test_dq03_accepts_base_date_boundaries(txn_dt):
    assert hit_rows(run([txn(txn_dt=txn_dt)]), "DQ-03") == []


# ---------------------------------------------------------------- DQ-04 금액


@pytest.mark.parametrize("amount", ["0", "-1000", "-1", "1000.5", "3.0", "１０００", "1,00", "1만원"])
def test_dq04_hits_non_integer_or_non_positive(amount):
    assert hit_rows(run([txn(amount=amount)]), "DQ-04") == [2]


@pytest.mark.parametrize("amount", ["1", "1,000", "1500000000", "1,500,000,000"])
def test_dq04_accepts_positive_integers_and_thousand_separators(amount):
    assert hit_rows(run([txn(amount=amount)]), "DQ-04") == []


# ---------------------------------------------------------------- DQ-05 입출금 구분


@pytest.mark.parametrize("direction", ["X", "d", "입금", "DW"])
def test_dq05_hits_unknown_direction(direction):
    assert hit_rows(run([txn(direction=direction)]), "DQ-05") == [2]


@pytest.mark.parametrize("direction", ["D", "W"])
def test_dq05_accepts_d_and_w(direction):
    code = "D01" if direction == "D" else "W01"
    assert hit_rows(run([txn(direction=direction, txn_code=code)]), "DQ-05") == []


# ---------------------------------------------------------------- DQ-06 거래번호 중복


def test_dq06_identical_rows_keep_first_and_quarantine_rest():
    row = txn()
    result = run([row, txn(), dict(row), dict(row)])
    assert hit_rows(result, "DQ-06") == [4, 5]
    assert 2 in set(result.clean["row_no"])


def test_dq06_different_content_quarantines_all():
    row = txn()
    result = run([row, txn(), dict(row, amount="20000")])
    assert hit_rows(result, "DQ-06") == [2, 4]
    assert set(result.quarantine["row_no"]) == {2, 4}


def test_dq06_ignores_unique_ids():
    assert hit_rows(run([txn(), txn(), txn()]), "DQ-06") == []


def test_dq06_ignores_blank_ids():
    # 빈 txn_id는 DQ-01만 걸리고 서로 중복으로 묶지 않는다
    result = run([txn(txn_id=""), txn(txn_id="")])
    assert hit_rows(result, "DQ-06") == []
    assert hit_rows(result, "DQ-01") == [2, 3]


# ---------------------------------------------------------------- DQ-07 의심 중복


def test_dq07_flags_later_row_as_warn_and_keeps_both():
    first = txn()
    result = run([first, txn(), dict(first, txn_id="T-COPY")])
    assert hit_rows(result, "DQ-07") == [4]
    assert hits(result, "DQ-07").loc[0, "severity"] == "WARN"
    assert {2, 4} <= set(result.clean["row_no"])  # 둘 다 대사에 포함


def test_dq07_treats_thousand_separator_as_same_amount():
    first = txn(amount="10000")
    assert hit_rows(run([first, dict(first, txn_id="T-COPY", amount="10,000")]), "DQ-07") == [3]


@pytest.mark.parametrize("change", [{"amount": "10001"}, {"txn_dt": "2026-10-15 10:00:01"}, {"account_no": ACC2}])
def test_dq07_ignores_rows_that_differ(change):
    first = txn()
    assert hit_rows(run([first, dict(first, txn_id="T-OTHER", **change)]), "DQ-07") == []


def test_dq07_ignores_rows_already_in_error():
    # 같은 txn_id 복제(DQ-06 ERROR)는 의심 중복으로 다시 올리지 않는다
    first = txn()
    assert hit_rows(run([first, dict(first)]), "DQ-07") == []


# ---------------------------------------------------------------- 단계 처리


def test_all_errors_in_one_row_are_recorded_within_stage():
    result = run([txn(account_no="123", amount="0", direction="X")])
    assert sorted(hits(result, r).loc[0, "rule_id"] for r in ("DQ-02", "DQ-04", "DQ-05")) == ["DQ-02", "DQ-04", "DQ-05"]
    assert len(result.quarantine) == 1
    assert result.quarantine.loc[0, "error_rules"] == "DQ-02, DQ-04, DQ-05"


def test_dq_error_rows_skip_md_checks():
    # 깨진 계좌번호는 MD-01(미등록 계좌)을 중복으로 일으키지 않는다
    result = run([txn(account_no="12345678901", txn_code="X99")])
    assert hit_rows(result, "DQ-02") == [2]
    assert hit_rows(result, "MD-01") == []
    assert hit_rows(result, "MD-03") == []
