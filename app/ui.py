"""화면 스타일과 HTML 구성 요소 (Meta 디자인 토큰 기반).

데이터에서 온 문자열은 모두 esc()로 이스케이프한 뒤 HTML에 넣는다.
"""

from __future__ import annotations

from html import escape
from typing import Iterable, Sequence

import streamlit as st

from recon.detect import Classified
from recon.glossary import FILE_GUIDES, STAGE_GUIDES, FileGuide
from recon.insights import CheckItem, Verdict
from recon.models import DEFAULT_FILE_NAMES, FILE_TYPES

# Meta 토큰 (docs/DESIGN-meta.md)
PRIMARY = "#0064e0"
PRIMARY_DEEP = "#0457cb"
INK_DEEP = "#0a1317"
INK = "#1c1e21"
STEEL = "#5d6c7b"
HAIRLINE_SOFT = "#dee3e9"
STATUS = {"good": "#31a24c", "warning": "#f2a918", "serious": "#ec835a", "critical": "#e41e3f"}
STATUS_ICON = {"good": "✓", "warning": "!", "serious": "±", "critical": "✕", "info": "i", "neutral": "·"}
LEVEL_LABEL = {"critical": "긴급", "warning": "검토", "info": "참고"}

CSS = """
:root {
  --c-primary: #0064e0; --c-primary-deep: #0457cb; --c-primary-soft: #0091ff;
  --c-ink-deep: #0a1317; --c-ink: #1c1e21; --c-charcoal: #444950; --c-slate: #4b4c4f;
  --c-steel: #5d6c7b; --c-stone: #8595a4; --c-hairline: #ced0d4; --c-hairline-soft: #dee3e9;
  --c-surface: #f1f4f7; --c-canvas: #ffffff;
  --c-good: #31a24c; --c-warning: #f2a918; --c-serious: #ec835a; --c-critical: #e41e3f;
}

/* 기본 바탕 */
.stApp { background: var(--c-canvas); }
[data-testid="stMainBlockContainer"] { max-width: 1200px; padding: 0 32px 64px; }
header[data-testid="stHeader"] { background: transparent; }
[data-testid="stAppDeployButton"], [data-testid="stMainMenu"] { display: none; }
[data-testid="stSidebarCollapsedControl"] { display: none; }
p, li, label, .stMarkdown { letter-spacing: -0.16px; }
h1, h2, h3, h4 { font-feature-settings: "ss01", "ss02"; color: var(--c-ink-deep); letter-spacing: -0.3px; }

/* 상단 바 */
.rc-topbar { display: flex; align-items: center; justify-content: space-between; height: 64px;
  border-bottom: 1px solid var(--c-hairline-soft); margin: 0 0 16px; }
.rc-logo { display: flex; align-items: center; gap: 10px; font-size: 18px; font-weight: 700; color: var(--c-ink-deep); }
.rc-logo-mark { flex: none; width: 28px; height: 28px; border-radius: 9999px; position: relative;
  background: conic-gradient(from 200deg, #0064e0, #0091ff, #a121ce, #0064e0); }
.rc-logo-mark::after { content: ""; position: absolute; inset: 6px; border-radius: 9999px; background: var(--c-canvas); }
.rc-logo small { font-size: 14px; font-weight: 400; color: var(--c-steel); margin-left: 6px; }
.rc-topbar-note { font-size: 14px; color: var(--c-steel); }

/* 메뉴·필터: pill 탭 (선택된 것은 진한 잉크색으로 채움) */
[data-testid="stButtonGroup"] > div { gap: 8px; flex-wrap: wrap; }
[data-testid="stButtonGroup"] button { border-radius: 100px !important; border: 1px solid var(--c-hairline) !important;
  background: var(--c-canvas) !important; color: var(--c-ink) !important; padding: 6px 16px !important;
  min-height: 36px; box-shadow: none !important; }
[data-testid="stButtonGroup"] button p { font-size: 14px; font-weight: 700; }
[data-testid="stButtonGroup"] button[aria-checked="true"], [data-testid="stButtonGroup"] button[data-selected="true"] {
  background: var(--c-ink-deep) !important;
  border-color: var(--c-ink-deep) !important; color: #fff !important; }
[data-testid="stButtonGroup"] button[aria-checked="true"] p, [data-testid="stButtonGroup"] button[data-selected="true"] p { color: #fff; }
.st-key-nav button { padding: 8px 18px !important; min-height: 40px; }
.st-key-nav { margin-bottom: 24px; }

/* 버튼: 실행(코발트) · 보조(외곽선) · 링크형 */
button[data-testid="stBaseButton-primary"] { background: var(--c-primary); border: none; color: #fff;
  min-height: 48px; padding: 0 30px; font-weight: 700; }
button[data-testid="stBaseButton-primary"]:hover { background: var(--c-primary-deep); color: #fff; }
button[data-testid="stBaseButton-primary"]:disabled { background: #bcc0c4; color: #fff; }
button[data-testid="stBaseButton-secondary"] { background: transparent; border: 2px solid var(--c-ink-deep);
  color: var(--c-ink-deep); min-height: 48px; padding: 0 28px; font-weight: 700; }
button[data-testid="stBaseButton-secondary"]:hover { background: var(--c-surface); border-color: var(--c-ink-deep); color: var(--c-ink-deep); }
button[data-testid="stBaseButton-primary"] p, button[data-testid="stBaseButton-secondary"] p { font-size: 14px; font-weight: 700; }
button[data-testid="stBaseButton-tertiary"] { color: var(--c-primary-deep); font-weight: 700; padding: 0; min-height: 32px; }
button[data-testid="stBaseButton-tertiary"] p { font-size: 14px; font-weight: 700; }
button[data-testid="stBaseButton-tertiary"]:hover { color: var(--c-primary); }

/* 히어로: 어두운 32px 카드 + 코발트·퍼플 빛 */
.st-key-hero { position: relative; overflow: hidden; background: var(--c-ink-deep); border-radius: 32px;
  padding: 56px; margin-bottom: 8px; isolation: isolate; }
.st-key-hero::before { content: ""; position: absolute; z-index: -1; width: 720px; height: 720px; right: -220px; top: -260px;
  background: radial-gradient(closest-side, rgba(0, 145, 255, .55), rgba(0, 100, 224, .25) 45%, transparent 72%); }
.st-key-hero::after { content: ""; position: absolute; z-index: -1; width: 520px; height: 520px; right: 180px; bottom: -330px;
  background: radial-gradient(closest-side, rgba(161, 33, 206, .38), transparent 70%); }
.st-key-hero button[data-testid="stBaseButton-secondary"] { border-color: rgba(255,255,255,.9); color: #fff; }
.st-key-hero button[data-testid="stBaseButton-secondary"]:hover { background: rgba(255,255,255,.08); color: #fff; }
.st-key-hero button[data-testid="stBaseButton-primary"] { background: #fff; color: var(--c-ink-deep); }
.st-key-hero button[data-testid="stBaseButton-primary"]:hover { background: #e9eef3; color: var(--c-ink-deep); }
.st-key-hero button[data-testid="stBaseButton-primary"] p { color: var(--c-ink-deep); }
.rc-eyebrow { display: inline-flex; align-items: center; gap: 8px; padding: 6px 14px; border-radius: 100px;
  background: rgba(255,255,255,.1); color: rgba(255,255,255,.88); font-size: 13px; font-weight: 700; }
.rc-eyebrow i { width: 8px; height: 8px; border-radius: 9999px; background: #0091ff; display: inline-block; }
.rc-hero-title { font-size: 52px; line-height: 1.16; font-weight: 500; color: #fff; margin: 20px 0 16px;
  letter-spacing: -1px; font-feature-settings: "ss01", "ss02"; }
.rc-hero-title em { font-style: normal; background: linear-gradient(90deg, #5cb2ff, #c48bff);
  -webkit-background-clip: text; background-clip: text; color: transparent; }
.rc-hero-lead { font-size: 18px; line-height: 1.6; color: rgba(255,255,255,.76); margin: 0 0 12px; max-width: 560px; }
.rc-preview { background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.12); border-radius: 24px;
  padding: 20px; backdrop-filter: blur(6px); }
.rc-preview-head { display: flex; justify-content: space-between; color: rgba(255,255,255,.6); font-size: 12px;
  font-weight: 700; margin-bottom: 12px; }
.rc-preview-row { display: grid; grid-template-columns: 28px 1fr auto; gap: 12px; align-items: center;
  background: rgba(255,255,255,.06); border-radius: 14px; padding: 12px 14px; margin-top: 8px; }
.rc-preview-row b { color: #fff; font-size: 14px; font-weight: 600; display: block; }
.rc-preview-row span { color: rgba(255,255,255,.6); font-size: 12px; }

/* 섹션 제목 */
.rc-section { margin: 72px 0 24px; }
.rc-section.first { margin-top: 8px; }
.rc-section-sm { margin: 40px 0 16px; }
.rc-kicker { font-size: 13px; font-weight: 700; color: var(--c-primary-deep); letter-spacing: 0; margin-bottom: 8px; }
.rc-title { font-size: 36px; line-height: 1.28; font-weight: 500; color: var(--c-ink-deep); margin: 0;
  letter-spacing: -0.6px; font-feature-settings: "ss01", "ss02"; }
.rc-title-sm { font-size: 24px; line-height: 1.25; font-weight: 600; color: var(--c-ink-deep); margin: 0; letter-spacing: -0.3px; }
.rc-lead { font-size: 18px; line-height: 1.5; font-weight: 300; color: var(--c-slate); margin: 8px 0 0; }
.rc-lead-sm { font-size: 15px; line-height: 1.5; color: var(--c-steel); margin: 6px 0 0; }

/* 흐름도 */
.rc-flow { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; align-items: stretch; }
.rc-flow-node { position: relative; background: var(--c-surface); border-radius: 24px; padding: 24px 20px; }
.rc-flow-node.accent { background: var(--c-canvas); border: 1px solid var(--c-hairline-soft); }
.rc-flow-node:not(:last-child)::after { content: "→"; position: absolute; right: -14px; top: 50%; transform: translateY(-50%);
  width: 24px; height: 24px; border-radius: 9999px; background: var(--c-ink-deep); color: #fff; font-size: 13px;
  display: flex; align-items: center; justify-content: center; z-index: 2; }
.rc-flow-step { width: 32px; height: 32px; border-radius: 9999px; background: var(--c-ink-deep); color: #fff;
  font-weight: 700; font-size: 14px; display: flex; align-items: center; justify-content: center; margin-bottom: 16px; }
.rc-flow-step.soft { background: var(--c-canvas); color: var(--c-ink-deep); border: 1px solid var(--c-hairline); }
.rc-flow-node b { display: block; font-size: 17px; font-weight: 700; color: var(--c-ink-deep); margin-bottom: 6px; }
.rc-flow-node span { display: block; font-size: 14px; line-height: 1.45; color: var(--c-steel); }

/* 카드 · 타일 */
.rc-grid-3 { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 24px; }
.rc-grid-4 { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; }
.rc-card { background: var(--c-canvas); border: 1px solid var(--c-hairline-soft); border-radius: 16px; padding: 24px; }
.rc-card-lg { background: var(--c-canvas); border: 1px solid var(--c-hairline-soft); border-radius: 32px; padding: 32px; }
.rc-card h4 { font-size: 18px; font-weight: 700; margin: 0 0 8px; color: var(--c-ink-deep); line-height: 1.44; }
.rc-card p { font-size: 14px; line-height: 1.5; color: var(--c-steel); margin: 0; }
.rc-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 16px; }
.rc-chip { padding: 4px 10px; border-radius: 100px; background: var(--c-surface); color: var(--c-charcoal);
  font-size: 12px; font-weight: 700; }
.rc-tile { background: var(--c-canvas); border: 1px solid var(--c-hairline-soft); border-radius: 16px; padding: 22px 24px; }
.rc-tile-label { display: flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 700; color: var(--c-charcoal); }
.rc-tile-value { font-size: 38px; line-height: 1.1; font-weight: 600; color: var(--c-ink-deep); margin: 14px 0 6px; letter-spacing: -0.8px; }
.rc-tile-value small { font-size: 16px; font-weight: 500; color: var(--c-steel); margin-left: 4px; letter-spacing: 0; }
.rc-tile-caption { font-size: 13px; line-height: 1.45; color: var(--c-steel); }

/* 상태 배지: 색 + 아이콘 + 글자 */
.rc-badge { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px 4px 4px; border-radius: 100px;
  font-size: 12px; font-weight: 700; line-height: 1.33; background: var(--c-surface); color: var(--c-ink-deep); white-space: nowrap; }
.rc-badge i { width: 18px; height: 18px; border-radius: 9999px; display: inline-flex; align-items: center; justify-content: center;
  font-style: normal; font-size: 11px; font-weight: 800; color: #fff; background: var(--c-steel); }
.rc-badge.good { background: rgba(49,162,76,.12); } .rc-badge.good i { background: var(--c-good); }
.rc-badge.warning { background: rgba(242,169,24,.16); } .rc-badge.warning i { background: var(--c-warning); color: var(--c-ink-deep); }
.rc-badge.serious { background: rgba(236,131,90,.16); } .rc-badge.serious i { background: var(--c-serious); color: var(--c-ink-deep); }
.rc-badge.critical { background: rgba(228,30,63,.10); } .rc-badge.critical i { background: var(--c-critical); }
.rc-badge.info { background: rgba(0,145,255,.12); } .rc-badge.info i { background: var(--c-primary); }
.rc-badge.neutral { background: var(--c-canvas); border: 1px solid var(--c-hairline); padding: 3px 10px 3px 4px; color: var(--c-charcoal); }
.rc-badge.neutral i { background: transparent; border: 2px dashed var(--c-stone); width: 14px; height: 14px; margin: 0 2px; }
.rc-badge.solid { padding: 6px 14px 6px 6px; font-size: 13px; }
.rc-badge.solid.good { background: var(--c-good); color: #fff; } .rc-badge.solid.good i { background: #fff; color: var(--c-good); }
.rc-badge.solid.warning { background: var(--c-warning); color: var(--c-ink-deep); } .rc-badge.solid.warning i { background: var(--c-ink-deep); color: var(--c-warning); }
.rc-badge.solid.critical { background: var(--c-critical); color: #fff; } .rc-badge.solid.critical i { background: #fff; color: var(--c-critical); }

/* 막대 미터 (같은 색의 옅은 트랙) */
.rc-meter { height: 8px; border-radius: 100px; background: rgba(0,100,224,.14); overflow: hidden; margin-top: 14px; }
.rc-meter > div { height: 100%; border-radius: 100px; background: var(--c-primary); }
.rc-meter.good { background: rgba(49,162,76,.16); } .rc-meter.good > div { background: var(--c-good); }

/* 판정 띠 */
.rc-verdict { position: relative; overflow: hidden; background: var(--c-ink-deep); color: #fff; border-radius: 32px;
  padding: 40px 48px; isolation: isolate; }
.rc-verdict::before { content: ""; position: absolute; z-index: -1; width: 560px; height: 560px; right: -160px; top: -280px;
  background: radial-gradient(closest-side, var(--glow), transparent 70%); }
.rc-verdict h2 { color: #fff; font-size: 34px; line-height: 1.25; font-weight: 500; margin: 16px 0 8px; letter-spacing: -0.6px; }
.rc-verdict p { color: rgba(255,255,255,.74); font-size: 16px; line-height: 1.5; margin: 0; }
.rc-verdict-meta { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 24px; }
.rc-verdict-meta span { padding: 6px 12px; border-radius: 100px; background: rgba(255,255,255,.1);
  color: rgba(255,255,255,.85); font-size: 13px; font-weight: 600; }

/* 먼저 확인할 것 */
.rc-check { display: grid; grid-template-columns: 44px minmax(0, 1fr) auto; gap: 18px; align-items: start;
  background: var(--c-canvas); border: 1px solid var(--c-hairline-soft); border-radius: 16px; padding: 22px 24px; }
.rc-check-no { width: 36px; height: 36px; border-radius: 9999px; background: var(--c-surface); color: var(--c-ink-deep);
  display: flex; align-items: center; justify-content: center; font-weight: 700; }
.rc-check-no.critical { background: var(--c-critical); color: #fff; }
.rc-check-no.warning { background: var(--c-warning); color: var(--c-ink-deep); }
.rc-check h4 { margin: 2px 0 6px; font-size: 18px; font-weight: 700; color: var(--c-ink-deep); line-height: 1.4; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.rc-check p { margin: 0; font-size: 14px; line-height: 1.5; color: var(--c-steel); }
.rc-check .rc-action { margin-top: 10px; font-size: 14px; color: var(--c-ink); }
.rc-check .rc-action b { color: var(--c-primary-deep); }
.rc-check-count { text-align: right; font-size: 30px; font-weight: 600; color: var(--c-ink-deep); line-height: 1.1; letter-spacing: -0.6px; white-space: nowrap; }
.rc-check-count small { font-size: 14px; font-weight: 500; color: var(--c-steel); margin-left: 2px; }
.rc-breakdown { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }

/* 파일 슬롯 */
.rc-slot { border-radius: 16px; padding: 18px 18px 16px; background: var(--c-surface); border: 1px solid transparent; min-height: 132px; }
.rc-slot.ready { background: var(--c-canvas); border-color: rgba(49,162,76,.45); }
.rc-slot-top { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.rc-slot b { display: block; font-size: 16px; font-weight: 700; color: var(--c-ink-deep); margin-top: 12px; }
.rc-slot span { display: block; font-size: 13px; color: var(--c-steel); line-height: 1.45; margin-top: 4px; }
.rc-slot code { font-size: 12px; background: transparent; color: var(--c-charcoal); padding: 0; }
.rc-slot .rc-file { margin-top: 10px; font-size: 13px; font-weight: 600; color: var(--c-ink); word-break: break-all; }

/* 단계 카드 (검증 실행) */
.st-key-step1, .st-key-step2, .st-key-step3 { border: 1px solid var(--c-hairline-soft); border-radius: 32px; padding: 32px; margin-bottom: 24px; }
.rc-step-head { display: flex; gap: 16px; align-items: flex-start; margin-bottom: 8px; }
.rc-step-no { flex: none; width: 40px; height: 40px; border-radius: 9999px; background: var(--c-ink-deep); color: #fff;
  font-weight: 700; display: flex; align-items: center; justify-content: center; }
.rc-step-head h3 { margin: 4px 0 4px; font-size: 24px; font-weight: 600; letter-spacing: -0.3px; }
.rc-step-head p { margin: 0; color: var(--c-steel); font-size: 15px; line-height: 1.5; }

/* 업로드 영역 */
[data-testid="stFileUploaderDropzone"] { background: var(--c-surface); border: 2px dashed var(--c-hairline); border-radius: 24px; padding: 28px; }
[data-testid="stFileUploaderDropzone"] button { border-radius: 100px; font-size: 0; }
[data-testid="stFileUploaderDropzone"] button * { font-size: 0 !important; }
[data-testid="stFileUploaderDropzone"] button svg { display: none; }
[data-testid="stFileUploaderDropzone"] button::after { content: "파일 선택"; font-size: 14px; font-weight: 700; white-space: nowrap; }
[data-testid="stFileUploaderDropzoneInstructions"] > * { display: none; }
[data-testid="stFileUploaderDropzoneInstructions"]::after { content: "여기로 파일 4개를 끌어다 놓거나 '파일 선택'을 누르세요 · CSV, XLSX · 파일당 200MB";
  font-size: 14px; color: var(--c-steel); }

/* 설명 표 (tech-specs-table) */
.rc-spec { width: 100%; border-collapse: collapse; font-size: 14px; }
.rc-spec td, .rc-spec th { padding: 10px 12px; border-bottom: 1px solid var(--c-hairline-soft); text-align: left; vertical-align: top; }
.rc-spec th { color: var(--c-steel); font-weight: 700; font-size: 12px; }
.rc-spec td:first-child { font-weight: 700; color: var(--c-ink); white-space: nowrap; }
.rc-spec td:last-child { color: var(--c-charcoal); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 13px; }
.rc-opt { color: var(--c-stone); font-weight: 400; font-size: 12px; margin-left: 4px; }

/* 펼치기 (FAQ) */
[data-testid="stExpander"] details { border: 1px solid var(--c-hairline-soft); border-radius: 16px; background: var(--c-canvas); }
[data-testid="stExpander"] summary { padding: 18px 22px; }
[data-testid="stExpander"] summary p { font-size: 16px; font-weight: 700; color: var(--c-ink-deep); }

/* 알림 · 빈 상태 */
.rc-note { display: flex; gap: 12px; align-items: flex-start; border-radius: 16px; padding: 16px 20px; background: rgba(0,145,255,.10);
  color: var(--c-ink); font-size: 14px; line-height: 1.5; margin: 16px 0; }
.rc-note.warning { background: rgba(242,169,24,.14); }
.rc-note.critical { background: rgba(228,30,63,.08); }
.rc-note b { color: var(--c-ink-deep); }
.rc-empty { text-align: center; background: var(--c-surface); border-radius: 32px; padding: 64px 32px; }
.rc-empty h3 { margin: 0 0 8px; font-size: 26px; font-weight: 600; }
.rc-empty p { margin: 0; color: var(--c-steel); }

/* 푸터 */
.rc-footer { margin-top: 80px; padding: 32px 0 8px; border-top: 1px solid var(--c-hairline-soft); color: var(--c-stone);
  font-size: 12px; display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; }

/* 반응형 */
@media (max-width: 1023px) {
  .rc-flow { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .rc-flow-node::after { display: none; }
  .rc-grid-4 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .rc-grid-3 { grid-template-columns: 1fr; }
  .rc-hero-title { font-size: 40px; }
}
@media (max-width: 640px) {
  [data-testid="stMainBlockContainer"] { padding: 0 16px 48px; }
  .rc-topbar-note, .rc-logo small { display: none; }
  .st-key-hero { padding: 32px 24px; border-radius: 24px; }
  .rc-hero-title { font-size: 32px; }
  .rc-flow, .rc-grid-4 { grid-template-columns: 1fr; }
  .rc-title { font-size: 28px; }
  .rc-verdict { padding: 28px 24px; }
  .rc-verdict h2 { font-size: 26px; }
  .rc-check { grid-template-columns: 36px minmax(0, 1fr); }
  .rc-check-count { grid-column: 2; text-align: left; }
  .st-key-step1, .st-key-step2, .st-key-step3 { padding: 22px; border-radius: 24px; }
}
"""


