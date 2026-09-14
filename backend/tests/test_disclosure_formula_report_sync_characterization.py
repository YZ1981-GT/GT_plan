"""Characterization 测试 — 锁定"报表↔附注金额/公式联动"当前 stub 可观察行为。

Spec:   .kiro/specs/disclosure-note-formula-and-report-sync/ Wave 0 (Task 1.2 / 1.3)
Reqs:   8.1, 8.4 (零回归基线) / 6.1, 6.3 (ValidationContext 装配核实)

作为后续（Wave1-5）开关关闭时的**零回归基线**，锁定当前**未修改前**行为：

- Task 1.2:
  - `note_source_resolvers.resolve_formula(binding, ctx)` 对任意输入恒返回 None。
  - `resolve_prior_year_note` 的 field="value" 返 None；field="text" 且缓存有文本时返回该文本。
  - `ReportNoteSyncService.sync_report_to_notes` 当前只把 note.is_stale=False，
    从不把报表金额写进 note.table_data；返回的 validation_run 恒 True、
    skipped_sections 恒 0（对齐现状硬编码）；无报表/无附注时 validation_run=False。

- Task 1.3:
  - 核实 `ValidationContext` 已装配 report_data(row_code→amount) / tb_data / prior_note_data
    （上游 disclosure-note-validation-completion 已交付），validate_all 端到端填充三者。

注：本文件为 characterization，断言的是**当前**行为；Wave1+ 改动后开关关闭时仍须逐条通过。
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import sqlalchemy as sa

from app.services.note_source_resolvers import (
    resolve_formula,
    resolve_prior_year_note,
)
from app.services.report_note_sync_service import ReportNoteSyncService
from app.services.note_validation_engine import NoteValidationEngine

PROJECT_ID = uuid4()
YEAR = 2025


# ---------------------------------------------------------------------------
# 辅助 mock
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


def _result_all(rows):
    res = MagicMock()
    res.all.return_value = rows
    return res


def _note_obj(section="五、1", table_data=None, is_stale=True):
    n = MagicMock()
    n.note_section = section
    n.table_data = table_data if table_data is not None else {"rows": [], "total": 0}
    n.is_stale = is_stale
    return n


# ===========================================================================
# Task 1.2 — resolve_formula stub 恒返 None
# ===========================================================================


class TestResolveFormulaStub:
    @pytest.mark.asyncio
    async def test_returns_none_for_empty_binding(self):
        assert await resolve_formula({}, {}) is None

    @pytest.mark.asyncio
    async def test_returns_none_for_sum_source(self):
        binding = {"source": "sum", "cells": ["R2C2", "R3C2"]}
        assert await resolve_formula(binding, {"table_data": {}}) is None

    @pytest.mark.asyncio
    async def test_returns_none_for_report_source(self):
        binding = {"source": "report", "row_code": "BS-015"}
        ctx = {"report_data": {"BS-015": Decimal("100")}}
        # 当前 stub 恒返 None，即便 ctx 里有 report_data
        assert await resolve_formula(binding, ctx) is None

    @pytest.mark.asyncio
    async def test_returns_none_for_aging_source(self):
        binding = {"source": "aging", "band": "1-2y"}
        assert await resolve_formula(binding, {}) is None


# ===========================================================================
# Task 1.2 — resolve_prior_year_note：value → None / text → 缓存文本
# ===========================================================================


class TestResolvePriorYearNoteStub:
    @pytest.mark.asyncio
    async def test_value_mode_returns_none_even_with_cache(self):
        binding = {"section": "五、1", "field": "value"}
        ctx = {"_prior_notes_cache": {"五、1": "上年附注文本"}}
        # 当前无单元格级反查 → value 模式恒返 None
        assert await resolve_prior_year_note(binding, ctx) is None

    @pytest.mark.asyncio
    async def test_text_mode_returns_cached_text(self):
        binding = {"section": "五、1", "field": "text"}
        ctx = {"_prior_notes_cache": {"五、1": "上年附注文本"}}
        assert await resolve_prior_year_note(binding, ctx) == "上年附注文本"

    @pytest.mark.asyncio
    async def test_text_mode_missing_section_returns_none(self):
        binding = {"section": "五、99", "field": "text"}
        ctx = {"_prior_notes_cache": {"五、1": "上年附注文本"}}
        assert await resolve_prior_year_note(binding, ctx) is None

    @pytest.mark.asyncio
    async def test_empty_cache_returns_none(self):
        binding = {"section": "五、1", "field": "text"}
        assert await resolve_prior_year_note(binding, {}) is None


# ===========================================================================
# Task 1.2 — sync_report_to_notes：仅清 is_stale + 硬编码统计
# ===========================================================================


class TestSyncReportToNotesStub:
    @pytest.mark.asyncio
    async def test_only_clears_is_stale_never_writes_report_amount(self):
        db = _make_db_mock()
        report_row = MagicMock()  # 只需非空即可
        note = _note_obj(table_data={"rows": [], "total": 0}, is_stale=True)
        original_table_data = dict(note.table_data)
        db.execute.side_effect = [
            _result_scalars([report_row]),  # report rows
            _result_scalars([note]),        # notes
        ]

        svc = ReportNoteSyncService(db)
        result = await svc.sync_report_to_notes(PROJECT_ID, YEAR)

        # 仅把 is_stale 清为 False
        assert note.is_stale is False
        # 从不改写 note.table_data（不把报表金额写进单元格）
        assert note.table_data == original_table_data
        # 硬编码统计：validation_run 恒 True、skipped_sections 恒 0
        assert result["validation_run"] is True
        assert result["skipped_sections"] == 0
        assert result["synced_sections"] == 1

    @pytest.mark.asyncio
    async def test_no_report_rows_returns_validation_run_false(self):
        db = _make_db_mock()
        db.execute.side_effect = [_result_scalars([])]  # 无报表行
        svc = ReportNoteSyncService(db)
        result = await svc.sync_report_to_notes(PROJECT_ID, YEAR)
        assert result == {
            "synced_sections": 0,
            "skipped_sections": 0,
            "validation_run": False,
        }

    @pytest.mark.asyncio
    async def test_no_notes_returns_validation_run_false(self):
        db = _make_db_mock()
        db.execute.side_effect = [
            _result_scalars([MagicMock()]),  # 有报表行
            _result_scalars([]),             # 无附注
        ]
        svc = ReportNoteSyncService(db)
        result = await svc.sync_report_to_notes(PROJECT_ID, YEAR)
        assert result == {
            "synced_sections": 0,
            "skipped_sections": 0,
            "validation_run": False,
        }

    @pytest.mark.asyncio
    async def test_no_stale_notes_still_counts_all_synced(self):
        db = _make_db_mock()
        note = _note_obj(is_stale=False)
        db.execute.side_effect = [
            _result_scalars([MagicMock()]),
            _result_scalars([note]),
        ]
        svc = ReportNoteSyncService(db)
        result = await svc.sync_report_to_notes(PROJECT_ID, YEAR)
        # 无 stale 笔数时仍按附注总数计 synced
        assert result["synced_sections"] == 1
        assert result["validation_run"] is True
        assert result["skipped_sections"] == 0


# ===========================================================================
# Task 1.3 — ValidationContext 已装配 report_data / tb_data / prior_note_data
# ===========================================================================


class TestValidationContextAssembly:
    @pytest.mark.asyncio
    async def test_validate_all_populates_all_three_sources(self):
        """核实 validate_all 端到端从 mock DB 装配 report/tb/prior 三源。

        断言经 captured context（execute_all 收到的 context）验证三者被填充。
        """
        db = _make_db_mock()

        # 依次：note_data(scalars) → report_data(all) → tb_data(all) → prior_notes(scalars)
        db.execute.side_effect = [
            _result_scalars([_note_obj("五、1", {"total": 100})]),      # note_data
            _result_all([("BS-015", Decimal("500"))]),                   # report_data
            _result_all([("1001", Decimal("300"))]),                     # tb_data
            _result_scalars([_note_obj("五、1", {"total": 90})]),        # prior_notes
        ]

        engine = NoteValidationEngine(db)

        captured = {}

        async def _fake_execute_all(project_id, year, *, template_type="soe", context=None):
            captured["ctx"] = context
            return []

        with patch.object(engine, "execute_all", side_effect=_fake_execute_all), patch(
            "app.services.dataset_query.get_active_filter",
            new=AsyncMock(return_value=sa.true()),
        ):
            result = await engine.validate_all(PROJECT_ID, YEAR, template_type="soe")

        ctx = captured["ctx"]
        assert ctx is not None
        # report_data(row_code → amount) 被装配
        assert ctx.report_data == {"BS-015": Decimal("500")}
        # tb_data(account_code → amount) 被装配
        assert ctx.tb_data == {"1001": Decimal("300")}
        # prior_note_data(section → table_data) 被装配
        assert ctx.prior_note_data == {"五、1": {"total": 90}}
        # note_data 亦被装配
        assert ctx.note_data == {"五、1": {"total": 100}}
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_assembly_fail_open_when_sources_raise(self):
        """P2/6.3：数据源异常时三者置 {}，validate_all 不抛。"""
        db = _make_db_mock()
        db.execute.side_effect = RuntimeError("db down")
        engine = NoteValidationEngine(db)

        captured = {}

        async def _fake_execute_all(project_id, year, *, template_type="soe", context=None):
            captured["ctx"] = context
            return []

        with patch.object(engine, "execute_all", side_effect=_fake_execute_all), patch(
            "app.services.dataset_query.get_active_filter",
            new=AsyncMock(return_value=sa.true()),
        ):
            result = await engine.validate_all(PROJECT_ID, YEAR, template_type="soe")

        ctx = captured["ctx"]
        assert ctx.report_data == {}
        assert ctx.tb_data == {}
        assert ctx.prior_note_data == {}
        assert isinstance(result, dict)
