# Feature: formula-management-library, Property 6: 公式保存往返字段保真
"""属性测试 P6：公式保存往返字段保真。

*对任意* 引用有效的公式（三类型 auto_calc/logic_check/reasonability +
target_cell/expression/refs），经 ``WpFormulaService.save`` 保存后再由
``list_by_wp`` 读回，其 target_cell / expression / formula_type / refs 与保存
输入逐一相等；且 save 返回可供前端回显的公式标识（id）与最新表达式（Req 9.4）。

被测：``app.services.wp_formula_service.WpFormulaService.save`` + ``list_by_wp``。
- 用内存 SQLite（``:memory:`` + ``aiosqlite``）+ SQLiteTypeCompiler.visit_UUID /
  visit_JSONB patch 建 ``wp_formula`` 表（参考 test_wp_formula_three_type.py）。
- monkeypatch ``validate_refs_via_acnr`` 返回 ``[]``（引用有效，不触发 422 分支）。
- refs 生成 str（``formula_ref`` 文本）与 dict（``addr_id`` / ``formula_ref``）混合，
  期望值按 service 的规范化口径（str → ``{"formula_ref": str}``，dict 原样）核对，
  验证保存不丢失、不篡改引用结构。

每个 example 用**独立 wp_id**保存单条公式后 ``list_by_wp(wp_id)`` 读回，确保读回
的恰是刚保存的那条，避免 upsert 维度干扰。

Framework: hypothesis（遵循 conftest fast profile，max_examples 可经
HYPOTHESIS_MAX_EXAMPLES 覆盖）。

**Validates: Requirements 9.1, 9.4, 14.1**
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
# 事件循环辅助：save / list_by_wp 为协程；每个 example 用独立内存引擎隔离。
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


def _expected_refs(refs: list) -> list:
    """按 service._normalize_refs 口径计算期望持久化的 refs（供往返核对）。

    - str（非空）→ ``{"formula_ref": <str.strip()>}``
    - dict → 原样保留
    - 其余（空串）→ 丢弃
    """
    normalized: list = []
    for item in refs:
        if isinstance(item, dict):
            normalized.append(item)
        elif isinstance(item, str) and item.strip():
            normalized.append({"formula_ref": item.strip()})
    return normalized


# ─────────────────────────────────────────────────────────────────────────────
# 智能生成器：约束到 save 的输入空间（三类型 + 合法单元 + 混合 refs）。
# ─────────────────────────────────────────────────────────────────────────────
_FORMULA_TYPES = st.sampled_from(["auto_calc", "logic_check", "reasonability"])

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

# 单条 ref：formula_ref 文本 或 addr_id / formula_ref dict。
_REF_STR = st.text(
    alphabet="ABCDEFGHIJ0123456789/'(),!", min_size=1, max_size=20
).filter(lambda s: s.strip() != "")
_REF_ADDR_DICT = st.builds(lambda a: {"addr_id": a}, _REF_STR)
_REF_FORMULA_DICT = st.builds(lambda f: {"formula_ref": f}, _REF_STR)
_REF_ITEM = st.one_of(_REF_STR, _REF_ADDR_DICT, _REF_FORMULA_DICT)
_REFS = st.lists(_REF_ITEM, min_size=0, max_size=5)


@st.composite
def _save_input(draw):
    """抽取一条 save 输入：sheet_name / target_cell / expression / type / refs。"""
    return {
        "sheet_name": draw(
            st.text(alphabet="审定表明细ABC ", min_size=1, max_size=8).filter(
                lambda s: s.strip() != ""
            )
        ),
        "target_cell": draw(_TARGET_CELL),
        "expression": draw(_EXPRESSION),
        "formula_type": draw(_FORMULA_TYPES),
        "refs": draw(_REFS),
    }


@given(_save_input())
@settings(max_examples=200)
def test_save_roundtrip_field_fidelity(inp):
    """P6：save → list_by_wp 读回，四字段逐一保真 + 返回可回显标识。

    **Validates: Requirements 9.1, 9.4, 14.1**
    """

    async def _scenario():
        factory, engine = await _make_session()
        try:
            async with factory() as db:
                svc = WpFormulaService()
                project_id = uuid.uuid4()
                wp_id = uuid.uuid4()

                with patch(
                    "app.services.wp_formula_service.validate_refs_via_acnr",
                    new_callable=AsyncMock,
                    return_value=[],
                ):
                    saved, issues = await svc.save(
                        db,
                        project_id=project_id,
                        wp_id=wp_id,
                        sheet_name=inp["sheet_name"],
                        target_cell=inp["target_cell"],
                        expression=inp["expression"],
                        year=2025,
                        formula_type=inp["formula_type"],
                        refs=list(inp["refs"]),
                    )

                # 引用有效 → 保存成功，返回 (WpFormula, [])（Req 14.1 契约）。
                assert issues == []
                assert saved is not None
                # Req 9.4：返回可供前端回显的公式标识与最新表达式。
                assert saved.id is not None
                assert saved.expression == inp["expression"]

                # 读回：list_by_wp 恰返回刚保存的这一条。
                loaded = await svc.list_by_wp(db, wp_id)
                assert len(loaded) == 1
                row = loaded[0]

                # Req 9.1 / 14.1：四字段逐一保真。
                assert row.target_cell == inp["target_cell"]
                assert row.expression == inp["expression"]
                assert row.formula_type == inp["formula_type"]
                assert row.refs == _expected_refs(inp["refs"])

                # 回显标识与读回一致。
                assert row.id == saved.id
        finally:
            await engine.dispose()

    _run(_scenario())
