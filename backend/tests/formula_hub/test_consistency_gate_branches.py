"""一致性门禁分支清单双射守卫。

任务 37 — AST 守卫验证 _branches.BRANCHES 与 _impl.py 出口一一对应。
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

_GATE_PKG = Path(__file__).resolve().parents[2] / "app" / "services" / "consistency_gate"
_IMPL = _GATE_PKG / "_impl.py"
_BRANCHES = _GATE_PKG / "_branches.py"


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text("utf-8"), str(path))


def _extract_impl_branch_ids() -> set[str]:
    """从 _impl.py AST 提取所有分支 ID。

    规则（ADR-FHIC-14 第 4 点）：
    - @_guarded("check_id") → "{check_id}.exception"
    - _not_executed(..., branch_id="xxx") → "xxx"
    - _not_applicable(..., branch_id="xxx") → "xxx"
    """
    tree = _parse(_IMPL)
    ids: set[str] = set()

    for node in ast.walk(tree):
        # @_guarded → exception 分支
        if isinstance(node, ast.AsyncFunctionDef):
            for d in node.decorator_list:
                if (
                    isinstance(d, ast.Call)
                    and isinstance(d.func, ast.Name)
                    and d.func.id == "_guarded"
                    and d.args
                    and isinstance(d.args[0], ast.Constant)
                ):
                    ids.add(d.args[0].value + ".exception")

        # _not_executed / _not_applicable → branch_id 参数
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in ("_not_executed", "_not_applicable"):
                for kw in node.keywords:
                    if kw.arg == "branch_id" and isinstance(kw.value, ast.Constant):
                        ids.add(kw.value.value)

    return ids


def _extract_branches_registry() -> set[str]:
    """从 _branches.py 的 BRANCHES dict 提取键集合"""
    from app.services.consistency_gate._branches import BRANCHES
    return set(BRANCHES.keys())


class TestBranchBijection:
    """分支清单与源码出口双射"""

    def test_impl_branch_ids_eq_registry(self):
        """AST 提取的分支 ID 集合 == BRANCHES 键集合"""
        impl_ids = _extract_impl_branch_ids()
        reg_ids = _extract_branches_registry()

        only_in_impl = impl_ids - reg_ids
        only_in_reg = reg_ids - impl_ids

        assert only_in_impl == set(), (
            f"_impl.py 有但 _branches.py 没有: {sorted(only_in_impl)}"
        )
        assert only_in_reg == set(), (
            f"_branches.py 有但 _impl.py 没有: {sorted(only_in_reg)}"
        )

    def test_branch_ids_are_string_literals(self):
        """branch_id 实参与 @_guarded 实参必须是字符串字面量"""
        tree = _parse(_IMPL)
        violations = []

        for node in ast.walk(tree):
            # @_guarded 参数
            if isinstance(node, ast.AsyncFunctionDef):
                for d in node.decorator_list:
                    if (
                        isinstance(d, ast.Call)
                        and isinstance(d.func, ast.Name)
                        and d.func.id == "_guarded"
                    ):
                        if not d.args or not isinstance(d.args[0], ast.Constant):
                            violations.append(
                                f"@_guarded 非字面量参数: {node.name}:{d.lineno}"
                            )

            # _not_executed / _not_applicable 的 branch_id
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in ("_not_executed", "_not_applicable"):
                    for kw in node.keywords:
                        if kw.arg == "branch_id":
                            if not isinstance(kw.value, ast.Constant):
                                violations.append(
                                    f"{node.func.id} branch_id 非字面量: L{node.lineno}"
                                )

        assert violations == [], f"非字面量分支 ID: {violations}"

    def test_branch_count(self):
        """分支总数 = 跳过/子异常分支 + 方法级异常分支"""
        impl_ids = _extract_impl_branch_ids()
        # 方法级异常：形如 "check_id.exception"（恰好 2 部分）
        method_exception_ids = {
            bid for bid in impl_ids
            if bid.endswith(".exception") and bid.count(".") == 1
        }
        other_ids = impl_ids - method_exception_ids

        # 方法异常 = check 方法数（16）
        assert len(method_exception_ids) == 16, (
            f"方法级异常分支应为 16，实为 {len(method_exception_ids)}"
        )
        # 其余分支（跳过 + 子检查异常）
        assert len(other_ids) > 0, "非方法级分支不应为空"
        # 总计
        assert len(impl_ids) == len(other_ids) + 16


# ---------------------------------------------------------------------------
# 参数化逐分支测试（需求 16.3，任务 38）
# ---------------------------------------------------------------------------

import asyncio
from unittest.mock import AsyncMock, patch

import pytest_asyncio

from tests.formula_hub.gate_fixtures import BRANCH_FIXTURES


def _tb_branch_ids() -> list[str]:
    """只返回 tb_balance 相关的分支 ID"""
    return sorted(BRANCH_FIXTURES.keys())


@pytest.mark.pg_only
class TestTbBalanceBranchTrigger:
    """每个 tb_balance 登记分支都由夹具触发并产出正确的 branch_id / status"""

    @pytest_asyncio.fixture(autouse=True)
    async def _gate(self, pg_tx):
        from app.services.consistency_gate._gate import ConsistencyGate
        self.gate = ConsistencyGate(pg_tx)
        self.db = pg_tx

    @pytest.mark.parametrize("branch_id", _tb_branch_ids())
    @pytest.mark.asyncio
    async def test_branch_produces_expected_status(self, branch_id):
        fixture_fn, expected_status = BRANCH_FIXTURES[branch_id]

        pid, year = await fixture_fn(self.db)

        if expected_status == "error":
            # 注入异常：让方法体抛错，由 @_guarded 捕获
            from app.services.consistency_gate._helpers import _guarded

            async def _inject_error(self_arg, project_id, yr):
                raise RuntimeError("injected SQL error for test")

            wrapped = _guarded("tb_balance")(_inject_error)
            with patch.object(
                self.gate.__class__, "check_tb_balance", wrapped,
            ):
                item = await self.gate.check_tb_balance(pid, year)
        else:
            item = await self.gate.check_tb_balance(pid, year)

        assert item.status == expected_status, (
            f"branch {branch_id}: 预期 {expected_status}，实得 {item.status}\n"
            f"  reason={item.reason}\n  branch_id={item.branch_id}"
        )
        if expected_status == "error":
            assert item.branch_id == "tb_balance.exception", (
                f"exception branch_id 应为 tb_balance.exception，"
                f"实得 {item.branch_id}"
            )
        else:
            assert item.branch_id == branch_id, (
                f"branch {branch_id}: 预期 branch_id={branch_id}，"
                f"实得 {item.branch_id}"
            )
