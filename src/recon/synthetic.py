"""합성 데이터 생성과 오류 주입 (설계서 8장). 시드가 같으면 같은 데이터가 나온다.

1. 깨끗한 데이터를 만든다 (이 상태에서 검증하면 오류 0건이어야 한다).
2. 정해진 오류를 정해진 개수만큼 심고, 심은 위치를 정답 파일(injected_errors.csv)에 기록한다.
"""

from __future__ import annotations

import copy
import csv
import io
import random
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import openpyxl

from recon.models import (
    ACCOUNT_MASTER,
    ACCOUNT_MASTER_COLUMNS,
    ACCOUNT_SUMMARY,
    ACTIVE,
    CLOSED,
    DEFAULT_FILE_NAMES,
    DEPOSIT,
    SUMMARY_COLUMNS,
    SUSPENDED,
    TRANSACTIONS,
    TXN_CODE_MASTER,
    TXN_CODE_MASTER_COLUMNS,
    TXN_COLUMNS,
    WITHDRAWAL,
)
from recon.values import parse_int

DEFAULT_SEED = 42
DEFAULT_BASE_DATE = date(2026, 10, 15)
TARGET_TXN_COUNT = 5000
ANSWER_FILE_NAME = "injected_errors.csv"
ANSWER_COLUMNS = ("error_id", "expected_rule", "file", "row_no", "record_key", "original_account_no", "detail")

# 설계서 8장 오류 주입 표: 규칙별 주입 오류 수 (DQ-06은 내용 동일 6 + 내용 상이 2)
INJECTION_PLAN = {
    "DQ-01": 10,
    "DQ-02": 8,
    "DQ-03": 5,
    "DQ-04": 8,
    "DQ-05": 3,
    "DQ-06": 8,
    "DQ-07": 4,
    "MD-01": 5,
    "MD-02": 4,
    "MD-03": 5,
    "MD-04": 4,
    "MD-05": 3,
    "SM-01": 2,
    "RC-01": 3,
    "RC-02": 3,
    "RC-03": 3,
    "RC-04": 3,
}

# 입금 6개, 출금 6개 (W06은 폐지 코드)
TXN_CODES = (
    ("D01", "현금입금", DEPOSIT, "Y"),
    ("D02", "계좌이체입금", DEPOSIT, "Y"),
    ("D03", "급여입금", DEPOSIT, "Y"),
    ("D04", "타행이체입금", DEPOSIT, "Y"),
    ("D05", "이자입금", DEPOSIT, "Y"),
    ("D06", "수표입금", DEPOSIT, "Y"),
    ("W01", "현금출금", WITHDRAWAL, "Y"),
    ("W02", "계좌이체출금", WITHDRAWAL, "Y"),
    ("W03", "카드대금출금", WITHDRAWAL, "Y"),
    ("W04", "타행이체출금", WITHDRAWAL, "Y"),
    ("W05", "공과금출금", WITHDRAWAL, "Y"),
    ("W06", "자동이체출금(폐지)", WITHDRAWAL, "N"),
)
INACTIVE_CODE = "W06"
CHANNELS = ("BRANCH", "ATM", "MOBILE", "INTERNET", "")
PRODUCTS = ("P01", "P02", "P03")
ZERO_TXN_ACCOUNT_COUNT = 4  # 설계서: 최소 3개


@dataclass
class Account:
    account_no: str
    product_code: str
    status: str
    open_date: date
    close_date: date | None = None

    def valid_on(self, day: date) -> bool:
        return self.open_date <= day and (self.close_date is None or self.close_date >= day)


