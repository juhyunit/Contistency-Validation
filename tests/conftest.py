from __future__ import annotations

import pytest

from recon.config import load_config
from recon.repository import Repository
from recon.synthetic import generate_datasets


@pytest.fixture(scope="session")
def config():
    return load_config()


@pytest.fixture(scope="session")
def datasets():
    """(깨끗한 데이터, 오류 주입 데이터). 시드 고정."""
    return generate_datasets()


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """실행마다 따로 쓰는 DB와 data 폴더."""
    data_dir = tmp_path / "data"
    monkeypatch.setenv("RECON_DATA_DIR", str(data_dir))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'recon.db').as_posix()}")
    return {"data_dir": data_dir, "repo": Repository()}
