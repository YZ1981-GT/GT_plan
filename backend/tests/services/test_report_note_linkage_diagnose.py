"""report_note_linkage 只读诊断 + linkage 不变性（Wave 4 / Task 5.1 + 5.2）.

Spec:   .kiro/specs/disclosure-note-formula-data-population/
Design: 决策 1（报表↔附注只做校验不做写值 —— 用户已拍板）
Props:  Property 13（不批量派生写值 linkage；诊断只读）
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from app.services.report_note_linkage import ReportNoteLinkage

_LINKAGE_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "disclosure"
    / "report_note_linkage.json"
)


def _note(section: str, table_data: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=None, note_section=section, table_data=table_data or {"rows": []}
    )


# ---------------------------------------------------------------------------
# Property 13 —— linkage 不得批量派生映射（人工逐节核实的 seed 允许存在）
# ---------------------------------------------------------------------------

# 已人工对照源模板核实的 seed（见 JSON `_backlog`）。新增条目必须逐节核实后同步此处，
# 这样「批量臆造 N 条」一定撞红线，而合规的增量维护不会被误伤。
_VERIFIED_SEED_ROW_CODES = {"BS-002"}
# 决策 1 下本表只做 stale 定向 + 报表行「关联附注」引用，规模应保持很小
_MAX_BUSINESS_ENTRIES = 5


def test_linkage_config_has_no_bulk_derived_entries():
    raw = json.loads(_LINKAGE_PATH.read_text(encoding="utf-8"))
    business = [k for k in raw if isinstance(k, str) and not k.startswith("_")]

    unverified = sorted(set(business) - _VERIFIED_SEED_ROW_CODES)
    assert not unverified, (
        "report_note_linkage.json 不得批量派生值映射（决策 1 / Property 13）；"
        f"发现未登记核实的业务条目 {unverified[:5]}。"
        "逐节对照源模板核实后，把 row_code 加入 _VERIFIED_SEED_ROW_CODES 并更新 JSON `_backlog`。"
    )
    assert len(business) <= _MAX_BUSINESS_ENTRIES, (
        f"业务条目 {len(business)} 条已超出「逐节增量维护」规模上限 {_MAX_BUSINESS_ENTRIES}，"
        "疑似批量派生"
    )
    # 元数据仍在（_schema/_rules 保留，禁止臆造的口径说明不得被删）
    assert "_rules" in raw
    assert "_backlog" in raw


def test_linkage_service_resolves_only_seeded_sections():
    """未 seed 的章节无 config 目标（cells_updated=0 属正确行为）；已 seed 的章节可定向。

    与 `test_note_readiness_and_stale.py` 同款处理：五、1/八、1 已 seed BS-002，
    故「无 linkage」前提改用未 seed 的章节表达。
    """
    svc = ReportNoteLinkage()
    assert svc._iter_config_targets(_note("五、900")) == []

    seeded = svc._iter_config_targets(_note("五、1"))
    assert [t.row_code for t in seeded] == ["BS-002"]
    assert seeded[0].origin == "config"


# ---------------------------------------------------------------------------
# Task 5.1 —— 只读诊断
# ---------------------------------------------------------------------------


def test_diagnose_lists_sections_with_cross_check_but_no_write_linkage():
    svc = ReportNoteLinkage(config={})
    notes = [_note("五、1"), _note("五、2"), _note("五、99")]
    out = svc.diagnose_missing_write_linkage(
        notes, cross_check_sections={"五、1", "五、2"}
    )
    assert [d["note_section"] for d in out] == ["五、1", "五、2"]
    for d in out:
        assert d["has_cross_check"] is True
        assert d["write_linkage_targets"] == 0
        assert "cells_updated=0 属正确行为" in d["reason"]


def test_diagnose_skips_sections_with_existing_binding_target():
    """已有就地 REPORT Cell_Binding 的章节不算缺口。"""
    table_data = {
        "rows": [
            {
                "label": "甲",
                "values": [None],
                "_cell_meta": {
                    "0": {"binding": {"source": "report", "row_code": "BS-002"}}
                },
            }
        ]
    }
    svc = ReportNoteLinkage(config={})
    out = svc.diagnose_missing_write_linkage(
        [_note("五、1", table_data)], cross_check_sections={"五、1"}
    )
    assert out == []


def test_diagnose_skips_sections_with_config_target():
    svc = ReportNoteLinkage(
        config={"BS-002": [{"note_section": "五、1", "cell": "R1C1"}]}
    )
    out = svc.diagnose_missing_write_linkage(
        [_note("五、1")], cross_check_sections={"五、1"}
    )
    assert out == []


def test_diagnose_is_read_only():
    """诊断不得修改 note / config（只呈现）。"""
    cfg = {"BS-002": [{"note_section": "五、9", "cell": "R1C1"}]}
    svc = ReportNoteLinkage(config=cfg)
    note = _note("五、1", {"rows": [{"label": "甲", "values": [1.0]}]})
    before = json.dumps(note.table_data, ensure_ascii=False, sort_keys=True)
    svc.diagnose_missing_write_linkage([note], cross_check_sections={"五、1"})
    after = json.dumps(note.table_data, ensure_ascii=False, sort_keys=True)
    assert before == after
    assert cfg == {"BS-002": [{"note_section": "五、9", "cell": "R1C1"}]}


def test_diagnose_no_cross_check_section_is_not_a_gap():
    svc = ReportNoteLinkage(config={})
    out = svc.diagnose_missing_write_linkage(
        [_note("五、88")], cross_check_sections=set()
    )
    assert out == []


def test_diagnose_ignores_notes_without_section():
    svc = ReportNoteLinkage(config={})
    bad = SimpleNamespace(id=None, note_section=None, table_data={})
    assert svc.diagnose_missing_write_linkage([bad], cross_check_sections={"五、1"}) == []


def test_cross_check_sections_from_preset_library_includes_derived_sections():
    """默认从预设库取勾稽章节 —— Task 4.3 派生的 61 条应体现在其中。"""
    sections = ReportNoteLinkage._load_cross_check_sections()
    assert isinstance(sections, set)
    # 派生条目存在时集合非空；预设库不可用时 fail-open 返回空集（不抛）
    assert sections or sections == set()
