"""화면 스타일과 HTML 구성 요소.

디자인 기준: docs/DESIGN-meta.md 토큰(흰 캔버스, 잉크·코발트, pill 버튼, 16·24·32px 카드)에
금융 앱처럼 숫자·표 중심의 타이포그래피를 더했다. 어두운 카드는 첫 화면, 결과 요약, 실행 확인 세 곳에만 쓴다.
데이터에서 온 문자열은 모두 esc()로 이스케이프한 뒤 HTML에 넣는다.
"""

from __future__ import annotations

from html import escape
from typing import Iterable, Sequence

import streamlit as st

from recon.detect import Classified
from recon.glossary import FILE_GUIDES, RULE_GUIDES, STAGE_GUIDES, FileGuide
from recon.insights import CheckItem, Verdict
from recon.models import DEFAULT_FILE_NAMES, FILE_TYPES
from recon.rules.registry import all_rules

# Meta 토큰 (docs/DESIGN-meta.md)
PRIMARY = "#0064e0"
INK_DEEP = "#0a1317"
INK = "#1c1e21"
STEEL = "#5d6c7b"
STONE = "#8595a4"
HAIRLINE_SOFT = "#dee3e9"
STATUS = {"good": "#31a24c", "warning": "#f2a918", "serious": "#ec835a", "critical": "#e41e3f", "info": "#0064e0"}
LEVEL_LABEL = {"critical": "긴급", "warning": "검토", "info": "참고"}
MONO = '"SF Mono", "JetBrains Mono", "Cascadia Mono", Consolas, ui-monospace, monospace'

