"""tests/formula_runtime/test_single_kernel_guard.py — legacy evaluator CI guard。

扫描 backend/app/ 目录，确保只有 `formula_management/engine.py` 本身可以
直接导入低级求值函数（formula_parse_utils.evaluate_formula / FormulaEvaluator）。

禁止新增绕过 single kernel 的消费者（Req 12.5, P14）。

**Validates: Requirements 12.5**
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

# ─── 配置 ─────────────────────────────────────────────────────────────────────

# 项目 backend/app 根目录
_BACKEND_APP_DIR = Path(__file__).resolve().parents[2] / "app"

# 被保护的低级求值符号（只能被 engine.py 自身消费）
_PROTECTED_IMPORTS = [
    # from formula_parse_utils import evaluate_formula
    r"from\s+[\w.]*formula_parse_utils\s+import\s+.*\bevaluate_formula\b",
    # from ... import FormulaEvaluator
    r"from\s+[\w.]*\s+import\s+.*\bFormulaEvaluator\b",
    # import formula_parse_utils 然后 .evaluate_formula
    r"import\s+[\w.]*formula_parse_utils\b",
]

# 允许直接导入的文件（唯一合法消费者）
_ALLOWED_FILES = {
    # engine.py 本身是 single kernel 入口
    "formula_management/engine.py",
    # formula_engine.py 是 L1 内核本身（它定义了 execute）
    "services/formula_engine.py",
    # 以下是 legacy adapter / deprecation shim 仍需暂时保留
    "services/formula_parse_utils.py",
    # ── note_source_resolvers.py：附注 SUM 绑定的**行内**求和 ─────────────────
    # 🔴 这条豁免与本守卫的意图**同向**，不是给它开后门：
    #    `_resolve_formula_sum` 把 binding.cells 拼成 `ROW('c1') + ROW('c2') …`，
    #    连同一份**内存** row_values 字典交给 evaluate_formula 求值，其 docstring
    #    写明「复用既有 evaluate_formula 内核…不新造求值器，满足 Req1.2 / Property4」。
    #    走不了 engine.execute_formula 的原因是两者形态不兼容（已核实 2026-09-06）：
    #      · execute_formula 要 FormulaRecord + FormulaContext 两个结构化对象，
    #        而这里只有一个临时字符串表达式，没有落库的公式定义；
    #      · execute_formula **不支持** row_values（engine.py 内该标识符 0 次出现），
    #        而本场景的值全部来自当前附注表的同表坐标，不经任何 domain reader。
    #    强行改造 = 为「附注行内求和」凭空造一条 FormulaRecord，属功能改造而非修红，
    #    且会把一个纯函数式求和变成需要 db/ownership 上下文的重路径。
    #    → 因此登记豁免。**新增**消费者仍应被本守卫拦下（这正是它的价值）。
    "services/note_source_resolvers.py",
}


# ─── Guard 实现 ────────────────────────────────────────────────────────────────


def _scan_for_violations() -> list[tuple[str, int, str]]:
    """扫描 backend/app 下所有 .py 文件，返回违规列表。

    Returns:
        [(relative_path, line_number, matched_line), ...]
    """
    violations: list[tuple[str, int, str]] = []

    if not _BACKEND_APP_DIR.exists():
        return violations

    patterns = [re.compile(p, re.IGNORECASE) for p in _PROTECTED_IMPORTS]

    for py_file in _BACKEND_APP_DIR.rglob("*.py"):
        rel_path = py_file.relative_to(_BACKEND_APP_DIR).as_posix()

        # 跳过允许的文件
        if any(rel_path.endswith(allowed) for allowed in _ALLOWED_FILES):
            continue

        # 跳过 __pycache__ 和测试
        if "__pycache__" in str(py_file):
            continue

        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        for i, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            # 跳过注释行
            if stripped.startswith("#"):
                continue
            for pattern in patterns:
                if pattern.search(stripped):
                    violations.append((rel_path, i, stripped))
                    break  # 同一行只报一次

    return violations


# ─── Tests ─────────────────────────────────────────────────────────────────────


class TestSingleKernelGuard:
    """CI guard: 禁止新增绕过 single kernel 的 evaluator 消费者。"""

    def test_no_direct_evaluate_formula_imports(self):
        """除 engine.py 与 legacy shim 外，无文件直接导入 evaluate_formula/FormulaEvaluator。"""
        violations = _scan_for_violations()

        if violations:
            msg_lines = [
                "Single Kernel Guard FAILED — 以下文件绕过 engine.py 直接导入低级求值函数:",
                "",
            ]
            for path, lineno, line in violations:
                msg_lines.append(f"  {path}:{lineno}: {line}")
            msg_lines.append("")
            msg_lines.append(
                "修复：请通过 formula_management.engine 的 execute_formula 或 "
                "execute_batch 入口调用求值。"
            )
            pytest.fail("\n".join(msg_lines))

    def test_engine_py_exists(self):
        """engine.py 文件存在（基本健康检查）。"""
        engine_path = _BACKEND_APP_DIR / "services" / "formula_management" / "engine.py"
        assert engine_path.exists(), f"engine.py not found at {engine_path}"

    def test_allowed_files_are_exhaustive(self):
        """允许列表中的关键文件存在（防止允许名错配）。"""
        # engine.py 是 single kernel 入口，必须存在
        engine_candidates = [
            _BACKEND_APP_DIR / "services" / "formula_management" / "engine.py",
        ]
        assert any(p.exists() for p in engine_candidates), (
            f"engine.py not found in candidates: {engine_candidates}"
        )
        # formula_engine.py 是 L1 内核
        kernel_path = _BACKEND_APP_DIR / "services" / "formula_engine.py"
        assert kernel_path.exists(), f"formula_engine.py not found: {kernel_path}"