def esc(value: object) -> str:
    return escape("" if value is None else str(value))


def html(markup: str) -> None:
    st.html(markup)


def inject_css() -> None:
    st.html(f"<style>{CSS}</style>")


def badge(text: str, level: str = "neutral", solid: bool = False) -> str:
    classes = f"rc-badge {level}" + (" solid" if solid else "")
    return f'<span class="{classes}"><i>{STATUS_ICON.get(level, "·")}</i>{esc(text)}</span>'


def top_bar(note: str) -> None:
    html(
        '<div class="rc-topbar"><div class="rc-logo"><span class="rc-logo-mark"></span>Recon'
        "<small>금융 데이터 검증·대사</small></div>"
        f'<div class="rc-topbar-note">{esc(note)}</div></div>'
    )


def section(title: str, lead: str = "", kicker: str = "", small: bool = False, first: bool = False) -> None:
    """섹션 제목. first=True는 페이지 맨 위 제목(메뉴 바로 아래라 위 여백을 줄인다)."""
    title_class = "rc-title-sm" if small else "rc-title"
    lead_class = "rc-lead-sm" if small else "rc-lead"
    wrapper = "rc-section-sm" if small else "rc-section" + (" first" if first else "")
    html(
        f'<div class="{wrapper}">'
        + (f'<div class="rc-kicker">{esc(kicker)}</div>' if kicker else "")
        + f'<h2 class="{title_class}">{esc(title)}</h2>'
        + (f'<p class="{lead_class}">{esc(lead)}</p>' if lead else "")
        + "</div>"
    )