CSS = """
:root {
  --c-primary: #0064e0; --c-primary-deep: #0457cb; --c-primary-soft: #0091ff;
  --c-ink-deep: #0a1317; --c-ink: #1c1e21; --c-charcoal: #444950; --c-slate: #4b4c4f;
  --c-steel: #5d6c7b; --c-stone: #8595a4; --c-hairline: #ced0d4; --c-hairline-soft: #dee3e9;
  --c-surface: #f1f4f7; --c-canvas: #ffffff;
  --c-good: #31a24c; --c-warning: #f2a918; --c-serious: #ec835a; --c-critical: #e41e3f;
  /* 어두운 카드 위 글자색 (대비 4.5:1 이상) */
  --d-good: #45c46a; --d-warning: #f7b928; --d-critical: #ff6378; --d-blue: #5cb2ff;
  --mono: "SF Mono", "JetBrains Mono", "Cascadia Mono", Consolas, ui-monospace, monospace;
}

/* ---------- 바탕 ---------- */
.stApp { background: var(--c-canvas); }
[data-testid="stMainBlockContainer"] { max-width: 1200px; padding: 0 32px 64px; }
header[data-testid="stHeader"] { background: transparent; }
[data-testid="stAppDeployButton"], [data-testid="stMainMenu"], [data-testid="stSidebarCollapsedControl"] { display: none; }
p, li, label { letter-spacing: -0.16px; }
/* 한국어는 단어 중간에서 줄을 바꾸지 않는다 */
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp p, .stApp li, .stApp label, .stApp span, .stApp b, .stApp dd, .stApp dt {
  word-break: keep-all; overflow-wrap: break-word; }
h1, h2, h3, h4 { font-feature-settings: "ss01", "ss02"; color: var(--c-ink-deep); letter-spacing: -0.3px; }
.rc-num { font-variant-numeric: tabular-nums; }
.rc-mono { font-family: var(--mono); font-size: .92em; letter-spacing: 0; }

/* ---------- 상단 바 · 메뉴 ---------- */
.rc-topbar { display: flex; align-items: center; justify-content: space-between; height: 64px; margin-bottom: 12px; }
.rc-logo { display: flex; align-items: center; gap: 10px; font-size: 19px; font-weight: 800; color: var(--c-ink-deep); letter-spacing: -0.5px; }
.rc-mark { flex: none; position: relative; width: 22px; height: 22px; border-radius: 7px; background: var(--c-ink-deep); }
.rc-mark::after { content: ""; position: absolute; right: 4px; bottom: 4px; width: 7px; height: 7px; border-radius: 2px; background: var(--c-primary-soft); }
.rc-logo small { font-size: 14px; font-weight: 500; color: var(--c-stone); letter-spacing: -0.1px; margin-left: 2px; }
.rc-topbar-note { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--c-steel); }
.rc-topbar-note i { width: 6px; height: 6px; border-radius: 9999px; background: var(--c-good); }

[data-testid="stButtonGroup"] > div { gap: 6px; flex-wrap: wrap; }
[data-testid="stButtonGroup"] button { border-radius: 100px !important; border: 1px solid var(--c-hairline) !important;
  background: var(--c-canvas) !important; color: var(--c-ink) !important; padding: 6px 16px !important;
  min-height: 36px; box-shadow: none !important; }
[data-testid="stButtonGroup"] button p { font-size: 14px; font-weight: 700; }
[data-testid="stButtonGroup"] button[aria-checked="true"], [data-testid="stButtonGroup"] button[data-selected="true"] {
  background: var(--c-ink-deep) !important; border-color: var(--c-ink-deep) !important; color: #fff !important; }
[data-testid="stButtonGroup"] button[aria-checked="true"] p, [data-testid="stButtonGroup"] button[data-selected="true"] p { color: #fff; }
.st-key-nav { padding-bottom: 20px; margin-bottom: 8px; border-bottom: 1px solid var(--c-hairline-soft); }
.st-key-nav button { min-height: 40px; padding: 8px 18px !important; }

/* ---------- 버튼 ---------- */
button[data-testid="stBaseButton-primary"] { background: var(--c-primary); border: none; color: #fff; min-height: 48px; padding: 0 30px; }
button[data-testid="stBaseButton-primary"]:hover { background: var(--c-primary-deep); color: #fff; }
button[data-testid="stBaseButton-primary"]:disabled { background: #bcc0c4; color: #fff; }
button[data-testid="stBaseButton-secondary"] { background: transparent; border: 2px solid var(--c-ink-deep);
  color: var(--c-ink-deep); min-height: 48px; padding: 0 28px; }
button[data-testid="stBaseButton-secondary"]:hover { background: var(--c-surface); border-color: var(--c-ink-deep); color: var(--c-ink-deep); }
button[data-testid="stBaseButton-primary"] p, button[data-testid="stBaseButton-secondary"] p { font-size: 14px; font-weight: 700; }
button[data-testid="stBaseButton-tertiary"] { color: var(--c-primary-deep); padding: 0; min-height: 32px; }
button[data-testid="stBaseButton-tertiary"] p { font-size: 14px; font-weight: 700; }
button[data-testid="stBaseButton-tertiary"]:hover { color: var(--c-primary); }

/* ---------- 어두운 카드 (첫 화면 · 결과 요약 · 실행 확인) ---------- */
.st-key-hero, .rc-dash, .st-key-step3 {
  position: relative; overflow: hidden; isolation: isolate; color: #fff; border-radius: 32px;
  background-color: var(--c-ink-deep);
  background-image: linear-gradient(rgba(255,255,255,.035) 1px, transparent 1px),
                    linear-gradient(90deg, rgba(255,255,255,.035) 1px, transparent 1px);
  background-size: 56px 56px; background-position: -1px -1px; }
.st-key-hero::before, .rc-dash::before, .st-key-step3::before { content: ""; position: absolute; z-index: -1; pointer-events: none;
  width: 760px; height: 760px; right: -240px; top: -300px;
  background: radial-gradient(closest-side, var(--glow, rgba(0,145,255,.5)), rgba(0,100,224,.18) 48%, transparent 72%); }
.st-key-hero::after, .st-key-step3::after { content: ""; position: absolute; z-index: -1; pointer-events: none;
  width: 520px; height: 520px; right: 200px; bottom: -340px; background: radial-gradient(closest-side, rgba(161,33,206,.34), transparent 70%); }
.st-key-hero { padding: 56px; }
.st-key-hero button[data-testid="stBaseButton-primary"], .st-key-hero button[data-testid="stBaseButton-primary"]:hover {
  background: #fff; color: var(--c-ink-deep); }
.st-key-hero button[data-testid="stBaseButton-primary"] p { color: var(--c-ink-deep); }
.st-key-hero button[data-testid="stBaseButton-primary"]:hover { background: #e9eef3; }
.st-key-hero button[data-testid="stBaseButton-secondary"], .st-key-step3 button[data-testid="stBaseButton-secondary"] {
  border-color: rgba(255,255,255,.85); color: #fff; }
.st-key-hero button[data-testid="stBaseButton-secondary"] p, .st-key-step3 button[data-testid="stBaseButton-secondary"] p { color: #fff; }
.st-key-hero button[data-testid="stBaseButton-secondary"]:hover, .st-key-step3 button[data-testid="stBaseButton-secondary"]:hover {
  background: rgba(255,255,255,.08); color: #fff; border-color: #fff; }
.st-key-step3 button[data-testid="stBaseButton-primary"]:disabled { background: rgba(255,255,255,.12); color: rgba(255,255,255,.45); }
.st-key-step3 button[data-testid="stBaseButton-primary"]:disabled p { color: rgba(255,255,255,.45); }

/* 첫 화면 문구 */
.rc-eyebrow { display: inline-flex; align-items: center; gap: 8px; padding: 6px 14px; border-radius: 100px;
  background: rgba(255,255,255,.1); color: rgba(255,255,255,.88); font-size: 13px; font-weight: 700; }
.rc-eyebrow i { width: 8px; height: 8px; border-radius: 9999px; background: var(--c-primary-soft); display: inline-block; }
.rc-hero-title { font-size: 52px; line-height: 1.16; font-weight: 500; color: #fff; margin: 20px 0 16px; letter-spacing: -1px;
  font-feature-settings: "ss01", "ss02"; }
.rc-hero-title em { font-style: normal; background: linear-gradient(90deg, #5cb2ff, #c48bff);
  -webkit-background-clip: text; background-clip: text; color: transparent; }
.rc-hero-lead { font-size: 18px; line-height: 1.6; color: rgba(255,255,255,.74); margin: 0 0 12px; max-width: 560px; }

/* 원장(레저) 미리보기: 거래 행이 판정되는 모습 */
.rc-ledger { background: rgba(255,255,255,.04); border: 1px solid rgba(255,255,255,.1); border-radius: 24px;
  padding: 18px 22px 20px; backdrop-filter: blur(8px); font-variant-numeric: tabular-nums; }
.rc-ledger-head { display: flex; justify-content: space-between; font-size: 12px; font-weight: 600; color: rgba(255,255,255,.5);
  padding-bottom: 10px; border-bottom: 1px solid rgba(255,255,255,.08); }
.rc-ledger-row { display: grid; grid-template-columns: minmax(0, 1fr) auto 44px; gap: 16px; align-items: center;
  padding: 11px 0; border-bottom: 1px solid rgba(255,255,255,.06); font-size: 13px; }
.rc-ledger-row .id { font-family: var(--mono); color: rgba(255,255,255,.82); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rc-ledger-row .amt { font-family: var(--mono); color: #fff; text-align: right; }
.rc-ledger-row .st { text-align: right; font-weight: 700; font-size: 12px; }
.rc-ledger-foot { margin-top: 16px; }
.d-good { color: var(--d-good); } .d-warning { color: var(--d-warning); } .d-critical { color: var(--d-critical); }
.d-muted { color: rgba(255,255,255,.55); }

/* 구성 막대 (세그먼트 사이 2px 간격) */
.rc-seg { display: flex; gap: 2px; height: 8px; border-radius: 100px; overflow: hidden; }
.rc-seg > span { display: block; height: 100%; min-width: 3px; }
.rc-seg-legend { display: flex; flex-wrap: wrap; gap: 6px 18px; margin-top: 12px; font-size: 12px; }
.rc-seg-legend span { display: inline-flex; align-items: center; gap: 6px; }
.rc-seg-legend i { width: 8px; height: 8px; border-radius: 2px; display: inline-block; }
.rc-seg-legend b { font-family: var(--mono); font-weight: 600; }

/* ---------- 섹션 제목 ---------- */
.rc-section { margin: 80px 0 28px; }
.rc-section.first { margin-top: 28px; }
.rc-section-sm { margin: 56px 0 18px; }
.rc-title { font-size: 36px; line-height: 1.28; font-weight: 500; color: var(--c-ink-deep); margin: 0; letter-spacing: -0.8px;
  font-feature-settings: "ss01", "ss02"; }
.rc-title-sm { font-size: 22px; line-height: 1.3; font-weight: 700; color: var(--c-ink-deep); margin: 0; letter-spacing: -0.4px; }
.rc-lead { font-size: 18px; line-height: 1.5; font-weight: 400; color: var(--c-steel); margin: 10px 0 0; }
.rc-lead-sm { font-size: 15px; line-height: 1.5; color: var(--c-steel); margin: 6px 0 0; }

/* ---------- 상태 표시: 점 + 글자 (아이콘 배지 대신) ---------- */
.rc-status { display: inline-flex; align-items: center; gap: 7px; font-size: 13px; font-weight: 700; color: var(--c-ink); white-space: nowrap; }
.rc-status i { width: 7px; height: 7px; border-radius: 9999px; background: var(--c-stone); flex: none; }
.rc-status.good i { background: var(--c-good); } .rc-status.warning i { background: var(--c-warning); }
.rc-status.serious i { background: var(--c-serious); } .rc-status.critical i { background: var(--c-critical); }
.rc-status.info i { background: var(--c-primary); }
.rc-status.idle i { background: transparent; border: 1.5px solid var(--c-stone); }
.rc-status.on-dark { color: rgba(255,255,255,.92); }

/* ---------- 동작 방식: 타임라인 ---------- */
.rc-steps { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); }
.rc-step { position: relative; padding: 26px 24px 0 0; border-top: 1px solid var(--c-hairline); }
.rc-step::before { content: ""; position: absolute; top: -5px; left: 0; width: 9px; height: 9px; border-radius: 9999px; background: var(--c-ink-deep); }
.rc-step.io::before { background: var(--c-canvas); border: 1.5px solid var(--c-ink-deep); width: 8px; height: 8px; }
.rc-step .no { font-family: var(--mono); font-size: 12px; color: var(--c-stone); }
.rc-step b { display: block; font-size: 18px; font-weight: 700; color: var(--c-ink-deep); margin: 10px 0 6px; letter-spacing: -0.3px; }
.rc-step span { display: block; font-size: 14px; line-height: 1.5; color: var(--c-steel); }

/* ---------- 규칙 카탈로그 ---------- */
.rc-catalog { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 20px; }
.rc-catalog-col { background: var(--c-surface); border-radius: 24px; padding: 28px 28px 18px; }
.rc-catalog-col .no { font-family: var(--mono); font-size: 12px; color: var(--c-stone); }
.rc-catalog-col h4 { font-size: 22px; font-weight: 700; margin: 8px 0 6px; letter-spacing: -0.4px; }
.rc-catalog-col p { font-size: 14px; line-height: 1.5; color: var(--c-steel); margin: 0 0 16px; }
.rc-rule { display: grid; grid-template-columns: 52px minmax(0, 1fr) auto; gap: 10px; align-items: baseline;
  padding: 10px 0; border-top: 1px solid var(--c-hairline-soft); font-size: 14px; color: var(--c-ink); }
.rc-rule code { font-family: var(--mono); font-size: 12px; color: var(--c-steel); background: none; padding: 0; }
.rc-rule em { font-style: normal; font-size: 12px; color: var(--c-stone); }

/* ---------- 결과 읽는 법 ---------- */
.rc-legend-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0; }
.rc-legend-item { padding: 4px 24px 4px 20px; border-left: 1px solid var(--c-hairline-soft); }
.rc-legend-item:first-child { border-left: none; padding-left: 0; }
.rc-legend-item p { margin: 10px 0 0; font-size: 14px; line-height: 1.55; color: var(--c-steel); }

/* ---------- 검증 실행 단계 ---------- */
.st-key-step1, .st-key-step2 { border: 1px solid var(--c-hairline-soft); border-radius: 24px; padding: 32px; margin-bottom: 20px; }
.st-key-step3 { padding: 36px 40px; }
.rc-step-head { margin-bottom: 8px; }
.rc-step-head .no { font-family: var(--mono); font-size: 12px; color: var(--c-stone); letter-spacing: .02em; }
.rc-step-head h3 { margin: 6px 0 6px; font-size: 24px; font-weight: 700; letter-spacing: -0.4px; }
.rc-step-head p { margin: 0; color: var(--c-steel); font-size: 15px; line-height: 1.5; }
.rc-confirm h3 { color: #fff; font-size: 28px; font-weight: 600; margin: 8px 0 20px; letter-spacing: -0.5px; }
.rc-confirm .no { font-family: var(--mono); font-size: 12px; color: rgba(255,255,255,.5); }
.rc-confirm dl { margin: 0 !important; padding: 0 !important; display: grid; gap: 0; max-width: 520px; }
.rc-confirm dl div { margin: 0 !important; }
.rc-confirm dl div { display: flex; justify-content: space-between; gap: 16px; padding: 11px 0; border-top: 1px solid rgba(255,255,255,.1); font-size: 14px; }
.rc-confirm dt { color: rgba(255,255,255,.6); } .rc-confirm dd { margin: 0; color: #fff; font-weight: 600; font-variant-numeric: tabular-nums; }

/* 파일 슬롯 */
.rc-slots { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.rc-slot { border-radius: 16px; padding: 18px; background: var(--c-surface); border: 1px solid transparent; min-height: 128px; }
.rc-slot.ready { background: var(--c-canvas); border-color: var(--c-hairline); }
.rc-slot-top { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.rc-slot code { font-family: var(--mono); font-size: 11px; color: var(--c-stone); background: none; padding: 0; }
.rc-slot b { display: block; font-size: 16px; font-weight: 700; color: var(--c-ink-deep); margin-top: 14px; }
.rc-slot span.role { display: block; font-size: 13px; color: var(--c-steel); line-height: 1.45; margin-top: 4px; }
.rc-slot .file { margin-top: 10px; font-family: var(--mono); font-size: 12px; color: var(--c-ink); word-break: break-all; }

/* 업로드 영역 */
[data-testid="stFileUploaderDropzone"] { background: var(--c-surface); border: 1.5px dashed var(--c-hairline); border-radius: 20px; padding: 26px; }
[data-testid="stFileUploaderDropzone"] button { border-radius: 100px; font-size: 0; }
[data-testid="stFileUploaderDropzone"] button * { font-size: 0 !important; }
[data-testid="stFileUploaderDropzone"] button svg { display: none; }
[data-testid="stFileUploaderDropzone"] button::after { content: "파일 선택"; font-size: 14px; font-weight: 700; white-space: nowrap; }
[data-testid="stFileUploaderDropzoneInstructions"] > * { display: none; }
[data-testid="stFileUploaderDropzoneInstructions"]::after { content: "여기로 파일 4개를 끌어다 놓거나 '파일 선택'을 누르세요 · CSV, XLSX · 파일당 200MB";
  font-size: 14px; color: var(--c-steel); }

/* 컬럼 안내 표 */
.rc-spec { width: 100%; border-collapse: collapse; font-size: 14px; }
.rc-spec td, .rc-spec th { padding: 10px 12px 10px 0; border-bottom: 1px solid var(--c-hairline-soft); text-align: left; vertical-align: top; }
.rc-spec th { color: var(--c-stone); font-weight: 600; font-size: 12px; }
.rc-spec td:first-child { font-family: var(--mono); font-size: 13px; color: var(--c-ink); white-space: nowrap; }
.rc-spec td:last-child { color: var(--c-charcoal); font-family: var(--mono); font-size: 12px; }
.rc-opt { font-family: inherit; color: var(--c-stone); font-size: 11px; margin-left: 6px; }

/* ---------- 결과 요약 대시보드 ---------- */
.rc-dash { padding: 40px 44px 36px; }
.rc-dash-grid { display: grid; grid-template-columns: minmax(0, 1.7fr) minmax(0, 1fr); gap: 48px; align-items: center; }
.rc-dash-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 14px; font-size: 13px; color: rgba(255,255,255,.6); }
.rc-dash-meta > span:last-child { font-variant-numeric: tabular-nums; }
.rc-dash h2 { color: #fff; font-size: 30px; line-height: 1.28; font-weight: 600; margin: 18px 0 8px; letter-spacing: -0.7px; }
.rc-dash .sub { color: rgba(255,255,255,.66); font-size: 15px; line-height: 1.5; margin: 0; }
.rc-kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); margin: 32px 0 18px; }
.rc-kpi { padding: 0 18px; border-left: 1px solid rgba(255,255,255,.1); }
.rc-kpi:first-child { padding-left: 0; border-left: none; }
.rc-kpi label { display: block; font-size: 12px; font-weight: 600; color: rgba(255,255,255,.55); margin-bottom: 8px; }
.rc-kpi div { font-size: 30px; font-weight: 600; letter-spacing: -0.8px; color: #fff; line-height: 1.1; }
.rc-kpi div small { font-size: 13px; font-weight: 500; color: rgba(255,255,255,.5); margin-left: 3px; letter-spacing: 0; }
.rc-ring-wrap { display: flex; flex-direction: column; align-items: center; }
.rc-ring { position: relative; width: 196px; height: 196px; }
.rc-ring-arc { position: absolute; inset: 0; border-radius: 9999px;
  background: conic-gradient(#0091ff 0deg, #5cb2ff calc(var(--p) * 3.6deg), rgba(255,255,255,.1) calc(var(--p) * 3.6deg) 360deg);
  -webkit-mask: radial-gradient(farthest-side, transparent calc(100% - 15px), #000 calc(100% - 14px));
  mask: radial-gradient(farthest-side, transparent calc(100% - 15px), #000 calc(100% - 14px)); }
.rc-ring-center { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; }
.rc-ring-center b { font-size: 40px; font-weight: 600; letter-spacing: -1.2px; color: #fff; line-height: 1; }
.rc-ring-center span { margin-top: 6px; font-size: 12px; color: rgba(255,255,255,.55); font-weight: 600; }
.rc-ring-legend { width: 100%; max-width: 280px; margin-top: 22px; }
.rc-ring-legend div { display: flex; justify-content: space-between; padding: 8px 0; border-top: 1px solid rgba(255,255,255,.08); font-size: 13px; }
.rc-ring-legend b { font-family: var(--mono); font-weight: 600; color: #fff; }

/* ---------- 먼저 확인할 것: 작업 목록 ---------- */
.st-key-queue { border: 1px solid var(--c-hairline-soft); border-radius: 24px; padding: 6px 28px; }
[class*="st-key-qrow_"] { padding: 20px 0; border-top: 1px solid var(--c-hairline-soft); }
.st-key-qrow_1 { border-top: none; }
.rc-q h4 { margin: 8px 0 6px; font-size: 17px; font-weight: 700; color: var(--c-ink-deep); line-height: 1.4; letter-spacing: -0.3px; }
.rc-q p { margin: 0; font-size: 14px; line-height: 1.55; color: var(--c-steel); }
.rc-q .todo { margin-top: 8px; font-size: 14px; color: var(--c-ink); }
.rc-q .todo b { font-weight: 700; margin-right: 6px; }
.rc-q .parts { margin-top: 8px; font-size: 13px; color: var(--c-steel); }
.rc-q .parts b { font-family: var(--mono); font-weight: 600; color: var(--c-ink); margin-left: 4px; }
[class*="st-key-check_"] { display: flex; justify-content: flex-end; }
.rc-q-count { text-align: right; font-size: 30px; font-weight: 600; color: var(--c-ink-deep); letter-spacing: -0.8px; white-space: nowrap; }
.rc-q-count small { font-size: 13px; font-weight: 500; color: var(--c-stone); margin-left: 3px; letter-spacing: 0; }

/* 차트 카드 · 파일 목록 */
.st-key-chart_diff, .st-key-chart_rules, .st-key-files { border: 1px solid var(--c-hairline-soft); border-radius: 24px; padding: 26px 28px; }
.rc-card-head h4 { margin: 0; font-size: 17px; font-weight: 700; color: var(--c-ink-deep); letter-spacing: -0.3px; }
.rc-card-head p { margin: 4px 0 8px; font-size: 13px; color: var(--c-steel); }
[class*="st-key-frow_"] { padding: 14px 0; border-top: 1px solid var(--c-hairline-soft); }
.st-key-frow_0 { border-top: none; }
.rc-file { display: grid; grid-template-columns: 48px minmax(0, 1fr); gap: 16px; align-items: center; }
.rc-file-type { width: 48px; height: 48px; border-radius: 12px; background: var(--c-surface); display: flex; align-items: center; justify-content: center;
  font-family: var(--mono); font-size: 11px; font-weight: 700; color: var(--c-charcoal); }
.rc-file-type.xlsx { background: var(--c-ink-deep); color: #fff; }
.rc-file b { display: block; font-size: 15px; font-weight: 700; color: var(--c-ink-deep); }
.rc-file span { display: block; font-size: 13px; color: var(--c-steel); margin-top: 2px; }
.rc-file code { font-family: var(--mono); font-size: 12px; color: var(--c-stone); background: none; padding: 0; }

/* ---------- 펼치기 · 알림 · 빈 상태 ---------- */
[data-testid="stExpander"] details { border: none; border-bottom: 1px solid var(--c-hairline-soft); border-radius: 0; background: transparent; }
[data-testid="stExpander"] summary { padding: 20px 2px; }
[data-testid="stExpander"] summary p { font-size: 16px; font-weight: 700; color: var(--c-ink-deep); }
.st-key-step1 [data-testid="stExpander"] details, .st-key-step2 [data-testid="stExpander"] details {
  border: 1px solid var(--c-hairline-soft); border-radius: 16px; }
.st-key-step1 [data-testid="stExpander"] summary, .st-key-step2 [data-testid="stExpander"] summary { padding: 16px 20px; }
.rc-note { display: flex; gap: 12px; align-items: baseline; border-radius: 14px; padding: 14px 18px; background: var(--c-surface);
  color: var(--c-ink); font-size: 14px; line-height: 1.55; margin: 14px 0; border-left: 3px solid var(--c-primary); }
.rc-note.warning { border-left-color: var(--c-warning); } .rc-note.critical { border-left-color: var(--c-critical); }
.rc-note.good { border-left-color: var(--c-good); }
.rc-note b { color: var(--c-ink-deep); white-space: nowrap; }
.rc-empty { text-align: center; background: var(--c-surface); border-radius: 32px; padding: 64px 32px; margin-bottom: 20px; }
.rc-empty h3 { margin: 0 0 8px; font-size: 26px; font-weight: 600; }
.rc-empty p { margin: 0; color: var(--c-steel); }

/* ---------- 푸터 ---------- */
.rc-footer { margin-top: 96px; padding: 28px 0 8px; border-top: 1px solid var(--c-hairline-soft); color: var(--c-stone);
  font-size: 12px; display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; }

/* ---------- 반응형 ---------- */
@media (max-width: 1023px) {
  .rc-steps { grid-template-columns: repeat(2, minmax(0, 1fr)); row-gap: 28px; }
  .rc-catalog { grid-template-columns: 1fr; }
  .rc-legend-grid, .rc-slots { grid-template-columns: repeat(2, minmax(0, 1fr)); row-gap: 20px; }
  .rc-legend-item:nth-child(3) { border-left: none; padding-left: 0; }
  .rc-dash-grid { grid-template-columns: 1fr; }
  .rc-hero-title { font-size: 40px; }
}
@media (max-width: 640px) {
  [data-testid="stMainBlockContainer"] { padding: 0 16px 48px; }
  .rc-topbar-note, .rc-logo small { display: none; }
  .st-key-hero { padding: 32px 22px; border-radius: 24px; }
  .rc-hero-title { font-size: 32px; }
  .rc-steps, .rc-legend-grid, .rc-slots { grid-template-columns: 1fr; }
  .rc-legend-item { border-left: none; padding-left: 0; }
  .rc-title { font-size: 28px; }
  .rc-dash, .st-key-step3 { padding: 26px 22px; border-radius: 24px; }
  .rc-dash h2 { font-size: 24px; }
  .rc-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); row-gap: 18px; }
  .rc-kpi:nth-child(3) { border-left: none; padding-left: 0; }
  .st-key-step1, .st-key-step2 { padding: 22px; }
  .st-key-queue, .st-key-chart_diff, .st-key-chart_rules, .st-key-files { padding: 6px 18px; }
}
"""


