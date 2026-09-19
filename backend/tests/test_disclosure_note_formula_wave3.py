"""Wave3 单测 + PBT — ReportNoteLinkage 单一真源 + 报表→附注真同步（Task 4.4）.

Spec:   .kiro/specs/disclosure-note-formula-and-report-sync/ Wave3 (Task 4.1/4.2/4.3)
Reqs:   3.1 / 3.3 / 3.4 / 4.1 / 4.2 / 4.4 / 8.3 / 8.4 / 9.1

覆盖正确性属性：
- Property 7（linkage 单一真源优先级）：同一 row_code 在 Cell_Binding 与 config 都有
  目标时以 Cell_Binding 为准；``targets_for_report_row`` 与 ``report_rows_for_note``
  对同一 note 取到相同目标集。
- Property 8（同步真实统计）：``sync_report_to_notes`` 的 cells_updated == 实际写入的
  公式单元格数；无 linkage 的报表行计入 skipped_sections；validation_run 反映实际。
- 开关关闭零回归：flag=False 时仅清 is_stale + validation_run/skipped_sections 硬编码
  （与 characterization 基线一致）。
- manual/locked 保留（Property 6 语义在同步路径复验）。
- 幂等（Req3.7）：相同报表数二次同步产生逐值相等的 table_data。
"""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from hypothesis import given, settings as hsettings
from hypothesis import strategies as st

from app.services.report_note_linkage import LinkTarget, ReportNoteLinkage
from app.services.report_note_sync_service import ReportNoteSyncService

PROJECT_ID = uuid4()
YEAR = 2025

_FLAG = "app.services.report_note_sync_service._formula_enabled"
_ENGINE = "app.services.note_validation_engine.NoteValidationEngine"


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


def _make_db_mock():
    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


def _result_scalars(objs):
    res = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = objs
    res.scalars.return_value = scalars
    return res


def _report_row(row_code, amount):
    r = MagicMock()
    r.row_code = row_code
    r.current_period_amount = Decimal(str(amount))
    return r


def _note_with_report_binding(
    section="五、22",
    row_code="BS-015",
    row_idx=2,
    col=1,
    value=None,
    mode=None,
):
    """一张附注单表：某单元格内嵌 REPORT Cell_Binding。

    合计行放在 rows[row_idx]，绑定列 col。mode 可设 manual/locked 测试保留。
    """
    rows = [
        {"values": ["项目", "期末"]},
        {"values": ["甲", 100.0]},
        {"values": ["乙", 200.0]},
    ]
    # 确保 rows 长度覆盖 row_idx
    while len(rows) <= row_idx:
        rows.append({"values": ["占位", None]})
    target_row: dict = {
        "values": ["合计", value],
        "_cell_meta": {str(col): {"binding": {"source": "report", "row_code": row_code}}},
    }
    if mode:
        target_row["_cell_modes"] = {str(col): mode}
    rows[row_idx] = target_row
    n = MagicMock()
    n.note_section = section
    n.id = uuid4()
    n.table_data = {"headers": ["项目", "期末"], "rows": rows}
    n.is_stale = True
    return n


def _plain_note(section="五、99", is_stale=True):
    n = MagicMock()
    n.note_section = section
    n.id = uuid4()
    n.table_data = {"rows": [{"values": ["甲", 1.0]}]}
    n.is_stale = is_stale
    return n


# ===========================================================================
# Property 7 — ReportNoteLinkage 单一真源优先级
# ===========================================================================


