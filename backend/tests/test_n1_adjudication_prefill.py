"""N1 审定表未审数预填（tb_balance 1811 子科目 → 暂时性差异 7 类）守卫。

对应本会话新增 `_build_adjudication_prefill` / `_classify_n1_subaccount`
（平台铁律「X-1 审定表未审数从 tb_balance 明细子科目预填」的 N1 落地）。

正确性属性：
- Property1  子科目按名称关键字归入审定表 7 类，同类聚合期初/期末
- Property2  仅取叶子子科目（无更深层级），防与中间级双算
- Property3  仅父级 1811（无子科目 like '1811.%'）→ 返回 {}（无法按类别拆分）
- Property4  全零类别跳过；查询异常 fail-open 返回 {}
"""

from __future__ import annotations

import asyncio
import types
from unittest.mock import AsyncMock

import pytest

from app.routers.wp_render_strategies import _n1_deferred_tax_assets as n1


def _row(code: str, name: str, opening: float, closing: float):
    return types.SimpleNamespace(
        account_code=code,
        account_name=name,
        opening_balance=opening,
        closing_balance=closing,
    )


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


def _ctx(rows, *, raise_on_execute: bool = False):
    db = AsyncMock()
    if raise_on_execute:
        db.execute = AsyncMock(side_effect=RuntimeError("boom"))
    else:
        db.execute = AsyncMock(return_value=_Result(rows))
    return types.SimpleNamespace(db=db, project_id="p1", year=2025)


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _patch_active_filter(monkeypatch):
    monkeypatch.setattr(n1, "get_active_filter", AsyncMock(return_value=True))


# ─── Property1: 关键字归类 + 同类聚合 ─────────────────────────────────────────


def test_classify_keyword_mapping():
    c = n1._classify_n1_subaccount
    assert c("递延所得税资产_资产减值准备") == "资产减值准备"
    assert c("坏账准备") == "资产减值准备"
    assert c("存货跌价准备") == "资产减值准备"
    assert c("可抵扣亏损") == "可抵扣亏损"
    assert c("内部交易未实现利润") == "内部交易未实现利润"
    assert c("公允价值变动") == "公允价值变动"
    assert c("经营租赁和企业年金") == "租赁负债"
    assert c("使用权资产") == "租赁负债"
    assert c("购入摊销年限差异") == "购入摊销年限小于税法规定的资产"
    assert c("长期职工薪酬") == "其他"
    assert c("预提费用相关") == "其他"
    assert c("") == "其他"
    assert c(None) == "其他"


def test_aggregate_by_category():
    rows = [
        _row("1811.02", "递延所得税资产_资产减值准备", 7138647.65, 7200000.0),
        _row("1811.03", "递延所得税资产_长期职工薪酬", 136973.08, 140000.0),
        _row("1811.05", "递延所得税资产_预提费用相关", 10000.0, 12000.0),
        _row("1811.07", "递延所得税资产_经营租赁和企业年金", 100950.45, 100950.45),
    ]
    out = _run(n1._build_adjudication_prefill(_ctx(rows)))
    assert out["资产减值准备"] == {"opening": 7138647.65, "closing": 7200000.0}
    # 长期职工薪酬 + 预提费用相关 → 其他（同类聚合）
    assert out["其他"] == {"opening": 146973.08, "closing": 152000.0}
    assert out["租赁负债"] == {"opening": 100950.45, "closing": 100950.45}


# ─── Property2: 仅叶子（防中间级双算）───────────────────────────────────────


def test_leaf_only_excludes_intermediate():
    rows = [
        _row("1811.02", "资产减值准备", 1000.0, 1000.0),          # 中间级（有更深子科目）
        _row("1811.02.01", "应收坏账", 600.0, 600.0),             # 叶子
        _row("1811.02.02", "存货跌价", 400.0, 400.0),             # 叶子
    ]
    out = _run(n1._build_adjudication_prefill(_ctx(rows)))
    # 只算两个叶子 = 1000（不含中间级 1811.02 的 1000，避免双算）
    assert out["资产减值准备"] == {"opening": 1000.0, "closing": 1000.0}


# ─── Property3: 仅父级 1811（无子科目）→ 空 ──────────────────────────────────


def test_parent_only_returns_empty():
    # like '1811.%' 不匹配裸父级 1811 → 查询结果为空
    out = _run(n1._build_adjudication_prefill(_ctx([])))
    assert out == {}


# ─── Property4: 全零跳过 / 查询异常 fail-open ────────────────────────────────


def test_zero_category_skipped():
    rows = [
        _row("1811.02", "资产减值准备", 0.0, 0.0),
        _row("1811.04", "可抵扣亏损", 0.0, 500.0),
    ]
    out = _run(n1._build_adjudication_prefill(_ctx(rows)))
    assert "资产减值准备" not in out
    assert out["可抵扣亏损"] == {"opening": 0.0, "closing": 500.0}


def test_query_error_fails_open():
    out = _run(n1._build_adjudication_prefill(_ctx([], raise_on_execute=True)))
    assert out == {}


def test_none_balances_treated_as_zero():
    rows = [_row("1811.04", "可抵扣亏损", None, 300.0)]
    out = _run(n1._build_adjudication_prefill(_ctx(rows)))
    assert out["可抵扣亏损"] == {"opening": 0.0, "closing": 300.0}
