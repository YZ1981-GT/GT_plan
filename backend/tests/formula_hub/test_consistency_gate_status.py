"""一致性门禁五态模型静态守卫与真 PG 级联。

任务 37 — AST 三条静态守卫 + 真 PG 级联测试。
变异 #39：@_guarded 去保存点 → 级联用例红。
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

# ── 路径 ──
_GATE_PKG = Path(__file__).resolve().parents[2] / "app" / "services" / "consistency_gate"
_IMPL = _GATE_PKG / "_impl.py"
_MODELS = _GATE_PKG / "_models.py"


# ════════════════════════════════════════════
# AST 静态守卫
# ════════════════════════════════════════════


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text("utf-8"), str(path))


class TestASTGuards:
    """三条 AST 守卫（需求 16.2）"""

    def test_no_direct_checkitem_outside_models(self):
        """_models 之外不得直接构造 CheckItem("""
        tree = _parse(_IMPL)
        violations = []
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "CheckItem"
            ):
                violations.append(node.lineno)
        assert violations == [], (
            f"_impl.py 仍有 {len(violations)} 处直接 CheckItem 构造: 行 {violations}"
        )

    def test_no_ok_in_except_block(self):
        """except 块内不得调用 _ok"""
        tree = _parse(_IMPL)
        violations = []
        except_depth = [0]
        current_method = [None]

        class Visitor(ast.NodeVisitor):
            def visit_AsyncFunctionDef(self, node):
                if node.name.startswith("check_"):
                    old = current_method[0]
                    current_method[0] = node.name
                    self.generic_visit(node)
                    current_method[0] = old
                else:
                    self.generic_visit(node)

            def visit_ExceptHandler(self, node):
                except_depth[0] += 1
                self.generic_visit(node)
                except_depth[0] -= 1

            def visit_Call(self, node):
                if (
                    except_depth[0] > 0
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "_ok"
                ):
                    violations.append(
                        f"{current_method[0]}:{node.lineno}"
                    )
                self.generic_visit(node)

        Visitor().visit(tree)
        assert violations == [], (
            f"except 块内调用 _ok: {violations}"
        )

    def test_all_check_methods_have_guarded(self):
        """每个 check_* 方法必须有 @_guarded 装饰器"""
        tree = _parse(_IMPL)
        missing = []
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name.startswith("check_"):
                has_guarded = any(
                    isinstance(d, ast.Call)
                    and isinstance(d.func, ast.Name)
                    and d.func.id == "_guarded"
                    for d in node.decorator_list
                )
                if not has_guarded:
                    missing.append(node.name)
        assert missing == [], f"缺少 @_guarded: {missing}"


# ════════════════════════════════════════════
# 真 PG 级联测试
# ════════════════════════════════════════════

# 🔴 2026-10-31 第 2 轮补：原先这里只有夹具与辅助函数、没有任何用例（另有一个从未被引用的自定义 skipif），
#    变异 #39 记录的「级联用例红」无从发生。下面是真用例：pg_only，快照库回滚事务。
@pytest.mark.pg_only
class TestConsistencyGateStatusPG:
    """真 PG 级联：第一个检查方法里 SQL 出错 ⇒ 该项 error、其余各项与不注入时相同（变异 #39 的判据）。

    注入经生产 ``_guarded`` 包装：保存点在，失败的语句只回滚到保存点；去掉保存点，PG 事务进入 aborted 状态，
    后面每项检查的第一条查询都失败 ⇒ 全变 error。
    """

    @staticmethod
    def _states(result) -> list[tuple[str, str]]:
        return [(c.check_name, c.status) for c in result.checks]

    @pytest.mark.asyncio
    async def test_sql_error_in_first_check_does_not_cascade(self, pg_tx):
        from unittest.mock import patch

        from sqlalchemy import text

        from app.services.consistency_gate import ConsistencyGate
        from app.services.consistency_gate._helpers import _guarded
        from tests.formula_hub.gate_fixtures import seed_test_project

        pid, year = await seed_test_project(pg_tx, name="【测试】FH-gate-cascade")
        gate = ConsistencyGate(pg_tx)
        baseline = self._states(await gate.run_all_checks(pid, year))
        rest = baseline[1:]
        assert baseline[0][0] == "试算平衡" and rest, baseline
        assert any(status != "error" for _, status in rest), f"不注入时其余各项已是 error，判据空转：{rest}"

        async def _bad_sql(self_arg, project_id, yr):
            await self_arg.db.execute(text("SELECT 1 FROM fh_cascade_no_such_table"))

        with patch.object(type(gate), "check_tb_balance", _guarded("tb_balance")(_bad_sql)):
            injected = await gate.run_all_checks(pid, year)
        first = injected.checks[0]
        assert (first.status, first.branch_id) == ("error", "tb_balance.exception"), first
        assert "ProgrammingError" in first.reason, first.reason
        assert self._states(injected)[1:] == rest, "第一项 SQL 失败连带了后面的检查（保存点失效）"
