from __future__ import annotations

import pandas as pd

from recon.evaluation import evaluate
from recon.models import ISSUE_COLUMNS
from recon.synthetic import ANSWER_COLUMNS

ACC = "111-11-111111"
ACC2 = "222-22-222222"


def issues(*rows) -> pd.DataFrame:
    frame = pd.DataFrame([dict(zip(ISSUE_COLUMNS, r)) for r in rows], columns=list(ISSUE_COLUMNS))
    frame["row_no"] = frame["row_no"].astype("Int64")
    return frame


def answer(*rows) -> pd.DataFrame:
    return pd.DataFrame([dict(zip(ANSWER_COLUMNS, r)) for r in rows], columns=list(ANSWER_COLUMNS))


def issue(rule, file_type, row_no, key):
    return (rule, "ERROR", file_type, row_no, key, "", "", "")


def test_matches_transactions_by_row_and_summary_by_account():
    ev = evaluate(
        issues(issue("DQ-01", "transactions", 5, "행 5"), issue("RC-02", "account_summary", 9, ACC)),
        answer(
            ("E001", "DQ-01", "transactions.csv", "5", "행 5", ACC2, "txn_id 삭제"),
            ("E002", "RC-02", "account_summary.xlsx", "9", ACC, ACC, "deposit_count +1"),
        ),
    )
    assert ev.passed
    assert ev.detected == 2


def test_error_with_two_rows_needs_both_detected():
    ev = evaluate(
        issues(issue("DQ-06", "transactions", 10, "T1")),
        answer(
            ("E001", "DQ-06", "transactions.csv", "10", "T1", ACC, ""),
            ("E001", "DQ-06", "transactions.csv", "11", "T1", ACC, ""),
        ),
    )
    assert ev.recall == 0.0
    assert len(ev.missed) == 1


def test_cascades_are_not_false_positives():
    ev = evaluate(
        issues(
            issue("DQ-02", "transactions", 3, "T3"),
            issue("RC-02", "account_summary", 4, ACC),  # 거래 오류가 만든 원래 계좌의 차이
            issue("RC-02", "account_summary", 5, ACC2),
            issue("RC-04", "account_summary", 5, ACC2),  # 금액 변조가 만든 잔액 등식 불일치
        ),
        answer(
            ("E001", "DQ-02", "transactions.csv", "3", "T3", ACC, "하이픈 제거"),
            ("E002", "RC-02", "account_summary.xlsx", "5", ACC2, ACC2, "deposit_amount +1000"),
        ),
    )
    assert ev.passed
    assert len(ev.cascades) == 2


def test_rc04_after_count_only_change_is_false_positive():
    ev = evaluate(
        issues(issue("RC-02", "account_summary", 5, ACC2), issue("RC-04", "account_summary", 5, ACC2)),
        answer(("E001", "RC-02", "account_summary.xlsx", "5", ACC2, ACC2, "deposit_count +1")),
    )
    assert not ev.passed
    assert list(ev.false_positives["rule_id"]) == ["RC-04"]


def test_unexplained_detection_is_false_positive():
    ev = evaluate(issues(issue("MD-01", "transactions", 7, "T7")), answer())
    assert list(ev.false_positives["rule_id"]) == ["MD-01"]