def hero_text() -> None:
    html(
        '<span class="rc-eyebrow"><i></i>엑셀 대사를 자동으로</span>'
        '<h1 class="rc-hero-title">하루치 거래내역,<br><em>3단계로 자동 검증</em>합니다</h1>'
        '<p class="rc-hero-lead">파일 4개를 올리면 오류가 있는 거래는 따로 빼 두고, 계좌별로 거래내역 합계와 '
        "집계표가 맞는지 비교해 엑셀 보고서로 정리해 드려요.</p>"
    )


def hero_preview() -> None:
    rows = [
        ("good", "T20261015000001 · 1,500,000원", "정상 — 대사에 반영"),
        ("critical", "T20261015000083 · 12000.75원", "금액 오류 — 격리"),
        ("warning", "T20261015900002 · 50,000원", "의심 중복 — 사람이 확인"),
        ("critical", "077-88-947837 · 입금 합계", "집계표와 23,217,000원 차이"),
    ]
    preview = "".join(
        f'<div class="rc-preview-row">{badge("", level)}<div><b>{esc(main)}</b><span>{esc(sub)}</span></div></div>'
        for level, main, sub in rows
    )
    html(
        f'<div class="rc-preview"><div class="rc-preview-head"><span>검증 결과 예시</span><span>샘플 데이터</span></div>{preview}</div>'
    )


