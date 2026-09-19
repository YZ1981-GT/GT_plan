"""D1 应收票据明细表四表库 seed 单测（D1-2 原值 / D1-4 坏账）.

spec: .kiro/specs/d1-four-table-extraction-formula-wiring/
      (Requirements 1.x / 2.x / Property 1, 2, 4, 5, 6)

覆盖：
  * 纯函数 build_d1_category_rows_from_tb —— 叶子→D1-cat-rows 映射、固定行/动态行、
    roll-forward 勾稽（Property 5, 6）、跳零。
  * 纯函数 build_d1_bad_debt_rows_from_tb —— 坏账 abs 归一、净变动记入 provision/reversal、
    宁缺勿造 individual 留空（Property 1）。
  * seed_d1_detail_rows —— 叶子只汇总、手工优先、fail-open、锚点校验（Property 1, 2, 4, 7）。

全部 fake async session，不触库。
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.d_cycle_extraction import d1_detail_seed as mod
from app.services.d_cycle_extraction.d1_detail_seed import (
    BD_PORTFOLIO_ANCHOR,
    CAT_ROWS_ANCHOR,
    build_d1_bad_debt_rows_from_tb,
    build_d1_category_rows_from_tb,
    seed_d1_detail_rows,
)


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# 纯函数 build_d1_category_rows_from_tb（原值）
# ---------------------------------------------------------------------------


def _leaf(code, name, opening=0.0, debit=0.0, credit=0.0, closing=0.0):
    return {
        "code": code,
        "name": name,
        "opening": opening,
        "debit": debit,
        "credit": credit,
        "closing": closing,
    }


def test_category_fixed_row_mapping():
    """银行承兑→fixed-bank、商业承兑→fixed-commercial（Property 6）。"""
    leaves = [
        _leaf("1121.01", "应收票据_银行承兑汇票", 100, 50, 30, 120),
        _leaf("1121.02", "应收票据_商业承兑汇票", 200, 10, 60, 150),
    ]
    rows = build_d1_category_rows_from_tb(leaves)
    by_id = {r["rowId"]: r for r in rows}
    assert by_id["fixed-bank"]["category"] == "银行承兑汇票"
    assert by_id["fixed-bank"]["isFixed"] is True
    assert by_id["fixed-commercial"]["category"] == "商业承兑汇票"


def test_category_rollforward_mapping():
    """priorUnadjusted=opening / currentIncrease=debit / currentDecrease=credit（Property 5）。

    → 前端 currentUnadjusted = opening + debit − credit = closing。
    """
    leaves = [_leaf("1121.01", "应收票据_银行承兑汇票", 37550925.38, 138564072.55, 163654386.64, 12460611.29)]
    row = build_d1_category_rows_from_tb(leaves)[0]
    assert row["priorUnadjusted"] == 37550925.38
    assert row["currentIncrease"] == 138564072.55
    assert row["currentDecrease"] == 163654386.64
    # 勾稽：opening + debit − credit == closing
    assert round(row["priorUnadjusted"] + row["currentIncrease"] - row["currentDecrease"], 2) == 12460611.29


def test_category_dynamic_row_strips_prefix():
    """非银承/商承叶子作动态行，种类名去「应收票据_」前缀（信用证）。"""
    leaves = [_leaf("1121.03", "应收票据_信用证", 55021577.23, 10490692.64, 65512269.87, 0.0)]
    row = build_d1_category_rows_from_tb(leaves)[0]
    assert row["rowId"].startswith("dynamic-tb-")
    assert row["isFixed"] is False
    assert row["category"] == "信用证"


def test_category_skips_all_zero_leaf():
    """全零叶子（无期初、无发生）跳过。"""
    leaves = [
        _leaf("1121.01", "应收票据_银行承兑汇票", 0, 0, 0, 0),
        _leaf("1121.02", "应收票据_商业承兑汇票", 100, 0, 0, 100),
    ]
    rows = build_d1_category_rows_from_tb(leaves)
    assert [r["rowId"] for r in rows] == ["fixed-commercial"]


# ---------------------------------------------------------------------------
# 纯函数 build_d1_bad_debt_rows_from_tb（坏账）
# ---------------------------------------------------------------------------


def test_bad_debt_abs_normalizes_signed_convention():
    """有符号约定（负值）与绝对值约定均归一为正（abs）。"""
    # 有符号：期初 -3,037,132.25 → 期末 -1,162,288.03（credit 备抵存负）
    ind, port = build_d1_bad_debt_rows_from_tb(
        [_leaf("1231.01", "坏账准备_应收票据", opening=-3037132.25, closing=-1162288.03)]
    )
    assert ind == []
    assert len(port) == 1
    row = port[0]
    assert row["rowId"] == "fixed-portfolio"
    assert row["priorUnadjusted"] == 3037132.25


def test_bad_debt_net_decrease_goes_to_reversal():
    """本期净减少（期末<期初）记入 currentReversal，roll-forward 守恒。"""
    ind, port = build_d1_bad_debt_rows_from_tb(
        [_leaf("1231.01", "坏账准备_应收票据", opening=3037132.25, closing=1162288.03)]
    )
    row = port[0]
    assert row["currentReversal"] == pytest.approx(1874844.22)
    assert row["currentProvision"] == 0
    # roll-forward: 期初 + 计提 − 转回 == 期末
    end = row["priorUnadjusted"] + row["currentProvision"] - row["currentReversal"]
    assert round(end, 2) == 1162288.03


def test_bad_debt_net_increase_goes_to_provision():
    """本期净增加（期末>期初）记入 currentProvision。"""
    _ind, port = build_d1_bad_debt_rows_from_tb(
        [_leaf("1231.01", "坏账准备_应收票据", opening=1000.0, closing=1500.0)]
    )
    assert port[0]["currentProvision"] == pytest.approx(500.0)
    assert port[0]["currentReversal"] == 0


def test_bad_debt_empty_when_all_zero():
    """无坏账余额 → 不 seed（宁缺勿造）。"""
    ind, port = build_d1_bad_debt_rows_from_tb([_leaf("1231.01", "坏账准备_应收票据", 0, 0, 0, 0)])
    assert ind == [] and port == []


# ---------------------------------------------------------------------------
# seed_d1_detail_rows（fake async session）
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)


class _FakeSession:
    """按 SQL 路由：startswith('1121') → 原值叶子；startswith('1231') → 坏账叶子。

    通过 group_by 后的行模拟（含中间级 rollup 行以验证 leaf-only）。
    """

    def __init__(self, *, gross=None, bad_debt=None, raise_on=None):
        self.gross = gross or []
        self.bad_debt = bad_debt or []
        self.raise_on = raise_on  # 'gross' | 'bad_debt' | 'all'

    async def execute(self, stmt, params=None):
        try:
            s = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        except Exception:
            s = str(stmt)
        if self.raise_on == "all":
            raise RuntimeError("boom")
        if "1231" in s:
            if self.raise_on == "bad_debt":
                raise RuntimeError("bd boom")
            return _FakeResult(self.bad_debt)
        if "1121" in s:
            if self.raise_on == "gross":
                raise RuntimeError("gross boom")
            return _FakeResult(self.gross)
        return _FakeResult([])


def _row(code, name, opening=0.0, closing=0.0, debit=0.0, credit=0.0):
    return SimpleNamespace(
        code=code, name=name, opening=opening, closing=closing, debit=debit, credit=credit
    )


async def _fake_active_filter(*_args, **_kwargs):
    return True


def _ctx(session):
    return SimpleNamespace(db=session, project_id=uuid4(), year=2025)


@pytest.fixture(autouse=True)
def _patch_active_filter(monkeypatch):
    monkeypatch.setattr(mod, "get_active_filter", _fake_active_filter)


def test_seed_populates_cat_and_bad_debt():
    """有 tb 叶子且无持久化 → seed D1-cat-rows + D1-bd-portfolio-rows。"""
    session = _FakeSession(
        gross=[
            _row("1121.01", "应收票据_银行承兑汇票", 100, 120, 50, 30),
            _row("1121.02", "应收票据_商业承兑汇票", 200, 150, 10, 60),
        ],
        bad_debt=[_row("1231.01", "坏账准备_应收票据", opening=3000, closing=1200)],
    )
    snap: dict = {}
    _run(seed_d1_detail_rows(_ctx(session), snap))
    cat = json.loads(snap[CAT_ROWS_ANCHOR]["remark"])
    assert {r["rowId"] for r in cat} == {"fixed-bank", "fixed-commercial"}
    bd = json.loads(snap[BD_PORTFOLIO_ANCHOR]["remark"])
    assert bd[0]["priorUnadjusted"] == 3000


def test_seed_leaf_only_excludes_rollup():
    """含中间级（1121.01 是 1121.0101 的前缀）→ 只取叶子 1121.0101（Property 1）。"""
    session = _FakeSession(
        gross=[
            _row("1121.01", "应收票据_银行承兑汇票", 300, 300, 0, 0),      # rollup（非叶子）
            _row("1121.0101", "应收票据_银行承兑汇票_A行", 300, 300, 0, 0),  # 叶子
        ],
    )
    snap: dict = {}
    _run(seed_d1_detail_rows(_ctx(session), snap))
    cat = json.loads(snap[CAT_ROWS_ANCHOR]["remark"])
    # 只应有 1 行（叶子），不双算
    assert len(cat) == 1
    assert cat[0]["priorUnadjusted"] == 300


def test_seed_manual_priority_skips_persisted():
    """已有持久化 D1-cat-rows → 不覆盖（Property 2）。"""
    session = _FakeSession(gross=[_row("1121.01", "应收票据_银行承兑汇票", 100, 120, 50, 30)])
    snap = {CAT_ROWS_ANCHOR: {"conclusion": "", "remark": '[{"rowId":"fixed-bank","priorUnadjusted":999}]'}}
    _run(seed_d1_detail_rows(_ctx(session), snap))
    cat = json.loads(snap[CAT_ROWS_ANCHOR]["remark"])
    assert cat[0]["priorUnadjusted"] == 999  # 用户值保留


def test_seed_treats_default_zero_skeleton_as_empty():
    """🔴 默认全零骨架不算手工数据 → 仍 seed（live 实测缺陷回归）。

    前端 `useD1BadDebt` 在底稿首次打开时就把 DEFAULT_PORTFOLIO_ROW 经防抖保存落库，
    remark 是**非空** JSON 全零骨架。若手工优先只看 remark 非空，则任何被打开过一次的
    底稿坏账 seed 永久不触发 —— 实证：真实项目 wp 68c7740e… 的 D1-bd-portfolio-rows
    自 2026-07-09 起即为该骨架，seed 一直静默跳过（浏览器/HTTP 实测才暴露）。
    """
    skeleton = (
        '[{"rowId":"fixed-portfolio","category":"portfolio","label":"按组合计提",'
        '"isSubRow":false,"priorUnadjusted":0,"priorAje":0,"priorRje":0,'
        '"currentProvision":0,"currentRecovery":0,"currentReversal":0,'
        '"currentWriteOff":0,"currentOther":0,"currentAje":0,"currentRje":0}]'
    )
    session = _FakeSession(bad_debt=[_row("1231.01", "坏账准备_应收票据", 6074264.50, 2324576.06, 0, 0)])
    snap = {BD_PORTFOLIO_ANCHOR: {"conclusion": "", "remark": skeleton}}
    _run(seed_d1_detail_rows(_ctx(session), snap))
    port = json.loads(snap[BD_PORTFOLIO_ANCHOR]["remark"])
    assert port[0]["priorUnadjusted"] == 6074264.50
    assert round(port[0]["currentReversal"], 2) == 3749688.44


def test_seed_keeps_any_nonzero_user_amount():
    """骨架里只要有**任一**非零金额即视为手工数据 → 不覆盖（手工优先边界）。"""
    almost_skeleton = (
        '[{"rowId":"fixed-portfolio","category":"portfolio","label":"按组合计提",'
        '"isSubRow":false,"priorUnadjusted":0,"priorAje":0,"priorRje":0,'
        '"currentProvision":0.5,"currentRecovery":0,"currentReversal":0,'
        '"currentWriteOff":0,"currentOther":0,"currentAje":0,"currentRje":0}]'
    )
    session = _FakeSession(bad_debt=[_row("1231.01", "坏账准备_应收票据", 6074264.50, 2324576.06, 0, 0)])
    snap = {BD_PORTFOLIO_ANCHOR: {"conclusion": "", "remark": almost_skeleton}}
    _run(seed_d1_detail_rows(_ctx(session), snap))
    port = json.loads(snap[BD_PORTFOLIO_ANCHOR]["remark"])
    assert port[0]["currentProvision"] == 0.5  # 用户值保留
    assert port[0]["priorUnadjusted"] == 0


def test_seed_unparsable_remark_treated_as_manual():
    """remark 非 JSON（内容未知）→ 保守视为手工数据，不覆盖。"""
    session = _FakeSession(bad_debt=[_row("1231.01", "坏账准备_应收票据", 6074264.50, 2324576.06, 0, 0)])
    snap = {BD_PORTFOLIO_ANCHOR: {"conclusion": "", "remark": "审计师手写说明：本期无需计提"}}
    _run(seed_d1_detail_rows(_ctx(session), snap))
    assert snap[BD_PORTFOLIO_ANCHOR]["remark"] == "审计师手写说明：本期无需计提"


def test_seed_fail_open_on_query_error():
    """查询异常 → 不抛、不写 seed（Property 4）。"""
    session = _FakeSession(raise_on="all")
    snap: dict = {}
    _run(seed_d1_detail_rows(_ctx(session), snap))  # 不抛
    assert snap == {}


def test_seed_fail_open_missing_year():
    """year 缺失 → 跳过 seed（fail-open）。"""
    session = _FakeSession(gross=[_row("1121.01", "应收票据_银行承兑汇票", 100, 120, 50, 30)])
    ctx = SimpleNamespace(db=session, project_id=uuid4(), year=None)
    snap: dict = {}
    _run(seed_d1_detail_rows(ctx, snap))
    assert snap == {}


def test_seed_partial_fail_open_gross_ok_bad_debt_error():
    """坏账查询异常时原值 seed 仍成功（各自 try/except）。"""
    session = _FakeSession(
        gross=[_row("1121.01", "应收票据_银行承兑汇票", 100, 120, 50, 30)],
        raise_on="bad_debt",
    )
    snap: dict = {}
    _run(seed_d1_detail_rows(_ctx(session), snap))
    assert CAT_ROWS_ANCHOR in snap
    assert BD_PORTFOLIO_ANCHOR not in snap
