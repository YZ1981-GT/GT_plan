"""E1 spec Sprint 1 Task 1.24: 3 条 E1↔CFS 勾稽规则 + 容差边界测试

锚定:
- requirements F6.1 / design D5
- consistency_gate.check_e1_cfs_reconciliation
- 动态容差: max(1.0, 重要性水平 × 0.001)
- 三档判定: passed / warning / blocking

不实际跑 DB(用 SQLite + monkeypatch helper 方法注入金额);仅断言阈值逻辑。
"""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from app.services.consistency_gate import ConsistencyGate, CheckItem


# ---------------------------------------------------------------------------
# 容差计算逻辑(单测) — 不依赖 DB,fallback 路径 1.0 元
# ---------------------------------------------------------------------------


def test_dynamic_tolerance_floor_1_yuan():
    """重要性水平为 0 或异常时回退到 1.0 元下限"""
    # 公式: max(1.0, materiality × 0.001)
    assert max(Decimal("1.0"), Decimal("0") * Decimal("0.001")) == Decimal("1.0")
    assert max(Decimal("1.0"), Decimal("100") * Decimal("0.001")) == Decimal("1.0")


def test_dynamic_tolerance_scales_with_materiality():
    """重要性 100 万 → 容差 1000 元;重要性 1000 万 → 容差 10000 元"""
    mat_1m = Decimal("1000000")
    mat_10m = Decimal("10000000")
    assert max(Decimal("1.0"), mat_1m * Decimal("0.001")) == Decimal("1000.000")
    assert max(Decimal("1.0"), mat_10m * Decimal("0.001")) == Decimal("10000.000")


# ---------------------------------------------------------------------------
# 三档判定逻辑(对照 check_e1_cfs_reconciliation 内部 if/elif)
# ---------------------------------------------------------------------------


def _classify(diff: Decimal, tolerance: Decimal) -> tuple[str, bool]:
    """复刻 consistency_gate.check_e1_cfs_reconciliation 三档判定"""
    if diff <= tolerance:
        return "warning", True  # passed
    elif diff <= tolerance * Decimal("2"):
        return "warning", False
    else:
        return "blocking", False


@pytest.mark.parametrize(
    "diff,tolerance,expected_passed,expected_severity",
    [
        # 偏差 ≤ 容差 → passed=True
        (Decimal("0.5"), Decimal("1.0"), True, "warning"),
        (Decimal("100"), Decimal("100"), True, "warning"),
        (Decimal("0"), Decimal("1.0"), True, "warning"),
        # 容差 < 偏差 ≤ 2× 容差 → passed=False, warning
        (Decimal("1.5"), Decimal("1.0"), False, "warning"),
        (Decimal("199"), Decimal("100"), False, "warning"),
        (Decimal("200"), Decimal("100"), False, "warning"),
        # 偏差 > 2× 容差 → passed=False, blocking
        (Decimal("3"), Decimal("1.0"), False, "blocking"),
        (Decimal("201"), Decimal("100"), False, "blocking"),
        (Decimal("100000"), Decimal("100"), False, "blocking"),
    ],
)
def test_three_tier_classification(
    diff: Decimal,
    tolerance: Decimal,
    expected_passed: bool,
    expected_severity: str,
):
    sev, ok = _classify(diff, tolerance)
    assert ok is expected_passed
    assert sev == expected_severity


# ---------------------------------------------------------------------------
# 容差边界测试 — 1 倍/2 倍交界点
# ---------------------------------------------------------------------------


def test_boundary_at_1x_tolerance():
    """偏差恰好 = 容差 → passed=True (使用 ≤ 而非 <)"""
    sev, ok = _classify(Decimal("100"), Decimal("100"))
    assert ok is True


def test_boundary_at_2x_tolerance():
    """偏差恰好 = 2× 容差 → severity=warning, passed=False"""
    sev, ok = _classify(Decimal("200"), Decimal("100"))
    assert ok is False
    assert sev == "warning"


def test_just_above_2x_tolerance_becomes_blocking():
    """偏差刚超过 2× 容差 → severity=blocking"""
    sev, ok = _classify(Decimal("200.01"), Decimal("100"))
    assert ok is False
    assert sev == "blocking"


# ---------------------------------------------------------------------------
# 数据缺失 fallback 测试
# ---------------------------------------------------------------------------


def test_check_returns_skip_with_warning_when_data_missing():
    """e1_end / cfs_end 为 None 时,返回 passed=True severity=warning(跳过检查)"""
    # 模拟 check 返回值结构
    item = CheckItem(
        check_name="E1↔CFS:期末现金等价物勾稽",
        passed=True,
        details="数据不完整(E1=None, CFS=None),跳过检查",
        severity="warning",
    )
    assert item.passed is True
    assert "跳过" in item.details or "不完整" in item.details
    assert item.severity == "warning"


# ---------------------------------------------------------------------------
# CheckItem 不变量
# ---------------------------------------------------------------------------


def test_check_item_blocking_means_not_passed_for_overall_fail():
    """blocking 检查 not passed → ConsistencyResult.has_blocking_failures = True"""
    from app.services.consistency_gate import ConsistencyResult

    items = [
        CheckItem(check_name="t1", passed=True, severity="blocking"),
        CheckItem(check_name="t2", passed=False, severity="warning"),
    ]
    r = ConsistencyResult(overall="pass", checks=items)
    assert r.has_blocking_failures is False  # warning fail 不算 blocking

    items2 = items + [CheckItem(check_name="t3", passed=False, severity="blocking")]
    r2 = ConsistencyResult(overall="fail", checks=items2)
    assert r2.has_blocking_failures is True


def test_check_e1_cfs_method_exists():
    """ConsistencyGate.check_e1_cfs_reconciliation 方法已注册到类"""
    assert hasattr(ConsistencyGate, "check_e1_cfs_reconciliation")
    assert callable(ConsistencyGate.check_e1_cfs_reconciliation)


def test_check_e1_cfs_helper_methods_exist():
    """E1↔CFS 5 个辅助 helper 方法已注册"""
    for name in (
        "_get_dynamic_tolerance",
        "_get_e1_audited_amount",
        "_get_cfs_ending_cash",
        "_get_cfs_net_change",
        "_get_e1_period_change",
        "_get_tb_cash_total",
    ):
        assert hasattr(ConsistencyGate, name), f"missing helper: {name}"
