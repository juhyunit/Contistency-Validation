"""문자열 값 해석.

파이썬의 int(), strptime(), 정규식 \\d는 전각 숫자(０１２)도 숫자로 받아들인다.
실무 데이터에서 전각 숫자는 수기 입력 오류이므로 ASCII 숫자만 허용한다.
"""

from __future__ import annotations

import re
from datetime import date, datetime

_INT_RE = re.compile(r"-?(?:\d{1,3}(?:,\d{3})+|\d+)", re.ASCII)


def parse_int(text: str) -> int | None:
    """정수 문자열을 int로 바꾼다. 천 단위 쉼표(1,000)는 허용, 소수점·전각 숫자는 None."""
    if not _INT_RE.fullmatch(text):
        return None
    return int(text.replace(",", ""))


def parse_datetime(text: str, fmt: str) -> datetime | None:
    """형식과 정확히 일치할 때만 datetime. 2026-1-5처럼 0이 빠진 값도 형식 오류로 본다."""
    if not text.isascii():
        return None
    try:
        value = datetime.strptime(text, fmt)
    except ValueError:
        return None
    return value if value.strftime(fmt) == text else None


def parse_date(text: str, fmt: str) -> date | None:
    value = parse_datetime(text, fmt)
    return value.date() if value else None
