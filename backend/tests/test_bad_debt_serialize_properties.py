# Feature: workpaper-bad-debt-nested-structure, Property 8: 序列化 Round-Trip
"""NestedTableService.serialize / deserialize 的 Round-Trip Property-Based Test。

- Property 8: 序列化 Round-Trip   (Validates Requirements 11.1, 11.2, 11.3)

策略：构造任意合法嵌套树（1~4 个父行，各带 0~3 子行，金额随机）→ 直接落库 →
serialize → deserialize 到同一底稿 → 再 serialize，断言两次 serialize 在语义上
等价（父行集合按 provision_method、子行按 row_label+金额、排序、13 金额列一致）。

DB 策略：in-process 内存 SQLite，每个 example 新建独立 engine + 仅建
bad_debt_detail_rows 表，保证 example 间完全隔离（铁律：PBT 含 DB 状态变更需隔离）。
hypothesis max_examples=5。
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.bad_debt_models import BadDebtDetailRow, ProvisionMethod
from app.services.bad_debt_auto_sum import AutoSumEngine
from app.services.bad_debt_nested_table_service import NestedTableService

_PBT = settings(
    max_examples=5,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)

_AMOUNT_COLUMNS = AutoSumEngine.AMOUNT_COLUMNS


async def _fresh_session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all, tables=[BadDebtDetailRow.__table__]
        )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return factory(), engine


# ─── 生成策略 ────────────────────────────────────────────────────────────────

st_amount = st.one_of(
    st.none(),
    st.decimals(
        min_value=Decimal("-100000.00"),
        max_value=Decimal("100000.00"),
        places=2,
        allow_nan=False,
        allow_infinity=False,
    ),
)

st_amounts_block = st.fixed_dictionaries(
    {col: st_amount for col in _AMOUNT_COLUMNS}
)

st_child = st.fixed_dictionaries(
    {
        "row_label": st.text(min_size=1, max_size=12),
        "amounts": st_amounts_block,
    }
)

# 父行：唯一 provision_method + 标签 + 0~3 子行
st_parent = st.fixed_dictionaries(
    {
        "provision_method": st.sampled_from([m.value for m in ProvisionMethod]),
        "row_label": st.text(min_size=1, max_size=12),
        "amounts": st_amounts_block,
        "children": st.lists(st_child, min_size=0, max_size=3),
    }
)


@st.composite
def st_nested_tree(draw) -> list[dict]:
    """生成 1~4 个 provision_method 互不相同的父行的嵌套树。"""
    methods = draw(
        st.lists(
            st.sampled_from([m.value for m in ProvisionMethod]),
            min_size=1,
            max_size=4,
            unique=True,
        )
    )
    parents: list[dict] = []
    for method in methods:
        parent = draw(st_parent)
        parent["provision_method"] = method
        parents.append(parent)
    return parents


def _normalize_amounts(block: dict) -> dict[str, str | None]:
    """量化两位小数后转 str（None 保持 None），用于语义等价比较。"""
    out: dict[str, str | None] = {}
    for col in _AMOUNT_COLUMNS:
        val = block.get(col)
        out[col] = None if val is None else str(Decimal(str(val)).quantize(Decimal("0.01")))
    return out


def _semantic_key(serialized: dict) -> list:
    """将 serialize 输出规约为可比较的语义结构：

    父行按 provision_method 排序，子行按 (sort_order, row_label) 排序，
    金额量化两位小数。忽略 id/created_at 等易变字段。
    """
    parents = sorted(
        serialized["parents"], key=lambda p: p["provision_method"] or ""
    )
    key = []
    for p in parents:
        children = sorted(
            p["children"], key=lambda c: (c["sort_order"], c["row_label"])
        )
        key.append(
            {
                "provision_method": p["provision_method"],
                "row_label": p["row_label"],
                "sort_order": p["sort_order"],
                "amounts": _normalize_amounts(p["amounts"]),
                "children": [
                    {
                        "row_label": c["row_label"],
                        "sort_order": c["sort_order"],
                        "amounts": _normalize_amounts(c["amounts"]),
                    }
                    for c in children
                ],
            }
        )
    return key


async def _seed_tree(session: AsyncSession, wp_index_id: uuid.UUID, tree: list[dict]) -> None:
    """将生成的 tree 直接落库（不经 service，避免父行被子行重算覆盖，保留原始金额）。"""
    for p_idx, p in enumerate(tree):
        parent = BadDebtDetailRow(
            id=uuid.uuid4(),
            wp_index_id=wp_index_id,
            parent_row_id=None,
            provision_method=p["provision_method"],
            sort_order=(p_idx + 1) * 10,
            row_label=p["row_label"],
            version=1,
        )
        for col in _AMOUNT_COLUMNS:
            setattr(parent, col, p["amounts"].get(col))
        session.add(parent)
        await session.flush()
        for c_idx, c in enumerate(p["children"]):
            child = BadDebtDetailRow(
                id=uuid.uuid4(),
                wp_index_id=wp_index_id,
                parent_row_id=parent.id,
                provision_method=None,
                sort_order=(c_idx + 1) * 10,
                row_label=c["row_label"],
                version=1,
            )
            for col in _AMOUNT_COLUMNS:
                setattr(child, col, c["amounts"].get(col))
            session.add(child)
        await session.flush()


@_PBT
@given(tree=st_nested_tree())
def test_property_8_serialize_round_trip(tree: list[dict]):
    """Property 8: 任意合法嵌套树 serialize→deserialize→serialize 语义等价。

    Validates: Requirements 11.1, 11.2, 11.3
    """

    async def _run():
        session, engine = await _fresh_session()
        try:
            svc = NestedTableService(session)
            wp_index_id = uuid.uuid4()
            await _seed_tree(session, wp_index_id, tree)

            first = await svc.serialize(wp_index_id)

            # round-trip：deserialize 到同一底稿（先清空再重建）应无错误
            errors = await svc.deserialize(wp_index_id, first)
            assert errors == [], f"deserialize 不应有错误: {errors}"

            second = await svc.serialize(wp_index_id)

            assert _semantic_key(first) == _semantic_key(second), (
                "serialize→deserialize→serialize 语义不等价"
            )
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_run())
