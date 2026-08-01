"""F2 存货审定表预填 + project_context 加固 — Property-Based Test

覆盖 F2 render 策略两处加固（`_f2_inventory_main.py`）：

Task 1: project_context 补 bs_date + related_parties
Task 2: `_build_adjudication_prefill` 从 tb_balance 存货科目预填审定期初/期末

三条正确性属性：
  Property1  预填期末合计 == tb_balance 存货科目期末汇总（1471 备抵取 abs）
  Property2  有持久化 F2-adjudication-data 时 adjudication_prefill == {}，
             无持久化时 adjudication_prefill == tb_values（同结构）
  Property3  related_party_registry 查询失败时 related_parties 返回 []，render 不抛

测试用 fake async session（不依赖真实 PG / SQLite），
monkeypatch `get_active_filter` 绕过 DatasetService 依赖。
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
import sqlalchemy as sa
from hypothesis import given, settings
from hypothesis import strategies as st

import app.routers.wp_render_strategies._f2_inventory_main as f2
from app.routers.wp_render_strategies._f2_inventory_main import (
    F2_CATEGORIES,
    _build_adjudication_prefill,
    render,
)

# 资产类存货科目（借方） + 备抵科目
#
# 🔴 归集判据是**科目名称**不是编码（`account_chart` 实测库内并存两版标准存货科目表，
#   `1405`/`1406`/`1407`/`1408`/`1411`/`1416`/`1461` 名称↔编码完全冲突）→ 构造 tb 行时
#   必须带 `account_name`。这里用 `F2_CATEGORIES` 的 label 作名称，
#   13 个 label 与其 rowKey 一一对应（见 `test_f2_category_rules`）。
_ASSET_ACCOUNTS = [
    (c["account"], c["label"]) for c in F2_CATEGORIES if c["account"] != "1471"
]
_IMPAIRMENT_ACCOUNT = next(
    (c["account"], c["label"]) for c in F2_CATEGORIES if c["account"] == "1471"
)


# ---------------------------------------------------------------------------
# Fake async DB —— 按 SQL 文本路由返回可编程结果
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, rows=None, one=None):
        self._rows = rows or []
        self._one = one

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._one


class _FakeSession:
    """拦截 execute()，按语句文本返回预置行；可配置 related_party 抛错。"""

    def __init__(
        self,
        *,
        tb_rows=None,
        checklist_rows=None,
        project_row=None,
        rp_rows=None,
        rp_raise=False,
    ):
        self.tb_rows = tb_rows or []
        self.checklist_rows = checklist_rows or []
        self.project_row = project_row
        self.rp_rows = rp_rows or []
        self.rp_raise = rp_raise

    async def execute(self, stmt, params=None):
        s = str(stmt).lower()
        if "checklist_responses" in s:
            return _FakeResult(rows=self.checklist_rows)
        if "related_party_registry" in s:
            if self.rp_raise:
                raise RuntimeError("related_party_registry boom")
            return _FakeResult(rows=self.rp_rows)
        if "from projects" in s or "projects where" in s:
            return _FakeResult(one=self.project_row)
        if "tb_balance" in s:
            return _FakeResult(rows=self.tb_rows)
        return _FakeResult()

    async def rollback(self):  # get_active_filter 异常路径兜底（本测试已 patch，不会触发）
        return None


def _tb_row(code: str, opening: float, closing: float, level: int = 1, name: str = ""):
    return SimpleNamespace(
        account_code=code,
        account_name=name,
        opening_balance=opening,
        closing_balance=closing,
        debit_amount=0,
        credit_amount=0,
        closing_direction="debit",
        dataset_id=None,
        level=level,
    )


def _ctx(db):
    return SimpleNamespace(db=db, wp_id=uuid4(), project_id=uuid4(), year=2025)


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# autouse: monkeypatch get_active_filter 绕过 DatasetService（返回恒真条件）
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _patch_active_filter(monkeypatch):
    async def _fake_filter(db, table, project_id, year, **kw):
        return sa.true()

    monkeypatch.setattr(f2, "get_active_filter", _fake_filter)


# ---------------------------------------------------------------------------
# Property1 —— 预填期末合计 == tb_balance 存货期末汇总（1471 取 abs）
# ---------------------------------------------------------------------------


@given(
    asset_closings=st.lists(
        st.integers(min_value=0, max_value=10**8),
        min_size=len(_ASSET_ACCOUNTS),
        max_size=len(_ASSET_ACCOUNTS),
    ),
    impair_closing=st.integers(min_value=-(10**8), max_value=0),
)
@settings(max_examples=15, deadline=None)
def test_property1_closing_total_matches_tb(asset_closings, impair_closing):
    """预填各分类期末合计 == tb_balance 存货科目期末汇总（备抵 1471 取绝对值）。

    每个存货科目构造一条叶子行（level=1，code==account），
    资产类期末为非负、跌价准备 1471 为非正（贷方存负数），
    断言 prefill 期末总额 == Σ资产期末 + |1471 期末|。
    """
    rows = [
        _tb_row(code, opening=0, closing=float(c), name=name)
        for (code, name), c in zip(_ASSET_ACCOUNTS, asset_closings)
    ]
    rows.append(
        _tb_row(
            _IMPAIRMENT_ACCOUNT[0],
            opening=0,
            closing=float(impair_closing),
            name=_IMPAIRMENT_ACCOUNT[1],
        )
    )

    ctx = _ctx(_FakeSession(tb_rows=rows))
    prefill = _run(_build_adjudication_prefill(ctx))

    expected_total = float(sum(asset_closings)) + abs(float(impair_closing))
    got_total = sum(v["closing"] for v in prefill.values())
    assert got_total == pytest.approx(expected_total)

    # 备抵科目若非零，必以绝对值出现在预填中
    if impair_closing != 0:
        assert "impairment-provision" in prefill
        assert prefill["impairment-provision"]["closing"] == pytest.approx(
            abs(float(impair_closing))
        )


def test_property1_impairment_abs_example():
    """定点用例：1471 期末 -55000（贷方）→ 预填取 abs=55000。"""
    rows = [
        _tb_row(
            _IMPAIRMENT_ACCOUNT[0],
            opening=-30000,
            closing=-55000,
            name=_IMPAIRMENT_ACCOUNT[1],
        )
    ]
    ctx = _ctx(_FakeSession(tb_rows=rows))
    prefill = _run(_build_adjudication_prefill(ctx))
    assert prefill["impairment-provision"]["opening"] == pytest.approx(30000)
    assert prefill["impairment-provision"]["closing"] == pytest.approx(55000)


# ---------------------------------------------------------------------------
# Property2 —— 持久化时 prefill=={}；无持久化时 prefill==tb_values
# ---------------------------------------------------------------------------


@given(
    closings=st.lists(
        st.integers(min_value=1, max_value=10**7),
        min_size=len(_ASSET_ACCOUNTS),
        max_size=len(_ASSET_ACCOUNTS),
    ),
    has_persisted=st.booleans(),
)
@settings(max_examples=15, deadline=None)
def test_property2_prefill_gated_by_persistence(closings, has_persisted):
    """有 F2-adjudication-data 持久化 → adjudication_prefill == {}；
    否则 adjudication_prefill == tb_values（同结构）。
    """
    rows = [
        _tb_row(code, opening=0, closing=float(c), name=name)
        for (code, name), c in zip(_ASSET_ACCOUNTS, closings)
    ]
    checklist_rows = []
    if has_persisted:
        checklist_rows = [
            SimpleNamespace(
                item_id="F2-adjudication-data", conclusion="", remark="{}"
            )
        ]

    project_row = SimpleNamespace(
        client_name="测试客户", audit_year=2025, applicable_standards="CAS"
    )
    ctx = _ctx(
        _FakeSession(
            tb_rows=rows,
            checklist_rows=checklist_rows,
            project_row=project_row,
            rp_rows=[SimpleNamespace(name="关联方甲")],
        )
    )
    out = _run(render(ctx))

    assert out is not None
    if has_persisted:
        assert out["adjudication_prefill"] == {}
    else:
        assert out["adjudication_prefill"] == out["tb_values"]
        assert out["adjudication_prefill"] != {}


def test_property2_project_context_bs_date_and_related_parties():
    """Task 1：bs_date == '{audit_year}-12-31'，related_parties 为名称列表。"""
    project_row = SimpleNamespace(
        client_name="甲公司", audit_year=2025, applicable_standards="CAS"
    )
    ctx = _ctx(
        _FakeSession(
            tb_rows=[],
            project_row=project_row,
            rp_rows=[
                SimpleNamespace(name="关联方甲"),
                SimpleNamespace(name="关联方乙"),
            ],
        )
    )
    out = _run(render(ctx))
    pc = out["project_context"]
    assert pc["bs_date"] == "2025-12-31"
    assert pc["related_parties"] == ["关联方甲", "关联方乙"]
    assert pc["client_name"] == "甲公司"


# ---------------------------------------------------------------------------
# Property3 —— related_parties 查询失败返回 []，render 不抛
# ---------------------------------------------------------------------------


@given(
    closings=st.lists(
        st.integers(min_value=0, max_value=10**7),
        min_size=len(_ASSET_ACCOUNTS),
        max_size=len(_ASSET_ACCOUNTS),
    ),
)
@settings(max_examples=15, deadline=None)
def test_property3_related_parties_failure_degrades(closings):
    """related_party_registry 查询抛错时，render 仍成功且 related_parties == []。"""
    rows = [
        _tb_row(code, opening=0, closing=float(c), name=name)
        for (code, name), c in zip(_ASSET_ACCOUNTS, closings)
    ]
    project_row = SimpleNamespace(
        client_name="乙公司", audit_year=2024, applicable_standards="CAS"
    )
    ctx = _ctx(
        _FakeSession(
            tb_rows=rows,
            project_row=project_row,
            rp_raise=True,  # 关联方查询抛错
        )
    )
    # 不应抛异常
    out = _run(render(ctx))
    assert out is not None
    assert out["project_context"]["related_parties"] == []
    # bs_date 仍正常（关联方失败不影响项目上下文其余字段）
    assert out["project_context"]["bs_date"] == "2024-12-31"
