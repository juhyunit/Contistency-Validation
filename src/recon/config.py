"""config/rules.yaml 읽기."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import yaml

from recon.paths import PROJECT_ROOT

DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "rules.yaml"


class ConfigError(ValueError):
    """설정 파일 형식 오류."""


@dataclass(frozen=True)
class Config:
    amount_tolerance: int
    account_no_pattern: re.Pattern[str]
    txn_dt_format: str
    date_format: str
    directions: tuple[str, ...]
    stale_running_minutes: int
    enabled_rules: Mapping[str, bool]

    def is_enabled(self, rule_id: str) -> bool:
        return self.enabled_rules.get(rule_id, True)


def load_config(path: str | Path | None = None) -> Config:
    path = Path(path) if path else DEFAULT_CONFIG_PATH
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    try:
        tolerance = int(raw["tolerance"]["amount"])
        formats = raw["formats"]
        pattern = re.compile(formats["account_no"], re.ASCII)
        txn_dt_format = str(formats["txn_dt"])
        date_format = str(formats["date"])
        directions = tuple(str(v) for v in raw["values"]["direction"])
        stale_minutes = int(raw["runtime"]["stale_running_minutes"])
        rules = raw.get("rules") or {}
    except (KeyError, TypeError, ValueError, re.error) as exc:
        raise ConfigError(f"{path}: 설정 형식 오류 ({exc!r})") from exc
    if tolerance < 0 or stale_minutes <= 0:
        raise ConfigError(f"{path}: 허용오차는 0 이상, stale_running_minutes는 1 이상이어야 합니다")

    from recon.rules.registry import rule_ids

    unknown = sorted(set(rules) - set(rule_ids()))
    if unknown:
        raise ConfigError(f"{path}: 알 수 없는 규칙 {', '.join(unknown)}")
    return Config(
        amount_tolerance=tolerance,
        account_no_pattern=pattern,
        txn_dt_format=txn_dt_format,
        date_format=date_format,
        directions=directions,
        stale_running_minutes=stale_minutes,
        enabled_rules={rule_id: bool(enabled) for rule_id, enabled in rules.items()},
    )