def flow() -> None:
    nodes = [
        ("soft", "↑", "파일 4개 올리기", "거래내역, 집계표, 계좌·거래코드 마스터"),
        ("", "1", "품질 검증", "빈 칸·형식·중복 오류를 찾아 격리해요"),
        ("", "2", "기준정보 확인", "없는 계좌, 해지 후 거래, 잘못된 코드"),
        ("", "3", "집계표 대사", "정상 거래 합계를 계좌별로 집계표와 비교"),
        ("soft", "↓", "결과·보고서", "먼저 볼 것 정리, 엑셀·CSV 내려받기"),
    ]
    html(
        '<div class="rc-flow">'
        + "".join(
            f'<div class="rc-flow-node{" accent" if kind else ""}"><div class="rc-flow-step {kind}">{esc(no)}</div>'
            f"<b>{esc(title)}</b><span>{esc(text)}</span></div>"
            for kind, no, title, text in nodes
        )
        + "</div>"
    )


def stage_cards() -> None:
    cards = []
    for stage in ("DQ", "MD", "RC"):
        guide = STAGE_GUIDES[stage]
        chips = "".join(f'<span class="rc-chip">{esc(e)}</span>' for e in guide.examples)
        cards.append(
            f'<div class="rc-card-lg"><div class="rc-flow-step">{esc(guide.number)}</div>'
            f"<h4 style=\"font-size:22px;margin:0 0 8px\">{esc(guide.title)}</h4><p style=\"font-size:15px;color:#5d6c7b;margin:0\">{esc(guide.summary)}</p>"
            f'<div class="rc-chips">{chips}</div></div>'
        )
    html(f'<div class="rc-grid-3">{"".join(cards)}</div>')


