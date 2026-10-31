"""S2 Task 4 (ADR-CCN-07 + ADR-CCN-05)：门禁规则异常不再放行 — AST 守卫 + 表间审核严重度守卫。

AST 守卫：gate_rules*.py 的 check() 内捕获 Exception 的处理块不得 return None。
28 处处理器已全部改为 self.not_executed(reason)。

表间审核守卫（ADR-CCN-05）：
- cross_check 域 exec_fields 含 severity
- 签字 / 导出门禁不读 cross_check_results（钉住现状）
- 预置规则均含 severity 缺省 warning
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

_SERVICES = Path(__file__).resolve().parents[1] / "app" / "services"
_GATE_RULE_FILES = sorted(_SERVICES.glob("gate_rules*.py"))
_DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _find_return_none_in_except(source_text: str) -> list[dict]:
    """找到 check() 方法内 except 块中的 return None 调用。

    返回 [{file_rel, method, lineno}]。
    """
    tree = ast.parse(source_text)
    violations: list[dict] = []

    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self._in_check = False
            self._except_depth = 0
            self._current_method = ""

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
            if node.name == "check":
                old = (self._in_check, self._current_method)
                self._in_check = True
                self._current_method = node.name
                self.generic_visit(node)
                self._in_check, self._current_method = old
            else:
                self.generic_visit(node)

        def visit_ExceptHandler(self, node: ast.ExceptHandler):
            if not self._in_check:
                self.generic_visit(node)
                return
            self._except_depth += 1
            self.generic_visit(node)
            self._except_depth -= 1

        def visit_Return(self, node: ast.Return):
            if (
                self._in_check
                and self._except_depth > 0
                and isinstance(node.value, ast.Constant)
                and node.value.value is None
            ):
                violations.append({
                    "method": self._current_method,
                    "lineno": node.lineno,
                })
            self.generic_visit(node)

    Visitor().visit(tree)
    return violations


class TestGateRulesNoSilentSwallow:
    """AST 守卫：gate_rules*.py check() 内 except 不得 return None"""

    @pytest.mark.parametrize("path", _GATE_RULE_FILES, ids=lambda p: p.name)
    def test_no_return_none_in_except(self, path: Path):
        src = path.read_text("utf-8")
        violations = _find_return_none_in_except(src)
        assert violations == [], (
            f"{path.name} 仍有 {len(violations)} 处 check() 内 except return None: "
            f"{violations}"
        )

    def test_gate_rule_files_found(self):
        """确保至少找到 7 个 gate_rules 文件"""
        assert len(_GATE_RULE_FILES) >= 7, (
            f"只找到 {len(_GATE_RULE_FILES)} 个 gate_rules*.py，预期 ≥ 7"
        )

    def test_violating_sample_detected(self):
        """自检：构造违规代码，守卫必须检测到"""
        bad_code = """
class FakeRule:
    async def check(self, db, ctx):
        try:
            pass
        except Exception:
            return None
"""
        violations = _find_return_none_in_except(bad_code)
        assert len(violations) == 1, "守卫未检测到 except 块内的 return None"

    def test_not_executed_call_not_flagged(self):
        """self.not_executed() 调用不应被标记"""
        good_code = """
class FakeRule:
    async def check(self, db, ctx):
        try:
            pass
        except Exception as e:
            return self.not_executed(str(e))
"""
        violations = _find_return_none_in_except(good_code)
        assert violations == []


# ════════════════════════════════════════════
# ADR-CCN-05：表间审核严重度守卫
# ════════════════════════════════════════════


class TestCrossCheckSeverityInDomain:
    """cross_check 域 exec_fields 必须包含 severity"""

    def test_severity_in_exec_fields(self):
        from app.services.formula_settings.definitions import DOMAINS
        spec = DOMAINS["cross_check"]
        assert "severity" in spec.exec_fields, (
            f"cross_check DomainSpec exec_fields 缺少 severity: {spec.exec_fields}"
        )


class TestPresetRulesHaveSeverity:
    """预置表间审核规则均含 severity 缺省 warning"""

    def test_all_presets_have_severity(self):
        data = json.loads((_DATA_DIR / "cross_check_preset_rules.json").read_text("utf-8"))
        for r in data["rules"]:
            assert "severity" in r, f"预置规则 {r.get('label')} 缺少 severity"
            assert r["severity"] == "warning", (
                f"预置规则 {r.get('label')} severity 应为 warning，实为 {r['severity']}"
            )


class TestSignOffExportDoNotReadCrossCheck:
    """守卫：签字/导出门禁不消费 cross_check_results（ADR-CCN-05 钉住现状）

    扫描 gate_rules*.py（不含 gate_rules_cross_check.py 本身——它 *是* cross_check 规则），
    确认不引用 cross_check_results 表名。
    """

    @pytest.mark.parametrize(
        "path",
        [p for p in _GATE_RULE_FILES if "cross_check" not in p.name],
        ids=lambda p: p.name,
    )
    def test_no_cross_check_results_reference(self, path: Path):
        src = path.read_text("utf-8")
        assert "cross_check_results" not in src, (
            f"{path.name} 引用了 cross_check_results —— "
            f"签字/导出门禁不应读表间审核结果（ADR-CCN-05）"
        )
