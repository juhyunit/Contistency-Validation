"""업로드한 파일이 4개 중 어떤 파일인지 알아낸다 (화면에서 파일을 한 번에 끌어다 놓을 수 있게).

헤더 컬럼으로 먼저 판단하고, 헤더를 읽을 수 없으면 파일 이름(transactions.csv 등)으로 판단한다.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl

from recon.models import FILE_TYPES, REQUIRED_COLUMNS


def _header(name: str, content: bytes) -> list[str] | None:
    suffix = Path(name).suffix.lower()
    try:
        if suffix in (".xlsx", ".xlsm"):
            workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            try:
                first = next(workbook.worksheets[0].iter_rows(max_row=1, values_only=True), ())
            finally:
                workbook.close()
            return [str(v).strip() for v in first if v is not None]
        if suffix == ".csv":
            # 컬럼명은 영문이므로 첫 줄만 읽으면 인코딩과 상관없이 판별할 수 있다.
            first_line = content.split(b"\n", 1)[0].decode("utf-8-sig", errors="replace")
            return [h.strip() for h in next(csv.reader([first_line]), [])]
    except Exception:  # 판별만 하는 단계라 읽지 못하면 이름으로 넘어간다
        return None
    return None


def detect_file_type(name: str, content: bytes) -> str | None:
    header = _header(name, content)
    if header:
        matches = [ft for ft in FILE_TYPES if set(REQUIRED_COLUMNS[ft]) <= set(header)]
        if len(matches) == 1:
            return matches[0]
    stem = Path(name).stem.lower()
    by_name = [ft for ft in FILE_TYPES if stem.startswith(ft)]
    return by_name[0] if len(by_name) == 1 else None


@dataclass
class Classified:
    files: dict[str, tuple[str, bytes]] = field(default_factory=dict)  # 파일 종류 → (파일명, 내용)
    unknown: list[str] = field(default_factory=list)  # 어떤 파일인지 알 수 없는 파일명
    duplicates: dict[str, list[str]] = field(default_factory=dict)  # 같은 종류로 판별된 파일이 여러 개

    @property
    def missing(self) -> list[str]:
        return [ft for ft in FILE_TYPES if ft not in self.files]


def classify(uploads: list[tuple[str, bytes]]) -> Classified:
    result = Classified()
    for name, content in uploads:
        file_type = detect_file_type(name, content)
        if file_type is None:
            result.unknown.append(name)
            continue
        if file_type in result.files:
            result.duplicates.setdefault(file_type, [result.files[file_type][0]]).append(name)
        result.files[file_type] = (name, content)  # 같은 종류가 여러 개면 마지막 파일을 쓴다
    return result
