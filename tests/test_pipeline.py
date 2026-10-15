"""통합 테스트와 실패 상황 테스트 (설계서 9장)."""

from __future__ import annotations

import io
from datetime import datetime, timedelta

import openpyxl
import pandas as pd
import pytest

from recon.evaluation import evaluate
from recon.models import ACCOUNT_SUMMARY, RUN_FAILED, RUN_RUNNING, RUN_SUCCESS, TRANSACTIONS, TXN_CODE_MASTER
from recon.pipeline import run_pipeline
from recon.reconcile import RESULT_MATCH
from recon.repository import runs as runs_table


def run(files, base_date, workspace, **kwargs):
    return run_pipeline(files, base_date, repository=workspace["repo"], data_dir=workspace["data_dir"], **kwargs)


# ---------------------------------------------------------------- 통합


def test_clean_data_has_no_issues_and_every_account_matches(datasets, workspace):
    clean, _ = datasets
    result = run(clean.files(), clean.base_date, workspace)
    assert result.status == RUN_SUCCESS
    assert result.validation.issues.empty
    assert set(result.validation.recon["result"]) == {RESULT_MATCH}
    assert result.validation.stats["quarantined_rows"] == 0


def test_injected_data_reaches_full_recall_with_no_false_positives(datasets, workspace):
    _, injected = datasets
    result = run(injected.files(), injected.base_date, workspace)
    ev = evaluate(result.validation.issues, pd.DataFrame(injected.answer))
    assert ev.missed.empty, ev.missed
    assert ev.false_positives.empty, ev.false_positives
    assert ev.recall == 1.0
    assert set(ev.per_rule["recall"]) == {1.0}


def test_same_input_gives_same_result(datasets, workspace):
    _, injected = datasets
    files = injected.files()
    first = run(files, injected.base_date, workspace).validation
    second = run(files, injected.base_date, workspace).validation
    pd.testing.assert_frame_equal(first.issues, second.issues)
    pd.testing.assert_frame_equal(first.recon, second.recon)
    assert first.stats == second.stats


def test_outputs_db_and_log_are_written(datasets, workspace):
    _, injected = datasets
    result = run(injected.files(), injected.base_date, workspace)
    repo = workspace["repo"]

    workbook = openpyxl.load_workbook(result.outputs.report, read_only=True)
    assert workbook.sheetnames == ["요약", "오류목록", "대사결과", "검토대상"]
    clean_csv = pd.read_csv(result.outputs.clean_csv, dtype=str, encoding="utf-8-sig")
    quarantine_csv = pd.read_csv(result.outputs.quarantine_csv, dtype=str, encoding="utf-8-sig")
    assert len(clean_csv) == result.validation.stats["clean_rows"]
    assert len(quarantine_csv) == result.validation.stats["quarantined_rows"]
    assert "error_rules" in quarantine_csv.columns

    saved = repo.get_run(result.run_id)
    assert saved["status"] == RUN_SUCCESS
    assert saved["stats"] == result.validation.stats
    assert len(repo.get_issues(result.run_id)) == len(result.validation.issues)
    assert len(repo.get_recon(result.run_id)) == len(result.validation.recon)
    assert dict(repo.get_rule_stats(result.run_id).values) == result.validation.rule_counts
    files = repo.get_input_files(result.run_id).set_index("file_type")
    assert files.loc[TXN_CODE_MASTER, "encoding"] == "cp949"
    assert files.loc[ACCOUNT_SUMMARY, "encoding"] == "xlsx"
    assert len(files.loc[TRANSACTIONS, "sha256"]) == 64

    log = (result.output_dir / "run.log").read_text(encoding="utf-8")
    for stage in ("DQ", "MD", "SM", "RC"):
        assert f"{stage}(" in log and f"{stage} 단계 종료" in log
    assert "SUCCESS" in log


# ---------------------------------------------------------------- 실패 상황


def _files_with(datasets, file_type, value):
    clean, _ = datasets
    files = clean.files()
    files[file_type] = value
    return files


