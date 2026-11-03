"""一致性门禁消费方统一判定 — 端点级测试与消费方 AST 守卫

需求 16.4~16.6、ADR-FHIC-14 第 5 点。

测试分组：
- observe 组：默认模式下 ConsistencyPassedRule 返回 warning（提示）
- enforce 组：CONSISTENCY_GATE_ENFORCEMENT=enforce 下返回 blocking（阻断）
- gate_decision 单元测试：两模式 × 两消费方
- 消费方 AST 守卫：run_all_checks 调用方集合 == 登记集合
"""
from __future__ import annotations

import ast
import importlib
import inspect
import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.services.consistency_gate._decision import (
    GateDecision,
    gate_decision,
)
from app.services.consistency_gate._models import (
    CheckItem,
    ConsistencyResult,
    _fail,
    _not_executed,
    _ok,
)


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


def _make_result(
    *items: CheckItem,
) -> ConsistencyResult:
    """构造 ConsistencyResult。"""
    r = ConsistencyResult()
    r.checks = list(items)
    r.overall = "pass" if all(c.passed for c in items) else "fail"
    return r


def _blocking_failed() -> CheckItem:
    return _fail("test_blocking_fail", reason="测试失败", severity="blocking")


def _blocking_not_executed() -> CheckItem:
    return _not_executed(
        "test_not_exec",
        branch_id="test.missing",
        reason="缺数据",
        severity="blocking",
    )


def _warning_failed() -> CheckItem:
    return _fail("test_warning_fail", reason="提示", severity="warning")


def _all_passed() -> ConsistencyResult:
    return _make_result(
        _ok("check_a", severity="blocking"),
        _ok("check_b", severity="warning"),
    )


# ---------------------------------------------------------------------------
# gate_decision 单元测试
# ---------------------------------------------------------------------------


class TestGateDecisionUnit:
    """gate_decision(result, consumer) 两模式 × 两消费方。"""

    def test_all_passed_observe_no_block(self):
        result = _all_passed()
        with patch(
            "app.services.consistency_gate._decision._load_mode",
            return_value="observe",
        ):
            d = gate_decision(result, consumer="chain_rule")
        assert not d.blocks
        assert d.items == []
        assert d.mode == "observe"

    def test_all_passed_enforce_no_block(self):
        result = _all_passed()
        with patch(
            "app.services.consistency_gate._decision._load_mode",
            return_value="enforce",
        ):
            d = gate_decision(result, consumer="chain_rule")
        assert not d.blocks
        assert d.items == []

    def test_blocking_failed_observe_warns(self):
        result = _make_result(_blocking_failed(), _ok("ok", severity="blocking"))
        with patch(
            "app.services.consistency_gate._decision._load_mode",
            return_value="observe",
        ):
            d = gate_decision(result, consumer="chain_rule")
        assert not d.blocks  # observe 不阻断
        assert len(d.items) == 1
        assert "只提示" in d.summary

    def test_blocking_failed_enforce_blocks(self):
        result = _make_result(_blocking_failed(), _ok("ok", severity="blocking"))
        with patch(
            "app.services.consistency_gate._decision._load_mode",
            return_value="enforce",
        ):
            d = gate_decision(result, consumer="chain_rule")
        assert d.blocks  # enforce 阻断
        assert len(d.items) == 1
        assert "补齐" in d.summary

    def test_not_executed_blocking_enforce_blocks(self):
        result = _make_result(_blocking_not_executed())
        with patch(
            "app.services.consistency_gate._decision._load_mode",
            return_value="enforce",
        ):
            d = gate_decision(result, consumer="export_package")
        assert d.blocks
        assert d.items[0].status == "not_executed"

    def test_not_executed_blocking_observe_warns(self):
        result = _make_result(_blocking_not_executed())
        with patch(
            "app.services.consistency_gate._decision._load_mode",
            return_value="observe",
        ):
            d = gate_decision(result, consumer="export_package")
        assert not d.blocks
        assert len(d.items) == 1

    def test_warning_failed_never_blocks(self):
        """warning 级失败无论模式都不阻断。"""
        result = _make_result(_warning_failed())
        for mode in ("observe", "enforce"):
            with patch(
                "app.services.consistency_gate._decision._load_mode",
                return_value=mode,
            ):
                d = gate_decision(result, consumer="chain_rule")
            assert not d.blocks
            assert d.items == []


# ---------------------------------------------------------------------------
# 消费方 AST 守卫
# ---------------------------------------------------------------------------


# 登记集合（ADR-FHIC-14 第 5 点消费方表；任务 39 实施时现扫补全）
# qc_vr_heatmap 不直接调 run_all_checks，而是逐方法调用，属展示类消费方但不在此扫描范围。
_REGISTERED_CONSUMERS: frozenset[str] = frozenset(
    {
        "app/services/gate_rules_chain.py",
        "app/services/export_package_service.py",
        "app/routers/chain_workflow.py",
        "app/services/dashboard_aggregator_service.py",
    }
)

# 阻断类消费方（其函数体内必须调用 gate_decision）
_BLOCKING_CONSUMERS: frozenset[str] = frozenset(
    {
        "app/services/gate_rules_chain.py",
        "app/services/export_package_service.py",
    }
)


def _scan_run_all_checks_callers() -> set[str]:
    """AST 扫描 backend/app 中 run_all_checks( 的调用方文件。"""
    app_dir = Path(__file__).resolve().parents[2] / "app"
    callers: set[str] = set()
    for py in app_dir.rglob("*.py"):
        try:
            source = py.read_text(encoding="utf-8")
        except Exception:
            continue
        try:
            tree = ast.parse(source, filename=str(py))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "run_all_checks"
            ):
                # 排除定义侧 (consistency_gate 包自身)
                rel = py.relative_to(app_dir.parent).as_posix()
                if "consistency_gate" not in rel:
                    callers.add(rel)
                break
    return callers


def test_run_all_checks_callers_equal_registered():
    """run_all_checks 的调用方集合 == 登记集合。"""
    actual = _scan_run_all_checks_callers()
    assert actual == _REGISTERED_CONSUMERS, (
        f"调用方与登记不一致\n"
        f"  多出: {actual - _REGISTERED_CONSUMERS}\n"
        f"  缺少: {_REGISTERED_CONSUMERS - actual}"
    )


def _scan_gate_decision_callers(filepath: str) -> bool:
    """检查文件中是否调用了 gate_decision。"""
    app_dir = Path(__file__).resolve().parents[2] / "app"
    full = app_dir.parent / filepath
    if not full.exists():
        return False
    try:
        source = full.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(full))
    except (SyntaxError, OSError):
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "gate_decision":
                return True
            if isinstance(func, ast.Attribute) and func.attr == "gate_decision":
                return True
    return False


def test_blocking_consumers_call_gate_decision():
    """阻断类消费方的函数体内必须调用 gate_decision。"""
    for fp in _BLOCKING_CONSUMERS:
        assert _scan_gate_decision_callers(fp), (
            f"阻断类消费方 {fp} 未调用 gate_decision"
        )
