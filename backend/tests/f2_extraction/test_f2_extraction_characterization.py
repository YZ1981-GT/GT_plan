"""F2 存货审定表预填行为基线（**新口径：按科目名称归类 + 叶子聚合**）。

═══════════════════════════════════════════════════════════════════════════════
本文件为什么改了断言
═══════════════════════════════════════════════════════════════════════════════

改造前本文件锁定的是「按科目编码写死 + 取最深层级」的旧行为。该行为经实证是**错的**：

1. **编码写死必错** —— `account_chart` `source='standard'` 实测库内并存两个互不兼容的
   标准存货科目表变体，`1405`/`1406`/`1407`/`1408`/`1411`/`1416`/`1461` 的
   名称↔编码对应完全冲突（同一个 `1406` 一半项目是「库存商品」、另一半是「发出商品」）。
   旧断言 `1401 → raw-materials`（原材料）在两个变体下都不成立 ——
   `1401` 两版都是「材料采购」，全库期末合计 0.00。
2. **取最深层级会丢叶子** —— 客户科目树参差时 `max(by_depth)` 只保留最深那一层，
   与 K1 已修的同款 bug。现委托共享件 `four_table.select_leaves`（严格点号边界）。

故本文件改为锁定**新口径**，并新增两条**旧实现必然失败**的断言（参差树 / 两变体），
使基线本身能防回退。

spec: .kiro/specs/f2-inventory-account-mapping-and-linkage/ (Task 2.1)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.routers.wp_render_strategies._f2_inventory_main import (
    F2_CATEGORIES,
    _build_adjudication_prefill,
    build_category_prefill,
)
from app.services.f2_extraction.category_rules import F2_CATEGORY_DEFAULT

PROJECT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
WP_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
YEAR = 2025

metadata = sa.MetaData()

#: 与 `_fetch_f2_inventory_leaves` 实际 SELECT 的列对齐（`to_leaf_rows` 需要全部这些列）
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
    sa.Column("debit_amount", sa.Numeric(20, 2), nullable=True),
    sa.Column("credit_amount", sa.Numeric(20, 2), nullable=True),
    sa.Column("closing_direction", sa.String, nullable=True),
    sa.Column("is_deleted", sa.Boolean, default=False),
    sa.Column("dataset_id", sa.String, nullable=True),
)


def _insert_rows(conn: sa.Connection, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        row.setdefault("id", str(uuid.uuid4()))
        row.setdefault("project_id", str(PROJECT_ID))
        row.setdefault("year", YEAR)
        row.setdefault("is_deleted", False)
        row.setdefault("dataset_id", None)
        row.setdefault("level", None)
        row.setdefault("account_name", None)
        row.setdefault("debit_amount", None)
        row.setdefault("credit_amount", None)
        row.setdefault("closing_direction", "debit")
    conn.execute(tb_balance_table.insert(), rows)
    conn.commit()


@pytest.fixture()
def sync_engine():
    engine = create_engine("sqlite:///:memory:")
    metadata.create_all(engine)
    yield engine
    engine.dispose()


def _make_ctx(sync_engine) -> Any:
    """构造 RenderContext 替身。

    `_fetch_inventory_chart_names` / `build_inventory_accounts` 用的是 Postgres 正则
    `~`，在 SQLite 上会抛 → 被 fail-open 捕获返回 `{}` / `[]`。
    这正是「客户科目表取不到时只靠叶子自身名归类」的路径，本文件即测该路径。
    """

    @dataclass
    class FakeCtx:
        db: Any
        project_id: uuid.UUID = PROJECT_ID
        wp_id: uuid.UUID = WP_ID
        year: int = YEAR

    session = Session(sync_engine)

    async def fake_execute(stmt):
        return session.execute(stmt)

    db_mock = AsyncMock()
    db_mock.execute = fake_execute
    return FakeCtx(db=db_mock), session


def _patch_active_filter(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.wp_render_strategies._f2_inventory_main.get_active_filter",
        AsyncMock(return_value=sa.literal(True)),
    )


# ══════════════════════ 单层科目：按名称归类 ══════════════════════


@pytest.mark.asyncio
async def test_prefill_single_level_accounts_by_name(sync_engine, monkeypatch):
    """单层科目直取，且 rowKey 由**科目名称**决定（不是编码）。"""
    with sync_engine.connect() as conn:
        _insert_rows(conn, [
            {"account_code": "1403", "account_name": "原材料",
             "opening_balance": Decimal("100.00"), "closing_balance": Decimal("200.00")},
            {"account_code": "1401", "account_name": "材料采购",
             "opening_balance": Decimal("50.00"), "closing_balance": Decimal("80.00")},
            {"account_code": "1416", "account_name": "存货跌价准备",
             "opening_balance": Decimal("-30.00"), "closing_balance": Decimal("-45.00")},
        ])

    ctx, session = _make_ctx(sync_engine)
    _patch_active_filter(monkeypatch)
    result = await _build_adjudication_prefill(ctx)

    # 🔴 1403「原材料」→ raw-materials（旧实现把 1403 当「周转材料」）
    assert result["raw-materials"] == {"opening": 100.0, "closing": 200.0}
    # 🔴 1401「材料采购」→ material-in-transit（旧实现把 1401 当「原材料」）
    assert result["material-in-transit"] == {"opening": 50.0, "closing": 80.0}
    # 备抵按名称识别并取绝对值（旧实现只认写死的 1471）
    assert result["impairment-provision"] == {"opening": 30.0, "closing": 45.0}

    session.close()


@pytest.mark.asyncio
async def test_prefill_is_code_agnostic_across_chart_variants(sync_engine, monkeypatch):
    """两个标准变体下「库存商品」都归 finished-goods —— 旧实现在变体 B 上必错。

    变体 A：`1406` = 库存商品；变体 B：`1405` = 库存商品、`1406` = 发出商品。
    这里用**变体 B** 的编码，旧实现（`1406 → finished-goods` 写死）会把「发出商品」
    的钱算进库存商品行。
    """
    with sync_engine.connect() as conn:
        _insert_rows(conn, [
            {"account_code": "1405", "account_name": "库存商品",
             "opening_balance": Decimal("700.00"), "closing_balance": Decimal("900.00")},
            {"account_code": "1406", "account_name": "发出商品",
             "opening_balance": Decimal("11.00"), "closing_balance": Decimal("22.00")},
        ])

    ctx, session = _make_ctx(sync_engine)
    _patch_active_filter(monkeypatch)
    result = await _build_adjudication_prefill(ctx)

    assert result["finished-goods"] == {"opening": 700.0, "closing": 900.0}
    assert result["goods-in-transit"] == {"opening": 11.0, "closing": 22.0}

    session.close()


# ══════════════════════ 叶子聚合（替代「取最深层级」） ══════════════════════


@pytest.mark.asyncio
async def test_prefill_aggregates_leaves_only(sync_engine, monkeypatch):
    """父 + 子并存时只汇总叶子（父级不重复计入）。"""
    with sync_engine.connect() as conn:
        _insert_rows(conn, [
            {"account_code": "1406", "account_name": "库存商品",
             "opening_balance": Decimal("1000.00"), "closing_balance": Decimal("2000.00")},
            {"account_code": "1406.01", "account_name": "库存商品_产成品",
             "opening_balance": Decimal("600.00"), "closing_balance": Decimal("1200.00")},
            {"account_code": "1406.02", "account_name": "库存商品_外购商品",
             "opening_balance": Decimal("400.00"), "closing_balance": Decimal("800.00")},
        ])

    ctx, session = _make_ctx(sync_engine)
    _patch_active_filter(monkeypatch)
    result = await _build_adjudication_prefill(ctx)

    # 叶子 = .01 + .02，父级 1406 被排除 → 600+400 / 1200+800
    assert result["finished-goods"] == {"opening": 1000.0, "closing": 2000.0}

    session.close()


@pytest.mark.asyncio
async def test_prefill_ragged_tree_keeps_shallow_leaf(sync_engine, monkeypatch):
    """🔴 参差科目树：旧实现 `max(by_depth)` 会整段丢掉浅层叶子，新实现不会。

    `1406.01`（二级，**自身就是叶子**）与 `1406.02.01`（三级叶子）并存时：
    - 旧行为：只取深度 3 → 只剩 300，丢掉 1000；
    - 新行为：两个叶子都算 → 1300，且等于父级 `1406` 期末（勾稽成立）。
    """
    with sync_engine.connect() as conn:
        _insert_rows(conn, [
            {"account_code": "1406", "account_name": "库存商品",
             "opening_balance": Decimal("0.00"), "closing_balance": Decimal("1300.00")},
            {"account_code": "1406.01", "account_name": "库存商品_产成品",
             "opening_balance": Decimal("0.00"), "closing_balance": Decimal("1000.00")},
            {"account_code": "1406.02", "account_name": "库存商品_外购商品",
             "opening_balance": Decimal("0.00"), "closing_balance": Decimal("300.00")},
            {"account_code": "1406.02.01", "account_name": "库存商品_外购商品_甲",
             "opening_balance": Decimal("0.00"), "closing_balance": Decimal("300.00")},
        ])

    ctx, session = _make_ctx(sync_engine)
    _patch_active_filter(monkeypatch)
    result = await _build_adjudication_prefill(ctx)

    assert result["finished-goods"]["closing"] == 1300.0, (
        "参差树下浅层叶子 1406.01 被丢了 —— 说明又回到了「取最深层级」"
    )

    session.close()


# ══════════════════════ 跳过 / 降级 / 结构 ══════════════════════


@pytest.mark.asyncio
async def test_prefill_skips_zero_rows(sync_engine, monkeypatch):
    with sync_engine.connect() as conn:
        _insert_rows(conn, [
            {"account_code": "1409", "account_name": "周转材料",
             "opening_balance": Decimal("0.00"), "closing_balance": Decimal("0.00")},
            {"account_code": "1403", "account_name": "原材料",
             "opening_balance": Decimal("10.00"), "closing_balance": Decimal("20.00")},
        ])

    ctx, session = _make_ctx(sync_engine)
    _patch_active_filter(monkeypatch)
    result = await _build_adjudication_prefill(ctx)

    assert "revolving-materials" not in result
    assert "raw-materials" in result

    session.close()


@pytest.mark.asyncio
async def test_prefill_impairment_abs(sync_engine, monkeypatch):
    """备抵贷方（负余额）→ 取绝对值（两种符号约定同解）。"""
    with sync_engine.connect() as conn:
        _insert_rows(conn, [
            {"account_code": "1416", "account_name": "存货跌价准备",
             "opening_balance": Decimal("-500.00"), "closing_balance": Decimal("-800.00"),
             "closing_direction": "credit"},
        ])

    ctx, session = _make_ctx(sync_engine)
    _patch_active_filter(monkeypatch)
    result = await _build_adjudication_prefill(ctx)

    assert result["impairment-provision"] == {"opening": 500.0, "closing": 800.0}

    session.close()


@pytest.mark.asyncio
async def test_prefill_empty_tb_balance(sync_engine, monkeypatch):
    ctx, session = _make_ctx(sync_engine)
    _patch_active_filter(monkeypatch)
    assert await _build_adjudication_prefill(ctx) == {}
    session.close()


@pytest.mark.asyncio
async def test_prefill_query_failure_graceful(monkeypatch):
    """查询异常 → 返回空 dict 不抛（fail-open）。"""
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

    assert await _build_adjudication_prefill(FakeCtx(db=AsyncMock())) == {}


@pytest.mark.asyncio
async def test_output_structure(sync_engine, monkeypatch):
    """结构 = `{rowKey: {opening: float, closing: float}}`，rowKey ∈ 分类闭集 ∪ {other}。"""
    with sync_engine.connect() as conn:
        _insert_rows(conn, [
            {"account_code": "1403", "account_name": "原材料",
             "opening_balance": Decimal("100.00"), "closing_balance": Decimal("200.00")},
            {"account_code": "1406", "account_name": "库存商品",
             "opening_balance": Decimal("300.00"), "closing_balance": Decimal("400.00")},
            {"account_code": "1416", "account_name": "存货跌价准备",
             "opening_balance": Decimal("-50.00"), "closing_balance": Decimal("-60.00")},
        ])

    ctx, session = _make_ctx(sync_engine)
    _patch_active_filter(monkeypatch)
    result = await _build_adjudication_prefill(ctx)

    valid = {cat["rowKey"] for cat in F2_CATEGORIES} | {F2_CATEGORY_DEFAULT}
    assert isinstance(result, dict)
    for row_key, values in result.items():
        assert row_key in valid, f"unexpected rowKey: {row_key}"
        assert set(values) == {"opening", "closing"}
        assert isinstance(values["opening"], (int, float))
        assert isinstance(values["closing"], (int, float))

    session.close()


# ══════════════════════ 纯函数层（Property 1：不重不漏） ══════════════════════


class _Leaf:
    """`LeafRow` 替身（只用到本函数读的字段）。"""

    def __init__(self, code: str, name: str, opening: float, closing: float) -> None:
        self.account_code = code
        self.account_name = name
        self.opening = opening
        self.closing = closing


def test_build_category_prefill_partitions_totals():
    leaves = [
        _Leaf("1403", "原材料", 1.0, 10.0),
        _Leaf("1406.01", "库存商品_产成品", 2.0, 20.0),
        _Leaf("1409", "周转材料", 3.0, 30.0),
        _Leaf("1405.03", "修复件", 4.0, 40.0),  # 无父级名 → other
    ]
    out = build_category_prefill(leaves)
    assert round(sum(v["closing"] for v in out.values()), 2) == 100.0
    assert out[F2_CATEGORY_DEFAULT]["closing"] == 40.0


def test_build_category_prefill_uses_parent_name_fallback():
    leaves = [_Leaf("1405.03", "修复件", 0.0, 40.0)]
    out = build_category_prefill(leaves, {"1405": "自制半成品"})
    assert out == {"semi-finished": {"opening": 0.0, "closing": 40.0}}


def test_build_category_prefill_ignores_non_inventory_codes():
    """非 14xx 科目不得进桶（`1401~1499` 区间口径 = 报表行 BS-010）。"""
    leaves = [
        _Leaf("1406", "库存商品", 0.0, 5.0),
        _Leaf("1122", "应收账款", 0.0, 999.0),
        _Leaf("1501", "债权投资", 0.0, 888.0),
    ]
    out = build_category_prefill(leaves)
    assert out == {"finished-goods": {"opening": 0.0, "closing": 5.0}}
