# Feature: formula-management-library, Property 30: 对任意已保存源公式，以 reference 来源引用后，引用方解析出的表达式等于源公式表达式（复用而非重录）；当源公式变更时，引用方经 ACNR 失效链被标记失效并可重算。
"""属性测试 P30：参照复用与源变更失效传播（Req 25.5 / 25.7）。

**Property 30**（model-based，普遍量化）：
  *对任意*已保存源公式（随机 expression）与*任意*数量的 reference 引用方，
  ① **复用保真（Req 25.5）**：经 ``resolve_reference_expression`` 解析引用方时，
     返回的表达式**逐字等于**源公式 ``expression``（复用而非重录），且
     ``source_formula_id`` 指回源公式。
  ② **源变更失效传播（Req 25.7）**：源公式变更时，经 **ACNR 失效链**
     （``acnr.events.invalidate``，打桩断言被调用——复用不自建）使**所有**引用方
     标失效并可重算，``invalidate_reference_dependents`` 返回的受影响数
     **恒等于引用方数量**，且失效链按 project 维度触发。

被测：``app.services.formula_management.reference_resolver`` 的
``resolve_reference_expression`` / ``find_reference_dependents`` /
``invalidate_reference_dependents``（Task 21.1 已建）。

测试基座（对齐 Task 21.1 的 ``test_reference_resolver.py``，同款已跑通）：
内存 SQLite（``:memory:`` + ``aiosqlite``）+ SQLite 方言 patch 建 ``wp_formula`` 表；
失效链经 patch ``app.services.acnr.events.invalidate`` 断言"复用不自建"。

**Validates: Requirements 25.5, 25.7**
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
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


# ─────────────────────────────────────────────────────────────────────────────
# 测试基座（每 example 新建内存引擎再 dispose 隔离，兼容 Hypothesis）
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


# ─────────────────────────────────────────────────────────────────────────────
# 智能生成器：约束到公式表达式输入空间（非空、可打印、含常见公式记号）
# ─────────────────────────────────────────────────────────────────────────────
# 源公式表达式：TB()/PREV()/AUX()/算术记号 + 中文/科目号，覆盖真实公式形态。
_expression_strategy = st.one_of(
    st.builds(
        lambda code: f"TB('{code}')",
        st.text(alphabet="0123456789", min_size=3, max_size=6),
    ),
    st.builds(
        lambda a, b: f"TB('{a}')+TB('{b}')",
        st.text(alphabet="0123456789", min_size=3, max_size=6),
        st.text(alphabet="0123456789", min_size=3, max_size=6),
    ),
    st.builds(
        lambda a, k: f"SUM_TB('{a}')*{k}",
        st.text(alphabet="0123456789", min_size=3, max_size=6),
        st.integers(min_value=1, max_value=100),
    ),
    st.text(min_size=1, max_size=40).filter(lambda s: s.strip() != ""),
)

# 引用方数量：1..5（P30 断言受影响数 == 引用方数）。
_dependent_count_strategy = st.integers(min_value=1, max_value=5)


# ═══════════════════════════════════════════════════════════════════════════════
# Property 30：参照复用（Req 25.5）+ 源变更失效传播（Req 25.7）
# ═══════════════════════════════════════════════════════════════════════════════
@settings(max_examples=5, deadline=None)
@given(
    source_expression=_expression_strategy,
    changed_expression=_expression_strategy,
    dependent_count=_dependent_count_strategy,
)
def test_p30_reference_reuse_and_source_change_invalidation(
    source_expression: str,
    changed_expression: str,
    dependent_count: int,
):
    """P30：引用方解析表达式 == 源表达式（复用）；源变更经 ACNR 失效链使全部引用方失效。

    **Validates: Requirements 25.5, 25.7**
    """

    async def _scenario():
        factory, engine = await _make_session()
        try:
            async with factory() as db:
                project_id = uuid.uuid4()
                src = await _add_formula(
                    db,
                    project_id=project_id,
                    wp_id=uuid.uuid4(),
                    target_cell="B5",
                    expression=source_expression,
                )

                # 建 N 个 reference 引用方，均指向同一源公式（复用而非各自重录）。
                dependents = []
                for i in range(dependent_count):
                    dep = await _add_formula(
                        db,
                        project_id=project_id,
                        wp_id=uuid.uuid4(),
                        target_cell=f"C{i}",
                        # 引用方自身 expression 是占位——解析应取源表达式，非此串。
                        expression="占位待复用",
                        formula_source="reference",
                        reference_formula_id=src.id,
                    )
                    dependents.append(dep)

                # ── ① 复用保真（Req 25.5）：每个引用方解析出的表达式 == 源表达式 ──
                for dep in dependents:
                    res = await resolve_reference_expression(
                        db,
                        reference_formula_id=dep.reference_formula_id,
                        requester_formula_id=str(dep.id),
                    )
                    assert res.resolved is True
                    # 复用而非重录：逐字等于源公式 expression。
                    assert res.expression == source_expression
                    assert res.source_formula_id == str(src.id)
                    assert res.dangling is False
                    assert res.issue is None

                # find_reference_dependents 精确覆盖全部引用方（无遗漏/无误纳）。
                found = await find_reference_dependents(
                    db, source_formula_id=src.id
                )
                assert {d.id for d in found} == {d.id for d in dependents}

                # ── ② 源变更失效传播（Req 25.7）：经 ACNR 失效链使全部引用方失效 ──
                # 模拟源公式变更（更新表达式）。
                src.expression = changed_expression
                await db.flush()

                with patch(
                    "app.services.acnr.events.invalidate",
                    new_callable=AsyncMock,
                ) as mock_inval:
                    affected = await invalidate_reference_dependents(
                        db, source_formula_id=src.id, project_id=project_id
                    )

                # 受影响数恒等于引用方数量（可重算范围完整）。
                assert affected == dependent_count
                # 复用 ACNR 失效链（不自建），且按 project 维度触发一次。
                mock_inval.assert_awaited_once()
                args, _kwargs = mock_inval.await_args
                assert args[0] == str(project_id)

                # 源变更后再解析，引用方复用的是新表达式（可重算 → 反映最新源）。
                res_after = await resolve_reference_expression(
                    db, reference_formula_id=dependents[0].reference_formula_id
                )
                assert res_after.resolved is True
                assert res_after.expression == changed_expression
        finally:
            await engine.dispose()

    _run(_scenario())


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
