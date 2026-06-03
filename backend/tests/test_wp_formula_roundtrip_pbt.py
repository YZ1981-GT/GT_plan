# Feature: custom-workpaper-formula-binding, Property 12: 公式持久化往返
"""
Property 12 — 公式持久化往返

    load(save(formula)) == formula

同 (wp_id, sheet_name, target_cell) 重复保存为覆盖更新而非新增。
生成器含中文 sheet_name（Req 9.4 覆盖）。

**Validates: Requirements 6.3**
属性: P12
"""
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from hypothesis import given, settings, strategies as st
from sqlalchemy import select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid
from sqlalchemy.orm import sessionmaker

from app.models.workpaper_models import WpFormula


# ---------------------------------------------------------------------------
# Strategies（生成器含中文 sheet_name，覆盖 Req 9.4）
# ---------------------------------------------------------------------------

_CN_SHEET_NAMES = ["审定表", "应收账款明细", "固定资产台账", "长期借款", "期末余额"]
_CELLS = ["A1", "B5", "C12", "D3", "E20", "Z99"]
_EXPRESSIONS = [
    "WP('D1','B5')+WP('D2','C3')",
    "TB('6001','审定数')",
    "NOTE('长期借款','期末')",
    "WP('E1','审定数')*0.5",
    "SUM_TB('6001','期末')",
]

sheet_name_st = st.sampled_from(_CN_SHEET_NAMES)
cell_st = st.sampled_from(_CELLS)
expression_st = st.sampled_from(_EXPRESSIONS)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    """Run async coroutine synchronously for hypothesis compatibility."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _make_session():
    """Create in-memory SQLite async session with wp_formula table only."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: WpFormula.__table__.create(sync_conn, checkfirst=True)
        )
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return factory, engine


# ---------------------------------------------------------------------------
# P12a: 往返一致 — load(save(formula)) == formula
# ---------------------------------------------------------------------------

class TestP12FormulaRoundtrip:
    """P12 属性 PBT：公式保存后读回字段一致。"""

    @given(
        sheet_name=sheet_name_st,
        target_cell=cell_st,
        expression=expression_st,
    )
    @settings(max_examples=5)
    def test_p12_save_then_load_roundtrip(self, sheet_name, target_cell, expression):
        """save then list_by_wp returns identical fields."""

        async def _inner():
            from app.services.wp_formula_service import WpFormulaService

            factory, engine = await _make_session()
            async with factory() as session:
                svc = WpFormulaService()
                project_id = uuid.uuid4()
                wp_id = uuid.uuid4()

                with patch(
                    "app.services.wp_formula_service.address_registry.validate_formula_refs",
                    new_callable=AsyncMock,
                    return_value=[],
                ):
                    saved, issues = await svc.save(
                        session,
                        project_id=project_id,
                        wp_id=wp_id,
                        sheet_name=sheet_name,
                        target_cell=target_cell,
                        expression=expression,
                        year=2025,
                        category="auto_calc",
                        description="测试公式描述",
                    )
                    assert issues == []
                    assert saved is not None
                    await session.commit()

                    # Load back
                    loaded_list = await svc.list_by_wp(session, wp_id)
                    assert len(loaded_list) == 1
                    loaded = loaded_list[0]

                    # Round-trip assertions
                    assert loaded.sheet_name == sheet_name
                    assert loaded.target_cell == target_cell
                    assert loaded.expression == expression
                    assert loaded.category == "auto_calc"
                    assert loaded.description == "测试公式描述"
                    assert loaded.project_id == project_id
                    assert loaded.wp_id == wp_id

            await engine.dispose()

        _run(_inner())

    # ------------------------------------------------------------------
    # P12b: 重复保存为覆盖更新而非新增
    # ------------------------------------------------------------------

    @given(
        sheet_name=sheet_name_st,
        target_cell=cell_st,
        expr1=expression_st,
        expr2=expression_st,
    )
    @settings(max_examples=5)
    def test_p12_upsert_no_duplicate(self, sheet_name, target_cell, expr1, expr2):
        """Same (wp_id, sheet_name, target_cell) twice → update, not duplicate."""

        async def _inner():
            from app.services.wp_formula_service import WpFormulaService

            factory, engine = await _make_session()
            async with factory() as session:
                svc = WpFormulaService()
                project_id = uuid.uuid4()
                wp_id = uuid.uuid4()

                with patch(
                    "app.services.wp_formula_service.address_registry.validate_formula_refs",
                    new_callable=AsyncMock,
                    return_value=[],
                ):
                    # First save
                    saved1, _ = await svc.save(
                        session,
                        project_id=project_id,
                        wp_id=wp_id,
                        sheet_name=sheet_name,
                        target_cell=target_cell,
                        expression=expr1,
                        year=2025,
                    )
                    await session.commit()

                    # Second save (same key, different expression)
                    saved2, _ = await svc.save(
                        session,
                        project_id=project_id,
                        wp_id=wp_id,
                        sheet_name=sheet_name,
                        target_cell=target_cell,
                        expression=expr2,
                        year=2025,
                        category="cross_check",
                    )
                    await session.commit()

                # Exactly 1 record, not 2
                all_formulas = await svc.list_by_wp(session, wp_id)
                assert len(all_formulas) == 1
                assert all_formulas[0].expression == expr2
                assert all_formulas[0].category == "cross_check"
                # Same id (update, not insert)
                assert saved1.id == saved2.id

            await engine.dispose()

        _run(_inner())
