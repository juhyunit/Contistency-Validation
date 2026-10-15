"""화면에서 쓰는 쉬운 설명: 규칙, 단계, 대사 차이 원인, 입력 파일.

판단 기준의 원본은 docs/업무규칙서.md이고, 여기서는 처음 보는 사람이 바로 이해할 수 있는 말로 옮긴다.
"""

from __future__ import annotations

from dataclasses import dataclass

from recon.models import ACCOUNT_MASTER, ACCOUNT_SUMMARY, TRANSACTIONS, TXN_CODE_MASTER
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


@dataclass(frozen=True)
class RuleGuide:
    title: str  # 쉬운 이름
    what: str  # 무엇이 문제인지
    action: str  # 무엇을 하면 되는지


RULE_GUIDES = {
    "DQ-01": RuleGuide(
        "빈 칸이 있는 거래",
        "필수 항목(거래번호·일시·계좌·코드·입출금 구분·금액) 중 빈 칸이 있어요.",
        "원천 시스템에서 빈 값을 채운 파일을 다시 받으세요.",
    ),
    "DQ-02": RuleGuide(
        "계좌번호 형식 오류",
        "계좌번호가 123-45-678901 형식이 아니에요. 엑셀로 열었다 저장하면 하이픈이나 앞자리 0이 사라지기도 해요.",
        "원본 파일의 계좌번호를 확인하고, 엑셀에서는 텍스트 형식으로 저장하세요.",
    ),
    "DQ-03": RuleGuide(
        "거래일시 오류",
        "거래일시 형식이 틀렸거나, 기준일이 아닌 날짜의 거래가 섞여 있어요.",
        "고른 기준일이 맞는지, 다른 날짜 거래가 들어왔는지 확인하세요.",
    ),
    "DQ-04": RuleGuide(
        "금액 오류",
        "금액이 0 이하이거나 소수점·문자가 섞여 있어요.",
        "원천 데이터의 금액 값을 확인하세요.",
    ),
    "DQ-05": RuleGuide(
        "입출금 구분 오류",
        "입출금 구분이 D(입금)·W(출금)가 아니에요.",
        "구분 값을 D 또는 W로 바로잡으세요.",
    ),
    "DQ-06": RuleGuide(
        "거래번호 중복",
        "같은 거래번호가 두 번 이상 나왔어요. 내용이 같으면 첫 건만 남기고, 다르면 모두 뺐어요.",
        "중복 전송인지, 번호가 잘못 붙은 다른 거래인지 확인하세요.",
    ),
    "DQ-07": RuleGuide(
        "의심 중복",
        "번호만 다르고 계좌·시각·코드·금액이 같은 거래예요. 대사에는 포함했어요.",
        "실제로 두 번 일어난 거래인지 확인하세요.",
    ),
    "MD-01": RuleGuide(
        "등록되지 않은 계좌",
        "계좌 마스터에 없는 계좌번호예요.",
        "계좌번호 오류인지, 마스터 갱신이 늦은 것인지 확인하세요.",
    ),
    "MD-02": RuleGuide(
        "개설 전·해지 후 거래",
        "계좌가 개설되기 전이나 해지된 뒤에 일어난 거래예요.",
        "계좌 상태와 거래의 계좌번호를 확인하세요.",
    ),
    "MD-03": RuleGuide(
        "쓸 수 없는 거래코드",
        "거래코드 마스터에 없거나 폐지된 코드예요.",
        "코드 매핑이나 거래코드 마스터를 확인하세요.",
    ),
    "MD-04": RuleGuide(
        "코드와 입출금 방향 불일치",
        "입금 코드인데 출금(W)으로 들어온 것처럼, 거래코드와 입출금 구분이 맞지 않아요.",
        "거래코드와 입출금 구분 중 어느 쪽이 틀렸는지 확인하세요.",
    ),
    "MD-05": RuleGuide(
        "지급정지 계좌 출금",
        "지급정지 계좌에서 출금이 있었어요. 대사에는 포함했어요.",
        "승인된 예외 거래인지 확인하세요.",
    ),
    "SM-01": RuleGuide(
        "집계표 형식 오류",
        "집계표에 같은 계좌가 두 번 있거나 기준일·숫자가 잘못됐어요. 이 계좌는 대사에서 뺐어요.",
        "집계표를 다시 만들거나 해당 행을 고치세요.",
    ),
    "RC-01": RuleGuide(
        "집계표 계좌 누락·초과",
        "집계해야 할 계좌가 집계표에 없거나, 없어야 할 계좌가 들어 있어요.",
        "기준일에 유효한 계좌가 모두 집계표에 있는지 확인하세요.",
    ),
    "RC-02": RuleGuide(
        "입금 합계 불일치",
        "거래내역을 합한 입금 건수·금액이 집계표와 달라요.",
        "차이 원인 표시를 보고, 격리된 거래가 있는 계좌부터 확인하세요.",
    ),
    "RC-03": RuleGuide(
        "출금 합계 불일치",
        "거래내역을 합한 출금 건수·금액이 집계표와 달라요.",
        "차이 원인 표시를 보고, 격리된 거래가 있는 계좌부터 확인하세요.",
    ),
    "RC-04": RuleGuide(
        "잔액 계산 불일치",
        "집계표 안에서 기초 + 입금 − 출금 = 기말이 맞지 않아요.",
        "집계표의 입출금 금액이나 기말잔액 계산을 확인하세요.",
    ),
}


@dataclass(frozen=True)
class StageGuide:
    number: str
    title: str
    summary: str
    examples: tuple[str, ...]


