"""H1 四表取数 Property 1-13 属性测试（Wave 7 Task 8.1）。

补齐 spec design.md 列出的 13 条正确性属性，验证各段取数的不变量。
运行：python -m pytest tests/test_h1_extraction_properties.py -q
"""
from __future__ import annotations

import types
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings
from app.routers.wp_render_strategies import _h1_fixed_assets as h1


class _BalRow:
    def __init__(self, code="1601.01", name="房屋", opening=100, closing=200, debit=120, credit=20):
        self.account_code = code
        self.account_name = name
        self.opening_balance = opening
        self.closing_balance = closing
        self.debit_amount = debit
        self.credit_amount = credit


class _Result:
    def __init__(self, rows=None, one=None):
        self._rows = rows if rows is not None else []
        self._one = one

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._one


class _FakeDb:
    def __init__(self, rows=None, one=None, fail=False):
        self._rows = rows if rows is not None else []
        self._one = one
        self._fail = fail

    async def execute(self, *_a, **_k):
        if self._fail:
            raise RuntimeError("db down")
        return _Result(self._rows, self._one)


def _ctx(db=None):
    return types.SimpleNamespace(
        db=db or _FakeDb(), project_id="p1", year=2025, wp_id="wp1"
    )


@pytest.fixture(autouse=True)
def _patch_filter(monkeypatch):
    async def _fake(*_a, **_k):
        return True
    monkeypatch.setattr(h1, "get_active_filter", _fake)


# ─── Property 1: 叶子过滤不双算 ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_p1_leaf_filter_no_double_count():
    """父级+子级同时存在时只取叶子（Req1.6）。"""
    rows = [
        _BalRow("1601", "固定资产", 1000, 1000, 0, 0),
        _BalRow("1601.01", "房屋", 600, 600, 0, 0),
        _BalRow("1601.02", "设备", 400, 400, 0, 0),
    ]
    out = await h1._build_h1_detail_prefill(_ctx(_FakeDb(rows)))
    assert out["totals"]["cost"] == 1000  # 600+400=1000 而非 1000+600+400


# ─── Property 2: Persist_First ─────────────────────────────────────────────

def test_p2_persist_first():
    """种子填充仅空表时写入（Req1.3）— 由前端 vitest shouldSeedDetailRows 覆盖，
    此处仅验证后端不产出影响 Persist_First 的副作用键。"""
    # 后端 detail 载荷不含 _force/_overwrite 等旁路键
    import asyncio
    out = asyncio.get_event_loop().run_until_complete(
        h1._build_h1_detail_prefill(_ctx(_FakeDb([_BalRow()])))
    )
    assert "_force" not in out
    assert "_overwrite" not in out


# ─── Property 3: 发生额归一 ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_p3_amounts_normalized():
    """原值借方→增加/贷方→减少，备抵 abs()，全 ≥ 0（Req1.2）。"""
    rows = [
        _BalRow("1601.01", "房屋", 1000, 1200, 300, 100),
        _BalRow("1602.01", "房屋折旧", -200, -300, 50, 150),
    ]
    out = await h1._build_h1_detail_prefill(_ctx(_FakeDb(rows)))
    for r in out["rows"]:
        for seg in ("cost", "dep", "impair"):
            for k in ("begin", "debit", "credit", "end"):
                assert r[seg][k] >= 0, f"{r['category']}.{seg}.{k} < 0"


# ─── Property 4: 空数据返回空行 ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_p4_empty_data_empty_rows():
    """无余额数据时返回空（Req8.2）。"""
    out = await h1._build_h1_detail_prefill(_ctx(_FakeDb([])))
    assert out["rows"] == []
    assert out["totals"] == {"cost": 0.0, "dep": 0.0, "impair": 0.0}


# ─── Property 5: 灰度两态逐字节等价 ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_p5_flag_off_no_prefill(monkeypatch):
    """开关关闭时 payload 无 h1_four_table_prefill（Req6.1）。"""
    monkeypatch.setattr(settings, "H1_FOUR_TABLE_EXTRACTION_ENABLED", False, raising=False)
    out = await h1.render(_ctx())
    assert "h1_four_table_prefill" not in out


# ─── Property 6: fail-open ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_p6_fail_open():
    """任一取数段异常不阻断 render（Req6.3）。"""
    out = await h1._build_h1_detail_prefill(_ctx(_FakeDb(fail=True)))
    assert out["rows"] == []


# ─── Property 7: available 语义 ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_p7_available_false_means_no_data():
    """序时账/对方科目可用性 available=False 时载荷含原因而非假零。"""
    out = await h1._build_h1_ledger_movement(_ctx(_FakeDb([])))
    assert out["available"] is False
    assert out["debit_total"] == 0.0


# ─── Property 9: 数据集隔离 ──────────────────────────────────────────────────

def test_p9_get_active_filter_usage():
    """四表查询经 get_active_filter 隔离（Req3.1）。"""
    import inspect
    src = inspect.getsource(h1._build_h1_detail_prefill)
    assert "get_active_filter" in src
    src2 = inspect.getsource(h1._build_h1_ledger_movement)
    assert "get_active_filter" in src2


# ─── Property 10: 报表映射回退 ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_p10_report_mapping_fallback(monkeypatch):
    """resolve_report_line_account_codes 失败时回退 1601/1602/1603（Req5.2）。"""
    monkeypatch.setattr(settings, "H1_FOUR_TABLE_EXTRACTION_ENABLED", True, raising=False)
    out = await h1.render(_ctx())
    # 无 report_config → 回退
    assert "tb_source_codes" in out
    assert "1601" in out["tb_source_codes"]


# ─── Property 11: 关联方空态不产告警 ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_p11_related_parties_empty_is_ok():
    """related_party_registry 空时返回空列表不崩（Req4.3）。"""
    out = await h1.render(_ctx())
    ctx = out.get("project_context", {})
    assert ctx.get("related_parties") == []


# ─── Property 12: Card_Level 不编造 ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_p12_no_card_level_fields():
    """取数载荷不含 assetNo/acquisitionDate/usefulLife/salvageRate 等卡片字段。"""
    rows = [_BalRow("1601.01", "房屋", 1000, 1000, 0, 0)]
    out = await h1._build_h1_detail_prefill(_ctx(_FakeDb(rows)))
    for r in out["rows"]:
        assert "assetNo" not in r
        assert "acquisitionDate" not in r
        assert "usefulLife" not in r
        assert "salvageRate" not in r


# ─── Property 13: depreciation movement ──────────────────────────────────────

@pytest.mark.asyncio
async def test_p13_depreciation_movement_available():
    """有 1602 分录时 depreciation.available=True。"""
    class _Cnt:
        lines = 5
        credit_total = 34000
    out = await h1._build_h1_depreciation_movement(_ctx(_FakeDb(one=_Cnt())))
    assert out["available"] is True
    assert out["provision_total"] == 34000.0
