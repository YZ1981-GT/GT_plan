# Feature: workpaper-bad-debt-nested-structure, Property 5/9/10/11/12: NestedTableService 层级/并发/排序
"""NestedTableService 的 Property-Based Tests（hypothesis, max_examples=5）。

- Property 5:  枚举唯一性          (Validates Requirements 1.3, 2.6)
- Property 9:  层级完整性          (Validates Requirements 2.6, 10.4)
- Property 10: 级联删除            (Validates Requirements 8.4)
- Property 11: 乐观锁冲突检测      (Validates Requirements 8.5)
- Property 12: 子行新增排序单调    (Validates Requirements 2.4)

DB 策略：使用 in-process 内存 SQLite 会话（与 backend/tests/conftest.py 既有
DB 测试同口径）。每个 hypothesis example 新建独立内存 engine + 仅建
bad_debt_detail_rows 表，保证 example 间完全隔离（铁律：PBT 含 DB 状态变更需隔离）。
SQLite 对 (wp_index_id, provision_method) 唯一索引同样拦截重复父行（NULL 视为
distinct，故子行不受约束），可验证 Property 5。
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.bad_debt_models import BadDebtDetailRow, ProvisionMethod
from app.schemas.bad_debt_schemas import (
    CreateChildRowDTO,
    CreateParentRowDTO,
    RowAmounts,
    UpdateRowDTO,
)
from app.services.bad_debt_nested_table_service import (
    DuplicateProvisionMethodError,
    HierarchyError,
    NestedTableService,
    OptimisticLockError,
)

_PBT = settings(
    max_examples=5,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)


# ─── in-process SQLite 会话工厂 ──────────────────────────────────────────────


async def _fresh_session() -> tuple[AsyncSession, object]:
    """新建独立内存 engine + 仅建 bad_debt_detail_rows 表，返回 (session, engine)。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all, tables=[BadDebtDetailRow.__table__]
        )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return factory(), engine


# ─── 生成策略 ────────────────────────────────────────────────────────────────

st_provision_method = st.sampled_from(list(ProvisionMethod))

# 一组互不相同的计提方法（1~4 个）
st_distinct_methods = st.lists(
    st_provision_method, min_size=1, max_size=4, unique=True
)

st_amount = st.decimals(
    min_value=Decimal("0.00"),
    max_value=Decimal("100000.00"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)


# ─── Property 5: 枚举唯一性 ─────────────────────────────────────────────────


@_PBT
@given(method=st_provision_method)
def test_property_5_provision_method_unique(method: ProvisionMethod):
    """Property 5: 同一 wp_index 下重复 provision_method 的第二个父行被拒绝。

    Validates: Requirements 1.3, 2.6
    """

    async def _run():
        session, engine = await _fresh_session()
        try:
            svc = NestedTableService(session)
            wp_index_id = uuid.uuid4()
            await svc.create_parent_row(
                wp_index_id, CreateParentRowDTO(provision_method=method, row_label="父1")
            )
            with pytest.raises(DuplicateProvisionMethodError):
                await svc.create_parent_row(
                    wp_index_id,
                    CreateParentRowDTO(provision_method=method, row_label="父2"),
                )
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_run())


# ─── Property 9: 层级完整性 ─────────────────────────────────────────────────


@_PBT
@given(methods=st_distinct_methods, child_counts=st.lists(st.integers(0, 3), max_size=4))
def test_property_9_hierarchy_integrity(methods, child_counts):
    """Property 9: 所有子行 parent_row_id 指向同 wp_index 下有效父行，无孤儿。

    Validates: Requirements 2.6, 10.4
    """

    async def _run():
        session, engine = await _fresh_session()
        try:
            svc = NestedTableService(session)
            wp_index_id = uuid.uuid4()
            for i, method in enumerate(methods):
                parent = await svc.create_parent_row(
                    wp_index_id,
                    CreateParentRowDTO(provision_method=method, row_label=f"父{i}"),
                )
                n_children = child_counts[i] if i < len(child_counts) else 0
                for j in range(n_children):
                    await svc.create_child_row(
                        parent.id, CreateChildRowDTO(row_label=f"子{i}-{j}")
                    )

            errors = await svc.validate_integrity(wp_index_id)
            orphans = [e for e in errors if e.code == "ORPHAN_CHILD"]
            assert orphans == [], f"出现孤儿子行: {orphans}"

            # 直接验证：每个子行 parent_row_id ∈ 父行 id 集合
            all_rows = (
                await session.execute(
                    select(BadDebtDetailRow).where(
                        BadDebtDetailRow.wp_index_id == wp_index_id
                    )
                )
            ).scalars().all()
            parent_ids = {r.id for r in all_rows if r.parent_row_id is None}
            for r in all_rows:
                if r.parent_row_id is not None:
                    assert r.parent_row_id in parent_ids
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_run())


