"""G7-1 审定表 TB 取数：叶子聚合 + fail-open。

**2026-08-01 改写**：原文件测的是已删除的自造实现
（`_is_leaf` / `_sum_leaf_by_prefix` / `_fetch_tb_values`）。旧实现的前缀判定
`code.startswith(prefix)` 缺点号边界（`1511` 会误命中 `15110`），科目前缀也硬编码，
现已换成 `four_table` 共享件 + `G7_ACCOUNT_SPEC` 报表映射解析。

断言意图逐条保留：父子共存只算叶子 / 备抵独立汇总 / 键名向后兼容 / 无匹配返 {} /
异常 fail-open。新增：备抵负值 abs 归一、点号边界。

真实数据背景（postgres 实证，项目 `2aa00f57`）：`tb_balance` 同时存父级 `1511`
与子级 `1511.01` / `1511.03`，父子同时累加会虚增；`1512` 期末为
**−4,790,032.97**（负值存储 + credit 方向）。
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.routers.wp_render_strategies import _g7_long_term_equity_main as g7
from app.services.four_table.leaf_aggregation import LeafRow
from app.services.four_table.report_line_accounts import (
    RESOLVED_FROM_REPORT,
    ReportLineAccounts,
)


def _accounts(gross=("1511",), provision=("1512",)) -> ReportLineAccounts:
    return ReportLineAccounts(
        gross=list(gross),
        provision=list(provision),
        gross_standard=list(gross),
        provision_standard=list(provision),
        row_code="BS-024",
        resolved_from=RESOLVED_FROM_REPORT,
    )


def _leaf(code, opening=0.0, closing=0.0, name="", debit=0.0, credit=0.0) -> LeafRow:
    return LeafRow(
        account_code=code,
        account_name=name,
        opening=opening,
        closing=closing,
        debit=debit,
        credit=credit,
    )


# ---------------------------------------------------------------------------
# 1) build_g7_tb_values —— 纯函数
# ---------------------------------------------------------------------------


def test_tb_values_only_sums_leaves():
    """父子共存时只算叶子：父 1511=100 / 子 60+40 → closing=100（非 200）。

    入参 `leaves` 已由 `select_leaves` 过滤，这里直接给叶子集验证聚合口径。
    """
    all_rows = [_leaf("1511", 10.0, 100.0), _leaf("1511.01", 6.0, 60.0), _leaf("1511.02", 4.0, 40.0)]
    leaves = [_leaf("1511.01", 6.0, 60.0), _leaf("1511.02", 4.0, 40.0)]
    tb = g7.build_g7_tb_values(_accounts(), all_rows, leaves)
    assert tb["closing"] == pytest.approx(100.0)
    assert tb["opening"] == pytest.approx(10.0)
    assert tb["source_codes"]["gross"] == ["1511.01", "1511.02"]


def test_tb_values_impairment_grouped_separately():
    """1512 减值准备独立汇总进 impairment / impairment_opening。"""
    leaves = [
        _leaf("1511.01", 6.0, 60.0),
        _leaf("1512.01", 1.0, 12.0),
        _leaf("1512.02", 2.0, 8.0),
    ]
    tb = g7.build_g7_tb_values(_accounts(), leaves, leaves)
    assert tb["closing"] == pytest.approx(60.0)
    assert tb["impairment"] == pytest.approx(20.0)
    assert tb["impairment_opening"] == pytest.approx(3.0)
    assert tb["source_codes"] == {
        "gross": ["1511.01"],
        "impairment": ["1512.01", "1512.02"],
    }


def test_tb_values_provision_negative_storage_normalised():
    """🔴 备抵负值存储必须 abs 归一（活体 1512 期末 −4,790,032.97）。

    不归一会让前端「减值准备」列显负数，与审定表「二、减值准备」段的正数口径相反。
    """
    leaves = [
        _leaf("1511.01", 40459060.60, 40459060.60),
        _leaf("1512", -2840032.97, -4790032.97, name="长期股权投资减值准备"),
    ]
    tb = g7.build_g7_tb_values(_accounts(), leaves, leaves)
    assert tb["impairment_opening"] == pytest.approx(2840032.97)
    assert tb["impairment"] == pytest.approx(4790032.97)


def test_tb_values_prefix_requires_dot_boundary():
    """前缀 `1511` 不得命中 `15110`（与 `1511` 无父子关系的另一科目）。"""
    leaves = [_leaf("1511", 0.0, 100.0), _leaf("15110", 0.0, 999.0)]
    tb = g7.build_g7_tb_values(_accounts(), leaves, leaves)
    assert tb["closing"] == pytest.approx(100.0)
    assert tb["source_codes"]["gross"] == ["1511"]


def test_tb_values_keeps_legacy_keys():
    """向后兼容：原有键名与含义不变（前端 fetchTrialBalance 已在读）。"""
    leaves = [_leaf("1511", 7.0, 77.0)]
    tb = g7.build_g7_tb_values(_accounts(), leaves, leaves)
    assert set(tb) == {
        "opening",
        "closing",
        "impairment",
        "impairment_opening",
        "source_codes",
    }
    assert (tb["opening"], tb["closing"]) == (pytest.approx(7.0), pytest.approx(77.0))
    assert tb["impairment"] == pytest.approx(0.0)


def test_tb_values_no_match_returns_empty_dict():
    """无匹配科目 → 降级返回 {}（宁缺勿造，前端允许手填）。"""
    assert g7.build_g7_tb_values(_accounts(), [], []) == {}
    other = [_leaf("1601", 1.0, 2.0)]
    assert g7.build_g7_tb_values(_accounts(), other, other) == {}
    assert g7.build_g7_tb_values(None, [], []) == {}


# ---------------------------------------------------------------------------
# 2) build_g7_source_codes —— 溯源 + 两口径自检
# ---------------------------------------------------------------------------


def test_source_codes_exposes_parent_check_both_sides():
    """叶子和 == 父额时 diff=0；不等时两个数都暴露（不静默取其一）。"""
    all_rows = [_leaf("1511", 0.0, 100.0), _leaf("1511.01", 0.0, 60.0), _leaf("1511.02", 0.0, 40.0)]
    leaves = [_leaf("1511.01", 0.0, 60.0), _leaf("1511.02", 0.0, 40.0)]
    src = g7.build_g7_source_codes(_accounts(), all_rows, leaves)
    assert src["row_code"] == "BS-024"
    assert src["gross_standard"] == ["1511"]
    assert src["parent_check"] == {"leaf_sum": 100.0, "parent": 100.0, "diff": 0.0}

    bad_rows = [_leaf("1511", 0.0, 120.0), _leaf("1511.01", 0.0, 60.0)]
    bad = g7.build_g7_source_codes(_accounts(), bad_rows, [_leaf("1511.01", 0.0, 60.0)])
    assert bad["parent_check"] == {"leaf_sum": 60.0, "parent": 120.0, "diff": -60.0}


def test_source_codes_empty_without_accounts():
    assert g7.build_g7_source_codes(None, [], []) == {}


# ---------------------------------------------------------------------------
# 3) _load_g7_leaves —— fail-open（假 db + monkeypatch）
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeDb:
    """最小 async db：execute 返回可 fetchall() 的行对象列表。"""

    def __init__(self, rows, raise_exc: Exception | None = None):
        self._rows = rows
        self._raise = raise_exc
        self.calls = 0

    async def execute(self, *_args, **_kwargs):
        self.calls += 1
        if self._raise is not None:
            raise self._raise
        return _FakeResult(self._rows)


def _tb_row(code, opening, closing, name=""):
    return SimpleNamespace(
        account_code=code,
        account_name=name,
        opening_balance=opening,
        closing_balance=closing,
        debit_amount=None,
        credit_amount=None,
        closing_direction="debit",
    )


def _ctx(db):
    return SimpleNamespace(db=db, project_id=uuid4(), year=2025)


@pytest.fixture(autouse=True)
def _stub_deps(monkeypatch):
    """`get_active_filter` 要求真实 dataset；科目解析要求 report_config → 均打桩。"""

    async def _fake_filter(_db, _table, _project_id, _year):
        import sqlalchemy as sa

        return sa.true()

    async def _fake_resolve(_ctx, _spec):
        return _accounts()

    monkeypatch.setattr(g7, "get_active_filter", _fake_filter)
    monkeypatch.setattr(g7, "resolve_report_line_accounts", _fake_resolve)


@pytest.mark.asyncio
async def test_load_leaves_single_query_and_leaf_filter():
    """一次查询取回两组；父子共存时 leaves 只含叶子。"""
    db = _FakeDb(
        [
            _tb_row("1511", 10.0, 100.0),
            _tb_row("1511.01", 6.0, 60.0),
            _tb_row("1511.02", 4.0, 40.0),
        ]
    )
    accounts, all_rows, leaves = await g7._load_g7_leaves(_ctx(db))
    assert accounts is not None
    assert db.calls == 1
    assert len(all_rows) == 3
    assert {r.account_code for r in leaves} == {"1511.01", "1511.02"}


@pytest.mark.asyncio
async def test_load_leaves_fail_open_on_query_exception():
    """查询异常 fail-open：返回空行集不抛出（不阻断 render）。"""
    db = _FakeDb([], raise_exc=RuntimeError("db down"))
    accounts, all_rows, leaves = await g7._load_g7_leaves(_ctx(db))
    assert accounts is not None  # 科目已解析成功
    assert (all_rows, leaves) == ([], [])
    assert g7.build_g7_tb_values(accounts, all_rows, leaves) == {}


@pytest.mark.asyncio
async def test_load_leaves_fail_open_on_resolve_exception(monkeypatch):
    """科目解析异常 fail-open：accounts 为 None，取数键全空。"""

    async def _boom(_ctx, _spec):
        raise RuntimeError("report_config down")

    monkeypatch.setattr(g7, "resolve_report_line_accounts", _boom)
    accounts, all_rows, leaves = await g7._load_g7_leaves(_ctx(_FakeDb([])))
    assert accounts is None
    assert (all_rows, leaves) == ([], [])
    assert g7.build_g7_tb_values(accounts, all_rows, leaves) == {}
    assert g7.build_g7_adjudication_prefill(accounts, leaves) == {}
