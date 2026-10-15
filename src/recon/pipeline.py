"""전체 실행 순서와 실행 상태 관리. 화면(app)과 명령행(cli)이 모두 이 함수를 호출한다.

PENDING → RUNNING → SUCCESS / FAILED
FAILED는 파일 누락·스키마 오류처럼 검증 자체를 못 한 경우이고, 데이터 오류가 많은 것은 SUCCESS다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Mapping

from recon.config import Config, load_config
from recon.loader import InputData, InputFile, LoadError, load_inputs
from recon.models import RUN_FAILED, RUN_SUCCESS
from recon.paths import data_dir as default_data_dir
from recon.reporter import OutputPaths, write_outputs
from recon.repository import Repository
from recon.validation import ValidationResult, validate


@dataclass
class RunResult:
    run_id: int
    status: str
    error_message: str | None = None
    warnings: list[str] = field(default_factory=list)
    validation: ValidationResult | None = None
    outputs: OutputPaths | None = None
    output_dir: Path | None = None
    cleaned_stale_runs: list[int] = field(default_factory=list)

    @property
    def succeeded(self) -> bool:
        return self.status == RUN_SUCCESS


def run_pipeline(
    files: Mapping[str, InputFile | None],
    base_date: date,
    *,
    parent_run_id: int | None = None,
    config: Config | None = None,
    repository: Repository | None = None,
    data_dir: Path | None = None,
) -> RunResult:
    config = config or load_config()
    repo = repository or Repository()
    data_dir = Path(data_dir) if data_dir else default_data_dir()

    stale = repo.cleanup_stale_runs(config.stale_running_minutes)
    if parent_run_id is not None and not repo.run_exists(parent_run_id):
        raise ValueError(f"재처리 대상 실행 #{parent_run_id}이 없습니다")

    # 재처리도 새 run_id로 남기고 이전 실행은 parent_run_id로 연결한다 (이전 결과는 덮어쓰지 않음).
    run_id = repo.create_run(base_date, parent_run_id)
    output_dir = data_dir / "output" / f"run_{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)
    logger, handler = _run_logger(run_id, output_dir / "run.log")
    result = RunResult(run_id, RUN_FAILED, output_dir=output_dir, cleaned_stale_runs=stale)
    try:
        repo.mark_running(run_id, output_dir)
        logger.info("실행 #%d 시작: 기준일 %s, 재처리 대상 %s", run_id, base_date, parent_run_id or "-")
        if stale:
            logger.warning("비정상 종료된 실행 정리: %s", ", ".join(f"#{n}" for n in stale))

        logger.info("파일 읽기 시작")
        loaded = load_inputs(files, config, archive_dir=data_dir / "archive")
        for f in loaded.values():
            logger.info("  %s: %s, %s, %d행, sha256 %s", f.file_type, f.file_name, f.encoding, f.row_count, f.sha256[:16])
            previous = repo.find_processed_file(f.sha256)
            if previous is not None:
                f.duplicate_of_run_id = previous
                result.warnings.append(f"이미 처리된 파일: {f.file_name} (실행 #{previous}에서 같은 내용 처리)")
        for warning in result.warnings:
            logger.warning(warning)
        repo.save_input_files(run_id, loaded.values())

        validation = validate(InputData.from_loaded(loaded), base_date, config, logger)
        logger.info("출력 파일 작성")
        outputs = write_outputs(output_dir, run_id, base_date, loaded, validation, result.warnings)
        repo.save_results(run_id, validation.issues, validation.recon, validation.rule_counts)
        repo.finish_run(run_id, RUN_SUCCESS, warnings=result.warnings, stats=validation.stats)
        result.status, result.validation, result.outputs = RUN_SUCCESS, validation, outputs
        logger.info("실행 #%d 완료 (SUCCESS)", run_id)
    except LoadError as exc:
        result.error_message = str(exc)
        repo.finish_run(run_id, RUN_FAILED, error_message=result.error_message, warnings=result.warnings)
        logger.error("실행 #%d 실패 (FAILED): %s", run_id, exc)
    except Exception as exc:
        # 예상하지 못한 오류도 실행 이력에 남긴 뒤 그대로 올린다 (버그를 숨기지 않음).
        repo.finish_run(run_id, RUN_FAILED, error_message=f"내부 오류: {exc!r}", warnings=result.warnings)
        logger.exception("실행 #%d 내부 오류", run_id)
        raise
    finally:
        logger.removeHandler(handler)
        handler.close()
    return result


def _run_logger(run_id: int, path: Path) -> tuple[logging.Logger, logging.Handler]:
    logger = logging.getLogger(f"recon.run.{run_id}")
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger, handler
