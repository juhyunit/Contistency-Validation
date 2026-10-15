"""SM·RC 규칙: 집계표 검증과 거래-집계 대사."""

from __future__ import annotations

import dataclasses

import pytest

from helpers import (
    ACC,
    ACC2,
    CLOSED_TODAY,
    CLOSED_YESTERDAY,
    OPENED_TODAY,
    SUSPENDED_ACC,
    consistent_summary,
    hit_keys,
    hits,
    run,
    summary_row,
    txn,
)
from recon.reconcile import (
    CAUSE_BALANCE,
    CAUSE_EXCLUDED_TXN,
    CAUSE_REVIEW_TXN,
    CAUSE_UNKNOWN,
    RESULT_EXCLUDED,
    RESULT_EXISTENCE,
    RESULT_MATCH,
    RESULT_MISMATCH,
)

TXNS = [
    txn(account_no=ACC, amount="10000"),
    txn(account_no=ACC, txn_code="W01", direction="W", amount="3000", txn_dt="2026-10-15 11:00:00"),
    txn(account_no=ACC2, amount="7000"),
]


def summary_with(account_no: str, **changes) -> list[dict]:
    rows = consistent_summary(TXNS)
    for row in rows:
        if row["account_no"] == account_no:
            row.update({k: str(v) for k, v in changes.items()})
    return rows


def recon_row(result, account_no: str) -> dict:
    return result.recon[result.recon["account_no"] == account_no].iloc[0].to_dict()


def test_consistent_data_has_no_issues_and_all_accounts_match():
    result = run(TXNS)
    assert result.issues.empty
    assert set(result.recon["result"]) == {RESULT_MATCH}
    assert len(result.recon) == 5  # 집계 대상 계좌 전부 (거래 0건 계좌 포함)


# ---------------------------------------------------------------- SM-01


def test_sm01_duplicate_account_rows_recorded_once_and_excluded_from_rc():
    rows = consistent_summary(TXNS)
    rows.append(dict(rows[0]))
    result = run(TXNS, rows)
    assert hit_keys(result, "SM-01") == [ACC]
    assert recon_row(result, ACC)["result"] == RESULT_EXCLUDED
    assert hit_keys(result, "RC-01") == []  # 대사에서 뺀 계좌에 RC-01이 또 나오지 않는다
    assert hit_keys(result, "RC-02") == []


@pytest.mark.parametrize(
    "changes",
    [
        {"base_date": "2026-10-14"},
        {"deposit_count": "-1"},
        {"withdrawal_amount": "abc"},
        {"opening_balance": "1000.5"},
        {"closing_balance": ""},
    ],
)
def test_sm01_hits_wrong_base_date_or_invalid_numbers(changes):
    result = run(TXNS, summary_with(ACC, **changes))
    assert hit_keys(result, "SM-01") == [ACC]
    assert hits(result, "SM-01").loc[0, "column_name"] == next(iter(changes))


def test_sm01_records_all_reasons_in_one_issue():
    result = run(TXNS, summary_with(ACC, base_date="2026-10-14", deposit_count="-1"))
    assert len(hits(result, "SM-01")) == 1
    assert "base_date" in hits(result, "SM-01").loc[0, "message"]
    assert "deposit_count 음수" in hits(result, "SM-01").loc[0, "message"]


def test_sm01_allows_thousand_separators_and_negative_balance():
    rows = summary_with(ACC2, opening_balance="-5000", deposit_amount="7,000", closing_balance="2000")
    assert hit_keys(run(TXNS, rows), "SM-01") == []


def test_sm01_blank_account_no():
    rows = consistent_summary(TXNS) + [summary_row("")]
    assert hit_keys(run(TXNS, rows), "SM-01") == [f"행 {len(rows) + 1}"]


# ---------------------------------------------------------------- RC-01


@pytest.mark.parametrize("account_no", [ACC, OPENED_TODAY])
def test_rc01_hits_target_account_missing_from_summary_with_or_without_txns(account_no):
    rows = [r for r in consistent_summary(TXNS) if r["account_no"] != account_no]
    result = run(TXNS, rows)
    assert hit_keys(result, "RC-01") == [account_no]
    assert hits(result, "RC-01").loc[0, "message"] == "집계 대상 계좌가 집계표에 없음"


@pytest.mark.parametrize(
    ("account_no", "message"),
    [("999-99-999999", "계좌 마스터에 없는"), (CLOSED_YESTERDAY, "기준일에 유효하지 않은")],
)
def test_rc01_hits_summary_row_for_non_target_account(account_no, message):
    rows = consistent_summary(TXNS) + [summary_row(account_no, 5000, (1, 100))]
    result = run(TXNS, rows)
    assert hit_keys(result, "RC-01") == [account_no]
    assert message in hits(result, "RC-01").loc[0, "message"]
    # 존재 불일치 계좌는 RC-02~04를 검사하지 않는다
    assert hit_keys(result, "RC-02") == []


