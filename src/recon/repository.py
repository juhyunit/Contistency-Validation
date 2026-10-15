"""DB 저장·조회. SQLAlchemy만 쓰므로 DATABASE_URL만 바꾸면 PostgreSQL로 옮길 수 있다."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

import pandas as pd
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    insert,
    select,
    update,
)
from sqlalchemy.engine import make_url

from recon.loader import LoadedFile
from recon.models import ISSUE_COLUMNS, RUN_FAILED, RUN_PENDING, RUN_RUNNING, RUN_SUCCESS
from recon.paths import default_database_url
from recon.reconcile import RECON_COLUMNS, RECON_INT_COLUMNS

metadata = MetaData()

runs = Table(
    "runs",
    metadata,
    Column("run_id", Integer, primary_key=True, autoincrement=True),
    Column("parent_run_id", Integer, ForeignKey("runs.run_id")),
    Column("base_date", Date, nullable=False),
    Column("status", String(16), nullable=False),
    Column("started_at", DateTime, nullable=False),
    Column("finished_at", DateTime),
    Column("error_message", Text),
    Column("warning_message", Text),  # 중복 업로드 등 실행을 막지 않는 경고
    Column("output_dir", Text),
    Column("stats_json", Text),  # 요약 시트의 건수 (화면 카드용)
)

input_files = Table(
    "input_files",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", Integer, ForeignKey("runs.run_id"), nullable=False, index=True),
    Column("file_type", String(32), nullable=False),
    Column("file_name", Text, nullable=False),
    Column("sha256", String(64), nullable=False, index=True),
    Column("encoding", String(16)),
    Column("row_count", Integer),
    Column("archive_path", Text),
    Column("duplicate_of_run_id", Integer),
)

issues = Table(
    "issues",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", Integer, ForeignKey("runs.run_id"), nullable=False, index=True),
    Column("rule_id", String(8), nullable=False),
    Column("severity", String(8), nullable=False),
    Column("file_type", String(32), nullable=False),
    Column("row_no", Integer),
    Column("record_key", Text),
    Column("column_name", Text),
    Column("value", Text),
    Column("message", Text),
)

_RECON_BOOL_COLUMNS = ("is_target", "in_summary", "deposit_mismatch", "withdrawal_mismatch", "balance_mismatch")


def _recon_column(name: str) -> Column:
    if name in RECON_INT_COLUMNS:
        return Column(name, Integer if name == "summary_row_no" else BigInteger)
    if name in _RECON_BOOL_COLUMNS:
        return Column(name, Boolean)
    return Column(name, Text)


recon_results = Table(
    "recon_results",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", Integer, ForeignKey("runs.run_id"), nullable=False, index=True),
    *(_recon_column(name) for name in RECON_COLUMNS),
)

rule_stats = Table(
    "rule_stats",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", Integer, ForeignKey("runs.run_id"), nullable=False, index=True),
    Column("rule_id", String(8), nullable=False),
    Column("hit_count", Integer, nullable=False),
)


def _now() -> datetime:
    return datetime.now().replace(microsecond=0)


def _plain(value):
    """pandas·numpy 값을 DB 드라이버가 받는 파이썬 기본형으로 바꾼다."""
    if value is None or value is pd.NA:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    return value.item() if hasattr(value, "item") else value


def _records(frame: pd.DataFrame, columns: Iterable[str]) -> list[dict]:
    columns = list(columns)
    return [
        {column: _plain(value) for column, value in zip(columns, row)}
        for row in frame[columns].itertuples(index=False, name=None)
    ]


class Repository:
    def __init__(self, url: str | None = None):
        self.url = url or default_database_url()
        parsed = make_url(self.url)
        if parsed.drivername.startswith("sqlite") and parsed.database not in (None, "", ":memory:"):
            Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(self.url)
        metadata.create_all(self.engine)  # 첫 실행 때 테이블 자동 생성

    # --- 실행 상태 ---

    def create_run(self, base_date: date, parent_run_id: int | None = None) -> int:
        with self.engine.begin() as conn:
            result = conn.execute(
                insert(runs).values(
                    parent_run_id=parent_run_id,
                    base_date=base_date,
                    status=RUN_PENDING,
                    started_at=_now(),
                )
            )
            return int(result.inserted_primary_key[0])

    def update_run(self, run_id: int, **values) -> None:
        with self.engine.begin() as conn:
            conn.execute(update(runs).where(runs.c.run_id == run_id).values(**values))

    def mark_running(self, run_id: int, output_dir: Path) -> None:
        self.update_run(run_id, status=RUN_RUNNING, output_dir=str(output_dir))

    def finish_run(
        self,
        run_id: int,
        status: str,
        *,
        error_message: str | None = None,
        warnings: list[str] | None = None,
        stats: dict | None = None,
    ) -> None:
        self.update_run(
            run_id,
            status=status,
            finished_at=_now(),
            error_message=error_message,
            warning_message="\n".join(warnings) if warnings else None,
            stats_json=json.dumps(stats, ensure_ascii=False) if stats is not None else None,
        )

    def cleanup_stale_runs(self, older_than_minutes: int, now: datetime | None = None) -> list[int]:
        """강제 중단된 실행은 스스로 상태를 바꿀 수 없으므로 다음 실행이 시작될 때 정리한다."""
        now = now or _now()
        limit = now - timedelta(minutes=older_than_minutes)
        condition = runs.c.status.in_([RUN_PENDING, RUN_RUNNING]) & (runs.c.started_at < limit)
        with self.engine.begin() as conn:
            stale = [row.run_id for row in conn.execute(select(runs.c.run_id).where(condition))]
            if stale:
                conn.execute(
                    update(runs)
                    .where(runs.c.run_id.in_(stale))
                    .values(
                        status=RUN_FAILED,
                        finished_at=now,
                        error_message=f"비정상 종료로 정리됨 ({older_than_minutes}분 넘게 완료되지 않음)",
                    )
                )
        return stale

    def run_exists(self, run_id: int) -> bool:
        with self.engine.connect() as conn:
            return conn.execute(select(runs.c.run_id).where(runs.c.run_id == run_id)).first() is not None

    def find_processed_file(self, sha256: str) -> int | None:
        """같은 해시의 파일을 성공적으로 처리한 가장 최근 실행 번호."""
        query = (
            select(runs.c.run_id)
            .join(input_files, input_files.c.run_id == runs.c.run_id)
            .where(input_files.c.sha256 == sha256, runs.c.status == RUN_SUCCESS)
            .order_by(runs.c.run_id.desc())
            .limit(1)
        )
        with self.engine.connect() as conn:
            row = conn.execute(query).first()
        return None if row is None else int(row.run_id)

    # --- 결과 저장 ---

    def save_input_files(self, run_id: int, files: Iterable[LoadedFile]) -> None:
        rows = [
            {
                "run_id": run_id,
                "file_type": f.file_type,
                "file_name": f.file_name,
                "sha256": f.sha256,
                "encoding": f.encoding,
                "row_count": f.row_count,
                "archive_path": str(f.archive_path) if f.archive_path else None,
                "duplicate_of_run_id": f.duplicate_of_run_id,
            }
            for f in files
        ]
        with self.engine.begin() as conn:
            conn.execute(insert(input_files), rows)

    def save_results(self, run_id: int, issue_frame: pd.DataFrame, recon: pd.DataFrame, rule_counts: dict[str, int]) -> None:
        issue_rows = [{"run_id": run_id, **r} for r in _records(issue_frame, ISSUE_COLUMNS)]
        recon_rows = [{"run_id": run_id, **r} for r in _records(recon, RECON_COLUMNS)]
        stat_rows = [{"run_id": run_id, "rule_id": k, "hit_count": v} for k, v in rule_counts.items()]
        with self.engine.begin() as conn:
            for table, rows in ((issues, issue_rows), (recon_results, recon_rows), (rule_stats, stat_rows)):
                if rows:
                    conn.execute(insert(table), rows)

    # --- 조회 ---

    def _frame(self, query, columns: Iterable[str] | None = None) -> pd.DataFrame:
        with self.engine.connect() as conn:
            result = conn.execute(query)
            return pd.DataFrame(result.fetchall(), columns=list(columns or result.keys()))

    def list_runs(self) -> pd.DataFrame:
        frame = self._frame(select(runs).order_by(runs.c.run_id.desc()))
        frame["parent_run_id"] = frame["parent_run_id"].astype("Int64")
        return frame

    def get_run(self, run_id: int) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(runs).where(runs.c.run_id == run_id)).mappings().first()
        if row is None:
            return None
        run = dict(row)
        run["stats"] = json.loads(run["stats_json"]) if run["stats_json"] else {}
        run["warnings"] = run["warning_message"].split("\n") if run["warning_message"] else []
        return run

    def get_input_files(self, run_id: int) -> pd.DataFrame:
        return self._frame(select(input_files).where(input_files.c.run_id == run_id).order_by(input_files.c.id))

    def get_issues(self, run_id: int) -> pd.DataFrame:
        query = select(*(issues.c[c] for c in ISSUE_COLUMNS)).where(issues.c.run_id == run_id).order_by(issues.c.id)
        frame = self._frame(query, ISSUE_COLUMNS)
        frame["row_no"] = frame["row_no"].astype("Int64")
        return frame

    def get_recon(self, run_id: int) -> pd.DataFrame:
        query = (
            select(*(recon_results.c[c] for c in RECON_COLUMNS))
            .where(recon_results.c.run_id == run_id)
            .order_by(recon_results.c.id)
        )
        frame = self._frame(query, RECON_COLUMNS)
        for column in RECON_INT_COLUMNS:
            frame[column] = frame[column].astype("Int64")
        return frame

    def get_rule_stats(self, run_id: int) -> pd.DataFrame:
        query = (
            select(rule_stats.c.rule_id, rule_stats.c.hit_count)
            .where(rule_stats.c.run_id == run_id)
            .order_by(rule_stats.c.id)
        )
        return self._frame(query)
