"""守护测试 — 附注/披露读取 trial_balance.audited_amount 在 v2 约定下符号正确.

Spec:   .kiro/specs/ledger-sign-convention-unify/ Task 5.3（需求 11）
背景：
  v2（类别自然正数）约定下，负债/权益/收入类科目的 audited_amount 已存为
  **自然正数**（不再是 v1 借正贷负下的负数）。本测试守护 disclosure 三模块
  （disclosure_engine / disclosure_trace / note_source_resolvers）读 audited_amount
  时**不做任何旧约定符号补偿**（不取反、不取绝对值、不假设负数）：

  1. 默认聚合 ``agg=sum`` 对 v2 正数**原样透传**——负债类披露金额为正。
  2. ``sum_minus`` 是**显式 opt-in 业务语义**（某行需展示相反数），仅在 binding
     显式声明时才取反；它**不是**为纠正 v1 负数而存在的隐式机制，故 v2 正数
     在未声明 sum_minus 时绝不会被翻号。
  3. disclosure_trace 公式展开（``_expand_formula``）默认不前置负号；仅
     显式 ``sum_minus`` 时渲染 ``=-...``（展示串，与符号约定无关）。

Validates: Requirements 11.1, 11.4
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.services.note_source_resolvers import (
    _aggregate,
    resolve_trial_balance,
)
from app.services.disclosure_trace import _expand_formula


def _ctx(**overrides) -> dict:
    base: dict = {
        "project_id": uuid4(),
        "year": 2025,
        "db": None,
        "_tb_cache": {},
        "_wp_cache": {},
        "_prior_notes_cache": {},
    }
    base.update(overrides)
    return base


# ===========================================================================
# 1) 负债类 v2 正数：默认 agg=sum 原样透传（不翻号）
# ===========================================================================


@pytest.mark.asyncio
async def test_liability_audited_amount_positive_passthrough():
    """应付账款（2202）v2 下审定数存正数 → resolver 默认 sum 返回正数，无补偿翻转."""
    ctx = _ctx()
    # v2：负债类自然正数（v1 旧约定此处会是 -5000）
    ctx["_tb_cache"]["2202"] = {"audited": 5000.0, "opening": 4000.0, "unadjusted": 5000.0}
    binding = {
        "source": "trial_balance",
        "field": "audited_amount",
        "account_codes": ["2202"],
        # 不声明 agg → 默认 sum
    }
    val = await resolve_trial_balance(binding, ctx)
    assert val == 5000.0, "v2 负债类审定数应原样正数透传，禁止隐式取反/取绝对值"


@pytest.mark.asyncio
async def test_equity_and_revenue_audited_amount_positive_passthrough():
    """权益（4001 实收资本）/ 收入（6001 主营业务收入）v2 正数默认透传."""
    ctx = _ctx()
    ctx["_tb_cache"]["4001"] = {"audited": 1_000_000.0, "opening": 1_000_000.0, "unadjusted": 1_000_000.0}
    ctx["_tb_cache"]["6001"] = {"audited": 800_000.0, "opening": 0.0, "unadjusted": 800_000.0}

    val_equity = await resolve_trial_balance(
        {"source": "trial_balance", "field": "audited_amount", "account_codes": ["4001"]},
        ctx,
    )
    val_revenue = await resolve_trial_balance(
        {"source": "trial_balance", "field": "audited_amount", "account_codes": ["6001"]},
        ctx,
    )
    assert val_equity == 1_000_000.0
    assert val_revenue == 800_000.0


@pytest.mark.asyncio
async def test_multi_liability_accounts_sum_positive():
    """多负债科目求和在 v2 下为正数合计（应付账款 + 其他应付款）."""
    ctx = _ctx()
    ctx["_tb_cache"]["2202"] = {"audited": 5000.0, "opening": 0, "unadjusted": 5000.0}
    ctx["_tb_cache"]["2241"] = {"audited": 3000.0, "opening": 0, "unadjusted": 3000.0}
    val = await resolve_trial_balance(
        {
            "source": "trial_balance",
            "field": "audited_amount",
            "account_codes": ["2202", "2241"],
            "agg": "sum",
        },
        ctx,
    )
    assert val == 8000.0


# ===========================================================================
# 2) sum_minus 是显式 opt-in，不是 v1 负数纠正机制
# ===========================================================================


def test_aggregate_default_sum_does_not_negate():
    """默认 sum 不翻号——v2 正数保持正数."""
    assert _aggregate([5000.0], "sum") == 5000.0
    assert _aggregate([5000.0, 3000.0], "sum") == 8000.0
    # agg 缺省（None / 空串）也走 sum 兜底，不翻号
    assert _aggregate([5000.0], "") == 5000.0


def test_aggregate_sum_minus_only_negates_when_explicit():
    """sum_minus 仅在显式声明时取反——属业务语义，非符号约定补偿."""
    assert _aggregate([5000.0], "sum_minus") == -5000.0


@pytest.mark.asyncio
async def test_sum_minus_is_opt_in_not_applied_by_default():
    """同一 v2 正数：默认透传为正，显式 sum_minus 才取反——证明无隐式 v1 补偿."""
    ctx = _ctx()
    ctx["_tb_cache"]["2202"] = {"audited": 5000.0, "opening": 0, "unadjusted": 5000.0}

    default_val = await resolve_trial_balance(
        {"source": "trial_balance", "field": "audited_amount", "account_codes": ["2202"]},
        ctx,
    )
    opt_in_val = await resolve_trial_balance(
        {
            "source": "trial_balance",
            "field": "audited_amount",
            "account_codes": ["2202"],
            "agg": "sum_minus",
        },
        ctx,
    )
    assert default_val == 5000.0
    assert opt_in_val == -5000.0


# ===========================================================================
# 3) disclosure_trace 公式展开：默认不前置负号
# ===========================================================================


def test_expand_formula_default_no_leading_minus():
    """默认（无 agg / agg=sum）TB 公式展开不前置负号——v2 正数语义."""
    s_default = _expand_formula(
        {"source": "trial_balance", "field": "audited_amount", "account_codes": ["2202"]}
    )
    s_sum = _expand_formula(
        {
            "source": "trial_balance",
            "field": "audited_amount",
            "account_codes": ["2202"],
            "agg": "sum",
        }
    )
    assert s_default == "=TB('2202','audited_amount')"
    assert not s_sum.startswith("=-"), "默认聚合不应前置负号"


def test_expand_formula_sum_minus_renders_leading_minus():
    """仅显式 sum_minus 时渲染前置负号（展示串，opt-in 语义）."""
    s = _expand_formula(
        {
            "source": "trial_balance",
            "field": "audited_amount",
            "account_codes": ["2202"],
            "agg": "sum_minus",
        }
    )
    assert s.startswith("=-")
