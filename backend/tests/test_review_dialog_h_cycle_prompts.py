"""H 循环披露 AI prompt 登记完备性守卫（Property 8）。

前端 `useHCycleDisclosureAi` 按 ``{wpCode}-disclosure-{variant}-{key}`` 构造
``section_id``；键集真源在三个 `.ts` 常量文件里。后端 `_SECTION_PROMPTS` 缺登记时
`resolve_review_ai_prompt` 回退**通用** prompt —— 过短的通用 prompt 会诱导模型自造
披露内容（平台铁律），且这种缺失不报错、不红测试、只能靠人肉发现。

故本守卫从**前端源码**抽键集，双向断言：
- 前端每个 section_id 都在 `_SECTION_PROMPTS` 里；
- `_SECTION_PROMPTS` 里 H 循环前缀的键都能在前端找到（无孤儿）。

spec: .kiro/specs/h-cycle-legacy-cleanup-and-platform-hygiene/ R2 / R3（Task 9）
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.routers.review_dialog import _SECTION_PROMPTS, resolve_review_ai_prompt

_ROOT = Path(__file__).resolve().parent.parent
_FE = (
    _ROOT.parent / "audit-platform" / "frontend" / "src" / "components"
    / "workpaper" / "composables"
)
_H_CYCLE_TS = _FE / "hCycleNoteAiSections.ts"
_H8_TS = _FE / "h8NoteAiSections.ts"
_H9_TS = _FE / "h9NoteAiSections.ts"

_NO_FABRICATION_MARK = "严禁虚构"

# 允许「后端有 prompt 但前端暂无调用点」的例外；每条须写明理由。
_ORPHAN_ALLOW: dict[str, str] = {}


def _strip_comments(src: str) -> str:
    src = re.sub(r"/\*[\s\S]*?\*/", "", src)
    src = re.sub(r"(^|[^:])//[^\n]*", r"\1", src)
    return src


def _block(src: str, name: str) -> str:
    """截取 `export const NAME = { … }` 的对象体（花括号配对）。"""
    i = src.find(f"export const {name}")
    assert i >= 0, f"未找到 {name}"
    j = src.find("{", i)
    depth = 0
    for k in range(j, len(src)):
        if src[k] == "{":
            depth += 1
        elif src[k] == "}":
            depth -= 1
            if depth == 0:
                return src[j : k + 1]
    raise AssertionError(f"{name} 对象体未闭合")


def _parse_variant_keys(body: str) -> dict[str, list[str]]:
    """从 `{ listed: { a: '…', b: '…' }, soe: { … } }` 抽 ``{变体: [键]}``。"""
    out: dict[str, list[str]] = {}
    for vm in re.finditer(r"(listed|soe)\s*:\s*\{", body):
        variant = vm.group(1)
        start = body.index("{", vm.end() - 1)
        depth = 0
        end = start
        for k in range(start, len(body)):
            if body[k] == "{":
                depth += 1
            elif body[k] == "}":
                depth -= 1
                if depth == 0:
                    end = k
                    break
        inner = body[start : end + 1]
        keys = [m.group(1) for m in re.finditer(r"(\w+)\s*:\s*'", inner)]
        out[variant] = keys
    return out


def _expected_section_ids() -> set[str]:
    ids: set[str] = set()

    # hCycleNoteAiSections.ts：{ H1: { listed: {...}, soe: {...} }, H2: {...}, ... }
    src = _strip_comments(_H_CYCLE_TS.read_text(encoding="utf-8"))
    body = _block(src, "H_CYCLE_NOTE_AI_SECTIONS")
    for wm in re.finditer(r"(H\d+)\s*:\s*\{", body):
        wp = wm.group(1)
        start = body.index("{", wm.end() - 1)
        depth = 0
        end = start
        for k in range(start, len(body)):
            if body[k] == "{":
                depth += 1
            elif body[k] == "}":
                depth -= 1
                if depth == 0:
                    end = k
                    break
        for variant, keys in _parse_variant_keys(body[start : end + 1]).items():
            for key in keys:
                ids.add(f"{wp}-disclosure-{variant}-{key}")

    for wp, path, const in (
        ("H8", _H8_TS, "H8_NOTE_AI_SECTIONS"),
        ("H9", _H9_TS, "H9_NOTE_AI_SECTIONS"),
    ):
        s = _strip_comments(path.read_text(encoding="utf-8"))
        for variant, keys in _parse_variant_keys(_block(s, const)).items():
            for key in keys:
                ids.add(f"{wp}-disclosure-{variant}-{key}")
    return ids


EXPECTED = _expected_section_ids()


def test_extraction_not_empty() -> None:
    """反向自检：抽取结果非空且覆盖 7 个循环，否则断言全在空转。"""
    assert len(EXPECTED) >= 20, f"抽到的 section_id 过少（{len(EXPECTED)}），正则可能失效"
    prefixes = {sid.split("-", 1)[0] for sid in EXPECTED}
    assert prefixes == {"H1", "H2", "H4", "H5", "H6", "H8", "H9"}, prefixes


@pytest.mark.parametrize("section_id", sorted(EXPECTED))
def test_prompt_registered(section_id: str) -> None:
    assert section_id in _SECTION_PROMPTS, (
        f"前端有 AI 按钮但后端 _SECTION_PROMPTS 未登记「{section_id}」→ "
        "回退通用 prompt（过短，会诱导模型自造披露内容）"
    )


@pytest.mark.parametrize("section_id", sorted(EXPECTED))
def test_prompt_quality(section_id: str) -> None:
    prompt = _SECTION_PROMPTS[section_id]
    body = prompt.split(_NO_FABRICATION_MARK)[0]
    assert len(body.strip()) >= 20, f"{section_id} 的 prompt 过短（{len(body)} 字）"
    assert _NO_FABRICATION_MARK in prompt, f"{section_id} 的 prompt 缺「不得虚构」约束"


def test_no_orphan_h_cycle_prompts() -> None:
    """后端不得残留前端已无调用点的 H 循环 prompt。"""
    registered = {
        sid
        for sid in _SECTION_PROMPTS
        if re.match(r"^H(1|2|4|5|6|8|9)-disclosure-", sid)
    }
    orphans = sorted(registered - EXPECTED - set(_ORPHAN_ALLOW))
    assert not orphans, f"以下 prompt 在前端无调用点（请删除或登记理由）：{orphans}"


def test_resolve_returns_specific_prompt() -> None:
    """`resolve_review_ai_prompt` 命中专属 prompt（不是回退通用）。"""
    sid = "H8-disclosure-listed-impairment"
    specific = resolve_review_ai_prompt(sid, "审计说明")
    generic = resolve_review_ai_prompt("H8-does-not-exist-xxx", "审计说明")
    assert specific != generic
    assert "可收回金额" in specific


def test_allowlist_has_no_stale_entries() -> None:
    stale = sorted(k for k in _ORPHAN_ALLOW if k in EXPECTED)
    assert not stale, f"以下条目已在前端使用，请从 _ORPHAN_ALLOW 移出：{stale}"
