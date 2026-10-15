from __future__ import annotations

import io
from datetime import datetime

import openpyxl
import pytest

from recon.loader import LoadError, load_inputs
from recon.models import ACCOUNT_MASTER, ACCOUNT_SUMMARY, ROW_NO, TRANSACTIONS, TXN_CODE_MASTER

TXN_CSV = (
    "txn_id,txn_dt,account_no,txn_code,direction,amount,channel,branch_code\n"
    "T1,2026-10-15 10:00:00,012-34-567890,D01,D,\"1,000\",ATM,\n"
    "\n"
    "T2 , 2026-10-15 11:00:00 ,012-34-567890,W01,W,500,,\n"
)
MASTER_CSV = (
    "account_no,product_code,status,open_date,close_date\n"
    "012-34-567890,P01,ACTIVE,2020-01-01,\n"
)
CODE_CSV = "txn_code,txn_name,direction,active_yn\nD01,현금입금,D,Y\nW01,현금출금,W,Y\n"


def summary_xlsx(rows=None, header=None) -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(header or ["base_date", "account_no", "opening_balance", "deposit_count", "deposit_amount",
                            "withdrawal_count", "withdrawal_amount", "closing_balance"])
    for row in rows if rows is not None else [[datetime(2026, 10, 15), "012-34-567890", 1000.0, 1, 1000, 1, 500, 1500]]:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def files(**overrides):
    base = {
        TRANSACTIONS: ("transactions.csv", TXN_CSV.encode("utf-8")),
        ACCOUNT_SUMMARY: ("account_summary.xlsx", summary_xlsx()),
        ACCOUNT_MASTER: ("account_master.csv", MASTER_CSV.encode("utf-8")),
        TXN_CODE_MASTER: ("txn_code_master.csv", CODE_CSV.encode("utf-8")),
    }
    base.update(overrides)
    return base


def test_reads_all_values_as_trimmed_strings_with_file_row_numbers(config):
    loaded = load_inputs(files(), config)
    frame = loaded[TRANSACTIONS].frame
    # 빈 줄(3행)은 건너뛰지만 행번호는 파일상의 위치를 유지한다.
    assert list(frame[ROW_NO]) == [2, 4]
    assert list(frame["account_no"]) == ["012-34-567890", "012-34-567890"]  # 앞자리 0 유지
    assert frame.loc[1, "txn_id"] == "T2"  # 앞뒤 공백 제거
    assert frame.loc[1, "txn_dt"] == "2026-10-15 11:00:00"
    assert frame.loc[0, "amount"] == "1,000"  # 숫자 변환은 검증 단계에서
    assert loaded[TRANSACTIONS].encoding == "utf-8"
    assert loaded[TRANSACTIONS].row_count == 2


def test_cp949_file_is_read_and_encoding_recorded(config):
    loaded = load_inputs(files(**{TXN_CODE_MASTER: ("txn_code_master.csv", CODE_CSV.encode("cp949"))}), config)
    assert loaded[TXN_CODE_MASTER].encoding == "cp949"
    assert loaded[TXN_CODE_MASTER].frame.loc[0, "txn_name"] == "현금입금"


def test_xlsx_cells_are_normalized_to_strings(config):
    summary = load_inputs(files(), config)[ACCOUNT_SUMMARY].frame
    row = summary.iloc[0]
    assert row["base_date"] == "2026-10-15"  # 날짜 셀
    assert row["opening_balance"] == "1000"  # 1000.0 → 1000
    assert row["deposit_amount"] == "1000"
    assert row[ROW_NO] == 2


def test_missing_optional_columns_are_filled_with_blank(config):
    csv_text = "txn_id,txn_dt,account_no,txn_code,direction,amount\nT1,2026-10-15 10:00:00,012-34-567890,D01,D,100\n"
    loaded = load_inputs(files(**{TRANSACTIONS: ("transactions.csv", csv_text.encode())}), config)
    assert loaded[TRANSACTIONS].frame.loc[0, "channel"] == ""


def test_hash_and_archive(config, tmp_path):
    loaded = load_inputs(files(), config, archive_dir=tmp_path)
    archived = loaded[TRANSACTIONS].archive_path
    assert archived.read_bytes() == TXN_CSV.encode("utf-8")
    assert archived.name.startswith(loaded[TRANSACTIONS].sha256[:16])


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({TRANSACTIONS: None}, "입력 파일 누락: 거래내역"),
        ({TRANSACTIONS: ("transactions.csv", b"")}, "빈 파일"),
        ({TRANSACTIONS: ("transactions.csv", b"txn_id,txn_dt,account_no,txn_code,direction,amount\n")}, "데이터 행이 없습니다"),
        ({TRANSACTIONS: ("transactions.csv", TXN_CSV.replace("txn_dt", "txn_date").encode())}, "필수 컬럼 누락 txn_dt"),
        ({TRANSACTIONS: ("transactions.csv",
                         b"txn_id,txn_dt,account_no,txn_code,direction\nT1,2026-10-15 10:00:00,012-34-567890,D01,D\n")},
         "필수 컬럼 누락 amount"),
        # 쉼표가 든 금액을 따옴표 없이 저장하면 컬럼이 밀린다
        ({TRANSACTIONS: ("transactions.csv", TXN_CSV.replace("\"1,000\"", "1,000").encode())}, "컬럼 수가 헤더와 다른 행"),
        ({TRANSACTIONS: ("transactions.txt", TXN_CSV.encode())}, "지원하지 않는 형식"),
        ({ACCOUNT_SUMMARY: ("account_summary.xlsx", b"not an excel file")}, "엑셀 파일을 열 수 없습니다"),
        ({ACCOUNT_SUMMARY: ("account_summary.xlsx", summary_xlsx(rows=[]))}, "데이터 행이 없습니다"),
        ({TXN_CODE_MASTER: ("txn_code_master.csv", "txn_code,txn_name,direction,active_yn\nD01,a,D,Y\nD01,b,D,Y\n".encode())},
         "txn_code 중복"),
        ({ACCOUNT_MASTER: ("account_master.csv",
                           (MASTER_CSV + "999-99-999999,P01,CLOSED,2020-01-01,\n").encode())}, "close_date 없음"),
        ({ACCOUNT_MASTER: ("account_master.csv", (MASTER_CSV + "999-99-999999,P01,DORMANT,2020-01-01,\n").encode())},
         "status 값 오류"),
    ],
)
def test_unusable_inputs_raise_load_error(config, overrides, message):
    with pytest.raises(LoadError, match=message):
        load_inputs(files(**overrides), config)


def test_undecodable_bytes(config):
    with pytest.raises(LoadError, match="인코딩"):
        load_inputs(files(**{TRANSACTIONS: ("transactions.csv", b"\xff\xfe\xfa\xfb\x80")}), config)