@pytest.mark.parametrize(
    ("file_type", "value", "message"),
    [
        (TRANSACTIONS, None, "입력 파일 누락"),
        (TRANSACTIONS, ("transactions.csv", b""), "빈 파일"),
        (TRANSACTIONS, ("transactions.csv", b"txn_id,txn_dt,account_no,txn_code,direction,amount\n"), "데이터 행이 없습니다"),
        (TRANSACTIONS, "rename", "필수 컬럼 누락 amount"),
        (TRANSACTIONS, "drop", "필수 컬럼 누락 txn_code"),
    ],
)
def test_unusable_input_fails_run_with_reason(datasets, workspace, file_type, value, message):
    clean, _ = datasets
    if value in ("rename", "drop"):
        frame = pd.read_csv(io.BytesIO(clean.files()[TRANSACTIONS][1]), dtype=str, keep_default_na=False)
        frame = frame.rename(columns={"amount": "amt"}) if value == "rename" else frame.drop(columns=["txn_code"])
        value = ("transactions.csv", frame.to_csv(index=False).encode("utf-8"))
    result = run(_files_with(datasets, file_type, value), clean.base_date, workspace)
    assert result.status == RUN_FAILED
    assert message in result.error_message
    saved = workspace["repo"].get_run(result.run_id)
    assert saved["status"] == RUN_FAILED
    assert message in saved["error_message"]
    assert workspace["repo"].get_issues(result.run_id).empty


def test_cp949_transactions_are_processed(datasets, workspace):
    clean, _ = datasets
    name, content = clean.files()[TRANSACTIONS]
    # 영문·숫자만 있으면 CP949와 UTF-8 바이트가 같으므로 한글 메모 컬럼(추가 컬럼)을 붙여 실제 CP949 파일을 만든다.
    lines = content.decode("utf-8-sig").splitlines()
    text = "\n".join([lines[0] + ",memo", *(line + ",현금 입출금" for line in lines[1:])]) + "\n"
    files = _files_with(datasets, TRANSACTIONS, (name, text.encode("cp949")))
    result = run(files, clean.base_date, workspace)
    assert result.status == RUN_SUCCESS
    assert result.validation.issues.empty
    files_saved = workspace["repo"].get_input_files(result.run_id).set_index("file_type")
    assert files_saved.loc[TRANSACTIONS, "encoding"] == "cp949"


def test_reupload_warns_but_still_runs(datasets, workspace):
    clean, _ = datasets
    files = clean.files()
    first = run(files, clean.base_date, workspace)
    second = run(files, clean.base_date, workspace)
    assert first.warnings == []
    assert second.status == RUN_SUCCESS
    assert len(second.warnings) == 4
    assert all(f"실행 #{first.run_id}" in w for w in second.warnings)
    saved = workspace["repo"].get_input_files(second.run_id)
    assert set(saved["duplicate_of_run_id"]) == {first.run_id}
    assert workspace["repo"].get_run(second.run_id)["warnings"] == second.warnings


def test_stale_running_run_is_marked_failed_on_next_start(datasets, workspace):
    clean, _ = datasets
    repo = workspace["repo"]
    stuck = repo.create_run(clean.base_date)
    repo.update_run(stuck, status=RUN_RUNNING, started_at=datetime.now() - timedelta(hours=3))
    recent = repo.create_run(clean.base_date)
    repo.update_run(recent, status=RUN_RUNNING)  # 방금 시작한 실행은 건드리지 않는다

    result = run(clean.files(), clean.base_date, workspace)
    assert result.cleaned_stale_runs == [stuck]
    assert repo.get_run(stuck)["status"] == RUN_FAILED
    assert "비정상 종료" in repo.get_run(stuck)["error_message"]
    assert repo.get_run(recent)["status"] == RUN_RUNNING


def test_reprocess_creates_new_run_linked_to_parent(datasets, workspace):
    clean, injected = datasets
    first = run(injected.files(), injected.base_date, workspace)
    second = run(clean.files(), clean.base_date, workspace, parent_run_id=first.run_id)
    repo = workspace["repo"]
    assert second.run_id != first.run_id
    assert repo.get_run(second.run_id)["parent_run_id"] == first.run_id
    assert len(repo.get_issues(first.run_id)) == len(first.validation.issues)  # 이전 결과는 그대로


def test_unknown_parent_run_is_rejected(datasets, workspace):
    clean, _ = datasets
    with pytest.raises(ValueError, match="재처리 대상"):
        run(clean.files(), clean.base_date, workspace, parent_run_id=999)
    assert workspace["repo"].list_runs().empty


def test_unexpected_error_is_recorded_and_raised(datasets, workspace, monkeypatch):
    clean, _ = datasets

    def broken(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("recon.pipeline.validate", broken)
    with pytest.raises(RuntimeError):
        run(clean.files(), clean.base_date, workspace)
    with workspace["repo"].engine.connect() as conn:
        row = conn.execute(runs_table.select()).mappings().one()
    assert row["status"] == RUN_FAILED
    assert "boom" in row["error_message"]
