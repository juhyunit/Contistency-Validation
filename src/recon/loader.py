"""입력 파일 읽기: 해시·원본 보관, 인코딩 판별, 스키마 확인, 기준정보 확인.

모든 값은 문자열로 읽고 앞뒤 공백만 제거한다. 숫자·날짜 변환은 검증 단계에서 한다.
여기서 나는 오류(LoadError)는 검증 자체를 할 수 없다는 뜻이며, 실행은 FAILED로 끝난다.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Mapping

import openpyxl
import pandas as pd
from openpyxl.utils.exceptions import InvalidFileException

from recon.config import Config
from recon.models import (
    ACCOUNT_MASTER,
    ACCOUNT_STATUSES,
    CLOSED,
    COLUMNS,
    DEFAULT_FILE_NAMES,
    FILE_LABELS,
    FILE_TYPES,
    REQUIRED_COLUMNS,
    ROW_NO,
    TXN_CODE_MASTER,
)
from recon.values import parse_date

InputFile = tuple[str, bytes]  # (파일명, 내용)


class LoadError(Exception):
    """검증 자체를 할 수 없는 입력 오류."""


@dataclass
class LoadedFile:
    file_type: str
    file_name: str
    sha256: str
    encoding: str
    frame: pd.DataFrame  # row_no + 컬럼별 문자열 값
    archive_path: Path | None = None
    duplicate_of_run_id: int | None = None

    @property
    def row_count(self) -> int:
        return len(self.frame)


@dataclass(frozen=True)
class InputData:
    transactions: pd.DataFrame
    account_summary: pd.DataFrame
    account_master: pd.DataFrame
    txn_code_master: pd.DataFrame

    @classmethod
    def from_loaded(cls, loaded: Mapping[str, LoadedFile]) -> InputData:
        return cls(**{file_type: loaded[file_type].frame for file_type in FILE_TYPES})


def read_input_dir(input_dir: Path) -> dict[str, InputFile | None]:
    """폴더에서 표준 파일명(transactions.csv 등)으로 입력 파일을 찾는다. 없는 파일은 None."""
    files: dict[str, InputFile | None] = {}
    for file_type, name in DEFAULT_FILE_NAMES.items():
        path = Path(input_dir) / name
        files[file_type] = (name, path.read_bytes()) if path.is_file() else None
    return files


def load_inputs(
    files: Mapping[str, InputFile | None],
    config: Config,
    archive_dir: Path | None = None,
) -> dict[str, LoadedFile]:
    missing = [
        f"{FILE_LABELS[ft]}({DEFAULT_FILE_NAMES[ft]})" for ft in FILE_TYPES if files.get(ft) is None
    ]
    if missing:
        raise LoadError("입력 파일 누락: " + ", ".join(missing))
    loaded = {ft: _load_file(ft, *files[ft], archive_dir) for ft in FILE_TYPES}  # type: ignore[misc]
    _check_reference(loaded, config)
    return loaded


def _load_file(file_type: str, file_name: str, content: bytes, archive_dir: Path | None) -> LoadedFile:
    label = f"{FILE_LABELS[file_type]} 파일({file_name})"
    if not content:
        raise LoadError(f"{label}: 빈 파일입니다")
    sha256 = hashlib.sha256(content).hexdigest()
    # 형식이 깨진 파일도 나중에 확인할 수 있도록 읽기 전에 원본부터 보관한다.
    archive_path = _archive(archive_dir, sha256, file_name, content) if archive_dir else None

    suffix = Path(file_name).suffix.lower()
    if suffix in (".xlsx", ".xlsm"):
        header, rows = _read_xlsx(content, label)
        encoding = "xlsx"
        header, rows = _clean_rows(header, rows, label, strict_width=False)
    elif suffix == ".csv":
        text, encoding = _decode(content, label)
        header, rows = _read_csv(text, label)
        header, rows = _clean_rows(header, rows, label, strict_width=True)
    else:
        raise LoadError(f"{label}: 지원하지 않는 형식입니다 (csv, xlsx만 가능)")

    frame = _to_frame(file_type, header, rows, label)
    return LoadedFile(file_type, file_name, sha256, encoding, frame, archive_path)


def _archive(archive_dir: Path, sha256: str, file_name: str, content: bytes) -> Path:
    archive_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^\w.\-]", "_", Path(file_name).name) or "file"
    path = archive_dir / f"{sha256[:16]}_{safe_name}"
    if not path.exists():
        path.write_bytes(content)
    return path


def _decode(content: bytes, label: str) -> tuple[str, str]:
    for codec, name in (("utf-8-sig", "utf-8"), ("cp949", "cp949")):
        try:
            return content.decode(codec), name
        except UnicodeDecodeError:
            continue
    raise LoadError(f"{label}: 인코딩을 읽을 수 없습니다 (UTF-8, CP949만 지원)")


def _read_csv(text: str, label: str) -> tuple[list[str], list[tuple[int, list[str]]]]:
    try:
        records = list(csv.reader(io.StringIO(text, newline="")))
    except csv.Error as exc:
        raise LoadError(f"{label}: CSV 구조 오류 ({exc})") from exc
    if not records:
        raise LoadError(f"{label}: 헤더 행이 없습니다")
    # 행번호는 헤더를 1행으로 센 파일상의 위치다 (엑셀로 열었을 때의 행번호와 같다).
    return records[0], list(enumerate(records[1:], start=2))


def _read_xlsx(content: bytes, label: str) -> tuple[list[str], list[tuple[int, list[str]]]]:
    try:
        workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    except (zipfile.BadZipFile, InvalidFileException, KeyError, ValueError, OSError) as exc:
        raise LoadError(f"{label}: 엑셀 파일을 열 수 없습니다 ({exc})") from exc
    try:
        sheet = workbook.worksheets[0]
        rows = [[_cell_text(v) for v in row] for row in sheet.iter_rows(min_row=1, values_only=True)]
    finally:
        workbook.close()
    if not rows:
        raise LoadError(f"{label}: 헤더 행이 없습니다")
    header = list(rows[0])
    while header and header[-1] == "":
        header.pop()
    return header, list(enumerate(rows[1:], start=2))


def _cell_text(value: object) -> str:
    """엑셀 셀 값을 문자열로. 정수형 실수(1000.0)는 1000, 자정 날짜는 YYYY-MM-DD."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, datetime):
        return value.date().isoformat() if value.time() == time(0) else value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _clean_rows(
    raw_header: list[str],
    rows: list[tuple[int, list[str]]],
    label: str,
    *,
    strict_width: bool,
) -> tuple[list[str], list[tuple[int, list[str]]]]:
    """빈 행 제거, 컬럼 수 확인, 앞뒤 공백 제거. 이름 없는 빈 컬럼(엑셀 저장 시 생기는 열)은 버린다."""
    header = [h.strip() for h in raw_header]
    if not any(header):
        raise LoadError(f"{label}: 헤더 행이 없습니다")
    width = len(header)
    keep = [i for i, name in enumerate(header) if name]
    cleaned: list[tuple[int, list[str]]] = []
    bad_rows: list[int] = []
    for row_no, record in rows:
        if not any(cell.strip() for cell in record):
            continue
        overflow = record[width:]
        if (strict_width and len(record) != width) or any(cell.strip() for cell in overflow):
            bad_rows.append(row_no)
            continue
        record = (list(record) + [""] * width)[:width]
        unnamed = [i for i, name in enumerate(header) if not name and record[i].strip()]
        if unnamed:
            raise LoadError(f"{label}: 이름 없는 컬럼에 값이 있습니다 (행 {row_no})")
        cleaned.append((row_no, [record[i].strip() for i in keep]))
    if bad_rows:
        shown = ", ".join(str(n) for n in bad_rows[:5])
        more = f" 외 {len(bad_rows) - 5}개" if len(bad_rows) > 5 else ""
        raise LoadError(f"{label}: 컬럼 수가 헤더와 다른 행이 있습니다 (행 {shown}{more})")
    return [header[i] for i in keep], cleaned