class TestReportNoteLinkagePriority:
    def test_binding_target_found(self):
        note = _note_with_report_binding(row_code="BS-015", row_idx=2, col=1)
        lk = ReportNoteLinkage(config={})
        targets = lk.targets_for_report_row([note], "BS-015")
        assert len(targets) == 1
        t = targets[0]
        assert t.origin == "binding"
        assert (t.table_index, t.row_idx, t.col_idx) == (0, 2, 1)
        assert t.note_section == "五、22"

    def test_config_fallback_when_no_binding(self):
        note = _plain_note(section="五、22")
        config = {"IS-001": [{"note_section": "五、22", "cell": "R2C2", "table_index": 0}]}
        lk = ReportNoteLinkage(config=config)
        targets = lk.targets_for_report_row([note], "IS-001")
        assert len(targets) == 1
        t = targets[0]
        assert t.origin == "config"
        assert (t.row_idx, t.col_idx) == (1, 1)  # R2C2 → 0-based (1,1)

    def test_binding_wins_over_config_same_row_code(self):
        """同一 row_code 两处都有目标 → 只取 Cell_Binding（Req4.2 / Property 7）。"""
        note = _note_with_report_binding(row_code="BS-015", row_idx=2, col=1)
        config = {"BS-015": [{"note_section": "五、22", "cell": "R9C9", "table_index": 0}]}
        lk = ReportNoteLinkage(config=config)
        targets = lk.targets_for_report_row([note], "BS-015")
        assert len(targets) == 1
        assert targets[0].origin == "binding"
        assert (targets[0].row_idx, targets[0].col_idx) == (2, 1)

    def test_report_rows_and_targets_same_set(self):
        """report_rows_for_note 与 targets_for_report_row 取相同目标集（Req4.4）。"""
        note = _note_with_report_binding(row_code="BS-015")
        lk = ReportNoteLinkage(config={})
        rows = lk.report_rows_for_note(note)
        assert rows == {"BS-015"}
        # 每个 row_code 的目标在两个 API 下一致
        for rc in rows:
            via_reverse = lk.report_targets_in_note(note)
            via_forward = lk.targets_for_report_row([note], rc)
            reverse_coords = {
                (t.table_index, t.row_idx, t.col_idx) for t in via_reverse if t.row_code == rc
            }
            forward_coords = {(t.table_index, t.row_idx, t.col_idx) for t in via_forward}
            assert reverse_coords == forward_coords

    def test_invalid_config_cell_skipped(self):
        note = _plain_note(section="五、22")
        config = {"IS-001": [{"note_section": "五、22", "cell": "not-a-cell"}]}
        lk = ReportNoteLinkage(config=config)
        assert lk.targets_for_report_row([note], "IS-001") == []

    def test_missing_config_returns_empty_map(self):
        # config=None 时走文件加载；文件即便存在也仅 _ 前缀元数据 → 空业务映射
        lk = ReportNoteLinkage()
        note = _plain_note(section="五、22")
        # 骨架文件只含 _schema/_rules/_example 元数据键，不产生任何业务目标
        assert lk.targets_for_report_row([note], "_example") == []

    def test_underscore_meta_keys_ignored(self):
        config = {
            "_schema": "meta",
            "_example": [{"note_section": "五、22", "cell": "R2C2"}],
            "BS-1": [{"note_section": "五、22", "cell": "R2C2"}],
        }
        lk = ReportNoteLinkage(config=config)
        note = _plain_note(section="五、22")
        assert lk.targets_for_report_row([note], "_schema") == []
        assert lk.targets_for_report_row([note], "_example") == []
        assert len(lk.targets_for_report_row([note], "BS-1")) == 1

    @hsettings(max_examples=5)
    @given(
        row_code=st.text(min_size=1, max_size=6).filter(lambda s: not s.startswith("_")),
        r=st.integers(min_value=0, max_value=4),
        c=st.integers(min_value=1, max_value=4),
    )
    def test_binding_priority_pbt(self, row_code, r, c):
        note = _note_with_report_binding(row_code=row_code, row_idx=r, col=c)
        config = {row_code: [{"note_section": "五、22", "cell": "R9C9"}]}
        lk = ReportNoteLinkage(config=config)
        targets = lk.targets_for_report_row([note], row_code)
        # 有 binding 目标 → 全部 origin=binding（config 被忽略）
        assert targets and all(t.origin == "binding" for t in targets)


# ===========================================================================
# Property 8 — sync_report_to_notes 真实统计（flag ON）
# ===========================================================================


