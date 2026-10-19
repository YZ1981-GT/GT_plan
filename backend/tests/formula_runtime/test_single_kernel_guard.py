"""tests/formula_runtime/test_single_kernel_guard.py — legacy evaluator CI guard。

扫描 backend/app/ 目录，确保只有 `formula_management/engine.py` 本身可以
直接导入低级求值函数（formula_parse_utils.evaluate_formula / FormulaEvaluator）。

禁止新增绕过 single kernel 的消费者（Req 12.5, P14）。

**Validates: Requirements 12.5**
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

# ─── 配置 ─────────────────────────────────────────────────────────────────────

# 项目 backend/app 根目录
_BACKEND_APP_DIR = Path(__file__).resolve().parents[2] / "app"

# check 脚本目录要进 sys.path：CI 脚本内部有 `from _spec_dir import` /
# `from _single_kernel_policy import`，被本测试用 importlib 加载时需要能解析它们
# （脚本自己作为 __main__ 跑时 sys.path[0] 即脚本目录，故平时无碍）。
_CHECK_DIR = Path(__file__).resolve().parents[2] / "scripts" / "check"
if str(_CHECK_DIR) not in sys.path:
    sys.path.insert(0, str(_CHECK_DIR))


def _load_single_kernel_policy():
    """从单一来源 backend/scripts/check/_single_kernel_policy.py 加载策略。

    白名单与保护 import 正则不在本文件维护拷贝——两个守卫（本 pytest + CI strict
    脚本）共用同一来源，根除历史上出现过的漂移（CI 缺 note_source_resolvers 豁免
    → pytest 绿而 CI 恒红）。
    """
    policy_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "check" / "_single_kernel_policy.py"
    )
    spec = importlib.util.spec_from_file_location("_single_kernel_policy", policy_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_POLICY = _load_single_kernel_policy()

# 被保护的低级求值符号（只能被 ALLOWED_FILES 中的文件直接导入）—— 来自单一来源
_PROTECTED_IMPORTS = list(_POLICY.PROTECTED_IMPORT_PATTERNS)

# 允许直接导入的文件（唯一合法消费者）—— 来自单一来源（含 note_source_resolvers 豁免论证）
_ALLOWED_FILES = set(_POLICY.ALLOWED_FILES)


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

    def test_ci_strict_guard_uses_single_source(self):
        """CI strict 脚本与本守卫都必须真的用同一个单一来源的白名单。

        白名单与保护模式已收敛到 backend/scripts/check/_single_kernel_policy.py。
        本断言验证三者相等：单一来源 == 本 pytest 守卫实际用的 == CI 脚本实际用的。
        这既保证一致性，又防止将来有人把任一侧改回本地拷贝（改回后值可能仍恰好相等，
        但下面的 `is 同一对象` 断言会抓住"没真的用单一来源"这件事）。
        历史：曾因 CI 缺 note_source_resolvers 豁免而 pytest 绿、CI strict 恒红。
        """
        policy_allow = set(_POLICY.ALLOWED_FILES)
        pytest_allow = set(_ALLOWED_FILES)

        script_path = (
            Path(__file__).resolve().parents[3]
            / "backend"
            / "scripts"
            / "check"
            / "check_formula_runtime_completion.py"
        )
        assert script_path.exists(), f"CI 守卫脚本不存在: {script_path}"

        spec = importlib.util.spec_from_file_location(
            "_check_formula_runtime_completion", script_path
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        ci_allow = set(module._KERNEL_ALLOWED_FILES)

        assert pytest_allow == policy_allow == ci_allow, (
            "single-kernel 白名单与单一来源不一致:\n"
            f"  仅单一来源有: {sorted(policy_allow - (pytest_allow & ci_allow))}\n"
            f"  仅 pytest 有:  {sorted(pytest_allow - policy_allow)}\n"
            f"  仅 CI 脚本有:  {sorted(ci_allow - policy_allow)}\n"
            "两处都应 `from _single_kernel_policy import ALLOWED_FILES`，不要留本地拷贝。"
        )

        # 保护 import 模式同样来自单一来源
        policy_patterns = tuple(_POLICY.PROTECTED_IMPORT_PATTERNS)
        pytest_patterns = tuple(_PROTECTED_IMPORTS)
        assert pytest_patterns == policy_patterns, (
            "保护 import 正则与单一来源漂移:\n"
            f"  单一来源: {policy_patterns}\n"
            f"  pytest:   {pytest_patterns}"
        )