def esc(value: object) -> str:
    return escape("" if value is None else str(value))


def html(markup: str) -> None:
    st.html(markup)


def inject_css() -> None:
    st.html(f"<style>{CSS}</style>")


def status(text: str, level: str = "idle", on_dark: bool = False) -> str:
    return f'<span class="rc-status {level}{" on-dark" if on_dark else ""}"><i></i>{esc(text)}</span>'


def top_bar(note: str) -> None:
    html(
        '<div class="rc-topbar"><div class="rc-logo"><span class="rc-mark"></span>Recon'
        "<small>금융 데이터 검증·대사</small></div>"
        f'<div class="rc-topbar-note"><i></i>{esc(note)}</div></div>'
    )


def section(title: str, lead: str = "", small: bool = False, first: bool = False) -> None:
    """섹션 제목. first=True는 페이지 맨 위 제목."""
    title_class = "rc-title-sm" if small else "rc-title"
    lead_class = "rc-lead-sm" if small else "rc-lead"
    wrapper = "rc-section-sm" if small else "rc-section" + (" first" if first else "")
    html(
        f'<div class="{wrapper}"><h2 class="{title_class}">{esc(title)}</h2>'
        + (f'<p class="{lead_class}">{esc(lead)}</p>' if lead else "")
        + "</div>"
    )