@dataclass
class Dataset:
    base_date: date
    accounts: list[Account]
    transactions: list[dict]
    summary: list[dict]
    answer: list[dict] | None = None
    codes: tuple = TXN_CODES

    def files(self) -> dict[str, tuple[str, bytes]]:
        """파이프라인 입력 형식 {파일 종류: (파일명, 내용)}."""
        master_rows = [
            {
                "account_no": a.account_no,
                "product_code": a.product_code,
                "status": a.status,
                "open_date": a.open_date.isoformat(),
                "close_date": a.close_date.isoformat() if a.close_date else "",
            }
            for a in sorted(self.accounts, key=lambda a: a.account_no)
        ]
        code_rows = [dict(zip(TXN_CODE_MASTER_COLUMNS, code)) for code in self.codes]
        return {
            TRANSACTIONS: (DEFAULT_FILE_NAMES[TRANSACTIONS], _csv_bytes(TXN_COLUMNS, self.transactions, "utf-8-sig")),
            ACCOUNT_SUMMARY: (DEFAULT_FILE_NAMES[ACCOUNT_SUMMARY], _xlsx_bytes(SUMMARY_COLUMNS, self.summary)),
            ACCOUNT_MASTER: (DEFAULT_FILE_NAMES[ACCOUNT_MASTER], _csv_bytes(ACCOUNT_MASTER_COLUMNS, master_rows, "utf-8-sig")),
            # 실무처럼 한글이 든 마스터 하나는 CP949로 만들어 인코딩 처리를 함께 검증한다.
            TXN_CODE_MASTER: (DEFAULT_FILE_NAMES[TXN_CODE_MASTER], _csv_bytes(TXN_CODE_MASTER_COLUMNS, code_rows, "cp949")),
        }

    def answer_csv(self) -> bytes:
        if self.answer is None:
            raise ValueError("오류를 주입하지 않은 데이터에는 정답 파일이 없습니다")
        return _csv_bytes(ANSWER_COLUMNS, self.answer, "utf-8-sig")

    def write(self, out_dir: Path) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        for name, content in self.files().values():
            (out_dir / name).write_bytes(content)
        if self.answer is not None:
            (out_dir / ANSWER_FILE_NAME).write_bytes(self.answer_csv())


def _csv_bytes(columns, rows, encoding: str) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow(["" if row[c] is None else row[c] for c in columns])
    return buffer.getvalue().encode(encoding)


def _xlsx_bytes(columns, rows) -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "account_summary"
    sheet.append(list(columns))
    for row in rows:
        sheet.append([row[c] for c in columns])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def generate_datasets(seed: int = DEFAULT_SEED, base_date: date = DEFAULT_BASE_DATE) -> tuple[Dataset, Dataset]:
    """(깨끗한 데이터, 오류 주입 데이터)."""
    clean = generate_clean(seed, base_date)
    return clean, inject_errors(clean, seed)


# ---------------------------------------------------------------- 깨끗한 데이터


def _new_account_no(rng: random.Random, used: set[str]) -> str:
    while True:
        number = f"{rng.randrange(1000):03d}-{rng.randrange(100):02d}-{rng.randrange(1_000_000):06d}"
        if number not in used:
            used.add(number)
            return number


def _make_accounts(rng: random.Random, base: date, used: set[str]) -> list[Account]:
    def past(lo: int, hi: int) -> date:
        return base - timedelta(days=rng.randint(lo, hi))

    def account(status: str, open_date: date, close_date: date | None = None) -> Account:
        return Account(_new_account_no(rng, used), rng.choice(PRODUCTS), status, open_date, close_date)

    accounts = [account(ACTIVE, past(1, 3650)) for _ in range(180)]
    accounts += [account(ACTIVE, base) for _ in range(3)]  # 기준일 개설 (당일 거래는 정상)
    accounts += [account(ACTIVE, base + timedelta(days=rng.randint(1, 10))) for _ in range(2)]  # 기준일 이후 개설
    for _ in range(6):  # 기준일 이전 해지
        close = past(1, 365)
        accounts.append(account(CLOSED, close - timedelta(days=rng.randint(30, 3000)), close))
    accounts += [account(CLOSED, past(30, 3000), base) for _ in range(2)]  # 기준일 해지 (당일 거래는 정상)
    accounts += [account(CLOSED, past(30, 3000), base + timedelta(days=rng.randint(1, 30))) for _ in range(2)]
    accounts += [account(SUSPENDED, past(30, 3000)) for _ in range(5)]
    return accounts  # ACTIVE 185, CLOSED 10, SUSPENDED 5


def _draw_amount(rng: random.Random) -> int:
    r = rng.random()
    if r < 0.6:
        return rng.randint(1, 500) * 1000
    if r < 0.9:
        return rng.randint(1, 5_000_000)
    return rng.randint(5_000, 50_000) * 1000


