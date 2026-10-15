"""화면을 돕는 모듈: 파일 종류 판별, 결과 판정·확인 목록, 쉬운 설명 사전."""

from __future__ import annotations

import io

import openpyxl
import pandas as pd

from recon.detect import classify, detect_file_type
from recon.glossary import FILE_GUIDES, RULE_GUIDES
from recon.insights import checklist, verdict
from recon.models import ACCOUNT_MASTER, ACCOUNT_SUMMARY, COLUMNS, FILE_TYPES, TRANSACTIONS, TXN_CODE_MASTER
from recon.pipeline import run_pipeline
from recon.rules.registry import rule_ids

TXN_HEADER = b"txn_id,txn_dt,account_no,txn_code,direction,amount,channel,branch_code\nT1,2026-10-15 10:00:00,1,D01,D,1,,\n"


def xlsx(header) -> bytes:
    workbook = openpyxl.Workbook()
    workbook.active.append(list(header))
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


# ---------------------------------------------------------------- 파일 종류 판별


def test_detects_by_columns_even_with_other_names():
    assert detect_file_type("거래내역_1015.csv", TXN_HEADER) == TRANSACTIONS
    assert detect_file_type("집계.xlsx", xlsx(COLUMNS[ACCOUNT_SUMMARY])) == ACCOUNT_SUMMARY
    assert detect_file_type("계좌.csv", "account_no,product_code,status,open_date,close_date\n".encode("cp949")) == ACCOUNT_MASTER
    assert detect_file_type("코드.csv", "﻿txn_code,txn_name,direction,active_yn\nD01,현금입금,D,Y\n".encode("utf-8")) == TXN_CODE_MASTER


def test_falls_back_to_standard_file_name():
    assert detect_file_type("transactions_20261015.csv", b"broken,header\n") == TRANSACTIONS
    assert detect_file_type("account_summary.xlsx", b"not an excel file") == ACCOUNT_SUMMARY


def test_unknown_files_are_reported():
    assert detect_file_type("memo.csv", b"a,b,c\n1,2,3\n") is None
    assert detect_file_type("image.png", b"\x89PNG") is None


def test_classify_collects_missing_unknown_and_duplicates():
    result = classify([
        ("a.csv", TXN_HEADER),
        ("b.csv", TXN_HEADER),
        ("memo.csv", b"x,y\n"),
        ("account_master.csv", b"account_no,product_code,status,open_date,close_date\n"),
    ])
    assert result.files[TRANSACTIONS][0] == "b.csv"  # 같은 종류가 여러 개면 마지막 파일
    assert result.duplicates == {TRANSACTIONS: ["a.csv", "b.csv"]}
    assert result.unknown == ["memo.csv"]
    assert result.missing == [ACCOUNT_SUMMARY, TXN_CODE_MASTER]


def test_sample_files_are_all_detected(datasets):
    _, injected = datasets
    result = classify(list(injected.files().values()))
    assert result.missing == [] and result.unknown == []


# ---------------------------------------------------------------- 판정과 확인 목록


def test_verdict_levels():
    assert verdict("FAILED", {}, "입력 파일 누락").level == "critical"
    clean = verdict("SUCCESS", {"error_issues": 0, "review_rows": 0, "total_rows": 10, "accounts_matched": 3})
    assert clean.level == "good" and clean.badge == "이상 없음"
    review = verdict("SUCCESS", {"error_issues": 0, "review_rows": 2})
    assert review.level == "warning"
    bad = verdict("SUCCESS", {"error_issues": 5, "quarantined_rows": 4, "accounts_mismatched": 2,
                              "accounts_existence_mismatch": 1, "accounts_excluded": 0})
    assert bad.headline == "거래 4건을 격리했고, 계좌 3개에서 차이가 났어요"


def test_checklist_orders_by_urgency(datasets, workspace):
    _, injected = datasets
    result = run_pipeline(injected.files(), injected.base_date, repository=workspace["repo"], data_dir=workspace["data_dir"])
    items = checklist(result.validation.stats, result.validation.issues, result.validation.recon)
    keys = [item.key for item in items]
    assert keys == ["unknown_diff", "summary_errors", "quarantined", "review", "explained_diff", "unidentified"]
    summary = next(i for i in items if i.key == "summary_errors")
    assert dict(summary.breakdown) == {"형식·중복": 2, "계좌 누락·초과": 3, "잔액 계산": 7}
    assert next(i for i in items if i.key == "quarantined").count == result.validation.stats["quarantined_rows"]
    # 계좌번호가 깨진 격리 거래가 있으면 '설명되지 않는 차이'의 가능한 원인으로 함께 안내한다
    assert "어느 계좌인지 모르는 격리 거래" in items[0].description


def test_checklist_is_empty_for_clean_data(datasets, workspace):
    clean, _ = datasets
    result = run_pipeline(clean.files(), clean.base_date, repository=workspace["repo"], data_dir=workspace["data_dir"])
    assert checklist(result.validation.stats, result.validation.issues, result.validation.recon) == []
    assert verdict("SUCCESS", result.validation.stats).level == "good"


def test_checklist_handles_empty_frames():
    empty_issues = pd.DataFrame(columns=["rule_id", "severity", "file_type", "row_no", "record_key",
                                         "column_name", "value", "message"])
    empty_recon = pd.DataFrame(columns=["diff_cause"])
    assert checklist({"quarantined_rows": 0, "review_rows": 0}, empty_issues, empty_recon) == []


# ---------------------------------------------------------------- 설명 사전


def test_every_rule_and_file_has_a_plain_language_guide():
    assert sorted(RULE_GUIDES) == sorted(rule_ids())
    for guide in RULE_GUIDES.values():
        assert guide.title and guide.what.endswith("요.") and guide.action
    for file_type in FILE_TYPES:
        assert [c.name for c in FILE_GUIDES[file_type].columns] == list(COLUMNS[file_type])