def segmented(parts: Sequence[tuple[str, int, str]], dark: bool = True) -> str:
    """구성 막대 + 범례. parts = (이름, 값, 색)."""
    total = sum(v for _, v, _ in parts) or 1
    bar = "".join(
        f'<span style="flex:{v} 0 0;background:{color}" title="{esc(name)} {v:,}"></span>' for name, v, color in parts if v
    )
    text_class = "d-muted" if dark else ""
    legend = "".join(
        f'<span class="{text_class}"><i style="background:{color}"></i>{esc(name)} <b>{v:,}</b>'
        f'<em style="font-style:normal;opacity:.7">&nbsp;{v / total:.1%}</em></span>'
        for name, v, color in parts
    )
    return f'<div class="rc-seg">{bar}</div><div class="rc-seg-legend">{legend}</div>'


# ---------------------------------------------------------------- 시작하기


def hero_text() -> None:
    html(
        '<span class="rc-eyebrow"><i></i>엑셀 대사를 자동으로</span>'
        '<h1 class="rc-hero-title">하루치 거래내역,<br><em>3단계로 자동 검증</em>합니다</h1>'
        '<p class="rc-hero-lead">파일 4개를 올리면 오류가 있는 거래는 따로 빼 두고, 계좌별로 거래내역 합계와 '
        "집계표가 맞는지 비교해 엑셀 보고서로 정리해 드려요.</p>"
    )


