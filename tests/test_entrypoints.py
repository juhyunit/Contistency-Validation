"""명령행(cli.py), 도구(tools/), 화면(app/)이 실제로 실행되는지 확인한다."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(relative: str):
    spec = importlib.util.spec_from_file_location(relative.replace("/", "_").removesuffix(".py"), ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generate_evaluate_and_cli(workspace, tmp_path, capsys):
    sample = tmp_path / "sample"
    assert load_module("tools/generate_data.py").main(["--out-dir", str(sample)]) == 0
    assert (sample / "injected" / "injected_errors.csv").is_file()

    assert load_module("tools/evaluate.py").main(["--data-dir", str(sample / "injected")]) == 0
    assert "결과: 통과" in capsys.readouterr().out

    cli = load_module("cli.py")
    assert cli.main(["run", "--input-dir", str(sample / "clean"), "--base-date", "2026-10-15"]) == 0
    out = capsys.readouterr().out
    assert "SUCCESS" in out and "규칙별 오류: 없음" in out

    assert cli.main(["run", "--input-dir", str(tmp_path / "empty"), "--base-date", "2026-10-15"]) == 2
    (tmp_path / "partial").mkdir()
    assert cli.main(["run", "--input-dir", str(tmp_path / "partial"), "--base-date", "2026-10-15"]) == 1
    assert "입력 파일 누락" in capsys.readouterr().out

    assert cli.main(["runs"]) == 0
    assert "FAILED" in capsys.readouterr().out


def test_evaluate_fails_when_answer_does_not_match(workspace, tmp_path):
    sample = tmp_path / "sample"
    load_module("tools/generate_data.py").main(["--out-dir", str(sample)])
    answer = sample / "injected" / "injected_errors.csv"
    lines = answer.read_text(encoding="utf-8-sig").splitlines()
    answer.write_text("\n".join(lines[:1] + lines[2:]) + "\n", encoding="utf-8-sig")  # 정답 1건을 지우면 오탐이 생긴다
    assert load_module("tools/evaluate.py").main(["--data-dir", str(sample / "injected")]) == 1


def test_streamlit_app_pages_and_sample_flow(workspace):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=120)
    at.run()
    assert not at.exception
    # 실행 기록이 없을 때도 모든 페이지가 열린다 (빈 상태 안내)
    for page in ("검증 실행", "결과", "상세 내역", "실행 이력"):
        at.session_state["page"] = page
        at.run()
        assert not at.exception, page

    # 파일이 없으면 시작 버튼은 비활성
    at.session_state["page"] = "검증 실행"
    at.run()
    assert at.button(key="run_button").disabled

    # 시작하기의 샘플 체험 → 결과 화면으로 이동
    at.session_state["page"] = "시작하기"
    at.run()
    at.button(key="cta_sample").click().run()
    assert not at.exception
    assert at.session_state["page"] == "결과"
    keys = [b.key for b in at.button]
    assert keys[:3] == ["check_unknown_diff", "check_summary_errors", "check_quarantined"]

    # '목록 보기'는 상세 내역으로 이동하면서 필터를 채운다
    at.button(key="check_quarantined").click().run()
    assert not at.exception
    assert at.session_state["page"] == "상세 내역"
    assert at.session_state["f_severity"] == ["ERROR"]
    assert len(at.dataframe) == 1

    for view in ("계좌별 대사 결과", "규칙 설명"):
        at.session_state["detail_view"] = view
        at.run()
        assert not at.exception, view

    at.session_state["page"] = "실행 이력"
    at.run()
    assert not at.exception


def test_run_bat_is_plain_ascii_with_crlf_and_never_closes_silently():
    raw = (ROOT / "run.bat").read_bytes()
    assert raw.isascii()  # cmd.exe가 UTF-8 한글을 잘못 읽어 창이 닫히는 문제를 피한다
    lines = raw.split(b"\n")
    assert all(line.endswith(b"\r") for line in lines[:-1])
    text = raw.decode("ascii")
    assert "streamlit run app/streamlit_app.py" in text
    assert 'if not exist "pyproject.toml" goto not_extracted' in text
    # 실패 경로마다 pause가 있어 이유를 보여 준 뒤 멈춘다
    for label in (":not_extracted", ":no_uv", ":failed"):
        block = text.split(label, 1)[1].split("exit /b", 1)[0]
        assert "pause" in block, label


def test_run_sh_checks_project_folder_and_uv():
    text = (ROOT / "run.sh").read_text(encoding="utf-8")
    assert "\r" not in text
    assert "pyproject.toml" in text and "$HOME/.local/bin/uv" in text
    assert "streamlit run app/streamlit_app.py" in text
