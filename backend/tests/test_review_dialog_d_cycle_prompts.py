"""D 类剩余循环（D3/D5/D6/D7）披露说明的 AI prompt 守卫。

背景：四个循环的说明文本域此前**完全没有 AI 辅助入口**（平台铁律要求每个文本区都有），
本 spec 接入共享 `useDisclosureNoteAi`。接入后立刻撞上第二条铁律 ——
**section_id 未在后端 `_SECTION_PROMPTS` 登记就会回退通用 prompt（过短 → 诱导模型
自造披露内容）**。

本守卫从**前端文本域键集常量**派生期望的 section_id，因此新增一个说明文本域时
必然要求后端补一条专属 prompt，不会出现「加了文本域但 AI 空转 / 乱编」。

section_id 命名规则（与各组件 `buildSectionId` 逐字一致）：
- D3：`d3-disclosure-listed-{key}-note`（键 = `nature` / `longTerm` / `change`；
  国企侧源模板无说明段，故不登记）
- D5：`d5-disclosure-{key}-note`（键已含变体，如 `listed-1` / `soe-1`）
- D6：`d6-disclosure-{key 去掉 D6-note- 前缀}-note`
- D7：`d7-disclosure-{key 去掉 D7-note- 前缀}-note`（含源模板要求的 3 段定性披露 × 两版）

spec: .kiro/specs/d-cycle-remaining-disclosure-alignment/ R4.1
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.routers.review_dialog import _SECTION_PROMPTS, resolve_review_ai_prompt

_REPO = Path(__file__).resolve().parent.parent.parent
_WORKPAPER = _REPO / "audit-platform" / "frontend" / "src" / "components" / "workpaper"
_COMPOSABLES = _WORKPAPER / "composables"

_TAB_SOURCES = {
    "d3": _WORKPAPER / "d3" / "D3TabDisclosureListed.vue",
    "d5": _WORKPAPER / "d5" / "D5TabDisclosure.vue",
    "d6": _WORKPAPER / "d6" / "D6TabDisclosure.vue",
    "d7": _WORKPAPER / "d7" / "D7TabDisclosure.vue",
}
_MAP_SOURCES = {
    cycle: _COMPOSABLES / f"{cycle}NoteSectionMap.ts" for cycle in ("d3", "d5", "d6", "d7")
}


def _read(path: Path) -> str:
    if not path.exists():
        pytest.skip(f"前端源码缺失：{path}")
    return path.read_text(encoding="utf-8")


def _text_section_keys(cycle: str) -> list[str]:
    """从 `DX_NOTE_TEXT_SECTIONS` 常量块抽静态声明的 `key: '...'`。"""
    src = _read(_MAP_SOURCES[cycle])
    const_name = f"{cycle.upper()}_NOTE_TEXT_SECTIONS"
    idx = src.find(f"export const {const_name}")
    assert idx >= 0, f"{cycle}: 缺常量 {const_name}"
    block = src[idx: idx + 2500]
    return re.findall(r"key:\s*'([^']+)'", block)


def _expected_ids(cycle: str) -> list[str]:
    keys = _text_section_keys(cycle)
    assert keys, f"{cycle}: 未抽到任何文本域键（正则可能失效）"
    if cycle == "d3":
        return [f"d3-disclosure-listed-{k}-note" for k in keys]
    prefix = f"{cycle.upper()}-note-"
    return [f"{cycle}-disclosure-{k.replace(prefix, '')}-note" for k in keys]


ALL_EXPECTED: list[tuple[str, str]] = [
    (cycle, sid) for cycle in ("d3", "d5", "d6", "d7") for sid in _expected_ids(cycle)
]

# D7 的 3 段定性披露由 `D7_QUALITATIVE_TITLES` 动态生成键（抓不到静态 `key:`），单独列
D7_QUALITATIVE_IDS = [
    f"d7-disclosure-{variant}-qual-{i}-note"
    for variant in ("listed", "soe")
    for i in (1, 2, 3)
]


@pytest.mark.parametrize(("cycle", "section_id"), ALL_EXPECTED, ids=[s for _, s in ALL_EXPECTED])
def test_section_has_dedicated_prompt(cycle: str, section_id: str) -> None:
    assert section_id in _SECTION_PROMPTS, (
        f"{section_id} 未登记专属 prompt → 回退通用 prompt，"
        "铁律：prompt 过短会诱导模型自造披露内容"
    )


@pytest.mark.parametrize("section_id", D7_QUALITATIVE_IDS)
def test_d7_qualitative_sections_registered(section_id: str) -> None:
    """源模板 A32-A34 / A15-A17 的三段定性披露（本 spec 新补的录入位置）。"""
    assert section_id in _SECTION_PROMPTS


def test_d7_qualitative_titles_count_is_three() -> None:
    """前端定性段数量变了就要同步补 prompt（防守卫与实现漂移）。"""
    src = _read(_MAP_SOURCES["d7"])
    idx = src.find("export const D7_QUALITATIVE_TITLES")
    assert idx >= 0
    start = src.index("= [", idx) + 3          # 跳过类型标注里的 `string[]`
    block = src[start: src.index("]", start)]
    # 每条标题是一个单引号字符串（可跨行拼接）→ 数行首引号
    count = len(re.findall(r"^\s+'", block, re.M))
    assert count == 3, f"定性段数量应为 3，实际 {count}"


@pytest.mark.parametrize("cycle", sorted(_TAB_SOURCES))
def test_tab_wires_shared_ai_composable(cycle: str) -> None:
    """四个 Tab 必须接共享 composable（禁止各写一份 http.post，字段名极易写错）。"""
    src = _read(_TAB_SOURCES[cycle])
    assert "useDisclosureNoteAi" in src, f"{cycle}: 未接入 useDisclosureNoteAi"
    assert "buildSectionId" in src, f"{cycle}: 未声明 buildSectionId"
    assert re.search(r"runAi\(", src), f"{cycle}: 模板里没有 AI 按钮"
    assert re.search(r"openReview\(", src), f"{cycle}: 模板里没有复核按钮"


@pytest.mark.parametrize("cycle", sorted(_TAB_SOURCES))
def test_build_section_id_matches_registered_prefix(cycle: str) -> None:
    """`buildSectionId` 的字面前缀必须与后端登记的键前缀一致。"""
    src = _read(_TAB_SOURCES[cycle])
    m = re.search(r"buildSectionId:\s*\(k\)\s*=>\s*`([^`]+)`", src)
    assert m, f"{cycle}: 未找到 buildSectionId 模板字符串"
    tmpl = m.group(1)
    assert tmpl.startswith(f"{cycle}-disclosure-"), f"{cycle}: 前缀不符 → {tmpl}"
    assert tmpl.endswith("-note"), f"{cycle}: 必须以 -note 结尾（后端按 note 判定说明/结论）"


def test_shared_composable_uses_correct_contract() -> None:
    """🔴 端点契约：请求 `section_id` / 响应 `generated_text`（写错会 422 + 静默空转）。"""
    src = _read(_COMPOSABLES / "useDisclosureNoteAi.ts")
    assert "review-dialog/ai-generate" in src
    assert "section_id:" in src
    assert "generated_text" in src
    assert not re.search(r"^\s*section:\s", src, re.M), "不得用 `section:` 字段"


@pytest.mark.parametrize(
    "section_id",
    sorted(sid for _, sid in ALL_EXPECTED) + D7_QUALITATIVE_IDS,
)
def test_resolve_returns_dedicated_prompt(section_id: str) -> None:
    resolved = resolve_review_ai_prompt(section_id, "审计说明")
    assert _SECTION_PROMPTS[section_id] in resolved


def test_no_orphan_d_cycle_prompts() -> None:
    """后端登记的 D3/D5/D6/D7 prompt 不得有前端不会发出的孤儿键。"""
    expected = {sid for _, sid in ALL_EXPECTED} | set(D7_QUALITATIVE_IDS)
    registered = {
        k for k in _SECTION_PROMPTS
        if re.match(r"^d[3567]-disclosure-", k)
    }
    orphans = sorted(registered - expected)
    assert orphans == [], f"后端登记了前端不会发出的 section_id：{orphans}"