def hero_ledger() -> None:
    rows = [
        ("T20261015000001", "1,500,000", "정상", "d-good"),
        ("T20261015000083", "12000.75", "격리", "d-critical"),
        ("T20261015900002", "50,000", "검토", "d-warning"),
        ("T20261015000188", "—", "격리", "d-critical"),
        ("077-88-947837", "−23,217,000", "차이", "d-critical"),
    ]
    body = "".join(
        f'<div class="rc-ledger-row"><span class="id">{esc(i)}</span><span class="amt">{esc(a)}</span>'
        f'<span class="st {cls}">{esc(s)}</span></div>'
        for i, a, s, cls in rows
    )
    foot = segmented([("정상", 4948, "#5cb2ff"), ("검토", 7, "#f7b928"), ("격리", 62, "#ff6378")])
    html(
        '<div class="rc-ledger"><div class="rc-ledger-head"><span>거래번호 · 계좌</span><span>금액 · 판정</span></div>'
        f'{body}<div class="rc-ledger-foot">{foot}</div>'
        '<div class="d-muted" style="font-size:11px;margin-top:10px">샘플 데이터 5,017건을 검증한 예시</div></div>'
    )


def steps() -> None:
    items = [
        ("io", "IN", "파일 4개 올리기", "거래내역, 계좌별 집계표, 계좌·거래코드 마스터"),
        ("", "01", "품질 검증", "빈 칸·형식·중복을 찾아 오류 거래를 격리해요"),
        ("", "02", "기준정보 확인", "없는 계좌, 해지 후 거래, 잘못된 코드를 걸러요"),
        ("", "03", "집계표 대사", "정상 거래만 계좌별로 더해 집계표와 비교해요"),
        ("io", "OUT", "결과와 보고서", "먼저 볼 것을 정리하고 엑셀·CSV로 내려받아요"),
    ]
    html(
        '<div class="rc-steps">'
        + "".join(
            f'<div class="rc-step {kind}"><div class="no">{esc(no)}</div><b>{esc(title)}</b><span>{esc(text)}</span></div>'
            for kind, no, title, text in items
        )
        + "</div>"
    )


