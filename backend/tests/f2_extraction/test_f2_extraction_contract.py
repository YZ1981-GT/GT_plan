"""F2 取数模块契约守卫.

Property 9: F2 取数路径不调 generic evaluate_wp_formula_expression
Property 7/10: F2_ANCHORS == 前端 itemId 穷举集；F2 列名 == F2_COLUMN_MAP.keys()
"""
from __future__ import annotations

import inspect
import re
from pathlib import Path

from app.services.f2_extraction.anchor_registry import F2_ANCHORS
from app.services.f2_extraction.extract import F2_COLUMN_MAP


# ---------------------------------------------------------------------------
# Property 9: F2 取数路径不 import/调 evaluate_wp_formula_expression
# ---------------------------------------------------------------------------

_F2_MODULE_DIR = Path(__file__).resolve().parents[2] / "app" / "services" / "f2_extraction"


def test_no_generic_evaluator_import_in_f2_extraction():
    """f2_extraction/ 所有 .py 文件不 import evaluate_wp_formula_expression.

    确保 F2 取数走专属 tb_balance 路径，与 trial_balance 通用评估器隔离。
    """
    violations: list[str] = []
    for py_file in _F2_MODULE_DIR.glob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        if "evaluate_wp_formula_expression" in content:
            # 允许 validation.py 导入 find_unsupported_formula_functions（同模块别名），
            # 但不允许导入 evaluate_wp_formula_expression 本身
            # 精确匹配 import 语句
            if re.search(r"\bevaluate_wp_formula_expression\b", content):
                # validation.py 导入的是 find_unsupported_formula_functions 不是 evaluate
                # 双重检查
                if "from app.services.wp_formula_eval_service import" in content:
                    imports_line = [
                        line for line in content.splitlines()
                        if "from app.services.wp_formula_eval_service import" in line
                    ]
                    for line in imports_line:
                        if "evaluate_wp_formula_expression" in line:
                            violations.append(f"{py_file.name}: {line.strip()}")
    assert not violations, (
        f"f2_extraction 模块禁止 import evaluate_wp_formula_expression:\n"
        + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# Property 7: F2_ANCHORS 数量 == 39 (12 gross × 3 + 1 impairment × 3)
# ---------------------------------------------------------------------------


def test_anchor_count():
    """F2_ANCHORS 恰好 39 项."""
    assert len(F2_ANCHORS) == 39


def test_anchor_format():
    """每个 anchor 格式为 F2-1-{block}-{rowKey}-{field}."""
    pattern = re.compile(r"^F2-1-(gross|impairment)-[\w-]+-(?:opening|increase|decrease)$")
    for anchor in F2_ANCHORS:
        assert pattern.match(anchor), f"格式不合法: {anchor}"


# ---------------------------------------------------------------------------
# Property 10: F2 列名集 == F2_COLUMN_MAP.keys()
# ---------------------------------------------------------------------------


def test_column_map_is_four():
    """F2_COLUMN_MAP 恰好 4 列: 期初余额/期末余额/借方发生额/贷方发生额."""
    expected = {"期初余额", "期末余额", "借方发生额", "贷方发生额"}
    assert set(F2_COLUMN_MAP.keys()) == expected


def test_column_map_values_are_tb_balance_cols():
    """F2_COLUMN_MAP 值全部是 tb_balance 的真实列名."""
    valid_cols = {"opening_balance", "closing_balance", "debit_amount", "credit_amount"}
    for col_name, db_col in F2_COLUMN_MAP.items():
        assert db_col in valid_cols, f"F2_COLUMN_MAP['{col_name}'] = '{db_col}' 不在 tb_balance 列集"
