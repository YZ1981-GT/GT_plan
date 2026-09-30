# -*- coding: utf-8 -*-
"""防复发：附注模板的「陈旧副本整体覆盖」必须被当场拦下。

═══ 为什么需要这条（2026-09-30 事故） ═══

`56acf363d feat(g-foundation)` 在一个与附注无关的提交里，把两份附注模板整体换成了
7 月下旬的陈旧副本（listed 带 `columns` 的表 411 → 11，soe 260 → 3，另删整章、
改名覆盖母公司章）。**既有守卫当场全红**（note 相关 67 个测试文件 ~43 红 → 1258 红），
但这批测试不在 pre-push 门里 ⇒ 没人被拦住，三天后才靠「逐条查红」撞出来；
期间还有两轮修复把守卫往陈旧数据上凑（改判据容 `<br/>`、把普查登记值改成陈旧值），
差点把错误固化。

⇒ 本文件只锁**不可能是有意改动**的几条宏观不变量，信号强、误报近零、跑得快
（纯 JSON 读，< 1 秒），适合放进任何快速门：

  * 结构元数据覆盖率是**棘轮**：带 `columns` / `guidance` 的表只许增不许减
    （本仓库所有附注 spec 都是往上补，从未有过「批量删列头」的合法动作）
  * 表头 `<br/>` 残留为 0（覆盖前实测 0，陈旧副本带回 67 / 77）
  * 零悬空 `parent_section_id`

阈值按 `restore_note_templates_from_stale_overwrite.py` 恢复后的**现算值**登记，
只许调低（收紧）不许调高，调高需要写明理由（沿用 `test_note_columns_coverage` 的棘轮约定）。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
DATA = BACKEND / "data"
VARIANTS = ("listed", "soe")

#: 恢复后现算（2026-09-30）：(带 columns 的表数下限, 带 guidance 的表数下限)
#: 🔴 只许调高下限（= 收紧）；下调意味着有人删了列头/编制提示，必须先查是不是又一次覆盖
COVERAGE_FLOOR: dict[str, tuple[int, int]] = {
    "listed": (411, 393),
    "soe": (260, 251),
}

#: 事故现场值（陈旧副本）—— 反向自检用：守卫必须能把它判红
STALE_SNAPSHOT: dict[str, tuple[int, int]] = {
    "listed": (11, 18),
    "soe": (3, 19),
}


def _load(variant: str) -> dict:
    return json.loads((DATA / f"note_template_{variant}.json").read_text(encoding="utf-8"))


def _coverage(doc: dict) -> tuple[int, int]:
    tables = [t for s in doc.get("sections") or [] for t in (s.get("tables") or [])]
    return (
        sum(1 for t in tables if t.get("columns")),
        sum(1 for t in tables if t.get("guidance")),
    )


def _br_headers(doc: dict) -> list[str]:
    return [
        f"{s.get('section_number')} / {t.get('name')} / {h!r}"
        for s in doc.get("sections") or []
        for t in (s.get("tables") or [])
        for h in (t.get("headers") or [])
        if "<br" in str(h).lower()
    ]


def _violations(variant: str, cols: int, guid: int) -> list[str]:
    floor_c, floor_g = COVERAGE_FLOOR[variant]
    out: list[str] = []
    if cols < floor_c:
        out.append(f"带 columns 的表 {cols} < 下限 {floor_c}")
    if guid < floor_g:
        out.append(f"带 guidance 的表 {guid} < 下限 {floor_g}")
    return out


@pytest.mark.parametrize("variant", VARIANTS)
def test_structure_metadata_coverage_is_a_ratchet(variant: str) -> None:
    cols, guid = _coverage(_load(variant))
    problems = _violations(variant, cols, guid)
    assert not problems, (
        f"[{variant}] 附注模板结构元数据覆盖率下降：{problems}。\n"
        "这几乎不可能是有意改动 —— 先查是不是又把陈旧副本整体提交了："
        "`git diff --stat HEAD -- backend/data/note_template_*.json`，"
        "若是，用 `python backend/scripts/fix/restore_note_templates_from_stale_overwrite.py`"
        " 的同一套三方比较恢复。"
    )


@pytest.mark.parametrize("variant", VARIANTS)
def test_no_br_markup_in_headers(variant: str) -> None:
    hits = _br_headers(_load(variant))
    assert not hits, (
        f"[{variant}] 表头含 {len(hits)} 处 `<br/>`（7 月份 md 重建的残留形态，后续 spec 已清零；"
        "重新出现通常意味着陈旧副本回来了）：\n  " + "\n  ".join(hits[:10])
    )


@pytest.mark.parametrize("variant", VARIANTS)
def test_no_dangling_parent_section_id(variant: str) -> None:
    secs = _load(variant).get("sections") or []
    ids = {s.get("section_id") for s in secs}
    dangling = [
        f"{s.get('section_number')} -> {s.get('parent_section_id')}"
        for s in secs
        if s.get("parent_section_id") and s["parent_section_id"] not in ids
    ]
    assert not dangling, f"[{variant}] 悬空 parent_section_id：{dangling}"


def test_ratchet_would_have_caught_the_incident() -> None:
    """反向自检：用事故现场的真实数值喂判据，必须判红（否则棘轮是摆设）。"""
    for variant, (cols, guid) in STALE_SNAPSHOT.items():
        assert _violations(variant, cols, guid), f"[{variant}] 事故现场值没被判红"


def test_floor_is_not_slack() -> None:
    """反向自检：下限必须贴着现值（差距 ≤ 5%），否则下限形同虚设、能漏掉小规模覆盖。"""
    for variant in VARIANTS:
        cols, guid = _coverage(_load(variant))
        floor_c, floor_g = COVERAGE_FLOOR[variant]
        assert floor_c >= int(cols * 0.95) and floor_g >= int(guid * 0.95), (
            f"[{variant}] 下限 ({floor_c},{floor_g}) 远低于现值 ({cols},{guid})，"
            "请把 COVERAGE_FLOOR 上调到现值（只许收紧）"
        )