def rule_catalog() -> None:
    rules = all_rules()
    columns = [("DQ", ("DQ",)), ("MD", ("MD",)), ("RC", ("SM", "RC"))]
    cols = []
    for key, stages in columns:
        guide = STAGE_GUIDES[key]
        rows = "".join(
            f'<div class="rc-rule"><code>{esc(r.rule_id)}</code><span>{esc(RULE_GUIDES[r.rule_id].title)}</span>'
            f'<em>{"검토" if r.severity == "WARN" else ""}</em></div>'
            for r in rules
            if r.stage in stages
        )
        cols.append(
            f'<div class="rc-catalog-col"><div class="no">0{esc(guide.number)}</div><h4>{esc(guide.title)}</h4>'
            f"<p>{esc(guide.summary)}</p>{rows}</div>"
        )
    html(f'<div class="rc-catalog">{"".join(cols)}</div>')


def reading_guide() -> None:
    items = [
        ("good", "정상 반영", "오류가 없어 계좌별 합계 계산에 쓰인 거래예요."),
        ("critical", "격리", "오류가 있어 대사에서 뺀 거래예요. 고친 뒤 다시 실행하면 돼요."),
        ("warning", "검토 필요", "대사에는 넣었지만 의심 중복처럼 사람이 판단해야 하는 거래예요."),
        ("serious", "계좌 차이", "거래내역 합계와 집계표가 다른 계좌예요. 원인 표시를 함께 보여 드려요."),
    ]
    html(
        '<div class="rc-legend-grid">'
        + "".join(f'<div class="rc-legend-item">{status(label, level)}<p>{esc(text)}</p></div>' for level, label, text in items)
        + "</div>"
    )


