"""F2 存货审定表预填 characterization 测试 — Property 14 零回归基线

锁定灰度关时旧 `_build_adjudication_prefill` 对 tb_balance 数据的输出：
- 各类别行的 opening/closing
- 深度启发式选层
- 跌价准备 1471 取绝对值
- 全零跳过
- 异常降级返空 dict

使用 SQLite 内存数据库模拟 tb_balance 表结构，通过 monkeypatch
替换 get_active_filter 返回 sa.literal(True)，隔离 dataset 逻辑。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Session

# ─── 被测模块 ─────────────────────────────────────────────────────────────
from app.routers.wp_render_strategies._f2_inventory_main import (
    F2_CATEGORIES,
    _build_adjudication_prefill,
)

# ─── 常量 ──────────────────────────────────────────────────────────────────
PROJECT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
WP_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
YEAR = 2025


# ─── SQLite 内存 tb_balance 表 ─────────────────────────────────────────────

metadata = sa.MetaData()

# 只建测试需要的最小列集（与 _build_adjudication_prefill 实际 SELECT 的列对齐）
tb_balance_table = sa.Table(
    "tb_balance",
    metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("project_id", sa.String, nullable=False),
    sa.Column("year", sa.Integer, nullable=False),
    sa.Column("account_code", sa.String, nullable=False),
    sa.Column("account_name", sa.String, nullable=True),
    sa.Column("level", sa.Integer, nullable=True),
    sa.Column("opening_balance", sa.Numeric(20, 2), nullable=True),
    sa.Column("closing_balance", sa.Numeric(20, 2), nullable=True),
    sa.Column("is_deleted", sa.Boolean, default=False),
    sa.Column("dataset_id", sa.String, nullable=True),
)


def _insert_rows(conn: sa.Connection, rows: list[dict[str, Any]]) -> None:
    """往 SQLite 内存 tb_balance 插入测试行"""
    for row in rows:
        row.setdefault("id", str(uuid.uuid4()))
        row.setdefault("project_id", str(PROJECT_ID))
        row.setdefault("year", YEAR)
        row.setdefault("is_deleted", False)
        row.setdefault("dataset_id", None)
        row.setdefault("level", None)
        row.setdefault("account_name", None)
    conn.execute(tb_balance_table.insert(), rows)
    conn.commit()


# ─── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture()
def sync_engine():
    """SQLite 内存同步引擎，每测试一份"""
    engine = create_engine("sqlite:///:memory:")
    metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def populated_engine(sync_engine):
    """供子测试填充数据后返回的引擎"""
    return sync_engine


def _make_ctx(sync_engine) -> Any:
    """构造 RenderContext mock，db 为同步 Session 包装

    _build_adjudication_prefill 内部:
      1. await get_active_filter(ctx.db, TbBalance.__table__, ctx.project_id, ctx.year)
      2. await ctx.db.execute(select(...).where(filter))
      3. result.fetchall()

    我们把 ctx.db.execute 替换为同步执行 SQLite 查询的 AsyncMock。
    """

    @dataclass
    class FakeCtx:
        db: Any
        project_id: uuid.UUID = PROJECT_ID
        wp_id: uuid.UUID = WP_ID
        year: int = YEAR

    session = Session(sync_engine)

    async def fake_execute(stmt):
        """同步执行 stmt 于 SQLite，返回包含 fetchall 的结果代理"""
        result = session.execute(stmt)
        return result

    db_mock = AsyncMock()
    db_mock.execute = fake_execute

    ctx = FakeCtx(db=db_mock)
    return ctx, session


# ─── Tests ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_prefill_single_level_accounts(sync_engine, monkeypatch):
    """单层科目（1401/1402/1471 各一行，无子科目）→ 直取"""
    with sync_engine.connect() as conn:
        _insert_rows(conn, [
            {"account_code": "1401", "opening_balance": Decimal("100.00"), "closing_balance": Decimal("200.00"), "level": 1},
            {"account_code": "1402", "opening_balance": Decimal("50.00"), "closing_balance": Decimal("80.00"), "level": 1},
            {"account_code": "1471", "opening_balance": Decimal("-30.00"), "closing_balance": Decimal("-45.00"), "level": 1},
        ])

    ctx, session = _make_ctx(sync_engine)

    # monkeypatch get_active_filter 返回 sa.literal(True)（绕过 dataset 逻辑）
    monkeypatch.setattr(
        "app.routers.wp_render_strategies._f2_inventory_main.get_active_filter",
        AsyncMock(return_value=sa.literal(True)),
    )

    result = await _build_adjudication_prefill(ctx)

    # 1401 → raw-materials
    assert result["raw-materials"] == {"opening": 100.0, "closing": 200.0}
    # 1402 → material-in-transit
    assert result["material-in-transit"] == {"opening": 50.0, "closing": 80.0}
    # 1471 跌价准备取绝对值
    assert result["impairment-provision"] == {"opening": 30.0, "closing": 45.0}

    session.close()


@pytest.mark.asyncio
async def test_prefill_multi_level_picks_deepest(sync_engine, monkeypatch):
    """多层级科目（1406 父 + 1406.01/1406.02 子）→ 只取最深层"""
    with sync_engine.connect() as conn:
        _insert_rows(conn, [
            # 父级 level=1
            {"account_code": "1406", "opening_balance": Decimal("1000.00"), "closing_balance": Decimal("2000.00"), "level": 1},
            # 子级 level=2（应被选中）
            {"account_code": "1406.01", "opening_balance": Decimal("600.00"), "closing_balance": Decimal("1200.00"), "level": 2},
            {"account_code": "1406.02", "opening_balance": Decimal("400.00"), "closing_balance": Decimal("800.00"), "level": 2},
        ])

    ctx, session = _make_ctx(sync_engine)
    monkeypatch.setattr(
        "app.routers.wp_render_strategies._f2_inventory_main.get_active_filter",
        AsyncMock(return_value=sa.literal(True)),
    )

    result = await _build_adjudication_prefill(ctx)

    # 深度启发式：优先最深层 level=2，600+400=1000, 1200+800=2000
    assert result["finished-goods"] == {"opening": 1000.0, "closing": 2000.0}

    session.close()


@pytest.mark.asyncio
async def test_prefill_skips_zero_rows(sync_engine, monkeypatch):
    """全零科目跳过"""
    with sync_engine.connect() as conn:
        _insert_rows(conn, [
            {"account_code": "1403", "opening_balance": Decimal("0.00"), "closing_balance": Decimal("0.00"), "level": 1},
            # 加一个有值的确保函数不整体返空
            {"account_code": "1401", "opening_balance": Decimal("10.00"), "closing_balance": Decimal("20.00"), "level": 1},
        ])

    ctx, session = _make_ctx(sync_engine)
    monkeypatch.setattr(
        "app.routers.wp_render_strategies._f2_inventory_main.get_active_filter",
        AsyncMock(return_value=sa.literal(True)),
    )

    result = await _build_adjudication_prefill(ctx)

    # 1403 周转材料 全零 → 跳过
    assert "revolving-materials" not in result
    # 1401 有值 → 存在
    assert "raw-materials" in result

    session.close()


@pytest.mark.asyncio
async def test_prefill_impairment_abs(sync_engine, monkeypatch):
    """跌价 1471 贷方（负余额）→ abs"""
    with sync_engine.connect() as conn:
        _insert_rows(conn, [
            # 备抵科目贷方余额存为负数
            {"account_code": "1471", "opening_balance": Decimal("-500.00"), "closing_balance": Decimal("-800.00"), "level": 1},
        ])

    ctx, session = _make_ctx(sync_engine)
    monkeypatch.setattr(
        "app.routers.wp_render_strategies._f2_inventory_main.get_active_filter",
        AsyncMock(return_value=sa.literal(True)),
    )

    result = await _build_adjudication_prefill(ctx)

    assert result["impairment-provision"] == {"opening": 500.0, "closing": 800.0}

    session.close()


@pytest.mark.asyncio
async def test_prefill_empty_tb_balance(sync_engine, monkeypatch):
    """无数据 → 返回空 dict"""
    # 不插入任何数据
    ctx, session = _make_ctx(sync_engine)
    monkeypatch.setattr(
        "app.routers.wp_render_strategies._f2_inventory_main.get_active_filter",
        AsyncMock(return_value=sa.literal(True)),
    )

    result = await _build_adjudication_prefill(ctx)

    assert result == {}

    session.close()


@pytest.mark.asyncio
async def test_prefill_query_failure_graceful(monkeypatch):
    """查询异常 → 返回空 dict 不抛"""
    # 让 get_active_filter 直接抛异常模拟 DB 不可用
    monkeypatch.setattr(
        "app.routers.wp_render_strategies._f2_inventory_main.get_active_filter",
        AsyncMock(side_effect=RuntimeError("DB connection lost")),
    )

    @dataclass
    class FakeCtx:
        db: Any = None
        project_id: uuid.UUID = PROJECT_ID
        wp_id: uuid.UUID = WP_ID
        year: int = YEAR

    ctx = FakeCtx(db=AsyncMock())

    result = await _build_adjudication_prefill(ctx)

    # 异常时优雅降级返回空 dict
    assert result == {}


@pytest.mark.asyncio
async def test_output_structure(sync_engine, monkeypatch):
    """返回值结构 = {str: {opening: float, closing: float}}，rowKey ∈ F2_CATEGORIES[].rowKey"""
    with sync_engine.connect() as conn:
        _insert_rows(conn, [
            {"account_code": "1401", "opening_balance": Decimal("100.00"), "closing_balance": Decimal("200.00"), "level": 1},
            {"account_code": "1406", "opening_balance": Decimal("300.00"), "closing_balance": Decimal("400.00"), "level": 1},
            {"account_code": "1471", "opening_balance": Decimal("-50.00"), "closing_balance": Decimal("-60.00"), "level": 1},
        ])

    ctx, session = _make_ctx(sync_engine)
    monkeypatch.setattr(
        "app.routers.wp_render_strategies._f2_inventory_main.get_active_filter",
        AsyncMock(return_value=sa.literal(True)),
    )

    result = await _build_adjudication_prefill(ctx)

    # 合法 rowKey 集合
    valid_row_keys = {cat["rowKey"] for cat in F2_CATEGORIES}

    assert isinstance(result, dict)
    for row_key, values in result.items():
        # rowKey 必须在 F2_CATEGORIES 定义范围内
        assert row_key in valid_row_keys, f"unexpected rowKey: {row_key}"
        # values 结构
        assert isinstance(values, dict)
        assert "opening" in values
        assert "closing" in values
        assert isinstance(values["opening"], (int, float))
        assert isinstance(values["closing"], (int, float))

    session.close()