def _to_frame(file_type: str, header: list[str], rows: list[tuple[int, list[str]]], label: str) -> pd.DataFrame:
    duplicates = sorted({name for name in header if header.count(name) > 1})
    if duplicates:
        raise LoadError(f"{label}: 컬럼명이 중복됩니다 ({', '.join(duplicates)})")
    missing = [c for c in REQUIRED_COLUMNS[file_type] if c not in header]
    if missing:
        raise LoadError(
            f"{label}: 필수 컬럼 누락 {', '.join(missing)} (현재 컬럼: {', '.join(header)})"
        )
    if not rows:
        raise LoadError(f"{label}: 데이터 행이 없습니다")
    spec = COLUMNS[file_type]
    extra = [name for name in header if name not in spec]
    empty = {column: "" for column in spec}  # 선택 컬럼이 없으면 빈 값
    records = [{ROW_NO: row_no, **empty, **dict(zip(header, values))} for row_no, values in rows]
    return pd.DataFrame.from_records(records, columns=[ROW_NO, *spec, *extra])


def _check_reference(loaded: Mapping[str, LoadedFile], config: Config) -> None:
    """기준정보(마스터) 파일이 깨져 있으면 거래를 판정할 기준이 없으므로 실행을 멈춘다."""
    problems: list[str] = []

    seen: set[str] = set()
    for r in loaded[ACCOUNT_MASTER].frame.to_dict("records"):
        where = f"계좌 마스터 {r[ROW_NO]}행"
        account_no = r["account_no"]
        if not account_no:
            problems.append(f"{where}: account_no 없음")
        elif account_no in seen:
            problems.append(f"{where}: account_no 중복 ({account_no})")
        seen.add(account_no)
        if r["status"] not in ACCOUNT_STATUSES:
            problems.append(f"{where}: status 값 오류 ({r['status']})")
        if parse_date(r["open_date"], config.date_format) is None:
            problems.append(f"{where}: open_date 형식 오류 ({r['open_date']})")
        if r["close_date"] and parse_date(r["close_date"], config.date_format) is None:
            problems.append(f"{where}: close_date 형식 오류 ({r['close_date']})")
        if r["status"] == CLOSED and not r["close_date"]:
            problems.append(f"{where}: CLOSED 계좌에 close_date 없음")

    seen = set()
    for r in loaded[TXN_CODE_MASTER].frame.to_dict("records"):
        where = f"거래코드 마스터 {r[ROW_NO]}행"
        code = r["txn_code"]
        if not code:
            problems.append(f"{where}: txn_code 없음")
        elif code in seen:
            problems.append(f"{where}: txn_code 중복 ({code})")
        seen.add(code)
        if r["direction"] not in config.directions:
            problems.append(f"{where}: direction 값 오류 ({r['direction']})")
        if r["active_yn"] not in ("Y", "N"):
            problems.append(f"{where}: active_yn 값 오류 ({r['active_yn']})")

    if problems:
        more = f" 외 {len(problems) - 5}건" if len(problems) > 5 else ""
        raise LoadError("기준정보 파일 오류로 검증할 수 없습니다: " + "; ".join(problems[:5]) + more)
