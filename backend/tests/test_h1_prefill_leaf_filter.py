"""H1 固定资产 render 预填 — 叶子过滤 / 发生额归一 守卫测试.

背景（真实数据实证）：tb_balance 同时存父级 1601 与子科目 1601.01…，
原实现 `code.startswith(prefix)` 会父子双算一倍，且父级 1601「固定资产」
名称无分类信号 → 全额落入「其他设备」。
"""
from __future__ import annotations

import types

import pytest

from app.routers.wp_render_strategies._h1_fixed_assets import (
    _build_category_prefill,
    _classify_fa_category,
    _leaf_codes,
)


class _FakeRow:
    def __init__(self, code, name, opening=0, closing=0, debit=0, credit=0):
        self.account_code = code
        self.account_name = name
        self.opening_balance = opening
        self.closing_balance = closing
        self.debit_amount = debit
        self.credit_amount = credit


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeDb:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, *_args, **_kwargs):
        return _FakeResult(self._rows)


def _ctx(rows):
    return types.SimpleNamespace(db=_FakeDb(rows), project_id="p1", year=2025, wp_id="wp1")


def test_leaf_codes_excludes_parents():
    codes = {"1601", "1601.01", "1601.02", "1602", "1602.01"}
    assert _leaf_codes(codes) == {"1601.01", "1601.02", "1602.01"}


def test_leaf_codes_keeps_single_level_account():
    """账套只有一级科目（无子科目）时该科目本身即叶子，不能被过滤掉。"""
    assert _leaf_codes({"1601", "1602"}) == {"1601", "1602"}


@pytest.mark.asyncio
async def test_prefill_does_not_double_count_parent_and_children(monkeypatch):
    async def _fake_filter(*_a, **_k):
        return True

    monkeypatch.setattr(
        "app.routers.wp_render_strategies._h1_fixed_assets.get_active_filter",
        _fake_filter,
    )
    rows = [
        _FakeRow("1601", "固定资产", 100, 300),          # 父级：应被跳过
        _FakeRow("1601.01", "固定资产_房屋建筑物", 60, 200),
        _FakeRow("1601.02", "固定资产_机器设备", 40, 100),
    ]
    payload = await _build_category_prefill(_ctx(rows))
    # 合计只等于子科目之和（300），而不是父+子 = 600
    assert payload["totals"]["cost1601"] == pytest.approx(300.0)
    by_cat = {c["category"]: c for c in payload["categories"]}
    assert by_cat["房屋及建筑物"]["cost"]["unadjusted"] == pytest.approx(200.0)
    assert by_cat["机器设备"]["cost"]["unadjusted"] == pytest.approx(100.0)
    # 父级「固定资产」不再被兜底塞进「其他设备」
    assert by_cat["其他设备"]["cost"]["unadjusted"] == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_prefill_normalizes_signed_movement_amounts(monkeypatch):
    """贷方类账套可能把发生额存负数；前端按正数发生额算备抵期末，需归一。"""
    async def _fake_filter(*_a, **_k):
        return True

    monkeypatch.setattr(
        "app.routers.wp_render_strategies._h1_fixed_assets.get_active_filter",
        _fake_filter,
    )
    rows = [
        _FakeRow("1602.01", "累计折旧_房屋建筑物", -100, -180, debit=-20, credit=-100),
    ]
    payload = await _build_category_prefill(_ctx(rows))
    dep = {c["category"]: c for c in payload["categories"]}["房屋及建筑物"]["dep"]
    assert dep["begin"] == pytest.approx(100.0)
    assert dep["end"] == pytest.approx(180.0)
    assert dep["debit"] == pytest.approx(20.0)
    assert dep["credit"] == pytest.approx(100.0)
    # 备抵：期末 = 期初 − 借 + 贷 = 100 − 20 + 100 = 180，与 end 自洽
    assert dep["begin"] - dep["debit"] + dep["credit"] == pytest.approx(dep["end"])


def test_classify_parent_account_still_falls_back():
    """一级科目单独存在时仍走兜底分类（由审计师复核），行为不变。"""
    assert _classify_fa_category("1601", "固定资产") == "其他设备"
    assert _classify_fa_category("1601.01", "固定资产_房屋建筑物") == "房屋及建筑物"