def reading_guide() -> None:
    items = [
        ("good", "정상 반영", "오류가 없어 계좌별 합계 계산에 쓰인 거래예요."),
        ("critical", "격리", "오류가 있어 대사에서 뺀 거래예요. 고친 뒤 다시 실행하면 돼요."),
        ("warning", "검토 필요", "대사에는 넣었지만 의심 중복처럼 사람이 판단해야 하는 거래예요."),
        ("serious", "계좌 차이", "거래내역 합계와 집계표가 다른 계좌예요. 원인 표시를 함께 보여 드려요."),
    ]
    html(
        '<div class="rc-grid-4">'
        + "".join(
            f'<div class="rc-tile">{badge(label, level)}<p style="margin:14px 0 0;font-size:14px;line-height:1.5;color:#444950">{esc(text)}</p></div>'
            for level, label, text in items
        )
        + "</div>"
    )


def step_head(number: str, title: str, text: str) -> None:
    html(
        f'<div class="rc-step-head"><div class="rc-step-no">{esc(number)}</div>'
        f"<div><h3>{esc(title)}</h3><p>{esc(text)}</p></div></div>"
    )


def file_slots(classified: Classified) -> None:
    slots = []
    for file_type in FILE_TYPES:
        guide = FILE_GUIDES[file_type]
        assigned = classified.files.get(file_type)
        status = badge("준비됨", "good") if assigned else badge("필요", "neutral")
        file_line = f'<div class="rc-file">{esc(assigned[0])}</div>' if assigned else ""
        slots.append(
            f'<div class="rc-slot{" ready" if assigned else ""}"><div class="rc-slot-top">{status}'
            f"<code>{esc(DEFAULT_FILE_NAMES[file_type])}</code></div>"
            f"<b>{esc(guide.title)}</b><span>{esc(guide.role)}</span>{file_line}</div>"
        )
    html(f'<div class="rc-grid-4">{"".join(slots)}</div>')


