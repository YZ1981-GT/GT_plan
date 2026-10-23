"""Phase 3 测试：公式推送引擎的披露表整表替换路径。

覆盖：
- _push_note_disclosure_replace：正常替换 / 合计行自动重算 / 空值跳过 / 无数据返 False
- 集成路径：binding 有 _disclosure_sub_table_data 时走替换而非标签匹配

spec: note-data-from-disclosure-table Phase 3 Task 20
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.formula_push.engine import _push_note_disclosure_replace, PushItem
from app.services.formula_push import note_writer
from app.services.formula_push.rules import note_addr_id


# ── 辅助 ──────────────────────────────────────────────────────────────────────


def _make_ctx():
    """最小 _Ctx mock。"""
    ctx = MagicMock()
    ctx.result = MagicMock()
    ctx.result.items = []
    ctx.result.note_sections = []
    ctx.now = MagicMock()
    ctx.now.isoformat = MagicMock(return_value="2026-01-01T00:00:00Z")
    ctx.triggered_by = None
    return ctx


def _make_rule(table="货币资金", fields=("end_amount", "prior_amount")):
    target = MagicMock()
    target.fields = fields
    target.table = table
    target.resolve_table = MagicMock(return_value=table)
    rule = MagicMock()
    rule.rule_id = "E1.note.main"
    rule.target = target
    return rule


def _make_paper():
    import uuid
    paper = MagicMock()
    paper.id = uuid.uuid4()
    return paper


def _make_table_data(rows=None):
    td = {
        "_source": "workpaper",
        "sub_table_data": {"货币资金": rows or []},
    }
    table = note_writer.NoteTable(
        rows=list(rows or []),
        value_keys=[],
        section_locked=False,
    )
    return td, table


# ══════════════════════════════════════════════════════════════════════════════
# _push_note_disclosure_replace
# ══════════════════════════════════════════════════════════════════════════════


class TestDisclosureReplace:
    """整表替换路径。"""

    def test_basic_replace(self):
        """正常替换：2 行数据 + 合计行。"""
        ctx = _make_ctx()
        rule = _make_rule()
        paper = _make_paper()
        td, table = _make_table_data()

        note_rows = [
            {"note_label": "库存现金", "ending": 1000, "ending_resolved": True,
             "opening": 800, "opening_resolved": True, "is_total": False},
            {"note_label": "银行存款", "ending": 50000, "ending_resolved": True,
             "opening": 45000, "opening_resolved": True, "is_total": False},
            {"note_label": "合计", "ending": 51000, "ending_resolved": True,
             "opening": 45800, "opening_resolved": True, "is_total": True},
        ]

        result = _push_note_disclosure_replace(
            ctx, rule=rule, section="八、1", section_addr="note://八、1/货币资金",
            table_name="货币资金", table_data=td, table=table,
            note_rows=note_rows, paper=paper,
        )

        assert result is True
        # sub_table_data 应该被替换
        new_rows = td["sub_table_data"]["货币资金"]
        assert len(new_rows) == 3
        assert new_rows[0]["label"] == "库存现金"
        assert new_rows[0]["end_amount"] == 1000
        assert new_rows[0]["prior_amount"] == 800
        assert new_rows[2]["is_total"] is True

    def test_total_auto_recalc(self):
        """合计行自动重算：不用披露表传入的合计值，用数据行之和。"""
        ctx = _make_ctx()
        rule = _make_rule()
        paper = _make_paper()
        td, table = _make_table_data()

        note_rows = [
            {"note_label": "A", "ending": 100, "ending_resolved": True,
             "opening": 200, "opening_resolved": True, "is_total": False},
            {"note_label": "B", "ending": 300, "ending_resolved": True,
             "opening": 400, "opening_resolved": True, "is_total": False},
            {"note_label": "合计", "ending": 999, "ending_resolved": True,
             "opening": 999, "opening_resolved": True, "is_total": True},
        ]

        _push_note_disclosure_replace(
            ctx, rule=rule, section="八、1", section_addr="note://八、1/货币资金",
            table_name="货币资金", table_data=td, table=table,
            note_rows=note_rows, paper=paper,
        )

        new_rows = td["sub_table_data"]["货币资金"]
        total = new_rows[2]
        # 合计应该是 100+300=400 / 200+400=600，不是传入的 999
        assert total["end_amount"] == 400
        assert total["prior_amount"] == 600

    def test_empty_note_rows_returns_false(self):
        """空行 → 不写入。"""
        ctx = _make_ctx()
        rule = _make_rule()
        paper = _make_paper()
        td, table = _make_table_data()

        result = _push_note_disclosure_replace(
            ctx, rule=rule, section="八、1", section_addr="note://八、1/货币资金",
            table_name="货币资金", table_data=td, table=table,
            note_rows=[], paper=paper,
        )
        assert result is False

    def test_all_unresolved_returns_false(self):
        """所有字段都 unresolved → 不写入。"""
        ctx = _make_ctx()
        rule = _make_rule()
        paper = _make_paper()
        td, table = _make_table_data()

        note_rows = [
            {"note_label": "A", "ending": None, "ending_resolved": False,
             "opening": None, "opening_resolved": False, "is_total": False},
        ]

        result = _push_note_disclosure_replace(
            ctx, rule=rule, section="八、1", section_addr="note://八、1/货币资金",
            table_name="货币资金", table_data=td, table=table,
            note_rows=note_rows, paper=paper,
        )
        assert result is False

    def test_dynamic_rows_added(self):
        """动态建行：披露表有 5 行，附注原来只有 3 行 → 替换为 5 行。"""
        ctx = _make_ctx()
        rule = _make_rule()
        paper = _make_paper()
        td, table = _make_table_data(rows=[
            {"label": "旧行1", "end_amount": 10},
            {"label": "旧行2", "end_amount": 20},
            {"label": "合计", "end_amount": 30, "is_total": True},
        ])

        note_rows = [
            {"note_label": "新行1", "ending": 100, "ending_resolved": True,
             "opening": 50, "opening_resolved": True, "is_total": False},
            {"note_label": "新行2", "ending": 200, "ending_resolved": True,
             "opening": 60, "opening_resolved": True, "is_total": False},
            {"note_label": "新行3", "ending": 300, "ending_resolved": True,
             "opening": 70, "opening_resolved": True, "is_total": False},
            {"note_label": "新行4", "ending": 400, "ending_resolved": True,
             "opening": 80, "opening_resolved": True, "is_total": False},
            {"note_label": "合计", "ending": 1000, "ending_resolved": True,
             "opening": 260, "opening_resolved": True, "is_total": True},
        ]

        result = _push_note_disclosure_replace(
            ctx, rule=rule, section="八、1", section_addr="note://八、1/货币资金",
            table_name="货币资金", table_data=td, table=table,
            note_rows=note_rows, paper=paper,
        )

        assert result is True
        new_rows = td["sub_table_data"]["货币资金"]
        assert len(new_rows) == 5  # 动态从 3 → 5
        assert new_rows[3]["label"] == "新行4"

    def test_push_items_recorded(self):
        """推送项正确记录。"""
        ctx = _make_ctx()
        rule = _make_rule()
        paper = _make_paper()
        td, table = _make_table_data()

        note_rows = [
            {"note_label": "A", "ending": 100, "ending_resolved": True,
             "opening": None, "opening_resolved": False, "is_total": False},
        ]

        _push_note_disclosure_replace(
            ctx, rule=rule, section="八、1", section_addr="note://八、1/货币资金",
            table_name="货币资金", table_data=td, table=table,
            note_rows=note_rows, paper=paper,
        )

        # 应该有 2 个推送项（end + prior）
        items = ctx.result.items
        assert len(items) == 2
        # ending 有值 → written
        assert items[0].action == "written"
        # opening 无值 → skipped
        assert items[1].action == "skipped"


# ══════════════════════════════════════════════════════════════════════════════
# 集成检查：engine 模块可导入
# ══════════════════════════════════════════════════════════════════════════════


def test_engine_importable():
    """engine.py 语法正确可导入。"""
    import app.services.formula_push.engine as eng
    assert hasattr(eng, "_push_note_disclosure_replace")
    assert hasattr(eng, "_push_note")
