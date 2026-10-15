"""명령행(cli.py), 도구(tools/), 화면(app/)이 실제로 실행되는지 확인한다."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

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


def test_streamlit_app_runs_sample_and_shows_results(workspace):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=120)
    at.run()
    assert not at.exception

    at.button(key="sample_button").click().run()
    assert not at.exception
    assert any("완료" in s.value for s in at.success)
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["격리"] != "0"
    assert len(at.dataframe) >= 3  # 오류목록, 대사결과, 실행 이력

    at.button(key="run_button").click().run()  # 파일 없이 실행 → FAILED로 기록
    assert not at.exception
    assert any("입력 파일 누락" in e.value for e in at.error)


@pytest.mark.parametrize("script", ["run.sh", "run.bat"])
def test_one_click_scripts_launch_streamlit_app(script):
    text = (ROOT / script).read_text(encoding="utf-8")
    assert "uv run streamlit run app/streamlit_app.py" in text