def spec_table(guide: FileGuide) -> None:
    rows = "".join(
        f"<tr><td>{esc(c.name)}{'' if c.required else '<span class=rc-opt>선택</span>'}</td>"
        f"<td>{esc(c.meaning)}</td><td>{esc(c.example) or '빈 값'}</td></tr>"
        for c in guide.columns
    )
    html(f'<table class="rc-spec"><tr><th>컬럼</th><th>뜻</th><th>예</th></tr>{rows}</table>')


def verdict_strip(v: Verdict, meta: Iterable[str]) -> None:
    glow = {"good": "rgba(49,162,76,.45)", "warning": "rgba(242,169,24,.40)", "critical": "rgba(228,30,63,.38)"}[v.level]
    chips = "".join(f"<span>{esc(m)}</span>" for m in meta)
    html(
        f'<div class="rc-verdict" style="--glow:{glow}">{badge(v.badge, v.level, solid=True)}'
        f"<h2>{esc(v.headline)}</h2><p>{esc(v.summary)}</p>"
        f'<div class="rc-verdict-meta">{chips}</div></div>'
    )


def tiles(items: Sequence[tuple[str, str, str, str, str | None, float | None]]) -> None:
    """(라벨, 값, 단위, 설명, 상태, 미터 비율)."""
    cells = []
    for label, value, unit, caption, level, ratio in items:
        label_html = badge(label, level) if level else esc(label)
        meter = ""
        if ratio is not None:
            meter_class = "rc-meter good" if level == "good" else "rc-meter"
            meter = f'<div class="{meter_class}"><div style="width:{max(0.0, min(ratio, 1.0)) * 100:.1f}%"></div></div>'
        cells.append(
            f'<div class="rc-tile"><div class="rc-tile-label">{label_html}</div>'
            f'<div class="rc-tile-value">{esc(value)}<small>{esc(unit)}</small></div>'
            f'<div class="rc-tile-caption">{esc(caption)}</div>{meter}</div>'
        )
    html(f'<div class="rc-grid-4">{"".join(cells)}</div>')