def _summary_rows(base: date, targets: list[Account], opening: dict[str, int], txns: list[dict]) -> list[dict]:
    totals: dict[str, list[int]] = {a.account_no: [0, 0, 0, 0] for a in targets}
    for t in txns:
        amount = parse_int(t["amount"])
        bucket = totals[t["account_no"]]
        if t["direction"] == DEPOSIT:
            bucket[0] += 1
            bucket[1] += amount
        else:
            bucket[2] += 1
            bucket[3] += amount
    rows = []
    for a in sorted(targets, key=lambda a: a.account_no):
        dep_count, dep_amount, wd_count, wd_amount = totals[a.account_no]
        rows.append(
            {
                "base_date": base.isoformat(),
                "account_no": a.account_no,
                "opening_balance": opening[a.account_no],
                "deposit_count": dep_count,
                "deposit_amount": dep_amount,
                "withdrawal_count": wd_count,
                "withdrawal_amount": wd_amount,
                "closing_balance": opening[a.account_no] + dep_amount - wd_amount,
            }
        )
    return rows


def generate_clean(seed: int = DEFAULT_SEED, base_date: date = DEFAULT_BASE_DATE) -> Dataset:
    rng = random.Random(seed)
    accounts = _make_accounts(rng, base_date, set())
    targets = [a for a in accounts if a.valid_on(base_date)]
    normal_active = [a for a in targets if a.status == ACTIVE and a.open_date < base_date]
    zero_txn = {a.account_no for a in rng.sample(normal_active, ZERO_TXN_ACCOUNT_COUNT)}
    eligible = [a for a in targets if a.account_no not in zero_txn]
    opening = {a.account_no: rng.randrange(0, 5_000_001) * 10 for a in targets}
    per_account = Counter(rng.choices(range(len(eligible)), k=TARGET_TXN_COUNT))
    deposit_codes = [c[0] for c in TXN_CODES if c[2] == DEPOSIT and c[3] == "Y"]
    withdrawal_codes = [c[0] for c in TXN_CODES if c[2] == WITHDRAWAL and c[3] == "Y"]

    raw: list[tuple[int, str, dict]] = []
    for idx, acc in enumerate(eligible):
        count = per_account.get(idx, 0)
        if count == 0:
            continue
        seconds = set(rng.sample(range(86400), count))  # 계좌 안에서 시각이 겹치지 않아 의심 중복이 생기지 않음
        if idx == 0:
            seconds |= {0, 86399}  # 경계값: 00:00:00, 23:59:59 거래
        balance = opening[acc.account_no]
        for k, second in enumerate(sorted(seconds)):
            if acc.status == SUSPENDED or balance < 10_000:
                direction = DEPOSIT  # 지급정지 계좌는 입금만, 잔액이 적으면 입금
            else:
                direction = DEPOSIT if rng.random() < 0.5 else WITHDRAWAL
            amount = _draw_amount(rng)
            if idx == 1 and k == 0:
                direction, amount = DEPOSIT, 1_500_000_000  # 경계값: 10억 이상 금액
            if direction == WITHDRAWAL:
                amount = min(amount, balance)  # 출금은 잔액을 넘지 않는다
            balance += amount if direction == DEPOSIT else -amount
            channel = rng.choice(CHANNELS)
            raw.append(
                (
                    second,
                    acc.account_no,
                    {
                        "txn_dt": f"{base_date.isoformat()} {second // 3600:02d}:{second // 60 % 60:02d}:{second % 60:02d}",
                        "account_no": acc.account_no,
                        "txn_code": rng.choice(deposit_codes if direction == DEPOSIT else withdrawal_codes),
                        "direction": direction,
                        # 일부 금액은 천 단위 쉼표 형식 (DQ-04 정상 케이스)
                        "amount": f"{amount:,}" if rng.random() < 0.05 else str(amount),
                        "channel": channel,
                        "branch_code": f"{rng.randrange(1, 10000):04d}" if channel == "BRANCH" else "",
                    },
                )
            )
    raw.sort(key=lambda item: (item[0], item[1]))
    ymd = base_date.strftime("%Y%m%d")
    txns = [{"txn_id": f"T{ymd}{seq:06d}", **row} for seq, (_, _, row) in enumerate(raw, start=1)]
    txns = [{c: t[c] for c in TXN_COLUMNS} for t in txns]
    return Dataset(base_date, accounts, txns, _summary_rows(base_date, targets, opening, txns))