# ---------------------------------------------------------------- 검증 실행


def step_head(number: str, title: str, text: str) -> None:
    html(f'<div class="rc-step-head"><div class="no">STEP {esc(number)}</div><h3>{esc(title)}</h3><p>{esc(text)}</p></div>')


def file_slots(classified: Classified) -> None:
    slots = []
    for file_type in FILE_TYPES:
        guide = FILE_GUIDES[file_type]
        assigned = classified.files.get(file_type)
        state = status("준비됨", "good") if assigned else status("필요", "idle")
        file_line = f'<div class="file">{esc(assigned[0])}</div>' if assigned else ""
        slots.append(
            f'<div class="rc-slot{" ready" if assigned else ""}"><div class="rc-slot-top">{state}'
            f"<code>{esc(DEFAULT_FILE_NAMES[file_type])}</code></div>"
            f'<b>{esc(guide.title)}</b><span class="role">{esc(guide.role)}</span>{file_line}</div>'
        )
    html(f'<div class="rc-slots">{"".join(slots)}</div>')


def spec_table(guide: FileGuide) -> None:
    rows = "".join(
        f"<tr><td>{esc(c.name)}{'' if c.required else '<span class=rc-opt>선택</span>'}</td>"
        f"<td>{esc(c.meaning)}</td><td>{esc(c.example) or '빈 값'}</td></tr>"
        for c in guide.columns
    )
    html(f'<table class="rc-spec"><tr><th>컬럼</th><th>뜻</th><th>예</th></tr>{rows}</table>')