def check_card(index: int, item: CheckItem) -> None:
    breakdown = "".join(f'<span class="rc-chip">{esc(name)} {count:,}</span>' for name, count in item.breakdown)
    html(
        f'<div class="rc-check"><div class="rc-check-no {item.level}">{index}</div><div>'
        f"<h4>{esc(item.title)} {badge(LEVEL_LABEL[item.level], item.level)}</h4>"
        f"<p>{esc(item.description)}</p>"
        f'<div class="rc-action"><b>할 일</b> · {esc(item.action)}</div>'
        + (f'<div class="rc-breakdown">{breakdown}</div>' if breakdown else "")
        + f'</div><div class="rc-check-count">{item.count:,}<small>{esc(item.unit)}</small></div></div>'
    )


def note(text: str, level: str = "info", title: str = "") -> None:
    head = f"<b>{esc(title)}</b> " if title else ""
    html(f'<div class="rc-note {level}">{badge("", level) if level != "info" else badge("", "info")}<div>{head}{esc(text)}</div></div>')


def empty_state(title: str, text: str) -> None:
    html(f'<div class="rc-empty"><h3>{esc(title)}</h3><p>{esc(text)}</p></div>')


def footer(note_text: str) -> None:
    html(f'<div class="rc-footer"><span>Recon · 금융 데이터 검증·대사 자동화</span><span>{esc(note_text)}</span></div>')
