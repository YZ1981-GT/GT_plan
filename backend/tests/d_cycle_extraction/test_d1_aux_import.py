"""D1-3 客户明细表辅助余额归集单测.

spec: .kiro/specs/d1-extraction-chain-completion/
      (Requirements 4.1~4.5 / Property 11)

覆盖：
  * `pick_d1_aux_type` —— 单一维度选取（防 aux_type 冗余双算），客户关键词优先。
  * `build_d1_customer_rows_from_aux` —— 只产出**录入列**（派生列不落库）、空名跳过、
    行数上限、roll-forward 与 tb 一致。
  * 宁缺勿造：无维度 / 无匹配科目 → 空结果不报错（Property 11）。

全部纯函数 + fake async session，不触库。
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.routers.wp_render_strategies._d1_import_export import (
    build_d1_customer_rows_from_aux,
    pick_d1_aux_type,
)
from app.routers.wp_render_strategies._d1_import_export import _impl as mod


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# pick_d1_aux_type
# ---------------------------------------------------------------------------


def test_pick_aux_type_prefers_customer_keyword():
    """实测项目 1121.xx 同时挂「客户」与「集团内外」→ 必须选「客户」。

    直接 group by aux_name 会把两个维度的余额双算（tb_aux_balance 按维度冗余存储）。
    """
    assert pick_d1_aux_type([("集团内外", 115, 1e9), ("客户", 307, 76108755.74)]) == "客户"


def test_pick_aux_type_falls_back_to_largest_amount():
    """无客户关键词时按余额绝对值合计取最大者。"""
    assert pick_d1_aux_type([("维度A", 10, 100.0), ("维度B", 2, 999.0)]) == "维度B"


def test_pick_aux_type_empty_returns_none():
    assert pick_d1_aux_type([]) is None


# ---------------------------------------------------------------------------
# build_d1_customer_rows_from_aux
# ---------------------------------------------------------------------------


def test_build_rows_only_persisted_columns():
    """🔴 只产出录入列：派生列（priorAudited / currentBalance / currentUnadjusted /
    currentAudited）由前端 `recalcRow` 现算且**不落库**，后端写了会被覆盖并违反派生列铁律。
    """
    rows = build_d1_customer_rows_from_aux([("甲公司", "C001", 100, 60, 20)])
    assert len(rows) == 1
    row = rows[0]
    for derived in ("priorAudited", "currentBalance", "currentUnadjusted", "currentAudited"):
        assert derived not in row, derived
    # 与前端 CustomerRow 持久化子集逐字一致
    assert set(row.keys()) == {
        "rowId",
        "customerName",
        "companyCode",
        "relationType",
        "priorUnadjusted",
        "priorAje",
        "priorRje",
        "currentIncrease",
        "currentDecrease",
        "reclassification",
        "currentAje",
        "currentRje",
        "postSettlement",
    }


def test_build_rows_maps_aux_code_to_company_code():
    row = build_d1_customer_rows_from_aux([("甲公司", "416456", 0, 0, 0)])[0]
    assert row["companyCode"] == "416456"
    # 关联关系留空：前端按项目关联方名单自动匹配，后端不臆造
    assert row["relationType"] == ""


def test_build_rows_skips_blank_customer_name():
    rows = build_d1_customer_rows_from_aux(
        [("甲公司", "C1", 1, 0, 0), ("", "C2", 9, 9, 9), ("  ", None, 1, 1, 1)]
    )
    assert [r["customerName"] for r in rows] == ["甲公司"]


def test_build_rows_respects_row_limit():
    entries = [(f"客户{i}", f"C{i}", i, 0, 0) for i in range(1, 11)]
    rows = build_d1_customer_rows_from_aux(entries, row_limit=4)
    assert len(rows) == 4


def test_build_rows_rollforward_matches_tb_leaves():
    """实测数据（项目 0ec33ac9 / 2025）：客户维度归集合计逐分等于 tb_balance 1121。

    期初 131,550,200.96 + 借 162,165,634.33 − 贷 273,506,637.11 = 期末 20,209,198.18
    """
    entries = [
        ("客户A", "1", 131550200.96, 162165634.33, 273506637.11),
    ]
    row = build_d1_customer_rows_from_aux(entries)[0]
    end = row["priorUnadjusted"] + row["currentIncrease"] - row["currentDecrease"]
    assert round(end, 2) == 20209198.18


def test_build_rows_generates_unique_row_ids():
    rows = build_d1_customer_rows_from_aux([("A", "1", 0, 1, 0), ("B", "2", 0, 1, 0)])
    assert rows[0]["rowId"] != rows[1]["rowId"]
    assert all(r["rowId"].startswith("dynamic-aux-") for r in rows)


# ---------------------------------------------------------------------------
# aggregate_d1_customer_rows_from_aux（Property 11：宁缺勿造）
# ---------------------------------------------------------------------------


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)


class _FakeSession:
    """按查询内容路由：第 1 次是 aux_type 候选，第 2 次是按客户归集，第 3 次是科目集。"""

    def __init__(self, *, type_rows=None, agg_rows=None, code_rows=None):
        self.type_rows = type_rows or []
        self.agg_rows = agg_rows or []
        self.code_rows = code_rows or []
        self.calls = 0

    async def execute(self, stmt, params=None):
        # 按调用顺序路由（比 SQL 串嗅探稳定：三条语句的 WHERE 都含 aux_type）
        self.calls += 1
        if self.calls == 1:
            return _Rows(self.type_rows)
        if self.calls == 2:
            return _Rows(self.agg_rows)
        return _Rows(self.code_rows)


async def _fake_active_filter(*_a, **_k):
    return True


@pytest.fixture(autouse=True)
def _patch_active_filter(monkeypatch):
    import app.services.dataset_query as dq

    monkeypatch.setattr(dq, "get_active_filter", _fake_active_filter)


def test_aggregate_returns_empty_when_no_prefixes():
    """无科目（报表映射解析全空，理论上不会发生）→ 空结果不抛错。"""
    out = _run(
        mod.aggregate_d1_customer_rows_from_aux(_FakeSession(), "p", 2025, [])
    )
    assert out == ([], None, 0, [])


def test_aggregate_returns_empty_when_no_aux_dimension():
    """Property 11：该项目辅助余额表无任何维度 → imported_count=0，不抛错、不写库。"""
    rows, aux_type, total, codes = _run(
        mod.aggregate_d1_customer_rows_from_aux(
            _FakeSession(type_rows=[]), "p", 2025, ["1121"]
        )
    )
    assert rows == [] and aux_type is None and total == 0 and codes == []


def test_aggregate_locks_single_dimension_then_groups():
    """先锁维度再归集：候选含两个维度时只按被选中的那个归集（防双算）。"""
    session = _FakeSession(
        type_rows=[
            SimpleNamespace(aux_type="集团内外", n=115, amt=1e9),
            SimpleNamespace(aux_type="客户", n=307, amt=76108755.74),
        ],
        agg_rows=[
            SimpleNamespace(aux_name="甲公司", aux_code="C1", opening=100, debit=60, credit=20),
        ],
        code_rows=[
            SimpleNamespace(account_code="1121.01"),
            SimpleNamespace(account_code="1121.02"),
        ],
    )
    rows, aux_type, total, codes = _run(
        mod.aggregate_d1_customer_rows_from_aux(session, "p", 2025, ["1121"])
    )
    assert aux_type == "客户"
    assert total == 1 and len(rows) == 1
    assert rows[0]["customerName"] == "甲公司"
    assert codes == ["1121.01", "1121.02"]
