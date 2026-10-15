"""프로젝트 경로와 기본 저장 위치.

실행 위치(현재 폴더)와 상관없이 같은 곳에 저장되도록 프로젝트 루트를 기준으로 잡는다.
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    """실행 데이터(DB, 원본 보관, 보고서) 폴더. 환경변수 RECON_DATA_DIR로 바꿀 수 있다."""
    return Path(os.environ.get("RECON_DATA_DIR") or PROJECT_ROOT / "data")


def default_database_url() -> str:
    """환경변수 DATABASE_URL, 없으면 data/recon.db (SQLite)."""
    return os.environ.get("DATABASE_URL") or f"sqlite:///{(data_dir() / 'recon.db').as_posix()}"
