"""review-dialog AI section prompt 守卫。

背景（2026-07-30 实证）：D1 的 7 个 AI 按钮长期空转 —— 前端发的是
``{section, context}``，后端 ``AiGenerateRequest`` 要 ``{section_id, related_data,
existing_content}`` → 必然 422，被前端 ``catch`` 吞成「AI生成失败」。修好字段名后又
撞上第二个铁律：**prompt 过短会诱导模型自造披露内容**（笼统的
「请为以下底稿区域生成审计说明」等于放任自由发挥）。

本守卫锁死三件事：

1. 前端**实际会发出**的 ``section_id``（从 `.ts` / `.vue` 源码正则抽取）都已登记专属 prompt
2. 每条专属 prompt ≥ 20 字且含「不得虚构 / 严禁虚构」类约束
3. 未登记的 ``section_id`` 回退通用 prompt（存量调用方零回归）

spec: .kiro/specs/d1-notes-receivable-disclosure-alignment/ R6.3
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.routers.review_dialog import (
    _REVIEW_AI_SYSTEM_PROMPT,
    _SECTION_PROMPTS,
    resolve_review_ai_prompt,
)

_REPO = Path(__file__).resolve().parent.parent.parent
_WORKPAPER = _REPO / "audit-platform" / "frontend" / "src" / "components" / "workpaper"

# D1 披露 5 个子节 × 2 变体 + 审定表 2 个
# 与前端 `NOTE_SECTION_KEYS` 一致（`transfer` / `badDebtMovement` 于第二阶段补齐 —— 
# 原先这两段有表格但没有说明文本域，附注 text_content 永远缺这两节）
_D1_DISCLOSURE_KEYS = [
    "top", "pledged", "endorsed", "transfer", "badDebtClass", "badDebtMovement", "writeOff",
]
EXPECTED_D1_SECTION_IDS = [
    f"d1-disclosure-{v}-{k}-note" for v in ("listed", "soe") for k in _D1_DISCLOSURE_KEYS
] + ["d1-adjudication-audit-note", "d1-adjudication-audit-conclusion"]

_FORBID_FABRICATION = ("不得虚构", "严禁虚构")


@pytest.mark.parametrize("section_id", EXPECTED_D1_SECTION_IDS)
def test_d1_section_has_dedicated_prompt(section_id: str) -> None:
    assert section_id in _SECTION_PROMPTS, (
        f"{section_id} 未登记专属 prompt → 会回退到笼统的通用 prompt，"
        "铁律：prompt 过短会诱导模型自造披露内容"
    )


@pytest.mark.parametrize("section_id", sorted(_SECTION_PROMPTS))
def test_prompt_长度与不虚构约束(section_id: str) -> None:
    text = _SECTION_PROMPTS[section_id]
    assert len(text.strip()) >= 20, f"{section_id} prompt 过短（{len(text)} 字）"
    assert any(k in text for k in _FORBID_FABRICATION), (
        f"{section_id} prompt 缺「不得虚构」类约束 → 上下文缺失时模型会编造披露内容"
    )


@pytest.mark.parametrize("section_id", sorted(_SECTION_PROMPTS))
def test_resolve_returns_dedicated_prompt(section_id: str) -> None:
    section_type = "审计说明" if "note" in section_id else "审计结论"
    resolved = resolve_review_ai_prompt(section_id, section_type)
    assert _SECTION_PROMPTS[section_id] in resolved
    assert section_type in resolved


def test_unknown_section_falls_back_to_generic() -> None:
    """未登记的 section_id 必须回退通用 prompt（存量调用方零回归）。"""
    resolved = resolve_review_ai_prompt("some-legacy-section-note", "审计说明")
    assert resolved == _REVIEW_AI_SYSTEM_PROMPT.format(section_type="审计说明")


# ─── 前端实际发出的 section_id 必须已登记 ────────────────────────────────────

_D1_SOURCES = [
    _WORKPAPER / "d1" / "D1TabDisclosure.vue",
    _WORKPAPER / "composables" / "useD1Adjudication.ts",
]


def _note_section_keys(text: str) -> list[str]:
    """从 `const NOTE_SECTION_KEYS = ['top', ...]` 抽子节键（前端真源，避免此处写死）。"""
    m = re.search(r"NOTE_SECTION_KEYS\s*=\s*\[([^\]]+)\]", text)
    if not m:
        return []
    return re.findall(r"['\"]([^'\"]+)['\"]", m.group(1))


def _extract_section_ids(text: str) -> set[str]:
    """抽取 `section_id: '...'`，并把 `${props.variant}` / `${sectionKey}` 静态展开。

    展开用的枚举取自同一份前端源码（`NOTE_SECTION_KEYS`），所以新增子节时
    本测试会自动要求后端登记对应 prompt —— 不会出现「加了子节但 prompt 空转」。
    """
    keys = _note_section_keys(text)
    ids: set[str] = set()
    for m in re.finditer(r"section_id:\s*[`'\"]([^`'\"]+)[`'\"]", text):
        variants = [m.group(1)]
        if "${props.variant}" in m.group(1):
            variants = [m.group(1).replace("${props.variant}", v) for v in ("listed", "soe")]
        for raw in variants:
            if "${sectionKey}" in raw:
                if not keys:
                    continue
                ids.update(raw.replace("${sectionKey}", k) for k in keys)
            elif "${" in raw:
                continue  # 其它运行时拼接，由下方 aiGenerate('...') 分支覆盖
            else:
                ids.add(raw)
    for m in re.finditer(r"aiGenerate\(\s*['\"]([^'\"]+)['\"]\s*\)", text):
        ids.add(m.group(1))
    return ids


def test_frontend_uses_section_id_not_section() -> None:
    """🔴 请求体字段名必须是 section_id —— 写成 section 会让后端返回 422。"""
    offenders = []
    for path in _D1_SOURCES:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        # 只看 review-dialog/ai-generate 调用附近的请求体
        for m in re.finditer(r"review-dialog/ai-generate[\s\S]{0,400}", text):
            block = m.group(0)
            if re.search(r"^\s*section:\s", block, re.M):
                offenders.append(f"{path.name}: 用了 `section:` 而非 `section_id:`")
    assert offenders == [], offenders


def test_frontend_reads_generated_text() -> None:
    """响应字段是 generated_text；读 `.text` 会永远拿到空串。"""
    offenders = []
    for path in _D1_SOURCES:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r"review-dialog/ai-generate[\s\S]{0,600}", text):
            if "generated_text" not in m.group(0):
                offenders.append(f"{path.name}: 未读取 generated_text")
    assert offenders == [], offenders


def test_all_frontend_section_ids_registered() -> None:
    found: set[str] = set()
    for path in _D1_SOURCES:
        if not path.exists():
            pytest.skip(f"前端源码缺失：{path}")
        found |= _extract_section_ids(path.read_text(encoding="utf-8"))
    assert found, "未从前端源码抽到任何 section_id（正则可能失效）"
    missing = sorted(s for s in found if s not in _SECTION_PROMPTS)
    assert missing == [], f"前端会发出但后端未登记专属 prompt 的 section_id：{missing}"