STAGE_GUIDES = {
    "DQ": StageGuide("1", "품질 검증", "거래내역 파일 안의 빈 칸, 형식 오류, 중복을 찾아요.",
                     ("빈 칸", "계좌번호 형식", "다른 날짜 거래", "0원·음수 금액", "거래번호 중복")),
    "MD": StageGuide("2", "기준정보 확인", "계좌 마스터·거래코드 마스터와 맞춰 봐요.",
                     ("없는 계좌", "해지 후 거래", "폐지된 코드", "코드·방향 불일치")),
    "RC": StageGuide("3", "집계표 대사", "정상 거래만 계좌별로 더해 집계표와 비교해요.",
                     ("입금 합계 차이", "출금 합계 차이", "계좌 누락", "잔액 계산 오류")),
}
RULE_STAGE_LABELS = {"DQ": "품질 검증", "MD": "기준정보", "SM": "집계표", "RC": "대사"}


@dataclass(frozen=True)
class CauseGuide:
    level: str  # critical, warning, info
    meaning: str


CAUSE_GUIDES = {
    CAUSE_UNKNOWN: CauseGuide(
        "critical",
        "격리·검토 거래로는 설명되지 않는 차이예요. 계좌번호가 깨져 어느 계좌인지 모르는 격리 거래가 원인일 수 있으니 함께 확인하고, 그게 아니라면 집계표를 확인하세요.",
    ),
    CAUSE_EXCLUDED_TXN: CauseGuide("info", "이 계좌에 격리된 거래가 있어요. 격리 거래를 고치면 대부분 풀려요."),
    CAUSE_REVIEW_TXN: CauseGuide("warning", "의심 중복·지급정지 출금 같은 검토 거래가 합계에 들어가 생긴 차이일 수 있어요."),
    CAUSE_BALANCE: CauseGuide("critical", "집계표 안의 잔액 계산이 맞지 않아요."),
}

RESULT_GUIDES = {
    RESULT_MATCH: ("good", "일치", "거래내역 합계와 집계표가 같아요."),
    RESULT_MISMATCH: ("critical", "불일치", "입금·출금 합계나 잔액 계산이 달라요."),
    RESULT_EXCLUDED: ("warning", "대사 제외", "집계표 행 자체가 잘못돼 비교하지 못했어요."),
    RESULT_EXISTENCE: ("serious", "계좌 누락·초과", "집계표에 있어야 할 계좌가 없거나, 없어야 할 계좌가 있어요."),
}


@dataclass(frozen=True)
class ColumnGuide:
    name: str
    meaning: str
    example: str
    required: bool = True


@dataclass(frozen=True)
class FileGuide:
    title: str
    role: str
    columns: tuple[ColumnGuide, ...]


FILE_GUIDES = {
    TRANSACTIONS: FileGuide(
        "거래내역",
        "기준일 하루 동안 일어난 입출금 거래 전체 (CSV)",
        (
            ColumnGuide("txn_id", "거래 고유번호", "T20261015000001"),
            ColumnGuide("txn_dt", "거래일시 (YYYY-MM-DD HH:MM:SS)", "2026-10-15 09:30:00"),
            ColumnGuide("account_no", "계좌번호 (123-45-678901)", "012-34-567890"),
            ColumnGuide("txn_code", "거래코드", "D01"),
            ColumnGuide("direction", "D 입금 / W 출금", "D"),
            ColumnGuide("amount", "금액 (원, 0보다 큼, 쉼표 허용)", "1,500,000"),
            ColumnGuide("channel", "채널", "ATM", required=False),
            ColumnGuide("branch_code", "영업점 코드", "0012", required=False),
        ),
    ),
    ACCOUNT_SUMMARY: FileGuide(
        "계좌별 일일 집계",
        "비교 대상이 되는 계좌별 입출금 합계와 잔액 (엑셀)",
        (
            ColumnGuide("base_date", "기준일", "2026-10-15"),
            ColumnGuide("account_no", "계좌번호", "012-34-567890"),
            ColumnGuide("opening_balance", "기초잔액", "1000000"),
            ColumnGuide("deposit_count", "입금 건수", "3"),
            ColumnGuide("deposit_amount", "입금 금액", "450000"),
            ColumnGuide("withdrawal_count", "출금 건수", "1"),
            ColumnGuide("withdrawal_amount", "출금 금액", "50000"),
            ColumnGuide("closing_balance", "기말잔액", "1400000"),
        ),
    ),
    ACCOUNT_MASTER: FileGuide(
        "계좌 마스터",
        "계좌 상태와 개설·해지일 (CSV)",
        (
            ColumnGuide("account_no", "계좌번호 (중복 불가)", "012-34-567890"),
            ColumnGuide("product_code", "상품코드", "P01"),
            ColumnGuide("status", "ACTIVE / CLOSED / SUSPENDED", "ACTIVE"),
            ColumnGuide("open_date", "개설일", "2020-03-02"),
            ColumnGuide("close_date", "해지일 (해지 전이면 빈 값)", ""),
        ),
    ),
    TXN_CODE_MASTER: FileGuide(
        "거래코드 마스터",
        "거래코드별 입출금 방향과 사용 여부 (CSV)",
        (
            ColumnGuide("txn_code", "거래코드 (중복 불가)", "D01"),
            ColumnGuide("txn_name", "거래명", "현금입금"),
            ColumnGuide("direction", "이 코드의 방향 D / W", "D"),
            ColumnGuide("active_yn", "사용 여부 Y / N", "Y"),
        ),
    ),
}
