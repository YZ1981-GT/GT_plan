# Feature: formula-management-library, Property 4: 未确认覆盖仅刷新非人工编辑单元
"""属性测试 P4：合伙人未确认覆盖时，一键刷新仅刷新非人工编辑单元。

**Property 4: 未确认覆盖仅刷新非人工编辑单元**

*对任意*由人工编辑单元（``draft_marker.state='human_edited'``）与未编辑单元
（既有 ``draft`` 标记 / 全新无标记）混合构成的数据集，当合伙人**未确认覆盖**
（``confirm_overwrite=False``）时触发 ``DraftRefreshService.refresh``：

1. 所有人工编辑单元被跳过、其 ``draft_marker`` 保持 ``human_edited`` 值不变
   （既不改状态、也不改 refresh_id）——即"保留既有人工编辑数据"（Req 4.4）；
2. 仅非人工编辑单元（draft / new）被刷新为 ``state='draft'`` 并关联本次 refresh_id；
3. ``result.skipped_human_edited`` 恰为人工编辑单元集合，
   ``result.refreshed_units`` 恰为非人工编辑单元集合，二者不相交、并集为全部单元。

被测：``app.services.draft_refresh_service.DraftRefreshService.refresh``
（``confirm_overwrite=False`` 时排除 ``human_edited`` 单元，Req 3.3 → 4.4 闭环）。
用内存 sqlite（参考 ``tests/test_draft_refresh_refresh.py``），每个 Hypothesis
example 建独立库，四表库最小种子使 precheck 通过。

Framework: hypothesis（遵循 conftest fast profile，max_examples 可经
HYPOTHESIS_MAX_EXAMPLES 覆盖）。

**Validates: Requirements 3.3, 4.4**
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

import pytest
import sqlalchemy as sa
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import MetaData
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_platform_models import (
    AccountCategory,
    TbAuxBalance,
    TbBalance,
    TbLedger,
    TrialBalance,
)
from app.models.dataset_models import LedgerDataset
from app.models.workpaper_models import (
    DraftMarker,
    DraftRefreshAudit,
    DraftRefreshSnapshot,
)
from app.services.draft_refresh_service import DraftRefreshService, RefreshUnit

# ── SQLite 方言补丁：JSONB → JSON，ARRAY → TEXT（与既有 draft_refresh 测试一致）──
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

_TEST_TABLES = [
    TbBalance.__table__,
    TbLedger.__table__,
    TbAuxBalance.__table__,
    TrialBalance.__table__,
    LedgerDataset.__table__,
    DraftMarker.__table__,
    DraftRefreshAudit.__table__,
    DraftRefreshSnapshot.__table__,
]


class _Operator:
    """最小 User 替身：refresh 只取 id / role。"""

    def __init__(self, role: str = "partner"):
        self.id = uuid.uuid4()
        self.role = role


def _seed_core(project_id: uuid.UUID, year: int):
    """四表库最小种子：使 precheck 通过（tb_balance + trial_balance 有非零未审数）。"""
    return [
        TbBalance(
            project_id=project_id, year=year, company_code="C1",
            account_code="1001", account_name="库存现金",
            closing_balance=Decimal("100"),
        ),
        TrialBalance(
            project_id=project_id, year=year, company_code="C1",
            standard_account_code="1001", account_name="库存现金",
            account_category=AccountCategory.asset,
            unadjusted_amount=Decimal("100"),
        ),
    ]


# ── 智能生成器：混合 human_edited / draft / new 单元（约束到 report 域前缀空间）──
_CELL = st.text(alphabet="ABCDEFGHIJKLMNOP0123456789-", min_size=1, max_size=5)


@st.composite
def _mixed_units(draw):
    """生成一组唯一 unit_scope，各随机赋 kind ∈ {human_edited, draft, new}。

    统一用 ``report:`` 前缀，配合 refresh ``scope='report'`` 使前缀匹配命中全部单元，
    从而完整覆盖"未确认覆盖 → 排除 human_edited"的判定路径。至少 1 个单元。
    """
    cells = draw(st.lists(_CELL, min_size=1, max_size=8, unique=True))
    return [
        (f"report:{c}", draw(st.sampled_from(["human_edited", "draft", "new"])))
        for c in cells
    ]


async def _run_case(units_spec: list[tuple[str, str]]):
    """在独立内存库上执行一次未确认覆盖的 refresh，返回 (result, 刷新后 marker 状态映射)。"""
    project_id = uuid.uuid4()
    year = 2025
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(
                lambda sc: MetaData().create_all(sc, tables=_TEST_TABLES)
            )
        factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        async with factory() as db:
            # 四表库种子 + 预置既有标记（human_edited / draft），new 单元不预置标记
            db.add_all(_seed_core(project_id, year))
            for scope, kind in units_spec:
                if kind in ("human_edited", "draft"):
                    db.add(
                        DraftMarker(
                            project_id=project_id, year=year,
                            unit_scope=scope, state=kind,
                        )
                    )
            await db.commit()

            svc = DraftRefreshService()
            result = await svc.refresh(
                db,
                project_id=project_id, year=year,
                operator=_Operator(),
                scope="report",
                units=[RefreshUnit(scope) for scope, _ in units_spec],
                confirm_overwrite=False,
            )
            await db.commit()

            rows = (await db.execute(sa.select(DraftMarker))).scalars().all()
            markers = {
                m.unit_scope: (m.state, m.refresh_id) for m in rows
            }
            return result, markers
    finally:
        await engine.dispose()


@given(units_spec=_mixed_units())
@settings(max_examples=30)
def test_p04_unconfirmed_refresh_skips_human_edited(units_spec):
    """P4：未确认覆盖时人工编辑单元被跳过保持不变，非人工编辑单元被刷新为 draft。

    **Validates: Requirements 3.3, 4.4**
    """
    result, markers = asyncio.run(_run_case(units_spec))

    expected_skipped = {s for s, k in units_spec if k == "human_edited"}
    expected_refreshed = {s for s, k in units_spec if k != "human_edited"}

    # ── 编排结果集合精确划分（不相交，并集为全部单元）──
    assert set(result.skipped_human_edited) == expected_skipped
    assert set(result.refreshed_units) == expected_refreshed
    assert result.affected_count == len(expected_refreshed)
    assert not (set(result.refreshed_units) & set(result.skipped_human_edited))
    assert (
        set(result.refreshed_units) | set(result.skipped_human_edited)
        == {s for s, _ in units_spec}
    )

    # ── 人工编辑单元保持 human_edited 值不变（状态与 refresh_id 均未被触碰）──
    for scope in expected_skipped:
        state, refresh_id = markers[scope]
        assert state == "human_edited", f"{scope} 人工编辑单元被覆盖"
        assert refresh_id is None, f"{scope} 人工编辑单元被关联到本次刷新"

    # ── 非人工编辑单元被刷新为 draft 并关联本次 refresh_id ──
    for scope in expected_refreshed:
        state, refresh_id = markers[scope]
        assert state == "draft", f"{scope} 非人工编辑单元未被刷新为 draft"
        assert refresh_id == result.refresh_id


@pytest.mark.asyncio
async def test_p04_all_human_edited_refreshes_nothing():
    """退化边界：全部单元均为人工编辑 → 未确认覆盖时 affected_count 为 0，全部跳过。"""
    result, markers = await _run_case(
        [("report:BS-1", "human_edited"), ("report:BS-2", "human_edited")]
    )
    assert result.affected_count == 0
    assert set(result.skipped_human_edited) == {"report:BS-1", "report:BS-2"}
    assert result.refreshed_units == []
    assert all(state == "human_edited" for state, _ in markers.values())
