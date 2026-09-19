"""J1 披露 AI section prompt 守卫（防空转 + 防自造披露内容）。

背景（2026-07-30 复盘 P1）：两个 J1 披露 Tab 的 AI 辅助调用的是**通用**端点
``POST /api/workpapers/{wp_id}/ai/generate-text``，该端点对 section **不做白名单拒绝** →
未登记的 section 会静默落到通用兜底「请根据提供的上下文信息生成专业的审计文本。」，
等于放任模型自造披露内容（平台已有 F2 同款教训：18~19 字的笼统 prompt 诱发虚构）。

本文件把「前端会发出的 section」与「后端已登记的 prompt」对齐锁死：

- 6 个 section 全部登记（listed 3 + soe 3）
- 每条 prompt ≥20 字、写明源模板 / CAS 9 口径、含「不得虚构」类约束
- section 名从前端 `.ts` 源码正则读出（防双真源漂移：改了 `J1_SOE_NOTE_FIELDS`
  的 key 而忘了改后端 prompt 时必须报红）

spec: .kiro/specs/j1-disclosure-template-alignment/ Task 9.2
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.routers.wp_guidance_chat import _SECTION_PROMPTS

_BACKEND = Path(__file__).resolve().parents[1]
_REPO = _BACKEND.parent
COMPOSABLES = (
    _REPO / "audit-platform" / "frontend" / "src" / "components" / "workpaper" / "composables"
)
J1_MAP = COMPOSABLES / "j1NoteSectionMap.ts"

# 上市侧 3 个文本域的 AI section 后缀（组件里写死为 `short-term-note` 等）
LISTED_SECTIONS = [
    "j1-disclosure-listed-short-term-note",
    "j1-disclosure-listed-post-employment-note",
    "j1-disclosure-listed-severance-note",
]

MIN_PROMPT_LEN = 20

# 「不得虚构」类约束的可接受表述（任一命中即可）
_NO_FABRICATION_MARKERS = ("不得虚构", "不要编造", "不得编造", "不要虚构")


def _soe_note_keys() -> list[str]:
    """从前端源码读 `J1_SOE_NOTE_FIELDS` 的 key（单一真源，防漂移）。"""
    src = J1_MAP.read_text(encoding="utf-8")
    block = re.search(
        r"J1_SOE_NOTE_FIELDS\s*:\s*readonly J1NoteFieldDef\[\]\s*=\s*\[(.*?)\n\]", src, re.S
    )
    assert block, "未找到 J1_SOE_NOTE_FIELDS 声明"
    keys = re.findall(r"key:\s*'([^']+)'", block.group(1))
    assert len(keys) == 3, f"国企侧说明域应为 3 段，实为 {len(keys)}：{keys}"
    return keys


def _soe_sections() -> list[str]:
    """组件里 `aiSection = `${key}-note``，section 前缀 `j1-disclosure-soe-`。"""
    return [f"j1-disclosure-soe-{k}-note" for k in _soe_note_keys()]


def _all_sections() -> list[str]:
    return [*LISTED_SECTIONS, *_soe_sections()]


# ─────────────────────────── 登记齐备 ───────────────────────────

@pytest.mark.parametrize("section", LISTED_SECTIONS)
def test_listed_sections_registered(section: str) -> None:
    assert section in _SECTION_PROMPTS, (
        f"{section} 未登记 → AI 会落到通用兜底，放任模型自造披露内容"
    )


def test_soe_sections_registered() -> None:
    """国企 3 段的 section 名由前端 `J1_SOE_NOTE_FIELDS` 的 key 派生，必须逐个登记。"""
    missing = [s for s in _soe_sections() if s not in _SECTION_PROMPTS]
    assert not missing, f"未登记的 section：{missing}（改了前端 key 就要同步后端 prompt）"


def test_soe_legacy_single_section_not_used() -> None:
    """历史单段实现的 section（`j1-disclosure-soe-soe-note`）不应再存在。"""
    assert "j1-disclosure-soe-soe-note" not in _SECTION_PROMPTS
    assert "soe" not in _soe_note_keys(), "国企说明域已拆 3 段，不应保留笼统的 `soe` 键"


# ─────────────────────────── prompt 质量 ───────────────────────────

def test_all_prompts_long_enough() -> None:
    """过短的 prompt 等于无指令生成（F2 已有教训）。"""
    too_short = {
        s: len(_SECTION_PROMPTS[s])
        for s in _all_sections()
        if len(_SECTION_PROMPTS.get(s, "")) < MIN_PROMPT_LEN
    }
    assert not too_short, f"以下 prompt 过短，缺少审计口径约束：{too_short}"


def test_all_prompts_have_no_fabrication_guard() -> None:
    """每条 prompt 必须含「不得虚构」类约束（披露是交付物，禁自造）。"""
    missing = [
        s
        for s in _all_sections()
        if not any(m in _SECTION_PROMPTS[s] for m in _NO_FABRICATION_MARKERS)
    ]
    assert not missing, f"以下 prompt 缺少不得虚构约束：{missing}"


def test_all_prompts_cite_cas9() -> None:
    """应付职工薪酬的披露口径唯一准则来源是 CAS 9，每条都要点名。"""
    missing = [s for s in _all_sections() if "CAS 9" not in _SECTION_PROMPTS[s]]
    assert not missing, f"以下 prompt 未写明 CAS 9 口径：{missing}"


@pytest.mark.parametrize(
    ("section", "keyword"),
    [
        ("j1-disclosure-listed-short-term-note", "非货币性福利"),
        ("j1-disclosure-listed-short-term-note", "短期利润分享计划"),
        ("j1-disclosure-listed-post-employment-note", "设定提存计划"),
        ("j1-disclosure-listed-severance-note", "辞退福利"),
        ("j1-disclosure-soe-soeNonMonetary-note", "非货币性福利"),
        ("j1-disclosure-soe-soeDefinedContribution-note", "缴费"),
        ("j1-disclosure-soe-soeDefinedBenefit-note", "设定受益计划"),
    ],
)
def test_prompt_topic_specific(section: str, keyword: str) -> None:
    """每条 prompt 必须带本小节的专有口径关键词（防复制粘贴串味）。"""
    assert keyword in _SECTION_PROMPTS[section], f"{section} 缺关键词「{keyword}」"


def test_soe_defined_benefit_cross_reference() -> None:
    """设定受益计划说明的交叉引用指向真实章节 八、54（源 xlsx 的 八、47 已过时）。"""
    prompt = _SECTION_PROMPTS["j1-disclosure-soe-soeDefinedBenefit-note"]
    assert "八、54" in prompt
    assert "八、47" not in prompt


def test_soe_defined_benefit_allows_not_applicable() -> None:
    """不存在设定受益计划时必须允许直接声明，而不是硬凑内容。"""
    prompt = _SECTION_PROMPTS["j1-disclosure-soe-soeDefinedBenefit-note"]
    assert "不存在设定受益计划" in prompt


# ─────────────────────────── 端点契约 ───────────────────────────

def test_generic_endpoint_has_no_reject_whitelist() -> None:
    """本守卫的前提：通用端点不做 section 白名单拒绝（否则未登记会 400 而非静默兜底）。

    该前提若变化（改成拒绝式白名单），本文件的价值判断需要重新评估 → 用测试锁住前提。
    """
    src = (_BACKEND / "app" / "routers" / "wp_guidance_chat.py").read_text(encoding="utf-8")
    body = re.search(r"async def workpaper_ai_generate_text\((.*?)\n\n\n", src, re.S)
    assert body, "未找到 workpaper_ai_generate_text"
    assert "不支持的 section" not in body.group(1), (
        "端点已改为拒绝式白名单 → 请同步调整本守卫的假设"
    )
