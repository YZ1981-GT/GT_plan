"""F 类披露文本域的 AI section 注册守卫（F1 / F3 / F4）。

平台铁律：AI section 需四处同时登记，缺一即空转 ——
  ① 后端 ``_SUPPORTED_SECTIONS``  ② 后端 ``_SECTION_PROMPTS``
  ③ 前端 ``useXAiGenerate`` 的联合类型  ④ 披露 Tab 的 ``AI_TARGETS``

本测试守 ①②③（④ 由前端 vitest 侧的 Tab 渲染断言覆盖），并要求 prompt
≥20 字且写明「不得虚构」类约束 —— 过短的笼统 prompt 会诱导模型自造披露内容。

spec: .kiro/specs/f-cycle-disclosure-parity/ R9
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
_REPO = _BACKEND.parent
_STRATEGIES = _BACKEND / "app" / "routers" / "wp_render_strategies"
_COMPOSABLES = (
    _REPO / "audit-platform" / "frontend" / "src" / "components" / "workpaper" / "composables"
)

# (循环, 后端模块, 前端 composable, 披露 section 列表)
CASES = [
    (
        "F1",
        "_f1_ai_generate",
        "useF1AiGenerate.ts",
        [
            "listed-note-aging",
            "listed-note-over1",
            "listed-note-top5",
            "soe-note-aging",
            "soe-note-over1",
            "soe-note-top5",
        ],
    ),
    ("F3", "_f3_notes_payable_ai", "useF3AiGenerate.ts", ["listed-note", "soe-note"]),
    (
        "F4",
        "_f4_accounts_payable_ai",
        "useF4AiGenerate.ts",
        ["disclosure-listed", "disclosure-soe"],
    ),
]

_FLAT_CASES = [
    (cycle, backend, frontend, section)
    for cycle, backend, frontend, sections in CASES
    for section in sections
]


def _load(module: str):
    import importlib

    return importlib.import_module(f"app.routers.wp_render_strategies.{module}")


@pytest.mark.parametrize("cycle,backend,frontend,section", _FLAT_CASES)
def test_section_supported(cycle: str, backend: str, frontend: str, section: str) -> None:
    mod = _load(backend)
    assert section in mod._SUPPORTED_SECTIONS, f"{cycle} 未在 _SUPPORTED_SECTIONS 登记 {section}"


@pytest.mark.parametrize("cycle,backend,frontend,section", _FLAT_CASES)
def test_section_prompt_is_specific(
    cycle: str, backend: str, frontend: str, section: str,
) -> None:
    """prompt 必须 ≥20 字：过短的笼统 prompt 等于放任模型自由发挥。"""
    mod = _load(backend)
    prompt = mod._SECTION_PROMPTS.get(section)
    assert prompt, f"{cycle} 缺 {section} 的 prompt（会导致 AI 按钮空转）"
    assert len(prompt) >= 20, f"{cycle}/{section} prompt 仅 {len(prompt)} 字，过于笼统"


@pytest.mark.parametrize("cycle,backend,frontend,section", _FLAT_CASES)
def test_frontend_union_type_declares_section(
    cycle: str, backend: str, frontend: str, section: str,
) -> None:
    src = (_COMPOSABLES / frontend).read_text(encoding="utf-8")
    assert f"'{section}'" in src, f"{frontend} 的联合类型缺 {section}"


@pytest.mark.parametrize("cycle,backend,_frontend,_sections", [
    (c, b, f, s) for c, b, f, s in CASES
])
def test_disclosure_prompts_forbid_fabrication(
    cycle: str, backend: str, _frontend: str, _sections: list[str],
) -> None:
    """披露类 prompt 至少有一条写明「不得虚构 / 只能依据传入数据」类约束。"""
    mod = _load(backend)
    texts = [mod._SECTION_PROMPTS[s] for s in _sections if s in mod._SECTION_PROMPTS]
    assert texts, f"{cycle} 无披露 prompt"
    guarded = [t for t in texts if re.search(r"不得虚构|只能依据|以传入", t)]
    assert guarded, f"{cycle} 披露 prompt 均未写明「不得虚构」约束"


@pytest.mark.parametrize("cycle,tab_dir,tabs,sections", [
    (
        "F1",
        "f1",
        ["F1TabDisclosureListed.vue", "F1TabDisclosureSoe.vue"],
        {
            "F1TabDisclosureListed.vue": [
                "listed-note-aging", "listed-note-over1", "listed-note-top5",
            ],
            "F1TabDisclosureSoe.vue": [
                "soe-note-aging", "soe-note-over1", "soe-note-top5",
            ],
        },
    ),
])
def test_tab_wires_ai_targets(
    cycle: str, tab_dir: str, tabs: list[str], sections: dict[str, list[str]],
) -> None:
    """④ 披露 Tab 必须把 section 接到 AI_TARGETS 且渲染 AI 按钮，否则后端注册空转。"""
    base = _COMPOSABLES.parent / tab_dir
    for tab in tabs:
        src = (base / tab).read_text(encoding="utf-8")
        assert "AI_TARGETS" in src, f"{tab} 未声明 AI_TARGETS"
        for section in sections[tab]:
            assert f"'{section}'" in src, f"{tab} 未接 {section}"
            assert f"runAi('{section}')" in src, f"{tab} 缺 {section} 的 AI 按钮"
