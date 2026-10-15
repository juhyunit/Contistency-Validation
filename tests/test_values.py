from datetime import datetime

import pytest

from recon.values import parse_date, parse_datetime, parse_int


@pytest.mark.parametrize(
    ("text", "expected"),
    [("1", 1), ("1,000", 1000), ("1,500,000,000", 1_500_000_000), ("-5,000", -5000), ("0010", 10)],
)
def test_parse_int_accepts_ascii_integers(text, expected):
    assert parse_int(text) == expected


@pytest.mark.parametrize("text", ["", "1.5", "3.0", "1,00", "12,3456", "１２３", "abc", "1 000", "+5"])
def test_parse_int_rejects_non_integers_and_full_width_digits(text):
    assert parse_int(text) is None


def test_parse_datetime_is_strict():
    fmt = "%Y-%m-%d %H:%M:%S"
    assert parse_datetime("2026-10-15 00:00:00", fmt) == datetime(2026, 10, 15)
    assert parse_datetime("2026-10-15 9:00:00", fmt) is None  # 0이 빠진 시각
    assert parse_datetime("２０２６-10-15 10:00:00", fmt) is None  # 전각 숫자
    assert parse_datetime("2026/10/15 10:00:00", fmt) is None
    assert parse_datetime("2026-02-30 10:00:00", fmt) is None


def test_parse_date():
    assert parse_date("2026-10-15", "%Y-%m-%d").isoformat() == "2026-10-15"
    assert parse_date("2026-10-15 00:00:00", "%Y-%m-%d") is None