# ---------------------------------------------------------------- 오류 주입


@dataclass
class _Injector:
    rng: random.Random
    dataset: Dataset
    answers: list[dict] = field(default_factory=list)
    insertions: list[tuple[dict | None, dict]] = field(default_factory=list)  # (원본 행, 새 행)
    _next_id: int = 1

    def error_id(self) -> str:
        value = f"E{self._next_id:03d}"
        self._next_id += 1
        return value

    def txn_answer(self, rule: str, rows: list[dict], original_account: str, detail: str) -> None:
        error_id = self.error_id()
        for row in rows:
            self.answers.append(
                {"error_id": error_id, "expected_rule": rule, "file": DEFAULT_FILE_NAMES[TRANSACTIONS],
                 "_row": row, "original_account_no": original_account, "detail": detail}
            )

    def summary_answer(self, rule: str, account_no: str, detail: str) -> None:
        self.answers.append(
            {"error_id": self.error_id(), "expected_rule": rule, "file": DEFAULT_FILE_NAMES[ACCOUNT_SUMMARY],
             "_account": account_no, "original_account_no": account_no, "detail": detail}
        )


def inject_errors(clean: Dataset, seed: int = DEFAULT_SEED) -> Dataset:
    rng = random.Random(seed * 7919 + 1)
    ds = copy.deepcopy(clean)
    base = ds.base_date
    inj = _Injector(rng, ds)
    by_no = {a.account_no: a for a in ds.accounts}
    used_numbers = set(by_no)
    txn_count = Counter(t["account_no"] for t in ds.transactions)

    # --- 집계표 오류: 어느 계좌가 바뀌었는지 분명하도록 거래 오류와 겹치지 않는 계좌를 쓴다.
    summary = {r["account_no"]: r for r in ds.summary}
    candidates = sorted(a for a in summary if txn_count[a] > 0 and by_no[a].status != SUSPENDED)
    picked = rng.sample(candidates, 12)
    duplicate_accounts, deleted_account = picked[0:2], picked[2]
    deposit_accounts, withdrawal_accounts, balance_accounts = picked[3:6], picked[6:9], picked[9:12]
    zero_account = rng.choice(sorted(a for a in summary if txn_count[a] == 0))
    touched = set(picked) | {zero_account}

    for i, account_no in enumerate(deposit_accounts):
        row = summary[account_no]
        if i == 0:  # 건수만 바꾼 경우: 잔액 등식(RC-04)은 깨지지 않아야 한다
            row["deposit_count"] += 1
            inj.summary_answer("RC-02", account_no, "deposit_count +1")
        else:  # 금액을 바꾼 경우: RC-04가 연쇄로 함께 나온다
            delta = rng.choice((1_000, 50_000, 123_456))
            row["deposit_amount"] += delta
            inj.summary_answer("RC-02", account_no, f"deposit_amount +{delta}")
    for i, account_no in enumerate(withdrawal_accounts):
        row = summary[account_no]
        if i == 0:
            row["withdrawal_count"] += 1
            inj.summary_answer("RC-03", account_no, "withdrawal_count +1")
        else:
            delta = rng.choice((1_000, 30_000, 77_777))
            row["withdrawal_amount"] += delta
            inj.summary_answer("RC-03", account_no, f"withdrawal_amount +{delta}")
    for account_no in balance_accounts:
        delta = rng.choice((1_000, 10_000, 777))
        summary[account_no]["closing_balance"] += delta
        inj.summary_answer("RC-04", account_no, f"closing_balance +{delta}")

    rows = [r for r in ds.summary if r["account_no"] not in (deleted_account, zero_account)]
    inj.summary_answer("RC-01", deleted_account, "집계표 행 삭제")
    inj.summary_answer("RC-01", zero_account, "집계표 행 삭제 (거래 0건 계좌)")
    extra_no = _new_account_no(rng, used_numbers)
    extra_opening = rng.randrange(0, 1_000_001) * 10
    rows.append(
        {"base_date": base.isoformat(), "account_no": extra_no, "opening_balance": extra_opening,
         "deposit_count": 0, "deposit_amount": 0, "withdrawal_count": 0, "withdrawal_amount": 0,
         "closing_balance": extra_opening}
    )
    inj.summary_answer("RC-01", extra_no, "마스터에 없는 계좌 행 추가")
    for account_no in duplicate_accounts:
        rows.append(dict(summary[account_no]))
        inj.summary_answer("SM-01", account_no, "계좌 행 중복")
    rows.sort(key=lambda r: r["account_no"])  # 정렬이 안정적이라 중복 행은 원래 행 바로 뒤에 온다
    ds.summary = rows

    # --- 거래내역 오류: 행마다 오류 하나만 심도록 서로 다른 행을 고른다.
    txns = ds.transactions
    pool = [t for t in txns if t["account_no"] not in touched and by_no[t["account_no"]].status != SUSPENDED]
    rng.shuffle(pool)

    def take(predicate=lambda t: True) -> dict:
        for i, t in enumerate(pool):
            if predicate(t):
                return pool.pop(i)
        raise RuntimeError("오류를 심을 거래 행이 부족합니다")

    def mutate(rule: str, row: dict, column: str, value: str, detail: str) -> None:
        original_account = row["account_no"]
        row[column] = value
        inj.txn_answer(rule, [row], original_account, detail)

    ymd = base.strftime("%Y%m%d")
    blank_columns = ("txn_id", "txn_dt", "account_no", "txn_code", "direction", "amount",
                     "account_no", "amount", "txn_dt", "txn_code")
    for k, column in enumerate(blank_columns):
        blank = "   " if k == len(blank_columns) - 1 else ""  # 마지막 하나는 공백뿐인 값
        mutate("DQ-01", take(), column, blank, f"{column} 삭제")

    def digits(no: str) -> str:
        return no.replace("-", "")

    account_mutations = (
        ("하이픈 제거", digits),
        ("하이픈 제거", digits),
        ("하이픈 제거", digits),
        ("엑셀 숫자 변환 (하이픈·앞자리 0 손실)", lambda no: digits(no).lstrip("0") or "0"),
        ("마지막 자리 삭제", lambda no: no[:-1]),
        ("마지막 자리 삭제", lambda no: no[:-1]),
        ("자리 추가", lambda no: no + "0"),
        ("하이픈 위치 변경", lambda no: f"{digits(no)[:2]}-{digits(no)[2:5]}-{digits(no)[5:]}"),
    )
    for detail, change in account_mutations:
        prefer_zero = detail.startswith("엑셀")
        row = take(lambda t: t["account_no"].startswith("0")) if prefer_zero else take()
        mutate("DQ-02", row, "account_no", change(row["account_no"]), detail)

    previous_day = (base - timedelta(days=1)).isoformat()
    for _ in range(INJECTION_PLAN["DQ-03"]):
        row = take()
        mutate("DQ-03", row, "txn_dt", previous_day + row["txn_dt"][10:], "거래일을 전일로 변경")

    for value in ("-15000", "0", "1500.5", "NEG", "0", "12000.75", "-1", "3.0"):
        row = take()
        if value == "NEG":
            value = f"-{parse_int(row['amount'])}"
        mutate("DQ-04", row, "amount", value, "금액 음수·0·소수점")

    for value in ("X", "d", "입금"):
        mutate("DQ-05", take(), "direction", value, "direction에 잘못된 값")

    for _ in range(6):  # 거래 행 그대로 복제: 복제 행만 정답에 기록
        row = take()
        duplicate = dict(row)
        inj.insertions.append((row, duplicate))
        inj.txn_answer("DQ-06", [duplicate], row["account_no"], "거래 행 그대로 복제")
    for _ in range(2):  # 같은 txn_id에 다른 내용: 두 행 모두 격리되므로 두 행을 같은 error_id로 기록
        row = take()
        changed = dict(row, amount=str(parse_int(row["amount"]) + 1000))
        inj.insertions.append((row, changed))
        inj.txn_answer("DQ-06", [row, changed], row["account_no"], "같은 txn_id에 다른 금액")

    for k in range(INJECTION_PLAN["DQ-07"]):
        row = take()
        copy_row = dict(row, txn_id=f"T{ymd}9{k:05d}")
        inj.insertions.append((row, copy_row))
        inj.txn_answer("DQ-07", [copy_row], row["account_no"], "txn_id만 바꿔 복제")

    for _ in range(INJECTION_PLAN["MD-01"]):
        mutate("MD-01", take(), "account_no", _new_account_no(rng, used_numbers), "마스터에 없는 계좌로 변경")

    closed_before = sorted((a for a in ds.accounts if a.status == CLOSED and a.close_date < base), key=lambda a: a.account_no)
    future_open = sorted((a for a in ds.accounts if a.open_date > base), key=lambda a: a.account_no)
    for k in range(INJECTION_PLAN["MD-02"]):
        target = rng.choice(closed_before if k < 2 else future_open)
        detail = "해지 계좌의 해지일 이후 거래" if k < 2 else "개설일 이전 거래"
        mutate("MD-02", take(), "account_no", target.account_no, detail)

    for _ in range(2):
        mutate("MD-03", take(lambda t: t["direction"] == WITHDRAWAL), "txn_code", INACTIVE_CODE, "폐지 거래코드")
    for code in ("X01", "D99", "W00"):
        mutate("MD-03", take(), "txn_code", code, "미등록 거래코드")

    for _ in range(INJECTION_PLAN["MD-04"]):
        mutate("MD-04", take(lambda t: t["direction"] == DEPOSIT), "direction", WITHDRAWAL, "입금 코드에 W 방향")

    suspended = sorted((a for a in ds.accounts if a.status == SUSPENDED), key=lambda a: a.account_no)
    existing = {(t["account_no"], t["txn_dt"], t["txn_code"], parse_int(t["amount"])) for t in txns}
    for k in range(INJECTION_PLAN["MD-05"]):
        account_no = suspended[k % len(suspended)].account_no
        while True:
            second, amount = rng.randrange(86400), rng.randint(1, 100) * 1000
            dt = f"{base.isoformat()} {second // 3600:02d}:{second // 60 % 60:02d}:{second % 60:02d}"
            if (account_no, dt, "W01", amount) not in existing:
                break
        new_row = {"txn_id": f"T{ymd}91{k:04d}", "txn_dt": dt, "account_no": account_no, "txn_code": "W01",
                   "direction": WITHDRAWAL, "amount": str(amount), "channel": "ATM", "branch_code": ""}
        inj.insertions.append((None, new_row))
        inj.txn_answer("MD-05", [new_row], account_no, "지급정지 계좌에 출금 추가")

    # 복제 행은 원본보다 뒤에, 새 거래는 아무 위치에 넣는다.
    index = {id(t): i for i, t in enumerate(txns)}
    placed = []
    for original, new_row in inj.insertions:
        start = index[id(original)] + 1 if original is not None else 0
        placed.append((rng.randint(start, len(txns)), new_row))
    for position, new_row in sorted(placed, key=lambda p: p[0], reverse=True):
        txns.insert(position, new_row)

    ds.answer = _finalize_answers(inj.answers, txns, ds.summary)
    _check_plan(ds.answer)
    return ds


def _finalize_answers(answers: list[dict], txns: list[dict], summary: list[dict]) -> list[dict]:
    txn_row_no = {id(t): i + 2 for i, t in enumerate(txns)}  # 헤더가 1행
    summary_row_no: dict[str, int] = {}
    for i, r in enumerate(summary):
        summary_row_no.setdefault(r["account_no"], i + 2)
    result = []
    for a in answers:
        if "_row" in a:
            row = a["_row"]
            row_no = txn_row_no[id(row)]
            record_key = row["txn_id"].strip() or f"행 {row_no}"
        else:
            row_no = summary_row_no.get(a["_account"], "")  # 삭제된 행은 행번호 없음
            record_key = a["_account"]
        result.append({**{k: a[k] for k in ("error_id", "expected_rule", "file", "original_account_no", "detail")},
                       "row_no": row_no, "record_key": record_key})
    return result


def _check_plan(answer: list[dict]) -> None:
    injected = Counter(rule for rule, _ in {(a["expected_rule"], a["error_id"]) for a in answer})
    if dict(injected) != INJECTION_PLAN:
        raise AssertionError(f"주입 오류 수가 계획과 다릅니다: {dict(injected)}")
