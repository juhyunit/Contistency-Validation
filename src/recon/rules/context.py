"""규칙들이 함께 쓰는 입력 데이터와 중간 결과."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import cached_property
from typing import Iterable

from recon.config import Config
from recon.loader import InputData
from recon.models import ERROR, ROW_NO, TRANSACTIONS, WARN, Issue
from recon.values import parse_date


@dataclass(frozen=True)
class AccountInfo:
    status: str
    open_date: date
    close_date: date | None

    def is_valid_on(self, day: date) -> bool:
        """기준일에 유효한 계좌 = 집계 대상 계좌 (개설일 ≤ 기준일 ≤ 해지일, 해지일 없으면 계속 유효)."""
        return self.open_date <= day and (self.close_date is None or self.close_date >= day)


@dataclass(frozen=True)
class CodeInfo:
    direction: str
    active: bool


class RuleContext:
    def __init__(self, data: InputData, base_date: date, config: Config):
        self.data = data
        self.base_date = base_date
        self.config = config
        self.txn_error_rows: set[int] = set()  # ERROR가 난 거래 행 (격리 대상)
        self.txn_warn_rows: set[int] = set()  # WARN이 난 거래 행 (검토 대상)
        self.dq_error_rows: frozenset[int] = frozenset()
        self._dq_finished = False

    def record(self, issues: Iterable[Issue]) -> None:
        for issue in issues:
            if issue.file_type != TRANSACTIONS or issue.row_no is None:
                continue
            if issue.severity == ERROR:
                self.txn_error_rows.add(issue.row_no)
            elif issue.severity == WARN:
                self.txn_warn_rows.add(issue.row_no)

    def finish_dq(self) -> None:
        """DQ 단계가 끝난 시점의 ERROR 행. 이 행들은 MD 검사를 받지 않는다."""
        self.dq_error_rows = frozenset(self.txn_error_rows)
        self._dq_finished = True

    @cached_property
    def txn_records(self) -> list[dict]:
        return self.data.transactions.to_dict("records")

    def md_records(self) -> list[dict]:
        if not self._dq_finished:
            raise RuntimeError("DQ 단계가 끝나기 전에 MD 대상 행을 요청했습니다")
        return [r for r in self.txn_records if r[ROW_NO] not in self.dq_error_rows]

    def clean_records(self) -> list[dict]:
        """DQ·MD ERROR가 없는 거래. WARN 행은 포함한다."""
        return [r for r in self.txn_records if r[ROW_NO] not in self.txn_error_rows]

    def quarantined_records(self) -> list[dict]:
        return [r for r in self.txn_records if r[ROW_NO] in self.txn_error_rows]

    @cached_property
    def accounts(self) -> dict[str, AccountInfo]:
        fmt = self.config.date_format
        result = {}
        for r in self.data.account_master.to_dict("records"):
            close = parse_date(r["close_date"], fmt) if r["close_date"] else None
            result[r["account_no"]] = AccountInfo(r["status"], parse_date(r["open_date"], fmt), close)
        return result

    @cached_property
    def codes(self) -> dict[str, CodeInfo]:
        return {
            r["txn_code"]: CodeInfo(r["direction"], r["active_yn"] == "Y")
            for r in self.data.txn_code_master.to_dict("records")
        }

    @cached_property
    def target_accounts(self) -> frozenset[str]:
        return frozenset(no for no, info in self.accounts.items() if info.is_valid_on(self.base_date))

    @cached_property
    def summary_analysis(self):
        from recon.reconcile import analyze_summary

        return analyze_summary(self.data.account_summary.to_dict("records"), self.base_date, self.config)

    @cached_property
    def recon_rows(self) -> list[dict]:
        """계좌별 대사 결과. DQ·MD가 끝난 뒤(RC 단계)에 처음 계산된다."""
        from recon.reconcile import build_recon_rows

        return build_recon_rows(self)