def confirm_panel(ready: int, base_date: str, parent_label: str) -> None:
    state = "준비 완료" if ready == 4 else f"{4 - ready}개 더 필요"
    html(
        '<div class="rc-confirm"><div class="no">STEP 03</div>'
        f"<h3>{'모두 준비됐어요. 검증을 시작하세요' if ready == 4 else '파일 4개가 준비되면 시작할 수 있어요'}</h3><dl>"
        f'<div><dt>입력 파일</dt><dd><span class="{"d-good" if ready == 4 else "d-warning"}">{ready} / 4</span> · {esc(state)}</dd></div>'
        f"<div><dt>기준일</dt><dd>{esc(base_date)}</dd></div>"
        f"<div><dt>재처리</dt><dd>{esc(parent_label)}</dd></div>"
        "</dl></div>"
    )


# ---------------------------------------------------------------- 결과


def ring(ratio: float, label: str) -> str:
    """계좌 일치율 링. st.html은 SVG를 걸러내므로 CSS conic-gradient로 그린다 (옅은 트랙 위에 같은 계열 색으로 채움)."""
    ratio = max(0.0, min(ratio, 1.0))
    return (
        f'<div class="rc-ring" role="img" aria-label="{esc(label)} {ratio:.0%}">'
        f'<div class="rc-ring-arc" style="--p:{ratio * 100:.2f}"></div>'
        f'<div class="rc-ring-center"><b class="rc-num">{ratio * 100:.0f}%</b><span>{esc(label)}</span></div></div>'
    )


def dashboard(
    v: Verdict,
    meta: Iterable[str],
    kpis: Sequence[tuple[str, int, str]] = (),
    composition: Sequence[tuple[str, int, str]] = (),
    accounts: Sequence[tuple[str, int, str]] = (),
) -> None:
    """결과 요약: 왼쪽은 판정·핵심 숫자·거래 구성, 오른쪽은 계좌 일치율."""
    glow = {"good": "rgba(49,162,76,.45)", "warning": "rgba(242,169,24,.40)", "critical": "rgba(228,30,63,.36)"}[v.level]
    meta_html = "<span>" + " · ".join(esc(m) for m in meta) + "</span>"
    left = (
        f'<div class="rc-dash-meta">{status(v.badge, v.level, on_dark=True)}{meta_html}</div>'
        f"<h2>{esc(v.headline)}</h2><p class='sub'>{esc(v.summary)}</p>"
    )
    if kpis:
        left += '<div class="rc-kpis">' + "".join(
            f'<div class="rc-kpi"><label>{esc(label)}</label><div class="rc-num">{value:,}<small>{esc(unit)}</small></div></div>'
            for label, value, unit in kpis
        ) + "</div>"
    if composition:
        left += segmented(composition)
    right = ""
    if accounts:
        total = sum(n for _, n, _ in accounts) or 1
        matched = accounts[0][1]
        legend = "".join(
            f'<div><span class="d-muted">{status(name, level, on_dark=True)}</span><b>{n:,}</b></div>' for name, n, level in accounts
        )
        right = f'<div class="rc-ring-wrap">{ring(matched / total, "계좌 일치율")}<div class="rc-ring-legend">{legend}</div></div>'
    grid = f'<div class="rc-dash-grid"><div>{left}</div>{right}</div>' if right else left
    html(f'<div class="rc-dash" style="--glow:{glow}">{grid}</div>')


def queue_item(item: CheckItem) -> str:
    parts = " · ".join(f"{esc(name)}<b>{count:,}</b>" for name, count in item.breakdown)
    return (
        f'<div class="rc-q">{status(LEVEL_LABEL[item.level], item.level)}<h4>{esc(item.title)}</h4>'
        f"<p>{esc(item.description)}</p>"
        f'<div class="todo"><b>할 일</b>{esc(item.action)}</div>'
        + (f'<div class="parts">{parts}</div>' if parts else "")
        + "</div>"
    )


def queue_count(item: CheckItem) -> str:
    return f'<div class="rc-q-count rc-num">{item.count:,}<small>{esc(item.unit)}</small></div>'


def card_head(title: str, text: str) -> None:
    html(f'<div class="rc-card-head"><h4>{esc(title)}</h4><p>{esc(text)}</p></div>')


def file_row(kind: str, title: str, name: str, text: str, size: str) -> str:
    return (
        f'<div class="rc-file"><div class="rc-file-type {esc(kind.lower())}">{esc(kind)}</div>'
        f"<div><b>{esc(title)}</b><span>{esc(text)}</span><code>{esc(name)} · {esc(size)}</code></div></div>"
    )


# ---------------------------------------------------------------- 공통


def note(text: str, level: str = "info", title: str = "") -> None:
    head = f"<b>{esc(title)}</b>" if title else ""
    html(f'<div class="rc-note {level}">{head}<div>{esc(text)}</div></div>')


def empty_state(title: str, text: str) -> None:
    html(f'<div class="rc-empty"><h3>{esc(title)}</h3><p>{esc(text)}</p></div>')


def footer(note_text: str) -> None:
    html(f'<div class="rc-footer"><span>Recon · 금융 데이터 검증·대사 자동화</span><span>{esc(note_text)}</span></div>')
