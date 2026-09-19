# Feature: workpaper-bad-debt-nested-structure — Task 7.3 Serializer 单元测试
"""NestedTableService.serialize / deserialize 单元测试。

覆盖：
- serialize：空底稿 / 父子结构 / Decimal→str 保精度 / None→null
- deserialize 正常：从 JSON 恢复、清空重建（覆盖旧数据）
- deserialize 错误：缺字段 / 层级断裂 / 枚举非法 / 重复枚举 / 金额越界
  → 返回详细 ValidationError 列表且不写库（不静默忽略）

DB：in-process 内存 SQLite，仅建 bad_debt_detail_rows 表（与服务单测同口径）。
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.bad_debt_models import BadDebtDetailRow, ProvisionMethod
from app.schemas.bad_debt_schemas import CreateChildRowDTO, CreateParentRowDTO
from app.services.bad_debt_nested_table_service import NestedTableService


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


async def _count_rows(session: AsyncSession, wp: uuid.UUID) -> int:
    return (
        await session.execute(
            select(func.count()).where(BadDebtDetailRow.wp_index_id == wp)
        )
    ).scalar() or 0


# ─── serialize ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_serialize_empty(session: AsyncSession):
    svc = NestedTableService(session)
    wp = uuid.uuid4()
    out = await svc.serialize(wp)
    assert out["wp_index_id"] == str(wp)
    assert out["parents"] == []
    assert out["format_version"] == 1


@pytest.mark.asyncio
async def test_serialize_parent_with_children(session: AsyncSession):
    svc = NestedTableService(session)
    wp = uuid.uuid4()
    parent = await svc.create_parent_row(
        wp, CreateParentRowDTO(provision_method=ProvisionMethod.INDIVIDUAL, row_label="单项")
    )
    await svc.create_child_row(
        parent.id, CreateChildRowDTO(row_label="甲公司", amount_n=Decimal("100.00"))
    )
    await svc.create_child_row(
        parent.id, CreateChildRowDTO(row_label="乙公司", amount_n=Decimal("50.50"))
    )

    out = await svc.serialize(wp)
    assert len(out["parents"]) == 1
    p = out["parents"][0]
    assert p["provision_method"] == "INDIVIDUAL"
    assert p["provision_method_label"] == "按单项评估计提"
    assert len(p["children"]) == 2
    # 父行金额已被汇总落库为子行合计，且 Decimal → str 保精度
    assert p["amounts"]["amount_n"] == "150.50"
    # 子行金额 str；未填列为 null
    assert p["children"][0]["amounts"]["amount_n"] == "100.00"
    assert p["children"][0]["amounts"]["amount_b"] is None


# ─── deserialize 正常 ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_deserialize_round_trip_basic(session: AsyncSession):
    svc = NestedTableService(session)
    wp = uuid.uuid4()
    payload = {
        "parents": [
            {
                "provision_method": "INDIVIDUAL",
                "row_label": "按单项评估计提",
                "sort_order": 10,
                "amounts": {"amount_n": "300.00"},
                "children": [
                    {"row_label": "甲", "sort_order": 10, "amounts": {"amount_n": "300.00"}},
                ],
            },
            {
                "provision_method": "CREDIT_RISK_AGING",
                "row_label": "账龄",
                "sort_order": 20,
                "amounts": {"amount_n": "88.00"},
                "children": [],
            },
        ]
    }
    errors = await svc.deserialize(wp, payload)
    assert errors == []
    # 2 父 + 1 子 = 3 行
    assert await _count_rows(session, wp) == 3

    out = await svc.serialize(wp)
    methods = {p["provision_method"] for p in out["parents"]}
    assert methods == {"INDIVIDUAL", "CREDIT_RISK_AGING"}


@pytest.mark.asyncio
async def test_deserialize_clears_existing_rows(session: AsyncSession):
    """deserialize 应清空底稿现有行再重建（覆盖语义），不残留旧数据。"""
    svc = NestedTableService(session)
    wp = uuid.uuid4()
    # 先放一个父行
    await svc.create_parent_row(
        wp, CreateParentRowDTO(provision_method=ProvisionMethod.OTHER, row_label="旧")
    )
    assert await _count_rows(session, wp) == 1

    payload = {
        "parents": [
            {
                "provision_method": "INDIVIDUAL",
                "row_label": "新",
                "sort_order": 10,
                "amounts": {},
                "children": [],
            }
        ]
    }
    errors = await svc.deserialize(wp, payload)
    assert errors == []
    # 旧 OTHER 父行被清掉，只剩新的 INDIVIDUAL
    rows = (
        await session.execute(
            select(BadDebtDetailRow).where(BadDebtDetailRow.wp_index_id == wp)
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].provision_method == "INDIVIDUAL"


@pytest.mark.asyncio
async def test_deserialize_isolates_other_wp(session: AsyncSession):
    """deserialize 只清空目标底稿，不影响其他底稿。"""
    svc = NestedTableService(session)
    wp_a = uuid.uuid4()
    wp_b = uuid.uuid4()
    await svc.create_parent_row(
        wp_b, CreateParentRowDTO(provision_method=ProvisionMethod.OTHER, row_label="B保留")
    )
    payload = {
        "parents": [
            {"provision_method": "INDIVIDUAL", "row_label": "A", "amounts": {}, "children": []}
        ]
    }
    errors = await svc.deserialize(wp_a, payload)
    assert errors == []
    assert await _count_rows(session, wp_b) == 1  # B 未受影响


# ─── deserialize 错误（缺字段 / 层级 / 枚举 / 金额）─────────────────────────


@pytest.mark.asyncio
async def test_deserialize_not_object(session: AsyncSession):
    svc = NestedTableService(session)
    errors = await svc.deserialize(uuid.uuid4(), ["not", "a", "dict"])  # type: ignore[arg-type]
    assert errors
    assert any("payload 必须是 JSON 对象" in e for e in errors)


@pytest.mark.asyncio
async def test_deserialize_missing_parents(session: AsyncSession):
    svc = NestedTableService(session)
    errors = await svc.deserialize(uuid.uuid4(), {"foo": "bar"})
    assert any("缺少必要字段: parents" in e for e in errors)


@pytest.mark.asyncio
async def test_deserialize_missing_provision_method(session: AsyncSession):
    svc = NestedTableService(session)
    payload = {"parents": [{"row_label": "无方法", "amounts": {}, "children": []}]}
    errors = await svc.deserialize(uuid.uuid4(), payload)
    assert any("provision_method" in e for e in errors)


@pytest.mark.asyncio
async def test_deserialize_invalid_provision_method(session: AsyncSession):
    svc = NestedTableService(session)
    payload = {
        "parents": [{"provision_method": "BOGUS", "row_label": "x", "amounts": {}, "children": []}]
    }
    errors = await svc.deserialize(uuid.uuid4(), payload)
    assert any("非法值" in e for e in errors)


@pytest.mark.asyncio
async def test_deserialize_duplicate_provision_method(session: AsyncSession):
    svc = NestedTableService(session)
    payload = {
        "parents": [
            {"provision_method": "INDIVIDUAL", "row_label": "a", "amounts": {}, "children": []},
            {"provision_method": "INDIVIDUAL", "row_label": "b", "amounts": {}, "children": []},
        ]
    }
    errors = await svc.deserialize(uuid.uuid4(), payload)
    assert any("重复" in e for e in errors)


@pytest.mark.asyncio
async def test_deserialize_missing_row_label(session: AsyncSession):
    svc = NestedTableService(session)
    payload = {
        "parents": [{"provision_method": "INDIVIDUAL", "amounts": {}, "children": []}]
    }
    errors = await svc.deserialize(uuid.uuid4(), payload)
    assert any("row_label" in e for e in errors)


@pytest.mark.asyncio
async def test_deserialize_child_missing_row_label(session: AsyncSession):
    """层级断裂：子行缺 row_label。"""
    svc = NestedTableService(session)
    payload = {
        "parents": [
            {
                "provision_method": "INDIVIDUAL",
                "row_label": "父",
                "amounts": {},
                "children": [{"amounts": {"amount_n": "1.00"}}],
            }
        ]
    }
    errors = await svc.deserialize(uuid.uuid4(), payload)
    assert any("children[0]" in e and "row_label" in e for e in errors)


@pytest.mark.asyncio
async def test_deserialize_amount_out_of_precision(session: AsyncSession):
    svc = NestedTableService(session)
    payload = {
        "parents": [
            {
                "provision_method": "INDIVIDUAL",
                "row_label": "父",
                "amounts": {"amount_n": "123456789012345678.00"},  # 整数位 18 > 16
                "children": [],
            }
        ]
    }
    errors = await svc.deserialize(uuid.uuid4(), payload)
    assert any("NUMERIC(18,2)" in e for e in errors)


@pytest.mark.asyncio
async def test_deserialize_amount_unparseable(session: AsyncSession):
    svc = NestedTableService(session)
    payload = {
        "parents": [
            {
                "provision_method": "INDIVIDUAL",
                "row_label": "父",
                "amounts": {"amount_n": "abc"},
                "children": [],
            }
        ]
    }
    errors = await svc.deserialize(uuid.uuid4(), payload)
    assert any("无法解析为数值" in e for e in errors)


@pytest.mark.asyncio
async def test_deserialize_errors_do_not_write_db(session: AsyncSession):
    """校验失败时不写库：先放一个父行，传入非法 payload，原有行应保留不变。"""
    svc = NestedTableService(session)
    wp = uuid.uuid4()
    await svc.create_parent_row(
        wp, CreateParentRowDTO(provision_method=ProvisionMethod.OTHER, row_label="原有")
    )
    before = await _count_rows(session, wp)

    bad_payload = {"parents": [{"row_label": "缺方法", "amounts": {}, "children": []}]}
    errors = await svc.deserialize(wp, bad_payload)
    assert errors  # 有错误

    after = await _count_rows(session, wp)
    assert after == before  # 未写库、未清空
