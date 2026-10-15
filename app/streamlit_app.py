"""Streamlit 화면 (4개 탭): 실행, 결과 요약, 상세, 실행 이력.

  uv run streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from recon.models import DEFAULT_FILE_NAMES, FILE_LABELS, FILE_TYPES, RUN_SUCCESS  # noqa: E402
from recon.paths import default_database_url  # noqa: E402
from recon.pipeline import run_pipeline  # noqa: E402
from recon.reconcile import RESULT_EXCLUDED, RESULT_EXISTENCE, RESULT_MATCH, RESULT_MISMATCH  # noqa: E402
from recon.reporter import ISSUE_HEADERS, RECON_HEADERS  # noqa: E402
from recon.repository import Repository  # noqa: E402
from recon.rules.registry import all_rules  # noqa: E402
from recon.synthetic import ANSWER_FILE_NAME, DEFAULT_BASE_DATE, generate_datasets  # noqa: E402

st.set_page_config(page_title="금융 데이터 검증·대사", layout="wide")

RULE_NAMES = {rule.rule_id: rule.name for rule in all_rules()}
ISSUE_COLUMN_LABELS = dict(
    zip(("rule_id", "severity", "file_type", "row_no", "record_key", "column_name", "value", "message"), ISSUE_HEADERS)
)
RUN_COLUMN_LABELS = {
    "run_id": "실행",
    "parent_run_id": "재처리 원본",
    "base_date": "기준일",
    "status": "상태",
    "started_at": "시작",
    "finished_at": "종료",
    "error_message": "실패 원인",
    "warning_message": "경고",
}


@st.cache_resource
def get_repository(url: str) -> Repository:
    return Repository(url)


@st.cache_data
def sample_zip() -> bytes:
    clean, injected = generate_datasets()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for folder, dataset in (("clean", clean), ("injected", injected)):
            for name, content in dataset.files().values():
                archive.writestr(f"{folder}/{name}", content)
        archive.writestr(f"injected/{ANSWER_FILE_NAME}", injected.answer_csv())
    return buffer.getvalue()


repo = get_repository(default_database_url())


def execute(files, base_date, parent_run_id) -> None:
    with st.spinner("검증 중입니다..."):
        result = run_pipeline(files, base_date, parent_run_id=parent_run_id, repository=repo)
    # 새 실행을 조회 대상으로 바꾼다 (사이드바 선택 상자가 만들어지기 전이라 바꿀 수 있다).
    st.session_state["selected_run"] = result.run_id
    st.session_state["flash"] = (result.run_id, result.status, result.error_message, result.warnings)


def run_label(run: dict) -> str:
    label = f"#{run['run_id']} · {run['base_date']} · {run['status']}"
    parent = run.get("parent_run_id")
    if parent is not None and not pd.isna(parent):
        label += f" · 재처리(#{int(parent)})"
    return label


def output_file(run: dict, name: str) -> Path | None:
    if not run.get("output_dir"):
        return None
    path = Path(run["output_dir"]) / name
    return path if path.is_file() else None


st.title("금융 데이터 검증·대사 자동화")
st.caption("거래내역 품질 검증(DQ) → 기준정보 정합성(MD) → 집계표 검증·대사(SM·RC)")

tab_run, tab_summary, tab_detail, tab_history = st.tabs(["실행", "결과 요약", "상세", "실행 이력"])

# ------------------------------------------------------------------ 실행
with tab_run:
    st.markdown("파일 4개를 올리고 기준일을 고른 뒤 **실행**을 누르세요. 파일이 없으면 **샘플 데이터로 실행**을 눌러 보세요.")
    uploads = {}
    upload_columns = st.columns(2)
    for i, file_type in enumerate(FILE_TYPES):
        uploads[file_type] = upload_columns[i % 2].file_uploader(
            f"{FILE_LABELS[file_type]} · {DEFAULT_FILE_NAMES[file_type]}",
            type=["csv", "xlsx"],
            key=f"upload_{file_type}",
        )
    left, right = st.columns(2)
    base_date = left.date_input(
        "기준일",
        value=DEFAULT_BASE_DATE,
        help=f"샘플 데이터의 기준일은 {DEFAULT_BASE_DATE}입니다. 실제 파일은 그 파일의 기준일을 고르세요.",
        key="base_date",
    )
    previous_runs = repo.list_runs()
    parent_options = [None, *previous_runs["run_id"].tolist()]
    parent_run_id = right.selectbox(
        "재처리 대상",
        parent_options,
        format_func=lambda v: "없음 (새 실행)" if v is None else f"#{v}",
        help="수정한 파일로 다시 돌릴 때 이전 실행을 고르면 실행 이력에서 서로 연결됩니다.",
        key="parent_run",
    )

    run_col, sample_col, download_col = st.columns([1, 1, 2])
    if run_col.button("실행", type="primary", key="run_button"):
        files = {ft: (u.name, u.getvalue()) if u is not None else None for ft, u in uploads.items()}
        execute(files, base_date, parent_run_id)
    if sample_col.button("샘플 데이터로 실행", key="sample_button", help="오류를 심어 둔 합성 데이터(기준일 2026-10-15)로 실행합니다."):
        _, injected = generate_datasets()
        execute(injected.files(), injected.base_date, None)
    download_col.download_button(
        "샘플 데이터 내려받기 (zip)",
        sample_zip(),
        file_name="sample_data.zip",
        mime="application/zip",
        key="sample_download",
    )

    flash = st.session_state.get("flash")
    if flash:
        run_id, status, error_message, warnings = flash
        if status == RUN_SUCCESS:
            st.success(f"실행 #{run_id} 완료. '결과 요약' 탭에서 결과를 확인하세요.")
        else:
            st.error(f"실행 #{run_id} 실패: {error_message}")
        for warning in warnings:
            st.warning(warning)

# ------------------------------------------------------------------ 조회할 실행 선택
runs = repo.list_runs()
selected_run_id = None
with st.sidebar:
    st.header("조회할 실행")
    if runs.empty:
        st.info("아직 실행 이력이 없습니다.")
    else:
        run_ids = runs["run_id"].tolist()
        if st.session_state.get("selected_run") not in run_ids:
            st.session_state["selected_run"] = run_ids[0]
        labels = {r["run_id"]: run_label(r) for r in runs.to_dict("records")}
        selected_run_id = st.selectbox("실행", run_ids, format_func=labels.get, key="selected_run")

selected_run = repo.get_run(selected_run_id) if selected_run_id is not None else None

# ------------------------------------------------------------------ 결과 요약
with tab_summary:
    if selected_run is None:
        st.info("실행 탭에서 검증을 먼저 실행하세요.")
    else:
        run = selected_run
        st.subheader(run_label(run))
        st.caption(f"시작 {run['started_at']} · 종료 {run['finished_at'] or '-'}")
        for warning in run["warnings"]:
            st.warning(warning)
        if run["status"] != RUN_SUCCESS:
            st.error(f"실패 원인: {run['error_message'] or '-'}")
        else:
            stats = run["stats"]
            first = st.columns(5)
            first[0].metric("총 거래", f"{stats['total_rows']:,}")
            first[1].metric("정상", f"{stats['clean_rows']:,}")
            first[2].metric("격리", f"{stats['quarantined_rows']:,}")
            first[3].metric("검토 대상 (WARN)", f"{stats['review_rows']:,}")
            first[4].metric("계좌 미식별 격리", f"{stats['unidentified_quarantined_rows']:,}")
            second = st.columns(5)
            second[0].metric("대사 일치 계좌", f"{stats['accounts_matched']:,}")
            second[1].metric("대사 불일치 계좌", f"{stats['accounts_mismatched']:,}")
            second[2].metric("집계표 오류로 제외", f"{stats['accounts_excluded']:,}")
            second[3].metric("계좌 존재 불일치", f"{stats['accounts_existence_mismatch']:,}")
            second[4].metric("오류 (ERROR / WARN)", f"{stats['error_issues']:,} / {stats['warn_issues']:,}")

            rule_stats = repo.get_rule_stats(run["run_id"])
            st.markdown("**규칙별 오류 건수**")
            st.bar_chart(rule_stats.set_index("rule_id")["hit_count"], x_label="규칙", y_label="건수")

            downloads = st.columns(3)
            for column, (name, label, mime) in zip(
                downloads,
                (
                    (f"report_{run['run_id']}.xlsx", "엑셀 보고서",
                     "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
                    ("clean_transactions.csv", "정상 거래 CSV", "text/csv"),
                    ("quarantine_transactions.csv", "격리 거래 CSV", "text/csv"),
                ),
            ):
                path = output_file(run, name)
                if path is None:
                    column.caption(f"{label} 파일이 없습니다 (저장소가 초기화되었을 수 있음)")
                else:
                    column.download_button(f"{label} 내려받기", path.read_bytes(), file_name=name, mime=mime,
                                           key=f"download_{run['run_id']}_{name}")

# ------------------------------------------------------------------ 상세
with tab_detail:
    if selected_run is None or selected_run["status"] != RUN_SUCCESS:
        st.info("성공한 실행을 고르면 오류목록과 대사결과를 볼 수 있습니다.")
    else:
        run_id = selected_run["run_id"]
        issues = repo.get_issues(run_id)
        st.subheader("오류목록")
        filters = st.columns(3)
        rules = filters[0].multiselect(
            "규칙", sorted(issues["rule_id"].unique()), format_func=lambda r: f"{r} {RULE_NAMES.get(r, '')}",
            placeholder="전체", key="filter_rules",
        )
        severities = filters[1].multiselect("심각도", ["ERROR", "WARN"], placeholder="전체", key="filter_severity")
        account = filters[2].text_input("계좌번호·키 검색", key="filter_account").strip()
        view = issues
        if rules:
            view = view[view["rule_id"].isin(rules)]
        if severities:
            view = view[view["severity"].isin(severities)]
        if account:
            view = view[
                view["record_key"].str.contains(account, regex=False, na=False)
                | view["value"].str.contains(account, regex=False, na=False)
            ]
        view = view.assign(file_type=view["file_type"].map(DEFAULT_FILE_NAMES).fillna(view["file_type"]))
        st.caption(f"{len(view):,}건 / 전체 {len(issues):,}건")
        st.dataframe(view.rename(columns=ISSUE_COLUMN_LABELS), hide_index=True, width="stretch")

        st.subheader("대사결과")
        recon = repo.get_recon(run_id)
        results = st.multiselect(
            "대사 결과",
            [RESULT_MISMATCH, RESULT_EXISTENCE, RESULT_EXCLUDED, RESULT_MATCH],
            default=[RESULT_MISMATCH, RESULT_EXISTENCE, RESULT_EXCLUDED],
            placeholder="전체",
            key="filter_recon",
        )
        recon_account = st.text_input("계좌번호 검색", key="filter_recon_account").strip()
        recon_view = recon[recon["result"].isin(results)] if results else recon
        if recon_account:
            recon_view = recon_view[recon_view["account_no"].str.contains(recon_account, regex=False)]
        st.caption(f"{len(recon_view):,}개 계좌 / 전체 {len(recon):,}개")
        st.dataframe(recon_view.rename(columns=RECON_HEADERS), hide_index=True, width="stretch")

# ------------------------------------------------------------------ 실행 이력
with tab_history:
    if runs.empty:
        st.info("아직 실행 이력이 없습니다.")
    else:
        history = runs[list(RUN_COLUMN_LABELS)].copy()
        history["parent_run_id"] = history["parent_run_id"].astype("Int64")
        st.dataframe(history.rename(columns=RUN_COLUMN_LABELS), hide_index=True, width="stretch")
        st.markdown("**이전 보고서 다시 내려받기**")
        pick = st.selectbox(
            "실행 선택",
            runs["run_id"].tolist(),
            format_func=lambda v: run_label(next(r for r in runs.to_dict("records") if r["run_id"] == v)),
            key="history_pick",
        )
        picked = repo.get_run(pick)
        report = output_file(picked, f"report_{pick}.xlsx")
        if report is None:
            st.caption("이 실행의 보고서가 없습니다 (실패한 실행이거나 저장소가 초기화됨).")
        else:
            st.download_button(
                f"보고서 #{pick} 내려받기",
                report.read_bytes(),
                file_name=report.name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"history_download_{pick}",
            )
