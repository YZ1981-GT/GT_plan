# Feature: workpaper-bad-debt-nested-structure — Task 3 NestedTableService 单元测试
"""NestedTableService CRUD + 层级管理 + get_tree + validate_integrity 单元测试。

DB：in-process 内存 SQLite，仅建 bad_debt_detail_rows 表（与 PBT 同口径，example 隔离）。
覆盖：
- 3.1 get_tree：父嵌套子 + Summary 合计 + balance_check + is_editable
- 3.2 create_parent_row / create_child_row：重复枚举拦截、子行汇总触发、排序
- 3.3 update_row（乐观锁/父行有子行拒编辑）/ delete_row（级联/拒删最后一个父行）
- 3.4 validate_integrity：孤儿/精度/父子合计不一致
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
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
    RowNotFoundError,
)


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all, tables=[BadDebtDetailRow.__table__]
        )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


# ─── 3.1 get_tree ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_tree_empty(session: AsyncSession):
    svc = NestedTableService(session)
    wp = uuid.uuid4()
    tree = await svc.get_tree(wp)
    assert tree.wp_index_id == wp
    assert tree.parents == []
    assert tree.summary.amounts.amount_n is None
    assert tree.summary.balance_check.is_balanced is True  # 全 0 平衡


@pytest.mark.asyncio
async def test_get_tree_parent_with_children_sums(session: AsyncSession):
    svc = NestedTableService(session)
    wp = uuid.uuid4()
    parent = await svc.create_parent_row(
        wp, CreateParentRowDTO(provision_method=ProvisionMethod.INDIVIDUAL, row_label="单项")
    )
    await svc.create_child_row(
        parent.id, CreateChildRowDTO(row_label="A", amount_n=Decimal("100.00"))
    )
    await svc.create_child_row(
        parent.id, CreateChildRowDTO(row_label="B", amount_n=Decimal("50.00"))
    )

    tree = await svc.get_tree(wp)
    assert len(tree.parents) == 1
    p = tree.parents[0]
    # 父行 = 子行合计
    assert p.amounts.amount_n == Decimal("150.00")
    assert p.is_editable is False  # 有子行不可直接编辑
    assert len(p.children) == 2
    # Summary = 父行合计
    assert tree.summary.amounts.amount_n == Decimal("150.00")


@pytest.mark.asyncio
async def test_get_tree_parent_without_children_uses_own_value(session: AsyncSession):
    svc = NestedTableService(session)
    wp = uuid.uuid4()
    parent = await svc.create_parent_row(
        wp, CreateParentRowDTO(provision_method=ProvisionMethod.OTHER, row_label="其他")
    )
    await svc.update_row(
        parent.id, UpdateRowDTO(version=parent.version, amounts=RowAmounts(amount_n=Decimal("88.00")))
    )
    tree = await svc.get_tree(wp)
    assert tree.parents[0].is_editable is True
    assert tree.parents[0].amounts.amount_n == Decimal("88.00")
    assert tree.summary.amounts.amount_n == Decimal("88.00")


# ─── 3.2 create_parent_row / create_child_row ──────────────────────────────


@pytest.mark.asyncio
async def test_create_parent_duplicate_method_rejected(session: AsyncSession):
    svc = NestedTableService(session)
    wp = uuid.uuid4()
    await svc.create_parent_row(
        wp, CreateParentRowDTO(provision_method=ProvisionMethod.INDIVIDUAL, row_label="1")
    )
    with pytest.raises(DuplicateProvisionMethodError):
        await svc.create_parent_row(
            wp, CreateParentRowDTO(provision_method=ProvisionMethod.INDIVIDUAL, row_label="2")
        )


@pytest.mark.asyncio
async def test_create_parent_same_method_different_wp_ok(session: AsyncSession):
    """不同 wp_index 下相同 provision_method 允许（唯一约束仅同 wp 内）。"""
    svc = NestedTableService(session)
    await svc.create_parent_row(
        uuid.uuid4(), CreateParentRowDTO(provision_method=ProvisionMethod.INDIVIDUAL, row_label="1")
    )
    # 不同 wp 不抛
    await svc.create_parent_row(
        uuid.uuid4(), CreateParentRowDTO(provision_method=ProvisionMethod.INDIVIDUAL, row_label="2")
    )


@pytest.mark.asyncio
async def test_create_child_triggers_parent_resum(session: AsyncSession):
    svc = NestedTableService(session)
    wp = uuid.uuid4()
    parent = await svc.create_parent_row(
        wp, CreateParentRowDTO(provision_method=ProvisionMethod.INDIVIDUAL, row_label="单项")
    )
    await svc.create_child_row(
        parent.id, CreateChildRowDTO(row_label="A", amount_e=Decimal("10.00"), amount_n=Decimal("30.00"))
    )
    # 父行已被重算落库
    db_parent = await session.get(BadDebtDetailRow, parent.id)
    assert db_parent.amount_n == Decimal("30.00")
    assert db_parent.amount_e == Decimal("10.00")


@pytest.mark.asyncio
async def test_create_child_under_child_rejected(session: AsyncSession):
    svc = NestedTableService(session)
    wp = uuid.uuid4()
    parent = await svc.create_parent_row(
        wp, CreateParentRowDTO(provision_method=ProvisionMethod.INDIVIDUAL, row_label="单项")
    )
    child = await svc.create_child_row(parent.id, CreateChildRowDTO(row_label="A"))
    with pytest.raises(HierarchyError):
        await svc.create_child_row(child.id, CreateChildRowDTO(row_label="孙"))


# ─── 3.3 update_row / delete_row ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_row_version_increment(session: AsyncSession):
    svc = NestedTableService(session)
    wp = uuid.uuid4()
    parent = await svc.create_parent_row(
        wp, CreateParentRowDTO(provision_method=ProvisionMethod.OTHER, row_label="其他")
    )
    await svc.update_row(
        parent.id, UpdateRowDTO(version=1, amounts=RowAmounts(amount_n=Decimal("5.00")))
    )
    db_parent = await session.get(BadDebtDetailRow, parent.id)
    assert db_parent.version == 2


@pytest.mark.asyncio
async def test_update_row_stale_version_conflict(session: AsyncSession):
    svc = NestedTableService(session)
    wp = uuid.uuid4()
    parent = await svc.create_parent_row(
        wp, CreateParentRowDTO(provision_method=ProvisionMethod.OTHER, row_label="其他")
    )
    await svc.update_row(parent.id, UpdateRowDTO(version=1, amounts=RowAmounts(amount_n=Decimal("1.00"))))
    with pytest.raises(OptimisticLockError):
        await svc.update_row(parent.id, UpdateRowDTO(version=1, amounts=RowAmounts(amount_n=Decimal("2.00"))))


@pytest.mark.asyncio
async def test_update_parent_with_children_amount_rejected(session: AsyncSession):
    svc = NestedTableService(session)
    wp = uuid.uuid4()
    parent = await svc.create_parent_row(
        wp, CreateParentRowDTO(provision_method=ProvisionMethod.INDIVIDUAL, row_label="单项")
    )
    await svc.create_child_row(parent.id, CreateChildRowDTO(row_label="A", amount_n=Decimal("1.00")))
    # 父行有子行，version 已因子行重算可能变化 → 重新读取
    db_parent = await session.get(BadDebtDetailRow, parent.id)
    with pytest.raises(HierarchyError):
        await svc.update_row(
            parent.id, UpdateRowDTO(version=db_parent.version, amounts=RowAmounts(amount_n=Decimal("9.00")))
        )


@pytest.mark.asyncio
async def test_delete_child_resums_parent(session: AsyncSession):
    svc = NestedTableService(session)
    wp = uuid.uuid4()
    parent = await svc.create_parent_row(
        wp, CreateParentRowDTO(provision_method=ProvisionMethod.INDIVIDUAL, row_label="单项")
    )
    c1 = await svc.create_child_row(parent.id, CreateChildRowDTO(row_label="A", amount_n=Decimal("10.00")))
    await svc.create_child_row(parent.id, CreateChildRowDTO(row_label="B", amount_n=Decimal("20.00")))
    await svc.delete_row(c1.id)
    db_parent = await session.get(BadDebtDetailRow, parent.id)
    assert db_parent.amount_n == Decimal("20.00")


@pytest.mark.asyncio
async def test_delete_last_parent_rejected(session: AsyncSession):
    svc = NestedTableService(session)
    wp = uuid.uuid4()
    parent = await svc.create_parent_row(
        wp, CreateParentRowDTO(provision_method=ProvisionMethod.INDIVIDUAL, row_label="单项")
    )
    with pytest.raises(HierarchyError):
        await svc.delete_row(parent.id)


@pytest.mark.asyncio
async def test_delete_parent_cascade(session: AsyncSession):
    svc = NestedTableService(session)
    wp = uuid.uuid4()
    p1 = await svc.create_parent_row(
        wp, CreateParentRowDTO(provision_method=ProvisionMethod.INDIVIDUAL, row_label="单项")
    )
    await svc.create_parent_row(
        wp, CreateParentRowDTO(provision_method=ProvisionMethod.OTHER, row_label="其他")
    )
    child = await svc.create_child_row(p1.id, CreateChildRowDTO(row_label="A"))
    await svc.delete_row(p1.id)
    assert await session.get(BadDebtDetailRow, p1.id) is None
    assert await session.get(BadDebtDetailRow, child.id) is None


@pytest.mark.asyncio
async def test_delete_nonexistent_row_raises(session: AsyncSession):
    svc = NestedTableService(session)
    with pytest.raises(RowNotFoundError):
        await svc.delete_row(uuid.uuid4())


# ─── 3.4 validate_integrity ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_validate_integrity_clean(session: AsyncSession):
    svc = NestedTableService(session)
    wp = uuid.uuid4()
    parent = await svc.create_parent_row(
        wp, CreateParentRowDTO(provision_method=ProvisionMethod.INDIVIDUAL, row_label="单项")
    )
    await svc.create_child_row(parent.id, CreateChildRowDTO(row_label="A", amount_n=Decimal("10.00")))
    errors = await svc.validate_integrity(wp)
    assert errors == []


@pytest.mark.asyncio
async def test_validate_integrity_orphan_child(session: AsyncSession):
    svc = NestedTableService(session)
    wp = uuid.uuid4()
    # 直接插入孤儿子行（parent_row_id 指向不存在父行）
    orphan = BadDebtDetailRow(
        id=uuid.uuid4(),
        wp_index_id=wp,
        parent_row_id=uuid.uuid4(),  # 不存在
        provision_method=None,
        sort_order=10,
        row_label="孤儿",
        version=1,
    )
    session.add(orphan)
    await session.flush()
    errors = await svc.validate_integrity(wp)
    assert any(e.code == "ORPHAN_CHILD" for e in errors)


@pytest.mark.asyncio
async def test_validate_integrity_parent_sum_mismatch(session: AsyncSession):
    svc = NestedTableService(session)
    wp = uuid.uuid4()
    parent = await svc.create_parent_row(
        wp, CreateParentRowDTO(provision_method=ProvisionMethod.INDIVIDUAL, row_label="单项")
    )
    await svc.create_child_row(parent.id, CreateChildRowDTO(row_label="A", amount_n=Decimal("10.00")))
    # 人为篡改父行显示值，制造与子行合计不一致
    db_parent = await session.get(BadDebtDetailRow, parent.id)
    db_parent.amount_n = Decimal("999.00")
    await session.flush()
    errors = await svc.validate_integrity(wp)
    mismatch = [e for e in errors if e.code == "PARENT_SUM_MISMATCH"]
    assert mismatch
    assert mismatch[0].action == "RESUM"