class TestSyncRealStats:
    @pytest.mark.asyncio
    async def test_writes_report_amount_into_formula_cell(self):
        db = _make_db_mock()
        note = _note_with_report_binding(row_code="BS-015", row_idx=2, col=1)
        db.execute.side_effect = [
            _result_scalars([_report_row("BS-015", "500")]),
            _result_scalars([note]),
        ]
        svc = ReportNoteSyncService(db)
        with patch(_FLAG, return_value=True), patch(_ENGINE) as MockEngine:
            MockEngine.return_value.validate_all = AsyncMock(return_value={})
            result = await svc.sync_report_to_notes(PROJECT_ID, YEAR)

        assert note.table_data["rows"][2]["values"][1] == 500.0
        assert result["cells_updated"] == 1
        assert result["synced_sections"] == 1
        assert result["skipped_sections"] == 0
        assert result["validation_run"] is True
        assert note.is_stale is False

    @pytest.mark.asyncio
    async def test_report_row_without_linkage_counts_skipped(self):
        db = _make_db_mock()
        note = _note_with_report_binding(row_code="BS-015", row_idx=2, col=1)
        db.execute.side_effect = [
            _result_scalars([_report_row("BS-015", "500"), _report_row("IS-099", "88")]),
            _result_scalars([note]),
        ]
        svc = ReportNoteSyncService(db)
        with patch(_FLAG, return_value=True), patch(_ENGINE) as MockEngine:
            MockEngine.return_value.validate_all = AsyncMock(return_value={})
            result = await svc.sync_report_to_notes(PROJECT_ID, YEAR)

        # BS-015 有目标 → 写入；IS-099 无 linkage → skipped
        assert result["cells_updated"] == 1
        assert result["skipped_sections"] == 1

    @pytest.mark.asyncio
    async def test_manual_cell_preserved_not_counted(self):
        db = _make_db_mock()
        note = _note_with_report_binding(
            row_code="BS-015", row_idx=2, col=1, value=999.0, mode="manual"
        )
        db.execute.side_effect = [
            _result_scalars([_report_row("BS-015", "500")]),
            _result_scalars([note]),
        ]
        svc = ReportNoteSyncService(db)
        with patch(_FLAG, return_value=True), patch(_ENGINE) as MockEngine:
            MockEngine.return_value.validate_all = AsyncMock(return_value={})
            result = await svc.sync_report_to_notes(PROJECT_ID, YEAR)

        # manual 保留原值 999，不被 500 覆盖（Req3.2）
        assert note.table_data["rows"][2]["values"][1] == 999.0
        assert result["cells_updated"] == 0
        # 有 linkage 目标（只是被保护）→ 不计 skipped
        assert result["skipped_sections"] == 0

    @pytest.mark.asyncio
    async def test_locked_cell_preserved(self):
        db = _make_db_mock()
        note = _note_with_report_binding(
            row_code="BS-015", row_idx=2, col=1, value=777.0, mode="locked"
        )
        db.execute.side_effect = [
            _result_scalars([_report_row("BS-015", "500")]),
            _result_scalars([note]),
        ]
        svc = ReportNoteSyncService(db)
        with patch(_FLAG, return_value=True), patch(_ENGINE) as MockEngine:
            MockEngine.return_value.validate_all = AsyncMock(return_value={})
            await svc.sync_report_to_notes(PROJECT_ID, YEAR)
        assert note.table_data["rows"][2]["values"][1] == 777.0

    @pytest.mark.asyncio
    async def test_validation_run_false_when_validate_raises(self):
        db = _make_db_mock()
        note = _note_with_report_binding(row_code="BS-015", row_idx=2, col=1)
        db.execute.side_effect = [
            _result_scalars([_report_row("BS-015", "500")]),
            _result_scalars([note]),
        ]
        svc = ReportNoteSyncService(db)
        with patch(_FLAG, return_value=True), patch(_ENGINE) as MockEngine:
            MockEngine.return_value.validate_all = AsyncMock(
                side_effect=RuntimeError("validate down")
            )
            result = await svc.sync_report_to_notes(PROJECT_ID, YEAR)
        # fail-open：校验异常不阻断，validation_run 反映实际（False）
        assert result["validation_run"] is False
        # 但金额已写入（校验在写入之后）
        assert note.table_data["rows"][2]["values"][1] == 500.0

    @pytest.mark.asyncio
    async def test_idempotent_second_sync_no_change(self):
        db = _make_db_mock()
        note = _note_with_report_binding(row_code="BS-015", row_idx=2, col=1)
        svc = ReportNoteSyncService(db)

        with patch(_FLAG, return_value=True), patch(_ENGINE) as MockEngine:
            MockEngine.return_value.validate_all = AsyncMock(return_value={})
            db.execute.side_effect = [
                _result_scalars([_report_row("BS-015", "500")]),
                _result_scalars([note]),
            ]
            await svc.sync_report_to_notes(PROJECT_ID, YEAR)
            td_after_first = deepcopy(note.table_data)

            db.execute.side_effect = [
                _result_scalars([_report_row("BS-015", "500")]),
                _result_scalars([note]),
            ]
            await svc.sync_report_to_notes(PROJECT_ID, YEAR)

        assert note.table_data == td_after_first


# ===========================================================================
# 开关关闭零回归 — 与 characterization 基线一致
# ===========================================================================


class TestSyncStubZeroRegression:
    @pytest.mark.asyncio
    async def test_flag_off_only_clears_stale_never_writes_amount(self):
        db = _make_db_mock()
        note = _note_with_report_binding(row_code="BS-015", row_idx=2, col=1, value=None)
        original_td = deepcopy(note.table_data)
        db.execute.side_effect = [
            _result_scalars([_report_row("BS-015", "500")]),
            _result_scalars([note]),
        ]
        svc = ReportNoteSyncService(db)
        with patch(_FLAG, return_value=False):
            result = await svc.sync_report_to_notes(PROJECT_ID, YEAR)

        # 关闭时不写报表金额（table_data 不变）
        assert note.table_data == original_td
        assert note.is_stale is False
        # 3-key stub 返回，硬编码统计
        assert result == {
            "synced_sections": 1,
            "skipped_sections": 0,
            "validation_run": True,
        }
        assert "cells_updated" not in result

    @pytest.mark.asyncio
    async def test_flag_off_no_report_rows(self):
        db = _make_db_mock()
        db.execute.side_effect = [_result_scalars([])]
        svc = ReportNoteSyncService(db)
        with patch(_FLAG, return_value=False):
            result = await svc.sync_report_to_notes(PROJECT_ID, YEAR)
        assert result == {
            "synced_sections": 0,
            "skipped_sections": 0,
            "validation_run": False,
        }

    @pytest.mark.asyncio
    async def test_default_flag_is_off(self):
        """默认（不 patch）开关关闭 → stub 行为（零回归）。"""
        db = _make_db_mock()
        note = _plain_note()
        original_td = deepcopy(note.table_data)
        db.execute.side_effect = [
            _result_scalars([_report_row("BS-015", "500")]),
            _result_scalars([note]),
        ]
        svc = ReportNoteSyncService(db)
        result = await svc.sync_report_to_notes(PROJECT_ID, YEAR)
        assert note.table_data == original_td
        assert "cells_updated" not in result
        assert result["validation_run"] is True
