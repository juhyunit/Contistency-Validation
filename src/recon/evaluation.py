"""정답 파일 대비 재현율·오탐 계산 (설계서 8장 평가 지표).

- 매칭 기준: 거래내역 오류는 (파일, 행번호, 규칙), 집계표 오류는 (파일, 계좌번호, 규칙)
- 재현율: 정답 error_id의 모든 행이 탐지되면 탐지로 본다
- 연쇄 차이: 거래내역에 심은 오류가 만든 원래 계좌의 RC-02·03, 집계표 금액 변조가 만든 RC-04는
  "예상된 연쇄"로 분류해 오탐에서 뺀다
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from recon.models import DEFAULT_FILE_NAMES, TRANSACTIONS
from recon.rules.registry import all_rules

TXN_FILE = DEFAULT_FILE_NAMES[TRANSACTIONS]


@dataclass
class EvaluationResult:
    per_rule: pd.DataFrame  # rule_id, injected, detected, recall
    missed: pd.DataFrame  # 탐지하지 못한 정답 행
    false_positives: pd.DataFrame  # 정답으로 설명되지 않는 탐지
    cascades: pd.DataFrame  # 예상된 연쇄로 분류된 탐지

    @property
    def injected(self) -> int:
        return int(self.per_rule["injected"].sum())

    @property
    def detected(self) -> int:
        return int(self.per_rule["detected"].sum())

    @property
    def recall(self) -> float:
        return self.detected / self.injected if self.injected else 1.0

    @property
    def passed(self) -> bool:
        return self.recall == 1.0 and self.false_positives.empty


def _row_no(value) -> int | None:
    if value is None or value is pd.NA or value == "" or (isinstance(value, float) and pd.isna(value)):
        return None
    return int(value)


def _key(file: str, rule: str, row_no, record_key: str) -> tuple:
    return (file, rule, _row_no(row_no)) if file == TXN_FILE else (file, rule, str(record_key))


def evaluate(issues: pd.DataFrame, answer: pd.DataFrame) -> EvaluationResult:
    issue_rows = [
        {**r, "file": DEFAULT_FILE_NAMES.get(r["file_type"], r["file_type"])}
        for r in issues.to_dict("records")
    ]
    detected_keys = {_key(r["file"], r["rule_id"], r["row_no"], r["record_key"]) for r in issue_rows}
    answer_rows = answer.to_dict("records")
    for a in answer_rows:
        a["_key"] = _key(a["file"], a["expected_rule"], a["row_no"], a["record_key"])
        a["_found"] = a["_key"] in detected_keys
    answer_keys = {a["_key"] for a in answer_rows}

    found_by_error: dict[str, bool] = {}
    rule_by_error: dict[str, str] = {}
    for a in answer_rows:
        found_by_error[a["error_id"]] = found_by_error.get(a["error_id"], True) and a["_found"]
        rule_by_error[a["error_id"]] = a["expected_rule"]

    per_rule = []
    for rule in all_rules():
        errors = [e for e, r in rule_by_error.items() if r == rule.rule_id]
        detected = sum(found_by_error[e] for e in errors)
        per_rule.append(
            {
                "rule_id": rule.rule_id,
                "injected": len(errors),
                "detected": detected,
                "recall": detected / len(errors) if errors else float("nan"),
            }
        )

    txn_cascade_accounts = {a["original_account_no"] for a in answer_rows if a["file"] == TXN_FILE}
    amount_tampered_accounts = {
        str(a["record_key"])
        for a in answer_rows
        if a["expected_rule"] in ("RC-02", "RC-03") and "amount" in str(a["detail"])
    }
    false_positives, cascades = [], []
    for r in issue_rows:
        if _key(r["file"], r["rule_id"], r["row_no"], r["record_key"]) in answer_keys:
            continue
        if r["rule_id"] in ("RC-02", "RC-03") and r["record_key"] in txn_cascade_accounts:
            cascades.append(r)
        elif r["rule_id"] == "RC-04" and r["record_key"] in amount_tampered_accounts:
            cascades.append(r)
        else:
            false_positives.append(r)

    columns = [*issues.columns, "file"]
    missed = [{k: v for k, v in a.items() if not k.startswith("_")} for a in answer_rows if not a["_found"]]
    return EvaluationResult(
        per_rule=pd.DataFrame(per_rule),
        missed=pd.DataFrame(missed, columns=list(answer.columns)),
        false_positives=pd.DataFrame(false_positives, columns=columns),
        cascades=pd.DataFrame(cascades, columns=columns),
    )