def test_rc01_accepts_zero_transaction_accounts_with_zero_rows():
    result = run(TXNS)
    assert hit_keys(result, "RC-01") == []
    assert recon_row(result, CLOSED_TODAY)["txn_deposit_count"] == 0


# ---------------------------------------------------------------- RC-02, RC-03


@pytest.mark.parametrize("changes", [{"deposit_count": "2"}, {"deposit_amount": "10001", "closing_balance": "1007001"}])
def test_rc02_hits_deposit_count_or_amount_difference(changes):
    result = run(TXNS, summary_with(ACC, **changes))
    assert hit_keys(result, "RC-02") == [ACC]
    assert hit_keys(result, "RC-03") == []


@pytest.mark.parametrize("changes", [{"withdrawal_count": "0"}, {"withdrawal_amount": "3500", "closing_balance": "1006500"}])
def test_rc03_hits_withdrawal_count_or_amount_difference(changes):
    result = run(TXNS, summary_with(ACC, **changes))
    assert hit_keys(result, "RC-03") == [ACC]
    assert hit_keys(result, "RC-02") == []


def test_rc02_rc03_ignore_matching_accounts():
    result = run(TXNS)
    assert hit_keys(result, "RC-02") == [] and hit_keys(result, "RC-03") == []


def test_amount_tolerance_comes_from_config(config):
    rows = summary_with(ACC, deposit_amount="10005", closing_balance="1007005")
    assert hit_keys(run(TXNS, rows), "RC-02") == [ACC]
    loose = dataclasses.replace(config, amount_tolerance=10)
    assert hit_keys(run(TXNS, rows, config=loose), "RC-02") == []


# ---------------------------------------------------------------- RC-04


@pytest.mark.parametrize("closing", ["1007001", "1006999"])
def test_rc04_hits_broken_balance_equation(closing):
    result = run(TXNS, summary_with(ACC, closing_balance=closing))
    assert hit_keys(result, "RC-04") == [ACC]
    assert recon_row(result, ACC)["diff_cause"] == CAUSE_BALANCE


def test_rc04_not_raised_when_only_count_changed():
    result = run(TXNS, summary_with(ACC, deposit_count="5"))
    assert hit_keys(result, "RC-04") == []


def test_rc04_raised_together_when_amount_changed_without_closing():
    result = run(TXNS, summary_with(ACC, deposit_amount="20000"))
    assert hit_keys(result, "RC-02") == [ACC]
    assert hit_keys(result, "RC-04") == [ACC]


# ---------------------------------------------------------------- 차이 원인 표시


def test_diff_cause_marks_excluded_transactions():
    # 집계표는 원래대로인데 거래 하나가 격리되면 "제외 거래 있음"
    txns = [*TXNS, txn(account_no=ACC2, amount="500", txn_code="X01")]
    result = run(txns, consistent_summary(txns))
    row = recon_row(result, ACC2)
    assert row["result"] == RESULT_MISMATCH
    assert row["diff_cause"] == CAUSE_EXCLUDED_TXN


def test_diff_cause_marks_review_transactions():
    # 의심 중복(WARN)은 대사에 포함되므로 차이가 생기면 "검토 거래 있음"
    copy = dict(TXNS[2], txn_id="T-COPY")
    result = run([*TXNS, copy], consistent_summary(TXNS))
    assert recon_row(result, ACC2)["diff_cause"] == CAUSE_REVIEW_TXN


def test_diff_cause_unknown_when_nothing_explains_difference():
    result = run(TXNS, summary_with(ACC2, deposit_count="2"))
    assert recon_row(result, ACC2)["diff_cause"] == CAUSE_UNKNOWN


def test_unidentified_quarantine_is_counted():
    txns = [*TXNS, txn(account_no="12345678901"), txn(account_no="999-99-999999")]
    result = run(txns)
    assert result.stats["unidentified_quarantined_rows"] == 2


def test_suspended_withdrawal_is_included_in_reconciliation():
    txns = [txn(account_no=SUSPENDED_ACC, txn_code="W01", direction="W", amount="100")]
    result = run(txns)
    assert recon_row(result, SUSPENDED_ACC)["result"] == RESULT_MATCH


def test_existence_result_label():
    rows = [r for r in consistent_summary(TXNS) if r["account_no"] != ACC]
    assert recon_row(run(TXNS, rows), ACC)["result"] == RESULT_EXISTENCE
