"""규칙 등록과 실행.

규칙은 모두 같은 형태(컨텍스트 → Finding 목록)의 함수이고 @register로 등록한다.
규칙을 추가해도 엔진 코드는 바뀌지 않는다.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Iterable

from recon.models import Issue

if TYPE_CHECKING:
    from recon.rules.context import RuleContext

STAGES = ("DQ", "MD", "SM", "RC")
STAGE_NAMES = {
    "DQ": "품질 검증",
    "MD": "기준정보 정합성",
    "SM": "집계표 검증",
    "RC": "거래-집계 대사",
}
_RULE_MODULES = ("recon.rules.dq", "recon.rules.md", "recon.rules.sm", "recon.rules.rc")


@dataclass(frozen=True)
class Finding:
    """규칙 함수가 돌려주는 오류 1건. 규칙 ID·심각도·파일은 등록 정보에서 채운다."""

    row_no: int | None
    record_key: str
    column_name: str
    value: str
    message: str


@dataclass(frozen=True)
class Rule:
    rule_id: str
    name: str
    stage: str
    severity: str
    file_type: str
    check: Callable[[RuleContext], Iterable[Finding]]


_REGISTRY: dict[str, Rule] = {}


def register(rule_id: str, name: str, *, severity: str, file_type: str):
    stage = rule_id.split("-")[0]
    if stage not in STAGES:
        raise ValueError(f"알 수 없는 단계: {rule_id}")

    def decorator(func: Callable[[RuleContext], Iterable[Finding]]):
        if rule_id in _REGISTRY:
            raise ValueError(f"규칙 ID 중복: {rule_id}")
        _REGISTRY[rule_id] = Rule(rule_id, name, stage, severity, file_type, func)
        return func

    return decorator


def _ensure_loaded() -> None:
    for module in _RULE_MODULES:
        importlib.import_module(module)


def all_rules() -> list[Rule]:
    _ensure_loaded()
    return sorted(_REGISTRY.values(), key=lambda r: (STAGES.index(r.stage), r.rule_id))


def rule_ids() -> list[str]:
    return [rule.rule_id for rule in all_rules()]


def get_rule(rule_id: str) -> Rule:
    _ensure_loaded()
    return _REGISTRY[rule_id]


def run_stage(stage: str, ctx: RuleContext) -> list[Issue]:
    """한 단계의 규칙을 ID 순서로 실행한다. 같은 단계 안에서는 한 행의 오류를 모두 기록한다."""
    issues: list[Issue] = []
    for rule in all_rules():
        if rule.stage != stage or not ctx.config.is_enabled(rule.rule_id):
            continue
        found = [
            Issue(
                rule_id=rule.rule_id,
                severity=rule.severity,
                file_type=rule.file_type,
                row_no=None if f.row_no is None else int(f.row_no),
                record_key=f.record_key,
                column_name=f.column_name,
                value=f.value,
                message=f.message,
            )
            for f in rule.check(ctx)
        ]
        ctx.record(found)
        issues.extend(found)
    return issues
