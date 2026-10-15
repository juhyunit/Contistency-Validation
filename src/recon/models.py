"""입력 파일 정의와 오류 기록 형식."""

from __future__ import annotations

from dataclasses import dataclass

TRANSACTIONS = "transactions"
ACCOUNT_SUMMARY = "account_summary"
ACCOUNT_MASTER = "account_master"
TXN_CODE_MASTER = "txn_code_master"
FILE_TYPES = (TRANSACTIONS, ACCOUNT_SUMMARY, ACCOUNT_MASTER, TXN_CODE_MASTER)

DEFAULT_FILE_NAMES = {
    TRANSACTIONS: "transactions.csv",
    ACCOUNT_SUMMARY: "account_summary.xlsx",
    ACCOUNT_MASTER: "account_master.csv",
    TXN_CODE_MASTER: "txn_code_master.csv",
}
FILE_LABELS = {
    TRANSACTIONS: "거래내역",
    ACCOUNT_SUMMARY: "계좌별 일일 집계",
    ACCOUNT_MASTER: "계좌 마스터",
    TXN_CODE_MASTER: "거래코드 마스터",
}

TXN_COLUMNS = (
    "txn_id",
    "txn_dt",
    "account_no",
    "txn_code",
    "direction",
    "amount",
    "channel",
    "branch_code",
)
TXN_REQUIRED = ("txn_id", "txn_dt", "account_no", "txn_code", "direction", "amount")
SUMMARY_COLUMNS = (
    "base_date",
    "account_no",
    "opening_balance",
    "deposit_count",
    "deposit_amount",
    "withdrawal_count",
    "withdrawal_amount",
    "closing_balance",
)
ACCOUNT_MASTER_COLUMNS = ("account_no", "product_code", "status", "open_date", "close_date")
TXN_CODE_MASTER_COLUMNS = ("txn_code", "txn_name", "direction", "active_yn")

COLUMNS = {
    TRANSACTIONS: TXN_COLUMNS,
    ACCOUNT_SUMMARY: SUMMARY_COLUMNS,
    ACCOUNT_MASTER: ACCOUNT_MASTER_COLUMNS,
    TXN_CODE_MASTER: TXN_CODE_MASTER_COLUMNS,
}
# 없으면 FAILED가 되는 컬럼. 거래내역의 channel, branch_code는 선택 컬럼이라 없으면 빈 값으로 채운다.
REQUIRED_COLUMNS = {
    TRANSACTIONS: TXN_REQUIRED,
    ACCOUNT_SUMMARY: SUMMARY_COLUMNS,
    ACCOUNT_MASTER: ACCOUNT_MASTER_COLUMNS,
    TXN_CODE_MASTER: TXN_CODE_MASTER_COLUMNS,
}

ROW_NO = "row_no"  # 원본 파일의 행번호 (헤더가 1행, 첫 데이터가 2행)

DEPOSIT = "D"
WITHDRAWAL = "W"

ACTIVE = "ACTIVE"
CLOSED = "CLOSED"
SUSPENDED = "SUSPENDED"
ACCOUNT_STATUSES = (ACTIVE, CLOSED, SUSPENDED)

ERROR = "ERROR"
WARN = "WARN"

RUN_PENDING = "PENDING"
RUN_RUNNING = "RUNNING"
RUN_SUCCESS = "SUCCESS"
RUN_FAILED = "FAILED"


@dataclass(frozen=True)
class Issue:
    """오류 1건. DB issues 테이블과 보고서 오류목록 시트의 한 행."""

    rule_id: str
    severity: str
    file_type: str
    row_no: int | None
    record_key: str
    column_name: str
    value: str
    message: str


ISSUE_COLUMNS = (
    "rule_id",
    "severity",
    "file_type",
    "row_no",
    "record_key",
    "column_name",
    "value",
    "message",
)
