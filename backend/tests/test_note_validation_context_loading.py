"""ValidationContext 数据装配测试 — report_data / tb_data / prior_note_data.

Spec:   .kiro/specs/disclosure-note-validation-completion/ Wave 0 Task 2
Reqs:   1.1, 1.2, 1.3, 1.4  Property: 1, 2, 12

覆盖：
- P1  装配非空：_load_report_data / _load_tb_data / _load_prior_notes 从 mock DB 返回非空
- P2  单源异常 fail-open：db.execute 抛异常 → 对应源置 {}，不抛
- P2  validate_all 端到端不因数据源异常而抛，其余照常
- P12 report_data 装配后 _execute_balance 用真实行金额比对（非恒 0）
- prior_note_data dataclass 向后兼容字段
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import sqlalchemy as sa

from app.services.note_validation_engine import (
    NoteValidationEngine,
    ValidationContext,
    ValidationRule,
    ValidationType,
)
from app.services.note_validation_executors import _execute_balance

PROJECT_ID = uuid4()
YEAR = 2025


def _make_db_mock():
    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


def _result_all(rows):
    """mock result 支持 .all() → list of tuples"""
    res = MagicMock()
    res.all.return_value = rows
    return res


def _result_scalars(objs):
    """mock result 支持 .scalars().all() → list of ORM objs"""
    res = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = objs
    res.scalars.return_value = scalars
    return res


def _note(section, table_data):
    n = MagicMock()
    n.note_section = section
    n.table_data = table_data
    return n


# ---------------------------------------------------------------------------
# dataclass 向后兼容
# ---------------------------------------------------------------------------


class TestPriorNoteDataField:
    def test_prior_note_data_default_empty(self):
        ctx = ValidationContext()
        assert hasattr(ctx, "prior_note_data")
        assert ctx.prior_note_data == {}


# ---------------------------------------------------------------------------
# P1: 装配非空
# ---------------------------------------------------------------------------


class TestLoadReportData:
    @pytest.mark.asyncio
    async def test_report_data_nonempty(self):
        db = _make_db_mock()
        db.execute.return_value = _result_all([
            ("BS_1001", Decimal("100.00")),
            ("IS_5001", Decimal("200.00")),
        ])
        engine = NoteValidationEngine(db)
        data = await engine._load_report_data(PROJECT_ID, YEAR)
        assert data == {"BS_1001": Decimal("100.00"), "IS_5001": Decimal("200.00")}

    @pytest.mark.asyncio
    async def test_report_data_skips_null_and_dup(self):
        db = _make_db_mock()
        db.execute.return_value = _result_all([
            ("R1", Decimal("10")),
            ("R1", Decimal("99")),   # 重复 row_code → 保留首个
            ("R2", None),            # 空金额跳过
            (None, Decimal("5")),    # 空 code 跳过
        ])
        engine = NoteValidationEngine(db)
        data = await engine._load_report_data(PROJECT_ID, YEAR)
        assert data == {"R1": Decimal("10")}

    @pytest.mark.asyncio
    async def test_no_db_returns_empty(self):
        engine = NoteValidationEngine(None)
        assert await engine._load_report_data(PROJECT_ID, YEAR) == {}


class TestLoadTbData:
    @pytest.mark.asyncio
    async def test_tb_data_nonempty(self):
        db = _make_db_mock()
        db.execute.return_value = _result_all([
            ("1001", Decimal("500.00")),
            ("1122", Decimal("300.00")),
        ])
        engine = NoteValidationEngine(db)
        with patch(
            "app.services.dataset_query.get_active_filter",
            new=AsyncMock(return_value=sa.true()),
        ):
            data = await engine._load_tb_data(PROJECT_ID, YEAR)
        assert data == {"1001": Decimal("500.00"), "1122": Decimal("300.00")}


class TestLoadPriorNotes:
    @pytest.mark.asyncio
    async def test_prior_notes_nonempty(self):
        db = _make_db_mock()
        db.execute.return_value = _result_scalars([
            _note("五、1", {"total": 100}),
            _note("五、3", {"rows": []}),
            _note("五、9", None),  # 空 table_data 跳过
        ])
        engine = NoteValidationEngine(db)
        data = await engine._load_prior_notes(PROJECT_ID, YEAR - 1)
        assert data == {"五、1": {"total": 100}, "五、3": {"rows": []}}


# ---------------------------------------------------------------------------
# P2: fail-open
# ---------------------------------------------------------------------------


class TestFailOpen:
    @pytest.mark.asyncio
    async def test_report_data_fail_open(self):
        db = _make_db_mock()
        db.execute.side_effect = RuntimeError("db down")
        engine = NoteValidationEngine(db)
        assert await engine._load_report_data(PROJECT_ID, YEAR) == {}

    @pytest.mark.asyncio
    async def test_tb_data_fail_open(self):
        db = _make_db_mock()
        db.execute.side_effect = RuntimeError("db down")
        engine = NoteValidationEngine(db)
        with patch(
            "app.services.dataset_query.get_active_filter",
            new=AsyncMock(return_value=sa.true()),
        ):
            assert await engine._load_tb_data(PROJECT_ID, YEAR) == {}

    @pytest.mark.asyncio
    async def test_prior_notes_fail_open(self):
        db = _make_db_mock()
        db.execute.side_effect = RuntimeError("db down")
        engine = NoteValidationEngine(db)
        assert await engine._load_prior_notes(PROJECT_ID, YEAR - 1) == {}

    @pytest.mark.asyncio
    async def test_validate_all_resilient_when_all_sources_raise(self):
        """P2：数据源全部异常时 validate_all 不抛、仍返回结构化结果。"""
        db = _make_db_mock()
        db.execute.side_effect = RuntimeError("db down")
        engine = NoteValidationEngine(db)
        with patch(
            "app.services.dataset_query.get_active_filter",
            new=AsyncMock(return_value=sa.true()),
        ):
            result = await engine.validate_all(PROJECT_ID, YEAR, template_type="soe")
        assert isinstance(result, dict)
        assert result["project_id"] == str(PROJECT_ID)
        assert result["year"] == YEAR
        assert "findings" in result


# ---------------------------------------------------------------------------
# P12: report_data 装配后 balance 用真实行金额比对
# ---------------------------------------------------------------------------


class TestBalanceUsesLoadedReportData:
    @pytest.mark.asyncio
    async def test_loaded_report_data_flows_into_balance(self):
        db = _make_db_mock()
        db.execute.return_value = _result_all([("五、1", Decimal("100"))])
        engine = NoteValidationEngine(db)
        report_data = await engine._load_report_data(PROJECT_ID, YEAR)

        ctx = ValidationContext(
            note_data={"五、1": {"total": 100}},
            report_data=report_data,
        )
        rule = ValidationRule(
            section_code="五、1",
            rule_type=ValidationType.BALANCE,
            expression="balance",
        )
        res = _execute_balance(rule, ctx)
        # 用真实报表行金额 100 比对（非恒 0）
        assert res.expected_value == Decimal("100")
        assert res.passed is True