# ─── Property 10: 级联删除 ──────────────────────────────────────────────────


@_PBT
@given(n_children=st.integers(min_value=0, max_value=4))
def test_property_10_cascade_delete(n_children: int):
    """Property 10: 删除父行后其全部子行也被删除（无孤儿残留）。

    需 ≥2 个父行（删最后一个父行被拒），故建 2 个父行，删带子行的那个。

    Validates: Requirements 8.4
    """

    async def _run():
        session, engine = await _fresh_session()
        try:
            svc = NestedTableService(session)
            wp_index_id = uuid.uuid4()
            target = await svc.create_parent_row(
                wp_index_id,
                CreateParentRowDTO(
                    provision_method=ProvisionMethod.INDIVIDUAL, row_label="待删父"
                ),
            )
            # 保留父行（防删最后一个被拒）
            await svc.create_parent_row(
                wp_index_id,
                CreateParentRowDTO(
                    provision_method=ProvisionMethod.OTHER, row_label="保留父"
                ),
            )
            child_ids = []
            for j in range(n_children):
                child = await svc.create_child_row(
                    target.id, CreateChildRowDTO(row_label=f"子{j}")
                )
                child_ids.append(child.id)

            await svc.delete_row(target.id)

            # 目标父行及其全部子行均不存在
            remaining = (
                await session.execute(
                    select(func.count()).where(
                        BadDebtDetailRow.parent_row_id == target.id
                    )
                )
            ).scalar()
            assert remaining == 0, "级联删除后仍有子行残留"
            assert await session.get(BadDebtDetailRow, target.id) is None
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_run())


# ─── Property 11: 乐观锁冲突检测 ────────────────────────────────────────────


@_PBT
@given(amount=st_amount)
def test_property_11_optimistic_lock_conflict(amount: Decimal):
    """Property 11: 相同起始 version 的第二次更新（stale version）被拒（冲突）。

    Validates: Requirements 8.5
    """

    async def _run():
        session, engine = await _fresh_session()
        try:
            svc = NestedTableService(session)
            wp_index_id = uuid.uuid4()
            # 用无子行父行（可直接编辑金额）
            parent = await svc.create_parent_row(
                wp_index_id,
                CreateParentRowDTO(
                    provision_method=ProvisionMethod.INDIVIDUAL, row_label="父"
                ),
            )
            start_version = parent.version  # 1

            # 第一次更新成功，version → 2
            await svc.update_row(
                parent.id,
                UpdateRowDTO(version=start_version, amounts=RowAmounts(amount_n=amount)),
            )

            # 第二次用 stale version（仍为 start_version）→ 冲突
            with pytest.raises(OptimisticLockError):
                await svc.update_row(
                    parent.id,
                    UpdateRowDTO(
                        version=start_version, amounts=RowAmounts(amount_n=amount)
                    ),
                )
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_run())


# ─── Property 12: 子行新增排序单调 ─────────────────────────────────────────


@_PBT
@given(n_children=st.integers(min_value=2, max_value=6))
def test_property_12_child_sort_order_monotonic(n_children: int):
    """Property 12: 同一父行下每个新子行 sort_order 严格大于现有所有子行。

    Validates: Requirements 2.4
    """

    async def _run():
        session, engine = await _fresh_session()
        try:
            svc = NestedTableService(session)
            wp_index_id = uuid.uuid4()
            parent = await svc.create_parent_row(
                wp_index_id,
                CreateParentRowDTO(
                    provision_method=ProvisionMethod.CREDIT_RISK_AGING, row_label="父"
                ),
            )
            sort_orders: list[int] = []
            for j in range(n_children):
                child = await svc.create_child_row(
                    parent.id, CreateChildRowDTO(row_label=f"子{j}")
                )
                # 新子行严格大于此前所有
                if sort_orders:
                    assert child.sort_order > max(sort_orders), (
                        f"新子行 sort_order={child.sort_order} 未严格大于 {sort_orders}"
                    )
                sort_orders.append(child.sort_order)

            # 整体严格单调递增
            assert sort_orders == sorted(sort_orders)
            assert len(set(sort_orders)) == len(sort_orders)
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_run())
