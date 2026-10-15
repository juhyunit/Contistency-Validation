"""Streamlit 화면: 시작하기 · 검증 실행 · 결과 · 상세 내역 · 실행 이력.

  uv run streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import io
import json
import logging
import sys
import zipfile
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR.parent / "src"))
sys.path.insert(0, str(APP_DIR))

import altair as alt  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

import ui  # noqa: E402
from recon.detect import classify  # noqa: E402
from recon.glossary import CAUSE_GUIDES, FILE_GUIDES, RESULT_GUIDES, RULE_GUIDES, RULE_STAGE_LABELS  # noqa: E402
from recon.insights import checklist, verdict  # noqa: E402
from recon.models import DEFAULT_FILE_NAMES, ERROR, FILE_LABELS, FILE_TYPES, RUN_FAILED, RUN_SUCCESS, WARN  # noqa: E402
from recon.paths import default_database_url  # noqa: E402
from recon.pipeline import run_pipeline  # noqa: E402
from recon.reconcile import (  # noqa: E402
    CAUSE_BALANCE,
    CAUSE_EXCLUDED_TXN,
    CAUSE_REVIEW_TXN,
    CAUSE_UNKNOWN,
    RESULT_EXCLUDED,
    RESULT_EXISTENCE,
    RESULT_MATCH,
    RESULT_MISMATCH,
)
from recon.repository import Repository  # noqa: E402
from recon.rules.registry import all_rules  # noqa: E402
from recon.synthetic import ANSWER_FILE_NAME, DEFAULT_BASE_DATE, generate_datasets  # noqa: E402

st.set_page_config(
    page_title="Recon · 금융 데이터 검증·대사",
    page_icon=":material/fact_check:",
    layout="wide",
    initial_sidebar_state="collapsed",
)

HOME, RUN, RESULT, DETAIL, HISTORY = "시작하기", "검증 실행", "결과", "상세 내역", "실행 이력"
PAGES = [HOME, RUN, RESULT, DETAIL, HISTORY]
RULES = {rule.rule_id: rule for rule in all_rules()}
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CHART_FONT = "Pretendard, sans-serif"
log = logging.getLogger("recon.app")


@st.cache_resource
def get_repository(url: str) -> Repository:
    return Repository(url)


@st.cache_resource
def sample_datasets():
    return generate_datasets()


@st.cache_data
def sample_zip() -> bytes:
    clean, injected = sample_datasets()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for folder, dataset in (("clean", clean), ("injected", injected)):
            for name, content in dataset.files().values():
                archive.writestr(f"{folder}/{name}", content)
        archive.writestr(f"injected/{ANSWER_FILE_NAME}", injected.answer_csv())
    return buffer.getvalue()


repo = get_repository(default_database_url())


# ------------------------------------------------------------------ 상태·이동


def go(page: str) -> None:
    st.session_state["page"] = page


def open_detail(detail_filter: dict) -> None:
    """결과 화면의 '목록 보기'에서 상세 내역 필터를 미리 채워 이동한다."""
    for key in ("f_severity", "f_stage", "f_rules", "f_search", "f_result", "f_cause"):
        st.session_state.pop(key, None)
    if detail_filter.get("view") == "recon":
        st.session_state["f_result"] = [RESULT_MISMATCH]
        st.session_state["f_cause"] = detail_filter.get("causes", [])
        st.session_state["detail_view"] = "계좌별 대사 결과"
    else:
        st.session_state["f_severity"] = detail_filter.get("severity", [])
        st.session_state["f_rules"] = detail_filter.get("rules", [])
        st.session_state["detail_view"] = "오류 목록"
    st.session_state["page"] = DETAIL


def execute(files, base_date, parent_run_id=None) -> None:
    try:
        with st.spinner("검증하고 있어요… 보통 몇 초면 끝나요."):
            result = run_pipeline(files, base_date, parent_run_id=parent_run_id, repository=repo)
    except Exception as exc:  # 예상하지 못한 오류도 화면을 멈추지 않고 이유를 보여 준다
        log.exception("검증 실행 중 오류")
        ui.note(f"{type(exc).__name__}: {exc}", "critical", "예상하지 못한 오류로 검증을 마치지 못했어요.")
        return
    st.session_state["selected_run"] = result.run_id
    st.session_state["goto"] = RESULT
    st.rerun()


def run_sample() -> None:
    _, injected = sample_datasets()
    execute(injected.files(), injected.base_date)


def run_label(run: dict) -> str:
    status = {RUN_SUCCESS: "완료", RUN_FAILED: "실패"}.get(run["status"], run["status"])
    label = f"#{run['run_id']} · 기준일 {run['base_date']} · {status}"
    parent = run.get("parent_run_id")
    if parent is not None and not pd.isna(parent):
        label += f" · #{int(parent)} 재처리"
    return label


def run_picker(runs: pd.DataFrame, key: str):
    """페이지마다 따로 그려도 고른 실행이 유지되도록 selected_run에 저장한다."""
    ids = runs["run_id"].tolist()
    current = st.session_state.get("selected_run")
    index = ids.index(current) if current in ids else 0
    labels = {r["run_id"]: run_label(r) for r in runs.to_dict("records")}
    choice = st.selectbox("조회할 실행", ids, index=index, format_func=labels.get, key=key)
    st.session_state["selected_run"] = choice
    return repo.get_run(choice)


def output_file(run: dict, name: str) -> Path | None:
    if not run.get("output_dir"):
        return None
    path = Path(run["output_dir"]) / name
    return path if path.is_file() else None


def human_size(path: Path) -> str:
    size = path.stat().st_size
    return f"{size / 1024:,.1f} KB" if size < 1024 * 1024 else f"{size / 1024 / 1024:,.1f} MB"


def no_runs_state() -> None:
    ui.empty_state("아직 실행한 검증이 없어요", "샘플 데이터로 먼저 체험해 보거나, 내 파일을 올려 검증을 시작하세요.")
    left, right, _ = st.columns([1, 1, 2])
    if left.button("샘플로 체험하기", type="primary", key="empty_sample", width="stretch"):
        run_sample()
    right.button("내 파일로 검증하기", key="empty_own", on_click=go, args=(RUN,), width="stretch")


# ------------------------------------------------------------------ 시작하기


FAQS = [
    ("어떤 파일이 필요한가요?",
     "거래내역(CSV), 계좌별 일일 집계(엑셀), 계좌 마스터(CSV), 거래코드 마스터(CSV) 4개예요. "
     "'검증 실행' 화면의 '파일 형식 안내'에서 필요한 컬럼과 예를 볼 수 있고, 샘플 파일도 내려받을 수 있어요."),
    ("결과에서 무엇부터 봐야 하나요?",
     "결과 화면의 '먼저 확인할 것'을 위에서부터 보세요. 급한 순서로 정리돼 있고, 항목마다 할 일과 목록 바로가기가 있어요. "
     "가장 먼저 볼 것은 '거래내역으로 설명되지 않는 차이'예요."),
    ("격리와 검토는 어떻게 다른가요?",
     "격리는 명백한 오류라 대사 계산에서 뺀 거래예요. 검토는 의심 중복처럼 틀렸다고 단정할 수 없어 계산에는 넣고 "
     "사람이 확인하도록 표시한 거래예요."),
    ("파일을 고친 뒤 다시 돌리려면요?",
     "'검증 실행'에서 고친 파일을 올리고 '재처리'에서 이전 실행을 고르세요. 새 실행으로 남고 이전 결과는 그대로 보존돼요."),
    ("데이터는 어디에 저장되나요?",
     "이 컴퓨터의 data 폴더에만 저장돼요 (DB, 원본 보관, 보고서). 외부로 전송하지 않아요."),
]


def page_home() -> None:
    with st.container(key="hero"):
        text_col, preview_col = st.columns([1.12, 0.88], gap="large", vertical_alignment="center")
        with text_col:
            ui.hero_text()
            left, right, _ = st.columns([1, 1, 0.4])
            if left.button("샘플로 1분 체험", type="primary", key="cta_sample", width="stretch"):
                run_sample()
            right.button("내 파일로 검증하기", key="cta_own", on_click=go, args=(RUN,), width="stretch")
        with preview_col:
            ui.hero_ledger()

    ui.section("어떻게 동작하나요", "파일 4개를 올리면 세 단계 검증을 차례로 거쳐 결과와 보고서가 나와요.")
    ui.steps()

    ui.section("무엇을 찾아내나요", "사람이 엑셀로 하나씩 보던 오류를 17개 규칙으로 자동 판정해요.")
    ui.rule_catalog()

    ui.section("결과는 이렇게 읽으세요", "거래와 계좌는 아래 네 가지 표시로 정리돼요.")
    ui.reading_guide()

    ui.section("자주 묻는 질문")
    for question, answer in FAQS:
        with st.expander(question):
            st.write(answer)


# ------------------------------------------------------------------ 검증 실행


def page_run() -> None:
    ui.section("검증 실행", "파일 4개를 올리고 기준일만 확인하면 돼요.", first=True)

    with st.container(key="step1"):
        ui.step_head("01", "파일 올리기", "4개 파일을 한 번에 끌어다 놓으세요. 파일 이름이 달라도 컬럼을 보고 어떤 파일인지 알아봐요.")
        uploads = st.file_uploader(
            "입력 파일", type=["csv", "xlsx", "xlsm"], accept_multiple_files=True, key="uploads",
            label_visibility="collapsed",
        )
        classified = classify([(u.name, u.getvalue()) for u in uploads or []])
        ui.file_slots(classified)
        if classified.unknown:
            ui.note(
                f"{', '.join(classified.unknown)} — 필요한 컬럼이 없어 어떤 파일인지 알 수 없어요. 아래 '파일 형식 안내'를 확인하세요.",
                "warning", "알 수 없는 파일",
            )
        for file_type, names in classified.duplicates.items():
            ui.note(
                f"{FILE_LABELS[file_type]} 파일이 여러 개예요 ({', '.join(names)}). 마지막 파일 {names[-1]}을 사용해요.",
                "warning", "중복 파일",
            )
        with st.expander("파일 형식 안내 — 어떤 컬럼이 필요한가요?"):
            st.caption("모든 파일은 기준일 하루치를 담아요. CSV는 UTF-8과 CP949(엑셀 기본) 모두 읽을 수 있어요.")
            tabs = st.tabs([FILE_GUIDES[ft].title for ft in FILE_TYPES])
            for tab, file_type in zip(tabs, FILE_TYPES):
                with tab:
                    st.markdown(f"**{DEFAULT_FILE_NAMES[file_type]}** · {FILE_GUIDES[file_type].role}")
                    ui.spec_table(FILE_GUIDES[file_type])
            st.download_button(
                "샘플 파일 내려받기 (zip)", sample_zip(), file_name="sample_data.zip", mime="application/zip",
                key="sample_download", help="clean(오류 없음)과 injected(오류 81건 주입) 두 세트가 들어 있어요.",
            )

    with st.container(key="step2"):
        ui.step_head("02", "기준일 확인", "파일에 담긴 거래가 일어난 날짜예요. 다른 날짜의 거래는 오류로 표시돼요.")
        left, right = st.columns([1, 2])
        base_date = left.date_input(
            "기준일", value=DEFAULT_BASE_DATE, format="YYYY-MM-DD", key="base_date",
            help=f"샘플 데이터의 기준일은 {DEFAULT_BASE_DATE}이에요.",
        )
        runs = repo.list_runs()
        labels = {r["run_id"]: run_label(r) for r in runs.to_dict("records")}
        with right.expander("수정한 파일로 다시 검증하나요? (재처리)"):
            parent_run_id = st.selectbox(
                "이전 실행", [None, *runs["run_id"].tolist()],
                format_func=lambda v: "선택 안 함 (새 검증)" if v is None else labels[v],
                key="parent_run",
                help="고른 실행과 연결된 새 실행으로 남아요. 이전 결과는 바뀌지 않아요.",
            )

    ready = len(FILE_TYPES) - len(classified.missing)
    with st.container(key="step3"):
        info_col, action_col = st.columns([1.5, 1], gap="large", vertical_alignment="center")
        with info_col:
            parent_label = "없음 (새 검증)" if parent_run_id is None else labels.get(parent_run_id, f"#{parent_run_id}")
            ui.confirm_panel(ready, base_date.isoformat(), parent_label)
        with action_col:
            if st.button("검증 시작", type="primary", key="run_button", disabled=ready < 4, width="stretch"):
                execute(classified.files, base_date, parent_run_id)
            if st.button("샘플 데이터로 실행", key="sample_button", width="stretch"):
                run_sample()
            ui.html('<div class="d-muted" style="font-size:12px;line-height:1.5;margin-top:4px">'
                    "샘플은 오류 81건을 심어 둔 합성 데이터예요 (기준일 2026-10-15).</div>")


# ------------------------------------------------------------------ 결과


def chart_config(chart: alt.TopLevelMixin) -> alt.TopLevelMixin:
    return (
        chart.configure(font=CHART_FONT)
        .configure_view(stroke=None)
        .configure_axis(grid=False, domain=False, ticks=False, labelColor=ui.STEEL, labelFontSize=12, labelPadding=8)
        .configure_axisX(labels=False)
        .configure_legend(orient="top", title=None, labelColor=ui.INK, labelFontSize=12, symbolType="square",
                          symbolSize=90, padding=0, offset=12)
    )


def rule_chart(rule_stats: pd.DataFrame) -> None:
    data = rule_stats[rule_stats["hit_count"] > 0].copy()
    if data.empty:
        ui.note("어떤 규칙에도 걸린 오류가 없어요.", "good")
        return
    data["label"] = [f"{RULE_GUIDES[r].title}{' (검토)' if RULES[r].severity == WARN else ''}" for r in data["rule_id"]]
    data["stage"] = [RULE_STAGE_LABELS[RULES[r].stage] for r in data["rule_id"]]
    bars = alt.Chart(data).mark_bar(cornerRadiusEnd=4, color=ui.PRIMARY, size=14).encode(
        x=alt.X("hit_count:Q", title=None),
        y=alt.Y("label:N", sort=list(data["label"]), title=None, axis=alt.Axis(labelLimit=200)),
        tooltip=[
            alt.Tooltip("rule_id:N", title="규칙"),
            alt.Tooltip("label:N", title="내용"),
            alt.Tooltip("stage:N", title="단계"),
            alt.Tooltip("hit_count:Q", title="건수", format=","),
        ],
    )
    labels = bars.mark_text(align="left", dx=6, color=ui.INK, fontWeight=600, fontSize=12).encode(
        text=alt.Text("hit_count:Q", format=",")
    )
    st.altair_chart(chart_config((bars + labels).properties(height=26 * len(data) + 10)), width="stretch", theme=None)


DIFF_CAUSES = [("원인 미상", ui.STATUS["critical"]), ("잔액 계산 오류", ui.STATUS["warning"]), ("격리·검토 거래 있음", ui.STONE)]


def diff_category(cause: str) -> str:
    if CAUSE_UNKNOWN in cause:
        return "원인 미상"
    if cause == CAUSE_BALANCE:
        return "잔액 계산 오류"
    return "격리·검토 거래 있음"


def diff_chart(recon: pd.DataFrame) -> None:
    data = recon[recon["result"] == RESULT_MISMATCH].copy()
    for column in ("deposit_amount_diff", "withdrawal_amount_diff", "balance_diff"):
        data[column] = data[column].astype("float").fillna(0)
    flow = data["deposit_amount_diff"].abs() + data["withdrawal_amount_diff"].abs()
    data["amount"] = flow.where(flow > 0, data["balance_diff"].abs())  # 입출금 차이가 없으면 잔액 차이
    data = data[data["amount"] > 0]
    if data.empty:
        ui.note("금액 차이가 난 계좌가 없어요. 건수 차이만 있다면 상세 내역에서 확인하세요.", "good")
        return
    data["cause"] = data["diff_cause"].fillna("").map(diff_category)
    top = data.sort_values("amount", ascending=False).head(10)
    bars = alt.Chart(top).mark_bar(cornerRadiusEnd=4, size=14).encode(
        x=alt.X("amount:Q", title=None),
        y=alt.Y("account_no:N", sort=list(top["account_no"]), title=None,
                axis=alt.Axis(labelFont=ui.MONO, labelLimit=160)),
        color=alt.Color("cause:N", scale=alt.Scale(domain=[c for c, _ in DIFF_CAUSES], range=[c for _, c in DIFF_CAUSES])),
        tooltip=[
            alt.Tooltip("account_no:N", title="계좌"),
            alt.Tooltip("cause:N", title="원인"),
            alt.Tooltip("deposit_amount_diff:Q", title="입금 금액 차이", format=","),
            alt.Tooltip("withdrawal_amount_diff:Q", title="출금 금액 차이", format=","),
            alt.Tooltip("balance_diff:Q", title="잔액 차이", format=","),
        ],
    )
    labels = bars.mark_text(align="left", dx=6, color=ui.INK, fontWeight=600, fontSize=12).encode(
        text=alt.Text("amount:Q", format=","), color=alt.value(ui.INK)
    )
    st.altair_chart(chart_config((bars + labels).properties(height=30 * len(top) + 10)), width="stretch", theme=None)


def failure_tip(message: str) -> str:
    if "누락" in message and "파일" in message:
        return "파일 4개가 모두 있어야 해요. '검증 실행'에서 빠진 파일을 함께 올리세요."
    if "컬럼" in message:
        return "필요한 컬럼 이름이 다르거나 빠졌어요. '파일 형식 안내'의 컬럼 이름과 똑같이 맞춰 주세요."
    if "기준정보" in message:
        return "계좌 마스터나 거래코드 마스터 값이 규칙에 맞지 않아요. 메시지에 나온 행을 고쳐 주세요."
    return "메시지에 나온 파일을 열어 형식(CSV·엑셀, 인코딩, 빈 파일 여부)을 확인해 주세요."


def page_result() -> None:
    runs = repo.list_runs()
    ui.section("결과", "검증이 끝난 내용을 급한 순서로 정리했어요.", first=True)
    if runs.empty:
        no_runs_state()
        return
    picker, _ = st.columns([2, 3])
    with picker:
        run = run_picker(runs, "pick_result")
    stats = run["stats"]
    v = verdict(run["status"], stats, run["error_message"])
    meta = [f"실행 #{run['run_id']}", f"기준일 {run['base_date']}", f"{run['started_at']:%Y-%m-%d %H:%M} 실행"]
    if run.get("parent_run_id"):
        meta.append(f"#{run['parent_run_id']} 재처리")

    if run["status"] != RUN_SUCCESS:
        ui.dashboard(v, meta)
        ui.note(failure_tip(run["error_message"] or ""), "critical", "이렇게 해결하세요")
        st.button("검증 실행으로 이동", type="primary", key="fail_retry", on_click=go, args=(RUN,))
        return

    issues = repo.get_issues(run["run_id"])
    recon = repo.get_recon(run["run_id"])
    counts = recon["result"].value_counts()
    review, quarantined = stats["review_rows"], stats["quarantined_rows"]
    ui.dashboard(
        v,
        meta,
        kpis=[("전체 거래", stats["total_rows"], "건"), ("정상 반영", stats["clean_rows"], "건"),
              ("격리", quarantined, "건"), ("검토 필요", review, "건")],
        composition=[("정상", stats["clean_rows"] - review, "#5cb2ff"), ("검토", review, "#f7b928"),
                     ("격리", quarantined, "#ff6378")],
        accounts=[(RESULT_GUIDES[r][1], int(counts.get(r, 0)), RESULT_GUIDES[r][0])
                  for r in (RESULT_MATCH, RESULT_MISMATCH, RESULT_EXCLUDED, RESULT_EXISTENCE)],
    )
    for warning in run["warnings"]:
        ui.note(f"{warning}. 결과에는 영향이 없어요.", "info", "같은 파일을 다시 올렸어요")

    items = checklist(stats, issues, recon)
    ui.section("먼저 확인할 것", "위에서부터 급한 순서예요. '목록 보기'를 누르면 해당 건만 골라 보여 드려요.", small=True)
    if not items:
        ui.note("확인할 항목이 없어요. 보고서를 내려받아 보관하면 끝이에요.", "good", "모두 정상이에요")
    else:
        with st.container(key="queue"):
            for index, item in enumerate(items, start=1):
                with st.container(key=f"qrow_{index}"):
                    body, count, action = st.columns([6.2, 1.5, 1.1], vertical_alignment="center")
                    with body:
                        ui.html(ui.queue_item(item))
                    with count:
                        ui.html(ui.queue_count(item))
                    action.button("목록 보기", key=f"check_{item.key}", type="tertiary",
                                  on_click=open_detail, args=(item.detail_filter,))

    ui.section("한눈에 보기", "어디서 차이가 크게 났고, 어떤 오류가 많은지예요. 막대에 마우스를 올리면 자세히 보여요.", small=True)
    left, right = st.columns(2, gap="medium")
    with left, st.container(key="chart_diff"):
        ui.card_head("차이 금액이 큰 계좌", "입금·출금 금액 차이 합계 기준 상위 10개 · 색은 차이 원인")
        diff_chart(recon)
    with right, st.container(key="chart_rules"):
        ui.card_head("규칙별 오류 건수", "격리·검토된 오류를 규칙별로 셌어요")
        rule_chart(repo.get_rule_stats(run["run_id"]))

    ui.section("보고서 내려받기", "엑셀 보고서 하나에 요약·오류목록·대사결과·검토대상이 모두 들어 있어요.", small=True)
    files = [
        (f"report_{run['run_id']}.xlsx", "XLSX", "엑셀 보고서", "요약 · 오류목록 · 대사결과 · 검토대상 4개 시트", XLSX_MIME, "primary"),
        ("quarantine_transactions.csv", "CSV", "격리 거래", "격리된 거래와 오류 사유 — 원천 데이터 수정용", "text/csv", "secondary"),
        ("clean_transactions.csv", "CSV", "정상 거래", "대사에 쓰인 거래만 모은 파일", "text/csv", "secondary"),
    ]
    with st.container(key="files"):
        for index, (name, kind, title, text, mime, button_type) in enumerate(files):
            path = output_file(run, name)
            with st.container(key=f"frow_{index}"):
                info, action = st.columns([5, 1.4], vertical_alignment="center")
                with info:
                    ui.html(ui.file_row(kind, title, name, text, human_size(path) if path else "파일 없음"))
                if path is None:
                    action.caption("저장소가 초기화돼 파일이 없어요.")
                else:
                    action.download_button("내려받기", path.read_bytes(), file_name=name, mime=mime, type=button_type,
                                           key=f"download_{run['run_id']}_{name}", width="stretch")


# ------------------------------------------------------------------ 상세 내역


ISSUE_COLUMNS_VIEW = {
    "rule_id": "규칙",
    "title": "내용",
    "severity_label": "처리",
    "file": "파일",
    "row_no": "행",
    "record_key": "키",
    "column_name": "컬럼",
    "value": "값",
    "message": "상세 메시지",
}
RECON_COLUMNS_VIEW = {
    "account_no": "계좌번호",
    "result": "결과",
    "diff_cause": "차이 원인",
    "deposit_count_diff": "입금 건수 차이",
    "deposit_amount_diff": "입금 금액 차이",
    "withdrawal_count_diff": "출금 건수 차이",
    "withdrawal_amount_diff": "출금 금액 차이",
    "balance_diff": "잔액 차이",
    "txn_deposit_amount": "입금(거래)",
    "sum_deposit_amount": "입금(집계표)",
    "txn_withdrawal_amount": "출금(거래)",
    "sum_withdrawal_amount": "출금(집계표)",
    "opening_balance": "기초잔액",
    "closing_balance": "기말잔액",
}


def page_detail() -> None:
    runs = repo.list_runs()
    ui.section("상세 내역", "오류 하나하나와 계좌별 비교 결과를 골라 볼 수 있어요.", first=True)
    if runs.empty:
        no_runs_state()
        return
    picker, _ = st.columns([2, 3])
    with picker:
        run = run_picker(runs, "pick_detail")
    if run["status"] != RUN_SUCCESS:
        ui.note("실패한 실행이라 상세 내역이 없어요. 다른 실행을 고르세요.", "warning")
        return

    st.session_state.setdefault("detail_view", "오류 목록")
    view = st.segmented_control(
        "보기", ["오류 목록", "계좌별 대사 결과", "규칙 설명"], key="detail_view", required=True,
        label_visibility="collapsed",
    ) or "오류 목록"

    if view == "오류 목록":
        issues = repo.get_issues(run["run_id"])
        issues["title"] = issues["rule_id"].map(lambda r: RULE_GUIDES[r].title)
        issues["severity_label"] = issues["severity"].map({ERROR: "격리", WARN: "검토"})
        issues["file"] = issues["file_type"].map(DEFAULT_FILE_NAMES)
        issues["stage"] = issues["rule_id"].map(lambda r: RULE_STAGE_LABELS[RULES[r].stage])
        left, middle = st.columns([1, 2])
        severity = left.pills("처리", [ERROR, WARN], selection_mode="multi", key="f_severity",
                              format_func={ERROR: "격리 (ERROR)", WARN: "검토 (WARN)"}.get)
        stages = middle.pills("단계", list(RULE_STAGE_LABELS.values()), selection_mode="multi", key="f_stage")
        left, right = st.columns([2, 1])
        rule_options = sorted(issues["rule_id"].unique())
        st.session_state["f_rules"] = [r for r in st.session_state.get("f_rules", []) if r in rule_options]
        rules = left.multiselect("규칙", rule_options, key="f_rules", placeholder="전체 규칙",
                                 format_func=lambda r: f"{r} {RULE_GUIDES[r].title}")
        search = right.text_input("계좌번호·거래번호 검색", key="f_search", placeholder="예: 012-34 또는 T2026").strip()
        shown = issues
        if severity:
            shown = shown[shown["severity"].isin(severity)]
        if stages:
            shown = shown[shown["stage"].isin(stages)]
        if rules:
            shown = shown[shown["rule_id"].isin(rules)]
        if search:
            shown = shown[
                shown["record_key"].str.contains(search, regex=False, na=False)
                | shown["value"].str.contains(search, regex=False, na=False)
            ]
        st.caption(f"{len(shown):,}건 / 전체 {len(issues):,}건 · '행'은 원본 파일을 엑셀로 열었을 때의 행번호예요.")
        st.dataframe(shown[list(ISSUE_COLUMNS_VIEW)].rename(columns=ISSUE_COLUMNS_VIEW), hide_index=True,
                     width="stretch", height=480,
                     column_config={"행": st.column_config.NumberColumn("행", format="plain")})

    elif view == "계좌별 대사 결과":
        recon = repo.get_recon(run["run_id"])
        left, right = st.columns([1, 1])
        results = left.pills("결과", [RESULT_MISMATCH, RESULT_EXISTENCE, RESULT_EXCLUDED, RESULT_MATCH],
                             selection_mode="multi", key="f_result", format_func=lambda r: RESULT_GUIDES[r][1])
        causes = right.pills("차이 원인", [CAUSE_UNKNOWN, CAUSE_EXCLUDED_TXN, CAUSE_REVIEW_TXN, CAUSE_BALANCE],
                             selection_mode="multi", key="f_cause")
        search = st.text_input("계좌번호 검색", key="f_recon_search", placeholder="예: 077-88").strip()
        shown = recon
        if results:
            shown = shown[shown["result"].isin(results)]
        if causes:
            text = shown["diff_cause"].fillna("")
            shown = shown[text.apply(lambda value: any(c in value for c in causes))]
            for cause in causes:
                ui.note(CAUSE_GUIDES[cause].meaning, CAUSE_GUIDES[cause].level, cause)
        if search:
            shown = shown[shown["account_no"].str.contains(search, regex=False)]
        st.caption(f"{len(shown):,}개 계좌 / 전체 {len(recon):,}개 · 차이 = 거래내역 합계 − 집계표 값")
        number_columns = {
            label: st.column_config.NumberColumn(label, format="localized")
            for column, label in RECON_COLUMNS_VIEW.items()
            if column not in ("account_no", "result", "diff_cause")
        }
        st.dataframe(shown[list(RECON_COLUMNS_VIEW)].rename(columns=RECON_COLUMNS_VIEW), hide_index=True,
                     width="stretch", height=480, column_config=number_columns)

    else:
        for rule in all_rules():
            guide = RULE_GUIDES[rule.rule_id]
            kind = "격리" if rule.severity == ERROR else "검토"
            with st.expander(f"{rule.rule_id} · {guide.title} — {kind}"):
                st.markdown(f"**무엇이 문제인가요?** {guide.what}")
                st.markdown(f"**어떻게 하면 되나요?** {guide.action}")
                st.caption(f"단계: {RULE_STAGE_LABELS[rule.stage]} · 판단 기준 원문은 docs/업무규칙서.md")


# ------------------------------------------------------------------ 실행 이력


def page_history() -> None:
    runs = repo.list_runs()
    ui.section("실행 이력", "지금까지 실행한 검증이에요. 재처리는 원래 실행 번호와 함께 표시돼요.", first=True)
    if runs.empty:
        no_runs_state()
        return
    table = pd.DataFrame({
        "실행": runs["run_id"],
        "기준일": runs["base_date"],
        "상태": runs["status"].map({RUN_SUCCESS: "완료", RUN_FAILED: "실패"}).fillna(runs["status"]),
        "재처리 원본": runs["parent_run_id"],
        "시작": runs["started_at"],
        "격리": [None if not s else json.loads(s).get("quarantined_rows") for s in runs["stats_json"]],
        "실패 원인": runs["error_message"],
    })
    st.dataframe(table, hide_index=True, width="stretch")
    ui.section("다시 보기", small=True)
    left, middle, right = st.columns([2, 1, 1], vertical_alignment="bottom")
    with left:
        run = run_picker(runs, "pick_history")
    middle.button("결과 화면으로", key="history_open", on_click=go, args=(RESULT,), width="stretch")
    report = output_file(run, f"report_{run['run_id']}.xlsx")
    if report is not None:
        right.download_button("보고서 내려받기", report.read_bytes(), file_name=report.name, mime=XLSX_MIME,
                              key=f"history_download_{run['run_id']}", width="stretch")


# ------------------------------------------------------------------ 화면 구성

if "goto" in st.session_state:
    st.session_state["page"] = st.session_state.pop("goto")
st.session_state.setdefault("page", HOME)

ui.inject_css()
ui.top_bar("데이터는 이 컴퓨터의 data 폴더에만 저장돼요")
with st.container(key="nav"):
    page = st.segmented_control("메뉴", PAGES, key="page", required=True, label_visibility="collapsed") or HOME

{HOME: page_home, RUN: page_run, RESULT: page_result, DETAIL: page_detail, HISTORY: page_history}[page]()
ui.footer("거래내역 품질 검증 → 기준정보 정합성 → 집계표 대사")
