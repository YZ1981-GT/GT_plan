"""Wave 6 / Task 7.1 —— Property 1/5/8/10 hypothesis 生成式 PBT（补齐全覆盖）.

spec: .kiro/specs/d-cycle-four-table-extraction-formulas/  (Requirements 8.1, 8.2)

现有 `test_prefill_presets.py` / `test_evaluator_active_filter.py` / `test_anchor_registry.py`
以**固定样例**覆盖 Property 1–11；本文件补**生成式** hypothesis 断言，对最适合属性化的
不变量施加随机输入压力（叶子判定 / 读时收敛优先级 / 未知锚点拒绝 / 求值幂等）：

  * **Property 1**（R1.4）：任意叶子/rollup 组合 → prefill 只含叶子，合计不含 rollup 双计。
  * **Property 5**（R3.3/5.4/5.5）：任意 (预设, 用户覆盖?, 禁用?) → 每锚点唯一，
    禁用 > custom > preset。
  * **Property 8**（R6.2）：未登记 wp_code 的任意 anchor → `is_known_anchor` 恒 False。
  * **Property 10**（R4.3/8.2）：同一四表库快照多次求值同一 Tier A 公式 → 结果恒一致。

conftest 已注册 `fast` hypothesis profile（max_examples=5、deadline=None、抑制
function_scoped_fixture 健康检查），故可与 monkeypatch（函数级 fixture）+ 同步 `_run`
包装 async 协程共用。
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import sqlalchemy as sa
from hypothesis import given
from hypothesis import strategies as st

from app.models.audit_platform_models import TrialBalance
from app.services import wp_formula_eval_service as eval_mod
from app.services.d_cycle_extraction import prefill as prefill_mod
from app.services.d_cycle_extraction import presets as presets_mod
from app.services.d_cycle_extraction.anchor_registry import is_known_anchor
from app.services.d_cycle_extraction.prefill import (
    MODE_BALANCE,
    build_d_adjudication_prefill,
)
from app.services.d_cycle_extraction.presets import (
    SOURCE_CUSTOM,
    SOURCE_DISABLED,
    SOURCE_PRESET,
    resolve_effective,
)
from app.services.wp_formula_eval_service import _resolve_tb


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fakes（自包含，不依赖其它测试模块）
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, rows=None):
        self._rows = rows or []

    def fetchall(self):
        return self._rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        return SimpleNamespace(all=lambda: list(self._rows))


class _FakeTbSession:
    def __init__(self, rows=None):
        self._rows = rows or []

    async def execute(self, stmt, params=None):
        return _FakeResult(rows=self._rows)

    async def rollback(self):
        return None


class _FakeFormulaSession:
    def __init__(self, formulas=None):
        self._formulas = formulas or []

    async def execute(self, stmt, params=None):
        return _FakeResult(rows=self._formulas)


def _tb_row(code, name, *, closing=0.0):
    return SimpleNamespace(
        code=code, name=name, opening=closing, closing=closing, debit=0.0, credit=0.0
    )


def _tb_eval_row(code, *, audited):
    return SimpleNamespace(
        standard_account_code=code,
        audited_amount=Decimal(str(audited)),
        opening_balance=Decimal("0"),
        unadjusted_amount=Decimal("0"),
        rje_adjustment=Decimal("0"),
        aje_adjustment=Decimal("0"),
    )


def _ctx(db):
    return SimpleNamespace(db=db, project_id=uuid4(), year=2025)


def _patch_prefill_filter(monkeypatch):
    async def _fake(db, table, project_id, year, **kw):
        return sa.true()
    monkeypatch.setattr(prefill_mod, "get_active_filter", _fake)


def _patch_eval_filter(monkeypatch):
    async def _fake(db, table, project_id, year, **kw):
        return sa.true()
    monkeypatch.setattr(eval_mod, "get_active_filter", _fake)


def _patch_presets(monkeypatch, wp_code, bindings):
    def _fake_load(code):
        return [dict(b) for b in bindings] if code == wp_code else []
    monkeypatch.setattr(presets_mod, "load_presets", _fake_load)


def _preset_binding(anchor, *, expression="TB('1402','期末余额')", sheet_name="D6-1"):
    return {
        "wp_code": "D6", "sheet_name": sheet_name, "anchor": anchor,
        "expression": expression, "formula_type": "auto_calc",
        "description": "预设", "source": SOURCE_PRESET, "tier": "A",
    }


def _fake_formula(target_cell, *, expression="TB('1402','期末余额')", category=None):
    return SimpleNamespace(
        target_cell=target_cell, expression=expression, sheet_name="D6-1",
        category=category, description="", formula_type="auto_calc",
    )


# ---------------------------------------------------------------------------
# Property 1: 只取叶子防双算（生成式）
# ---------------------------------------------------------------------------


@given(
    k=st.integers(min_value=1, max_value=5),
    grandchild=st.booleans(),
    amt=st.floats(min_value=1.0, max_value=1e6, allow_nan=False, allow_infinity=False),
)
def test_pbt_p1_leaf_only(monkeypatch, k, grandchild, amt):
    """任意 k 个子科目（可选给首个添加孙级）→ prefill 只含叶子，排除 rollup 中间级。"""
    _patch_prefill_filter(monkeypatch)
    rows = [_tb_row(f"1402.{i:02d}", f"子{i}", closing=amt) for i in range(1, k + 1)]
    expected = {r.code for r in rows}
    if grandchild:
        # 给 1402.01 添加孙级 → 1402.01 变为 rollup 中间级被排除
        rows.append(_tb_row("1402.01.01", "孙", closing=amt))
        expected.discard("1402.01")
        expected.add("1402.01.01")
    result = _run(build_d_adjudication_prefill(
        _ctx(_FakeTbSession(rows)), account_prefix="1402", mode=MODE_BALANCE
    ))
    assert {r["code"] for r in result} == expected
    # 合计 = 叶子数 × amt（不含 rollup 双计）
    assert abs(sum(r["closing_balance"] for r in result) - len(expected) * amt) < 1e-3


# ---------------------------------------------------------------------------
# Property 5: 读时收敛优先级（生成式）
# ---------------------------------------------------------------------------


@given(has_user=st.booleans(), disabled=st.booleans())
def test_pbt_p5_precedence(monkeypatch, has_user, disabled):
    """任意 (预设 + 可选用户覆盖 + 可选禁用) → 每锚点唯一，禁用 > custom > preset。"""
    _patch_presets(monkeypatch, "D6", [_preset_binding("D6-1-tb-amount")])
    users = []
    if has_user:
        if disabled:
            users.append(_fake_formula("D6-1-tb-amount", category="__disabled__"))
        else:
            users.append(_fake_formula("D6-1-tb-amount", expression="TB('1402','期初余额')"))
    result = _run(resolve_effective(_FakeFormulaSession(users), uuid4(), "D6", uuid4()))
    # 每锚点唯一
    anchors = [b["anchor"] for b in result]
    assert len(anchors) == len(set(anchors)) == 1
    src = result[0]["source"]
    if not has_user:
        assert src == SOURCE_PRESET
    elif disabled:
        assert src == SOURCE_DISABLED
    else:
        assert src == SOURCE_CUSTOM


# ---------------------------------------------------------------------------
# Property 8: 未登记 wp_code 的任意 anchor 恒 False（生成式）
# ---------------------------------------------------------------------------


@given(
    wp_code=st.sampled_from(["ZZZ", "D99", "X1", "__meta__", "d6"]),
    anchor=st.text(min_size=1, max_size=40),
)
def test_pbt_p8_unregistered_wpcode_anchor_always_false(wp_code, anchor):
    """未登记 wp_code（含大小写错的 'd6'）+ 任意 anchor → is_known_anchor 恒 False（不静默放行）。"""
    assert is_known_anchor(wp_code, anchor) is False


@given(anchor=st.text(min_size=1, max_size=40))
def test_pbt_p8_empty_wpcode_always_false(anchor):
    assert is_known_anchor("", anchor) is False


# ---------------------------------------------------------------------------
# Property 10: 求值幂等（生成式）
# ---------------------------------------------------------------------------


@given(amt=st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False))
def test_pbt_p10_resolve_tb_idempotent(monkeypatch, amt):
    """同一四表库快照多次求值同一 TB 公式 → 结果恒一致。"""
    _patch_eval_filter(monkeypatch)
    sess = _FakeTbSession([_tb_eval_row("1402", audited=amt)])
    v1 = _run(_resolve_tb(sess, uuid4(), 2025, "1402", "期末余额"))
    v2 = _run(_resolve_tb(sess, uuid4(), 2025, "1402", "期末余额"))
    v3 = _run(_resolve_tb(sess, uuid4(), 2025, "1402", "期末余额"))
    assert v1 == v2 == v3 == Decimal(str(amt))
