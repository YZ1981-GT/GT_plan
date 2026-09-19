"""坏账 D2-3 真 PG 冒烟 — 偏索引 / 级联 / 乐观锁 / 子行排序。

默认 skip（SQLite CI）；本地 PG 跑：
  DATABASE_URL=postgresql+asyncpg://... pytest tests/test_bad_debt_pg_smoke.py -m pg_only -v
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.bad_debt_models import BadDebtDetailRow, ProvisionMethod
from app.schemas.bad_debt_schemas import CreateChildRowDTO, CreateParentRowDTO, UpdateRowDTO
from app.services.bad_debt_nested_table_service import NestedTableService, OptimisticLockError


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_pg_bad_debt_child_sort_and_optimistic_lock(db_session):
    """真 PG：子行 insert_before 排序 + version 乐观锁 409 语义。"""
    svc = NestedTableService(db_session)
    wp = uuid.uuid4()
    parent = await svc.create_parent_row(
        wp, CreateParentRowDTO(provision_method=ProvisionMethod.INDIVIDUAL, row_label="PG单项")
    )
    a = await svc.create_child_row(parent.id, CreateChildRowDTO(row_label="A", amount_n=Decimal("1")))
    b = await svc.create_child_row(
        parent.id,
        CreateChildRowDTO(row_label="B", amount_n=Decimal("2"), insert_before_id=a.id),
    )
    children = (
        await db_session.execute(
            select(BadDebtDetailRow)
            .where(BadDebtDetailRow.parent_row_id == parent.id)
            .order_by(BadDebtDetailRow.sort_order)
        )
    ).scalars().all()
    assert [c.row_label for c in children] == ["B", "A"]

    with pytest.raises(OptimisticLockError):
        await svc.update_row(
            a.id,
            UpdateRowDTO(row_label="A2", amounts=None, version=a.version - 1),
        )
