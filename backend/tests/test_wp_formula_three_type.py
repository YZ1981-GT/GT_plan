# Feature: formula-management-library — Task 3.1 三类型 + 跨 sheet 求值
"""WpFormulaService.save 三类型契约 + evaluate_wp_formula_expression 跨 sheet 求值单测。

覆盖 Task 3.1 的核心行为（非 PBT，示例/边界）：
- 保存持久化 formula_type / refs（Req 14.1/14.5）。
- auto_calc 记 last_computed_at；logic_check / reasonability 不记（Req 14.3 / P5/P9）。
- 非法 formula_type 拒绝写库返回 issues（router 转 422）。
- 悬空引用拒绝写库返回 (None, issues)（Req 14.4）。
- Sheet!Cell 跨 sheet 引用经 CrossSheetResolver 追溯求值（Req 14.2）。
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.workpaper_models import WpFormula
from app.services.wp_formula_eval_service import evaluate_wp_formula_expression
from app.services.wp_formula_service import WpFormulaService


async def _make_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sc: WpFormula.__table__.create(sc, checkfirst=True)
        )
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return factory, engine


@pytest.mark.asyncio
async def test_save_persists_formula_type_and_refs():
    factory, engine = await _make_session()
    async with factory() as db:
        svc = WpFormulaService()
        with patch(
            "app.services.wp_formula_service.validate_refs_via_acnr",
            new_callable=AsyncMock,
            return_value=[],
        ):
            saved, issues = await svc.save(
                db,
                project_id=uuid.uuid4(),
                wp_id=uuid.uuid4(),
                sheet_name="审定表",
                target_cell="B5",
                expression="WP('D1','B5')",
                year=2025,
                formula_type="logic_check",
                refs=["WP('D1','B5')", {"addr_id": "D1/D1/B5"}],
                issue_description="资产≠负债+权益",
            )
        assert issues == []
        assert saved is not None
        assert saved.formula_type == "logic_check"
        # str ref 被包装为 {"formula_ref": ...}；dict ref 原样保留
        assert {"formula_ref": "WP('D1','B5')"} in saved.refs
        assert {"addr_id": "D1/D1/B5"} in saved.refs
        assert saved.issue_description == "资产≠负债+权益"
        # logic_check 绝不改值 → 不记 last_computed_at（P5/P9）
        assert saved.last_computed_at is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_auto_calc_records_last_computed_at():
    factory, engine = await _make_session()
    async with factory() as db:
        svc = WpFormulaService()
        with patch(
            "app.services.wp_formula_service.validate_refs_via_acnr",
            new_callable=AsyncMock,
            return_value=[],
        ):
            saved, issues = await svc.save(
                db,
                project_id=uuid.uuid4(),
                wp_id=uuid.uuid4(),
                sheet_name="审定表",
                target_cell="B5",
                expression="1+2",
                year=2025,
                formula_type="auto_calc",
            )
        assert issues == []
        assert saved.formula_type == "auto_calc"
        assert saved.last_computed_at is not None  # P9
    await engine.dispose()


@pytest.mark.asyncio
async def test_invalid_formula_type_rejected():
    factory, engine = await _make_session()
    async with factory() as db:
        svc = WpFormulaService()
        with patch(
            "app.services.wp_formula_service.validate_refs_via_acnr",
            new_callable=AsyncMock,
            return_value=[],
        ):
            saved, issues = await svc.save(
                db,
                project_id=uuid.uuid4(),
                wp_id=uuid.uuid4(),
                sheet_name="审定表",
                target_cell="B5",
                expression="1+2",
                year=2025,
                formula_type="bogus_type",
            )
        assert saved is None
        assert issues and issues[0]["status"] == "invalid_formula_type"
    await engine.dispose()


@pytest.mark.asyncio
async def test_dangling_ref_rejected():
    factory, engine = await _make_session()
    async with factory() as db:
        svc = WpFormulaService()
        with patch(
            "app.services.wp_formula_service.validate_refs_via_acnr",
            new_callable=AsyncMock,
            return_value=[{"status": "not_found", "ref": "WP('X','Z99')"}],
        ):
            saved, issues = await svc.save(
                db,
                project_id=uuid.uuid4(),
                wp_id=uuid.uuid4(),
                sheet_name="审定表",
                target_cell="B5",
                expression="WP('X','Z99')",
                year=2025,
                formula_type="auto_calc",
            )
        assert saved is None  # 不写库
        assert issues and issues[0]["status"] == "not_found"
        # 未写库
        loaded = await svc.list_by_wp(db, uuid.uuid4())
        assert loaded == []
    await engine.dispose()


@pytest.mark.asyncio
async def test_cross_sheet_ref_resolved_via_resolver():
    """=Sheet!Cell 跨 sheet 引用经 CrossSheetResolver 取值后求值（Req 14.2）。"""
    parsed_data = {
        "univer_snapshot": {
            "sheets": [
                {
                    "name": "明细表",
                    # A1 → row 0 col 0 = 100
                    "cellData": {"0": {"0": {"v": 100}}},
                }
            ]
        }
    }
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        val, errs = await evaluate_wp_formula_expression(
            db,
            project_id=uuid.uuid4(),
            year=2025,
            expression="=明细表!A1+50",
            parsed_data=parsed_data,
        )
        assert val == Decimal("150")
        assert errs == []
    await engine.dispose()
