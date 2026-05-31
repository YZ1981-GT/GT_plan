"""B2 worksheet ↔ trial 对账 — 纯函数单元测试（consol-phase0-core-pipeline 任务 4）

只验证 `_reconcile_amounts` 的纯逻辑（喂内存字典 + tolerance），不依赖真实 PG / DB。
完整 PBT P4（对账等价）见任务 10。

覆盖场景：
  ① 完全一致 → is_reconciled=true，diffs 空
  ② 某科目超容差 → is_reconciled=false，该科目进 diffs
  ③ diff 恰好等于 tolerance → 不进 diffs（`<=` 边界，diff > tolerance 才算）
  ④ 只在一侧存在的科目（另一侧视为 ZERO）
  ⑤ max_abs_diff 计算正确

Validates: Requirements 3.1, 3.2, 3.4
"""

from decimal import Decimal

from app.services.consol_reconciliation_service import (
    ZERO,
    ReconciliationResult,
    _reconcile_amounts,
)

TOL = Decimal("0.01")


def test_fully_reconciled_returns_empty_diffs():
    """① 两侧科目金额完全一致 → is_reconciled=true，diffs 空，max_abs_diff=0。"""
    ws = {"1001": Decimal("100.00"), "1002": Decimal("200.00")}
    trial = {"1001": Decimal("100.00"), "1002": Decimal("200.00")}

    result = _reconcile_amounts(ws, trial, TOL)

    assert isinstance(result, ReconciliationResult)
    assert result.is_reconciled is True
    assert result.diffs == []
    assert result.max_abs_diff == ZERO
    assert result.tolerance == TOL


def test_account_over_tolerance_enters_diffs():
    """② 某科目差异超容差 → is_reconciled=false，该科目进 diffs，字段为 str(Decimal)。"""
    ws = {"1001": Decimal("100.00"), "1002": Decimal("200.00")}
    trial = {"1001": Decimal("100.00"), "1002": Decimal("150.00")}  # 1002 差 50

    result = _reconcile_amounts(ws, trial, TOL)

    assert result.is_reconciled is False
    assert len(result.diffs) == 1
    diff = result.diffs[0]
    assert diff["account_code"] == "1002"
    assert diff["worksheet_amount"] == "200.00"
    assert diff["trial_amount"] == "150.00"
    assert diff["diff"] == "50.00"
    # 一致的科目 1001 不进 diffs
    assert all(d["account_code"] != "1001" for d in result.diffs)


def test_diff_exactly_equals_tolerance_not_in_diffs():
    """③ diff 恰好等于 tolerance → 不进 diffs（边界：仅 abs(d) > tolerance 才算）。"""
    ws = {"1001": Decimal("100.01")}
    trial = {"1001": Decimal("100.00")}  # diff = 0.01 == tolerance

    result = _reconcile_amounts(ws, trial, TOL)

    assert result.is_reconciled is True
    assert result.diffs == []
    # max_abs_diff 仍记录该差异（== tolerance）
    assert result.max_abs_diff == Decimal("0.01")


def test_diff_just_over_tolerance_enters_diffs():
    """③b diff 略超 tolerance（0.02 > 0.01）→ 进 diffs（确认严格大于判定）。"""
    ws = {"1001": Decimal("100.02")}
    trial = {"1001": Decimal("100.00")}  # diff = 0.02 > tolerance

    result = _reconcile_amounts(ws, trial, TOL)

    assert result.is_reconciled is False
    assert len(result.diffs) == 1
    assert result.diffs[0]["account_code"] == "1001"


def test_account_only_on_one_side_treated_as_zero():
    """④ 只在一侧存在的科目 → 另一侧视为 ZERO，差额 = 该侧金额。"""
    ws = {"1001": Decimal("100.00"), "3001": Decimal("80.00")}  # 3001 仅 worksheet 有
    trial = {"1001": Decimal("100.00"), "4001": Decimal("60.00")}  # 4001 仅 trial 有

    result = _reconcile_amounts(ws, trial, TOL)

    assert result.is_reconciled is False
    codes = {d["account_code"] for d in result.diffs}
    # 3001（ws 80 vs trial 0）和 4001（ws 0 vs trial 60）都进 diffs
    assert codes == {"3001", "4001"}

    by_code = {d["account_code"]: d for d in result.diffs}
    assert by_code["3001"]["worksheet_amount"] == "80.00"
    assert by_code["3001"]["trial_amount"] == "0"
    assert by_code["3001"]["diff"] == "80.00"
    assert by_code["4001"]["worksheet_amount"] == "0"
    assert by_code["4001"]["trial_amount"] == "60.00"
    assert by_code["4001"]["diff"] == "-60.00"


def test_max_abs_diff_is_largest_absolute_difference():
    """⑤ max_abs_diff = 所有科目 |ws - trial| 的最大值（含负数差额取绝对值）。"""
    ws = {
        "1001": Decimal("100.00"),   # diff 0
        "1002": Decimal("200.00"),   # diff +30 vs 170
        "1601": Decimal("-50.00"),   # diff -120 vs 70  → abs 120 最大
    }
    trial = {
        "1001": Decimal("100.00"),
        "1002": Decimal("170.00"),
        "1601": Decimal("70.00"),
    }

    result = _reconcile_amounts(ws, trial, TOL)

    assert result.is_reconciled is False
    # 最大绝对差额来自 1601：|-50 - 70| = 120
    assert result.max_abs_diff == Decimal("120.00")


def test_empty_inputs_reconciled():
    """边界：两侧均空 → 视为对平。"""
    result = _reconcile_amounts({}, {}, TOL)

    assert result.is_reconciled is True
    assert result.diffs == []
    assert result.max_abs_diff == ZERO


def test_is_reconciled_equals_max_abs_le_tolerance():
    """属性预演（P4 核心）：is_reconciled == (max_abs_diff <= tolerance)。"""
    # 全部 diff <= tolerance
    ws = {"1001": Decimal("100.01"), "1002": Decimal("200.00")}
    trial = {"1001": Decimal("100.00"), "1002": Decimal("200.00")}
    result = _reconcile_amounts(ws, trial, TOL)
    assert result.is_reconciled == (result.max_abs_diff <= TOL)
    assert result.is_reconciled is True

    # 存在 diff > tolerance
    ws2 = {"1001": Decimal("100.50")}
    trial2 = {"1001": Decimal("100.00")}
    result2 = _reconcile_amounts(ws2, trial2, TOL)
    assert result2.is_reconciled == (result2.max_abs_diff <= TOL)
    assert result2.is_reconciled is False
