# Feature: formula-management-library, Task 21.1 — reference 来源解析 + 源变更失效链
"""Task 21.1 功能测试：公式 ``reference`` 来源解析 + 源变更失效链（Req 25.5/25.7）。

验证三条核心行为：
  ① reference 来源解析取**被参照源公式**的 ``expression``（复用而非重录，Req 25.5）。
  ② 被参照源公式**变更/删除**时经 **ACNR 失效链**使引用方标失效并可重算（Req 25.7），
     复用 ``acnr.events.invalidate``（打桩断言被调用），不自建失效逻辑。
  ③ ``reference_formula_id`` **悬空**（指向已删除/不存在源公式）→ fail-open 记
     Issue_List，**不静默产错值**（不返回凭空/错误表达式）。

被测：
  - ``app.services.formula_management.reference_resolver`` 的
    ``resolve_reference_expression`` / ``find_reference_dependents`` /
    ``invalidate_reference_dependents``。
  - ``app.services.wp_formula_service.WpFormulaService.save`` 的 reference 来源分支
    （复用源表达式 + 悬空拒写）与 ``save``/``delete`` 的源变更失效传播接线。

测试基座：内存 SQLite（``:memory:`` + ``aiosqlite``）+ SQLite 方言 patch 建
``wp_formula`` 表（对齐 test_pbt_p06_save_roundtrip.py）；失效链经 patch
``app.services.acnr.events.invalidate`` 断言"复用不自建"。

**Validates: Requirements 25.5, 25.7**
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

# SQLite 测试方言：UUID → uuid 编译；JSONB → JSON 编译（建表所需）。
if hasattr(SQLiteTypeCompiler, "visit_uuid"):
    SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid
if not hasattr(SQLiteTypeCompiler, "visit_JSONB"):
    SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.models.workpaper_models import WpFormula  # noqa: E402
from app.services.formula_management.reference_resolver import (  # noqa: E402
    find_reference_dependents,
    invalidate_reference_dependents,
    resolve_reference_expression,
)
from app.services.wp_formula_service import WpFormulaService  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# 测试基座
# ─────────────────────────────────────────────────────────────────────────────
def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _make_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sc: WpFormula.__table__.create(sc, checkfirst=True)
        )
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return factory, engine


async def _add_formula(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    wp_id: uuid.UUID,
    target_cell: str,
    expression: str,
    sheet_name: str = "审定表",
    formula_source: str = "custom",
    reference_formula_id: uuid.UUID | None = None,
) -> WpFormula:
    """直接经 ORM 落一条公式（绕过 save 的 ACNR 校验，便于构造源/引用方）。"""
    row = WpFormula(
        project_id=project_id,
        wp_id=wp_id,
        sheet_name=sheet_name,
        target_cell=target_cell,
        expression=expression,
        formula_type="auto_calc",
        refs=[],
        formula_source=formula_source,
        reference_formula_id=reference_formula_id,
    )
    db.add(row)
    await db.flush()
    return row


# ═══════════════════════════════════════════════════════════════════════════════
# ① reference 来源解析取源公式 expression（复用而非重录，Req 25.5）
# ═══════════════════════════════════════════════════════════════════════════════
def test_reference_resolves_source_expression():
    """reference 解引用返回被参照源公式的 expression（复用而非重录）。"""

    async def _scenario():
        factory, engine = await _make_session()
        try:
            async with factory() as db:
                project_id = uuid.uuid4()
                wp_id = uuid.uuid4()
                src = await _add_formula(
                    db,
                    project_id=project_id,
                    wp_id=wp_id,
                    target_cell="B5",
                    expression="TB('1001')+TB('1002')",
                )

                res = await resolve_reference_expression(
                    db, reference_formula_id=src.id
                )

                assert res.resolved is True
                # 复用源公式表达式，逐字相等（非重录）。
                assert res.expression == "TB('1001')+TB('1002')"
                assert res.source_formula_id == str(src.id)
                assert res.dangling is False
                assert res.issue is None
        finally:
            await engine.dispose()

    _run(_scenario())


def test_save_reference_source_reuses_source_expression():
    """save(formula_source='reference') 复用源公式表达式并落库 reference_formula_id。"""

    async def _scenario():
        factory, engine = await _make_session()
        try:
            async with factory() as db:
                svc = WpFormulaService()
                project_id = uuid.uuid4()
                wp_id = uuid.uuid4()
                src = await _add_formula(
                    db,
                    project_id=project_id,
                    wp_id=wp_id,
                    target_cell="B5",
                    expression="SUM_TB('1001','1002')",
                )

                with patch(
                    "app.services.wp_formula_service.validate_refs_via_acnr",
                    new_callable=AsyncMock,
                    return_value=[],
                ), patch(
                    "app.services.acnr.events.invalidate",
                    new_callable=AsyncMock,
                ):
                    # 引用方提交一个占位 expression，reference 分支应改用源表达式。
                    saved, issues = await svc.save(
                        db,
                        project_id=project_id,
                        wp_id=uuid.uuid4(),
                        sheet_name="审定表",
                        target_cell="C9",
                        expression="占位待复用",
                        year=2025,
                        formula_source="reference",
                        reference_formula_id=src.id,
                    )

                assert issues == []
                assert saved is not None
                # 复用而非重录：落库表达式 == 源公式表达式。
                assert saved.expression == "SUM_TB('1001','1002')"
                assert saved.formula_source == "reference"
                assert saved.reference_formula_id == src.id
        finally:
            await engine.dispose()

    _run(_scenario())


# ═══════════════════════════════════════════════════════════════════════════════
# ② 源变更经 ACNR 失效链使引用方失效（Req 25.7，复用不自建）
# ═══════════════════════════════════════════════════════════════════════════════
def test_find_reference_dependents_lists_referencing_formulas():
    """find_reference_dependents 精确返回以某源为参照的引用方。"""

    async def _scenario():
        factory, engine = await _make_session()
        try:
            async with factory() as db:
                project_id = uuid.uuid4()
                wp_id = uuid.uuid4()
                src = await _add_formula(
                    db, project_id=project_id, wp_id=wp_id,
                    target_cell="B5", expression="TB('1001')",
                )
                dep1 = await _add_formula(
                    db, project_id=project_id, wp_id=uuid.uuid4(),
                    target_cell="C1", expression="TB('1001')",
                    formula_source="reference", reference_formula_id=src.id,
                )
                dep2 = await _add_formula(
                    db, project_id=project_id, wp_id=uuid.uuid4(),
                    target_cell="C2", expression="TB('1001')",
                    formula_source="reference", reference_formula_id=src.id,
                )
                # 无关公式（custom / 指向别的源）不应被计入。
                await _add_formula(
                    db, project_id=project_id, wp_id=uuid.uuid4(),
                    target_cell="C3", expression="TB('2001')",
                )
                await _add_formula(
                    db, project_id=project_id, wp_id=uuid.uuid4(),
                    target_cell="C4", expression="TB('2001')",
                    formula_source="reference", reference_formula_id=uuid.uuid4(),
                )

                deps = await find_reference_dependents(
                    db, source_formula_id=src.id
                )
                dep_ids = {d.id for d in deps}
                assert dep_ids == {dep1.id, dep2.id}
        finally:
            await engine.dispose()

    _run(_scenario())


def test_source_change_invalidation_uses_acnr_chain():
    """源公式变更 → 经 ACNR 失效链使引用方失效（复用 acnr.events.invalidate）。"""

    async def _scenario():
        factory, engine = await _make_session()
        try:
            async with factory() as db:
                project_id = uuid.uuid4()
                wp_id = uuid.uuid4()
                src = await _add_formula(
                    db, project_id=project_id, wp_id=wp_id,
                    target_cell="B5", expression="TB('1001')",
                )
                await _add_formula(
                    db, project_id=project_id, wp_id=uuid.uuid4(),
                    target_cell="C1", expression="TB('1001')",
                    formula_source="reference", reference_formula_id=src.id,
                )

                with patch(
                    "app.services.acnr.events.invalidate",
                    new_callable=AsyncMock,
                ) as mock_inval:
                    affected = await invalidate_reference_dependents(
                        db, source_formula_id=src.id, project_id=project_id
                    )

                # 有 1 个引用方受影响，且复用 ACNR 失效链（不自建）。
                assert affected == 1
                mock_inval.assert_awaited_once()
                # 失效链按 project 维度触发。
                args, kwargs = mock_inval.await_args
                assert args[0] == str(project_id)
        finally:
            await engine.dispose()

    _run(_scenario())


def test_invalidation_noop_when_no_dependents():
    """无引用方时不触发失效链（避免无谓开销），返回 0。"""

    async def _scenario():
        factory, engine = await _make_session()
        try:
            async with factory() as db:
                project_id = uuid.uuid4()
                src = await _add_formula(
                    db, project_id=project_id, wp_id=uuid.uuid4(),
                    target_cell="B5", expression="TB('1001')",
                )

                with patch(
                    "app.services.acnr.events.invalidate",
                    new_callable=AsyncMock,
                ) as mock_inval:
                    affected = await invalidate_reference_dependents(
                        db, source_formula_id=src.id, project_id=project_id
                    )

                assert affected == 0
                mock_inval.assert_not_awaited()
        finally:
            await engine.dispose()

    _run(_scenario())


def test_save_update_of_source_triggers_invalidation():
    """save 更新既有源公式 → 经失效链传播到引用方（复用 acnr.events.invalidate）。"""

    async def _scenario():
        factory, engine = await _make_session()
        try:
            async with factory() as db:
                svc = WpFormulaService()
                project_id = uuid.uuid4()
                wp_id = uuid.uuid4()
                src = await _add_formula(
                    db, project_id=project_id, wp_id=wp_id,
                    target_cell="B5", expression="TB('1001')",
                )
                await _add_formula(
                    db, project_id=project_id, wp_id=uuid.uuid4(),
                    target_cell="C1", expression="TB('1001')",
                    formula_source="reference", reference_formula_id=src.id,
                )

                with patch(
                    "app.services.wp_formula_service.validate_refs_via_acnr",
                    new_callable=AsyncMock,
                    return_value=[],
                ), patch(
                    "app.services.acnr.events.invalidate",
                    new_callable=AsyncMock,
                ) as mock_inval:
                    # upsert 命中既有源（同 wp_id/sheet/cell）→ 更新 = 源变更。
                    saved, issues = await svc.save(
                        db,
                        project_id=project_id,
                        wp_id=wp_id,
                        sheet_name="审定表",
                        target_cell="B5",
                        expression="TB('1001')+100",
                        year=2025,
                    )

                assert issues == []
                assert saved is not None
                assert saved.expression == "TB('1001')+100"
                # 源变更经 ACNR 失效链传播到引用方。
                mock_inval.assert_awaited()
        finally:
            await engine.dispose()

    _run(_scenario())


# ═══════════════════════════════════════════════════════════════════════════════
# ③ 悬空 reference_formula_id → fail-open 记 Issue，不静默产错值（Req 25.7）
# ═══════════════════════════════════════════════════════════════════════════════
def test_dangling_reference_fail_open_records_issue():
    """指向不存在源公式 → dangling + Issue，不返回任何表达式（不产错值）。"""

    async def _scenario():
        factory, engine = await _make_session()
        try:
            async with factory() as db:
                ghost_id = uuid.uuid4()  # 从未落库
                res = await resolve_reference_expression(
                    db,
                    reference_formula_id=ghost_id,
                    requester_formula_id="req-1",
                )

                assert res.resolved is False
                assert res.dangling is True
                # 关键：不静默产错值 —— expression 必须为 None。
                assert res.expression is None
                assert res.issue is not None
                assert str(ghost_id) in res.issue.description
        finally:
            await engine.dispose()

    _run(_scenario())


def test_missing_reference_id_fail_open_records_issue():
    """reference_formula_id 缺失 → 记 Issue，不产错值。"""

    async def _scenario():
        factory, engine = await _make_session()
        try:
            async with factory() as db:
                res = await resolve_reference_expression(
                    db, reference_formula_id=None
                )
                assert res.resolved is False
                assert res.expression is None
                assert res.issue is not None
        finally:
            await engine.dispose()

    _run(_scenario())


def test_invalid_reference_id_fail_open_records_issue():
    """reference_formula_id 非法（非 UUID）→ 记 Issue，不产错值。"""

    async def _scenario():
        factory, engine = await _make_session()
        try:
            async with factory() as db:
                res = await resolve_reference_expression(
                    db, reference_formula_id="not-a-uuid"
                )
                assert res.resolved is False
                assert res.expression is None
                assert res.issue is not None
        finally:
            await engine.dispose()

    _run(_scenario())


def test_save_dangling_reference_rejected_not_written():
    """save(reference) 悬空 → 返回 (None, issues)，不写库（不产错值）。"""

    async def _scenario():
        factory, engine = await _make_session()
        try:
            async with factory() as db:
                svc = WpFormulaService()
                project_id = uuid.uuid4()
                ghost_id = uuid.uuid4()

                with patch(
                    "app.services.wp_formula_service.validate_refs_via_acnr",
                    new_callable=AsyncMock,
                    return_value=[],
                ), patch(
                    "app.services.acnr.events.invalidate",
                    new_callable=AsyncMock,
                ):
                    saved, issues = await svc.save(
                        db,
                        project_id=project_id,
                        wp_id=uuid.uuid4(),
                        sheet_name="审定表",
                        target_cell="C9",
                        expression="占位",
                        year=2025,
                        formula_source="reference",
                        reference_formula_id=ghost_id,
                    )

                assert saved is None
                assert issues
                assert issues[0]["reason"] == "reference_dangling"

                # 确认未写库。
                loaded = await svc.list_by_wp(db, uuid.uuid4())
                assert loaded == []
        finally:
            await engine.dispose()

    _run(_scenario())


def test_invalid_formula_source_rejected():
    """非法 formula_source → 拒绝写库并返回 issue。"""

    async def _scenario():
        factory, engine = await _make_session()
        try:
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
                        expression="TB('1001')",
                        year=2025,
                        formula_source="bogus",
                    )
                assert saved is None
                assert issues
                assert issues[0]["reason"] == "invalid_formula_source"
        finally:
            await engine.dispose()

    _run(_scenario())


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
