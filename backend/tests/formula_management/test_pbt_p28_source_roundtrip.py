# Feature: formula-management-library, Property 28: 公式来源往返保真
"""属性测试 P28：公式来源往返保真。

*对任意* 公式与任意 ``Formula_Source ∈ {preset, custom, reference}``，经
``WpFormulaService.save`` 保存后再由 ``list_by_wp`` 读回，其 ``formula_source``
与保存输入相等（前端据此可区分预设/自定义/参照）。``reference`` 来源额外保真
``reference_formula_id``（指向被参照源公式）。

被测：``app.services.wp_formula_service.WpFormulaService.save`` + ``list_by_wp``。
- 用内存 SQLite（``:memory:`` + ``aiosqlite``）+ SQLiteTypeCompiler.visit_UUID /
  visit_JSONB patch 建 ``wp_formula`` 表（参考 test_reference_resolver.py /
  test_pbt_p06_save_roundtrip.py）。
- monkeypatch ``validate_refs_via_acnr`` 返回 ``[]``（引用有效，不触发 422 分支）。
- monkeypatch ``acnr.events.invalidate``（source 变更失效链复用不自建，本属性不断言）。
- ``preset`` / ``custom`` 来源直接 save 后读回；``reference`` 来源须**先经 ORM
  落一条源公式再引用**（save 复用源表达式并落 reference_formula_id）。

每个 example 用**独立 wp_id**保存单条公式后 ``list_by_wp(wp_id)`` 读回，确保读回
的恰是刚保存的那条，避免 upsert 维度干扰。

Framework: hypothesis（遵循 conftest fast profile，max_examples=5）。

**Validates: Requirements 25.1, 25.6**
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

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
from app.services.wp_formula_service import WpFormulaService  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# 测试基座：save / list_by_wp 为协程；每个 example 用独立内存引擎隔离。
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
) -> WpFormula:
    """直接经 ORM 落一条源公式（绕过 save 的 ACNR 校验），供 reference 参照。"""
    row = WpFormula(
        project_id=project_id,
        wp_id=wp_id,
        sheet_name=sheet_name,
        target_cell=target_cell,
        expression=expression,
        formula_type="auto_calc",
        refs=[],
        formula_source="custom",
    )
    db.add(row)
    await db.flush()
    return row


# ─────────────────────────────────────────────────────────────────────────────
# 智能生成器：约束到 save 输入空间（三来源 + 合法单元 + 非空表达式）。
# ─────────────────────────────────────────────────────────────────────────────
_FORMULA_SOURCES = st.sampled_from(["preset", "custom", "reference"])

# target_cell 形如 A1 / B5 / AB12（列字母 + 行号）。
_TARGET_CELL = st.builds(
    lambda col, row: f"{col}{row}",
    st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=1, max_size=2),
    st.integers(min_value=1, max_value=999),
)

# expression：非空文本（save 前 validate 被桩为 []，内容不影响持久化）。
_EXPRESSION = st.text(
    alphabet="ABCDEFGHIJ0123456789+-*/()',!=<> ", min_size=1, max_size=40
).filter(lambda s: s.strip() != "")

_SHEET_NAME = st.text(alphabet="审定表明细ABC ", min_size=1, max_size=8).filter(
    lambda s: s.strip() != ""
)


@st.composite
def _save_input(draw):
    """抽取一条 save 输入：formula_source / sheet_name / target_cell / expression。"""
    return {
        "formula_source": draw(_FORMULA_SOURCES),
        "sheet_name": draw(_SHEET_NAME),
        "target_cell": draw(_TARGET_CELL),
        "expression": draw(_EXPRESSION),
    }


@given(_save_input())
@settings(max_examples=5)
def test_source_roundtrip_fidelity(inp):
    """P28：save(formula_source=X) → list_by_wp 读回 formula_source==X。

    reference 来源须先建源公式再引用，读回额外保真 reference_formula_id。

    **Validates: Requirements 25.1, 25.6**
    """

    async def _scenario():
        factory, engine = await _make_session()
        try:
            async with factory() as db:
                svc = WpFormulaService()
                project_id = uuid.uuid4()
                wp_id = uuid.uuid4()
                source = inp["formula_source"]

                # reference 来源须先落一条源公式再引用。
                reference_formula_id = None
                if source == "reference":
                    src = await _add_formula(
                        db,
                        project_id=project_id,
                        wp_id=uuid.uuid4(),
                        target_cell="B5",
                        expression="TB('1001')+TB('1002')",
                    )
                    reference_formula_id = src.id

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
                        wp_id=wp_id,
                        sheet_name=inp["sheet_name"],
                        target_cell=inp["target_cell"],
                        expression=inp["expression"],
                        year=2025,
                        formula_source=source,
                        reference_formula_id=reference_formula_id,
                    )

                # 引用有效 → 保存成功，返回 (WpFormula, [])。
                assert issues == []
                assert saved is not None

                # 读回：list_by_wp 恰返回刚保存的这一条。
                loaded = await svc.list_by_wp(db, wp_id)
                assert len(loaded) == 1
                row = loaded[0]

                # Req 25.1 / 25.6：formula_source 往返保真（前端据此区分三来源）。
                assert row.formula_source == source
                assert saved.formula_source == source

                # reference 来源额外保真被参照源公式标识。
                if source == "reference":
                    assert row.reference_formula_id == reference_formula_id
        finally:
            await engine.dispose()

    _run(_scenario())


if __name__ == "__main__":  # pragma: no cover
    import pytest

    pytest.main([__file__, "-v"])
