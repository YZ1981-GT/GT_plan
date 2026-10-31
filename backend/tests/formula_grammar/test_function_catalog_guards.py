"""S1 ADR-FGR-01 守卫：函数目录是唯一来源。

1. 目录键集合 == _REGISTRY 内置键集合
2. 生成文件 --check 无差异
3. 前端 formulaSyntaxParser.ts 不得出现函数名字面量集合（KNOWN_FUNCTIONS / FUNCTION_ARITY 已删）
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]  # 仓库根
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "audit-platform" / "frontend"


class TestCatalogKeysMatchRegistry:
    """目录 L1 函数名 == _REGISTRY 内置键。"""

    def test_l1_names_equal_registry_keys(self):
        from app.services.formula_function_catalog import L1_FUNCTION_NAMES
        from app.services.formula_engine import _REGISTRY

        registry_keys = frozenset(_REGISTRY._handlers.keys())
        assert L1_FUNCTION_NAMES == registry_keys, (
            f"目录多: {L1_FUNCTION_NAMES - registry_keys}, "
            f"_REGISTRY 多: {registry_keys - L1_FUNCTION_NAMES}"
        )

    def test_arity_keys_equal_l1_names(self):
        """formula_arity.ARITY 的键 == 目录 L1 函数名。"""
        from app.services.formula_arity import ARITY, BUILTIN_FUNCTION_NAMES
        from app.services.formula_function_catalog import L1_FUNCTION_NAMES

        assert set(ARITY.keys()) == set(L1_FUNCTION_NAMES)
        assert BUILTIN_FUNCTION_NAMES == L1_FUNCTION_NAMES

    def test_formula_grammar_arity_keys(self):
        """formula_grammar.FORMULA_ARITY 的键 == 目录 L1 函数名。"""
        from app.services.formula_grammar import FORMULA_ARITY
        from app.services.formula_function_catalog import L1_FUNCTION_NAMES

        assert set(FORMULA_ARITY.keys()) == set(L1_FUNCTION_NAMES)


class TestGeneratedFileCheck:
    """生成文件 --check 无差异。"""

    def test_gen_check_passes(self):
        script = BACKEND / "scripts" / "gen" / "gen_formula_function_catalog.py"
        result = subprocess.run(
            [sys.executable, str(script), "--check"],
            capture_output=True, text=True, timeout=30,
            cwd=str(ROOT),
            env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
        )
        assert result.returncode == 0, (
            f"--check 失败（退出码 {result.returncode}）：\n{result.stderr}"
        )

    def test_gen_check_detects_drift(self):
        """手改生成文件后 --check 应退出码 2（变异自检）。"""
        output = FRONTEND / "src" / "generated" / "formulaFunctionCatalog.ts"
        original = output.read_text(encoding="utf-8")
        try:
            # 在文件末尾加一行
            output.write_text(original + "\n// drift\n", encoding="utf-8")
            script = BACKEND / "scripts" / "gen" / "gen_formula_function_catalog.py"
            result = subprocess.run(
                [sys.executable, str(script), "--check"],
                capture_output=True, text=True, timeout=30,
                cwd=str(ROOT),
                env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
            )
            assert result.returncode == 2, (
                f"手改后 --check 应退出码 2，实际 {result.returncode}"
            )
        finally:
            output.write_text(original, encoding="utf-8")


class TestFrontendNoLiteralFunctionSets:
    """前端 formulaSyntaxParser.ts 不得出现函数名字面量集合。

    改造后 KNOWN_FUNCTIONS / FUNCTION_ARITY 从生成文件导入，
    源码里不应再有 ``new Set(['TB', ...])`` 或 ``{ TB: [2, 2], ... }``
    形式的函数名硬编码集合。

    注意：任务 2 改造 formulaSyntaxParser.ts 之前，这些字面量仍然存在，
    本守卫先写成 xfail(strict=True)——任务 2 删掉字面量后去掉 xfail。
    """

    def test_no_literal_function_set(self):
        parser_file = FRONTEND / "src" / "composables" / "formula" / "formulaSyntaxParser.ts"
        content = parser_file.read_text(encoding="utf-8")

        # 模式：含 3 个以上大写函数名的 Set 或 Record 字面量
        # 例如 new Set(['TB', 'SUM_TB', ...]) 或 { TB: [2, 2], SUM_TB: ... }
        func_names_pattern = re.compile(
            r"(?:new\s+Set\s*\(\s*\[|Record<[^>]+>\s*=\s*\{)"
            r"[^})\]]*"
            r"(?:'(?:TB|SUM_TB|PREV|AUX|NOTE|WP|ADJ|ROW|REPORT|ABS|IF|ROUND|MAX|MIN)'[^})\]]*){3,}"
        )
        matches = func_names_pattern.findall(content)
        assert not matches, (
            f"formulaSyntaxParser.ts 仍含函数名字面量集合（{len(matches)} 处），"
            f"应从 formulaFunctionCatalog.ts 导入"
        )
