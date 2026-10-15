"""결과 화면의 한 줄 판정과 "먼저 확인할 것" 목록.

숫자만 늘어놓지 않고, 무엇이 얼마나 급한지와 다음에 할 일을 정리한다.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import pandas as pd

from recon.glossary import RULE_GUIDES
from recon.models import ERROR, RUN_SUCCESS, TRANSACTIONS, WARN
from recon.reconcile import CAUSE_EXCLUDED_TXN, CAUSE_REVIEW_TXN, CAUSE_UNKNOWN

LEVEL_ORDER = {"critical": 0, "warning": 1, "info": 2}


@dataclass(frozen=True)
class Verdict:
    level: str  # good, warning, critical
    badge: str
    headline: str
    summary: str


@dataclass(frozen=True)
class CheckItem:
    key: str
    level: str  # critical, warning, info
    title: str
    count: int
    unit: str
    description: str
    action: str
    breakdown: tuple[tuple[str, int], ...] = ()
    detail_filter: dict = field(default_factory=dict, hash=False, compare=False)


def verdict(status: str, stats: dict, error_message: str | None = None) -> Verdict:
    if status != RUN_SUCCESS:
        return Verdict(
            "critical",
            "실행 실패",
            "파일을 읽지 못해 검증하지 못했어요",
            error_message or "실패 원인을 확인할 수 없어요.",
        )
    errors = stats.get("error_issues", 0)
    reviews = stats.get("review_rows", 0)
    mismatched = stats.get("accounts_mismatched", 0) + stats.get("accounts_existence_mismatch", 0) + stats.get(
        "accounts_excluded", 0
    )
    if errors == 0 and reviews == 0:
        return Verdict(
            "good",
            "이상 없음",
            "모든 거래가 정상이고 계좌별 금액이 일치해요",
            f"거래 {stats.get('total_rows', 0):,}건, 계좌 {stats.get('accounts_matched', 0):,}개를 확인했어요.",
        )
    if errors == 0:
        return Verdict(
            "warning",
            "검토 필요",
            f"오류는 없지만 사람이 확인할 거래가 {reviews:,}건 있어요",
            "대사에는 포함했어요. 아래 목록에서 실제 문제인지 확인하세요.",
        )
    quarantined = stats.get("quarantined_rows", 0)
    if quarantined and mismatched:
        headline = f"거래 {quarantined:,}건을 격리했고, 계좌 {mismatched:,}개에서 차이가 났어요"
    elif quarantined:
        headline = f"거래 {quarantined:,}건을 격리했어요"
    elif mismatched:
        headline = f"계좌 {mismatched:,}개에서 차이가 났어요"
    else:
        headline = f"오류 {errors:,}건을 찾았어요"
    return Verdict("critical", "확인 필요", headline, "아래 '먼저 확인할 것'을 위에서부터 차례로 보세요.")


def checklist(stats: dict, issues: pd.DataFrame, recon: pd.DataFrame) -> list[CheckItem]:
    items: list[CheckItem] = []
    rule_counts = Counter(issues["rule_id"]) if not issues.empty else Counter()
    causes = recon["diff_cause"].fillna("") if not recon.empty else pd.Series(dtype=str)

    unknown = int(causes.str.contains(CAUSE_UNKNOWN, regex=False).sum())
    if unknown:
        description = "이 계좌에는 격리·검토 거래가 없는데도 합계가 달라요."
        if stats.get("unidentified_quarantined_rows"):
            description += (
                f" 계좌번호가 깨져 어느 계좌인지 모르는 격리 거래 {stats['unidentified_quarantined_rows']:,}건이"
                " 원인일 수 있고, 그렇지 않다면 집계표 쪽 문제예요."
            )
        else:
            description += " 집계표나 원장 쪽 문제일 가능성이 커요."
        items.append(
            CheckItem(
                "unknown_diff",
                "critical",
                "거래내역으로 설명되지 않는 차이",
                unknown,
                "개 계좌",
                description,
                "이 계좌들의 집계표 값을 원장과 대조하세요.",
                detail_filter={"view": "recon", "causes": [CAUSE_UNKNOWN]},
            )
        )

    summary_rules = [("SM-01", "형식·중복"), ("RC-01", "계좌 누락·초과"), ("RC-04", "잔액 계산")]
    summary_breakdown = tuple((label, rule_counts[rule]) for rule, label in summary_rules if rule_counts[rule])
    if summary_breakdown:
        items.append(
            CheckItem(
                "summary_errors",
                "critical",
                "집계표 자체의 오류",
                sum(n for _, n in summary_breakdown),
                "건",
                "거래내역과 상관없이 집계표 안에서 틀린 부분이에요.",
                "집계표를 만드는 쪽에 수정을 요청하세요.",
                summary_breakdown,
                {"view": "issues", "rules": [rule for rule, _ in summary_rules]},
            )
        )

    txn_errors = issues[(issues["file_type"] == TRANSACTIONS) & (issues["severity"] == ERROR)] if not issues.empty else issues
    if stats.get("quarantined_rows"):
        top = Counter(txn_errors["rule_id"]).most_common(3)
        items.append(
            CheckItem(
                "quarantined",
                "critical",
                "격리된 거래",
                stats["quarantined_rows"],
                "건",
                "오류가 있어 대사에서 뺀 거래예요. 격리 거래 CSV에 오류 사유가 함께 들어 있어요.",
                "원천 데이터를 고친 뒤 '재처리'로 다시 실행하세요.",
                tuple((f"{RULE_GUIDES[rule].title}", n) for rule, n in top),
                {"view": "issues", "severity": [ERROR], "files": [TRANSACTIONS]},
            )
        )

    explained = int(causes.str.contains(CAUSE_EXCLUDED_TXN, regex=False).sum())
    if explained:
        items.append(
            CheckItem(
                "explained_diff",
                "info",
                "격리 거래 때문에 생긴 계좌 차이",
                explained,
                "개 계좌",
                "이 계좌의 차이는 격리된 거래로 설명될 가능성이 커요.",
                "격리 거래를 고치면 대부분 함께 풀려요.",
                detail_filter={"view": "recon", "causes": [CAUSE_EXCLUDED_TXN]},
            )
        )

    if stats.get("review_rows"):
        warn_counts = Counter(issues.loc[issues["severity"] == WARN, "rule_id"])
        review_diff = int(causes.str.contains(CAUSE_REVIEW_TXN, regex=False).sum())
        description = "대사에는 포함했지만 사람이 판단해야 하는 거래예요."
        if review_diff:
            description += f" 이 때문에 {review_diff}개 계좌에 차이가 났을 수 있어요."
        items.append(
            CheckItem(
                "review",
                "warning",
                "검토가 필요한 거래",
                stats["review_rows"],
                "건",
                description,
                "실제 문제인지 확인하고, 문제라면 원천 데이터를 고쳐 다시 실행하세요.",
                tuple((RULE_GUIDES[rule].title, n) for rule, n in warn_counts.most_common()),
                {"view": "issues", "severity": [WARN]},
            )
        )

    if stats.get("unidentified_quarantined_rows"):
        items.append(
            CheckItem(
                "unidentified",
                "info",
                "어느 계좌인지 알 수 없는 격리 거래",
                stats["unidentified_quarantined_rows"],
                "건",
                "계좌번호가 깨졌거나 마스터에 없어 어떤 계좌의 차이와 연결되는지 알 수 없어요.",
                "원천 데이터에서 계좌번호부터 확인하세요.",
                detail_filter={"view": "issues", "rules": ["DQ-02", "MD-01"]},
            )
        )

    return sorted(items, key=lambda item: LEVEL_ORDER[item.level])
