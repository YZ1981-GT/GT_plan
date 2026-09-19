"""H1 明细级四表取数载荷（Req1/Req2/Req6）."""
from __future__ import annotations

import types

import pytest

from app.core.config import settings
from app.routers.wp_render_strategies import _h1_fixed_assets as h1


class _BalRow:
    def __init__(self, code, name, opening=0, closing=0, debit=0, credit=0):
        self.account_code = code
        self.account_name = name
        self.opening_balance = opening
        self.closing_balance = closing
        self.debit_amount = debit
        self.credit_amount = credit


class _LedgerRow:
    def __init__(self, lines, debit_total, credit_total):
        self.lines = lines
        self.debit_total = debit_total
        self.credit_total = credit_total


class _FakeResult:
    def __init__(self, rows=None, one=None):
        self._rows = rows or []
        self._one = one

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._one


class _FakeDb:
    def __init__(self, rows=None, one=None, raise_exc=False):
        self._rows = rows
        self._one = one
        self._raise = raise_exc

    async def execute(self, *_a, **_k):
        if self._raise:
            raise RuntimeError("db down")
        return _FakeResult(self._rows, self._one)


def _ctx(db):
    return types.SimpleNamespace(db=db, project_id="p1", year=2025, wp_id="wp1", classification=None)


@pytest.fixture(autouse=True)
def _patch_filter(monkeypatch):
    async def _fake_filter(*_a, **_k):
        return True

    monkeypatch.setattr(h1, "get_active_filter", _fake_filter)


_REAL_ROWS = [
    _BalRow("1601", "固定资产", 0, 51188971.32),           # 父级 → 跳过
    _BalRow("1601.01", "固定资产_房屋建筑物", 40000000, 41049967.97, debit=1049967.97),
    _BalRow("1601.02", "固定资产_机器设备", 800000, 802866.44, debit=2866.44),
    _BalRow("1602", "累计折旧", 0, 28063493.29),            # 父级 → 跳过
    _BalRow("1602.01", "累计折旧_房屋建筑物", -18000000, -19168421.47, credit=-1168421.47),
    _BalRow("1602.02", "累计折旧_机器设备", 200000, 279527.70, credit=79527.70),
]


@pytest.mark.asyncio
async def test_detail_rows_aggregate_by_category_without_double_count():
    out = await h1._build_h1_detail_prefill(_ctx(_FakeDb(rows=_REAL_ROWS)))
    cats = [r["category"] for r in out["rows"]]
    assert cats == ["房屋及建筑物", "机器设备"]  # 按 canonical 分类顺序
    houses = out["rows"][0]
    # 同类的原值与折旧合并到一行（不拆成"折旧行原值为 0"）
    assert houses["cost"]["end"] == pytest.approx(41049967.97)
    assert houses["dep"]["end"] == pytest.approx(19168421.47)  # 负数账套归一为正
    assert houses["source_codes"] == ["1601.01", "1602.01"]
    assert "TB('1601.01','期末余额')" in houses["formula"]
    # 父级不参与 → 合计等于叶子之和，而非 2 倍
    assert out["totals"]["cost"] == pytest.approx(41049967.97 + 802866.44)
    assert out["totals"]["dep"] == pytest.approx(19168421.47 + 279527.70)


@pytest.mark.asyncio
async def test_movement_amounts_normalized_non_negative():
    out = await h1._build_h1_detail_prefill(_ctx(_FakeDb(rows=_REAL_ROWS)))
    for r in out["rows"]:
        for block in ("cost", "dep", "impair"):
            assert r[block]["debit"] >= 0
            assert r[block]["credit"] >= 0
    houses_dep = out["rows"][0]["dep"]
    # 备抵自洽：期末 = 期初 − 借 + 贷
    assert houses_dep["begin"] - houses_dep["debit"] + houses_dep["credit"] == pytest.approx(
        houses_dep["end"]
    )


@pytest.mark.asyncio
async def test_no_card_level_fields_in_payload():
    out = await h1._build_h1_detail_prefill(_ctx(_FakeDb(rows=_REAL_ROWS)))
    forbidden = {"assetNo", "asset_no", "acquisitionDate", "acquisition_date",
                 "usefulLife", "useful_life", "salvageRate", "salvage_rate", "location"}
    for r in out["rows"]:
        assert not (set(r.keys()) & forbidden)


@pytest.mark.asyncio
async def test_empty_balance_yields_no_rows():
    out = await h1._build_h1_detail_prefill(_ctx(_FakeDb(rows=[])))
    assert out["rows"] == []
    assert out["totals"] == {"cost": 0.0, "dep": 0.0, "impair": 0.0}


@pytest.mark.asyncio
async def test_detail_prefill_fail_open():
    out = await h1._build_h1_detail_prefill(_ctx(_FakeDb(raise_exc=True)))
    assert out["rows"] == []


@pytest.mark.asyncio
async def test_ledger_movement_available_and_absent():
    ok = await h1._build_h1_ledger_movement(_ctx(_FakeDb(one=_LedgerRow(12, 1000, -300))))
    assert ok["available"] is True
    assert ok["debit_total"] == pytest.approx(1000)
    assert ok["credit_total"] == pytest.approx(300)  # 归一非负

    none = await h1._build_h1_ledger_movement(_ctx(_FakeDb(one=_LedgerRow(0, 0, 0))))
    assert none["available"] is False

    err = await h1._build_h1_ledger_movement(_ctx(_FakeDb(raise_exc=True)))
    assert err["available"] is False


@pytest.mark.asyncio
async def test_render_includes_prefill_only_when_flag_on(monkeypatch):
    monkeypatch.setattr(settings, "H1_FOUR_TABLE_EXTRACTION_ENABLED", True, raising=False)
    out = await h1.render(_ctx(_FakeDb(rows=_REAL_ROWS)))
    assert "h1_four_table_prefill" in out
    pf = out["h1_four_table_prefill"]
    assert pf["enabled"] is True
    assert set(pf.keys()) == {"enabled", "detail", "ledger_movement", "depreciation", "counterpart"}

    monkeypatch.setattr(settings, "H1_FOUR_TABLE_EXTRACTION_ENABLED", False, raising=False)
    off = await h1.render(_ctx(_FakeDb(rows=_REAL_ROWS)))
    assert "h1_four_table_prefill" not in off


@pytest.mark.asyncio
async def test_render_survives_section_failure(monkeypatch):
    monkeypatch.setattr(settings, "H1_FOUR_TABLE_EXTRACTION_ENABLED", True, raising=False)

    async def _boom(_ctx):
        raise RuntimeError("section down")

    monkeypatch.setattr(h1, "_build_h1_detail_prefill", _boom)
    out = await h1.render(_ctx(_FakeDb(rows=_REAL_ROWS)))
    assert out["h1_four_table_prefill"]["detail"]["rows"] == []
    assert out["component_type"] == "h1-fixed-assets"
