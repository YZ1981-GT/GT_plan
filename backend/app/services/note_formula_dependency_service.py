"""附注公式依赖图服务

提供公式依赖解析、语义锚点解析、冲突检测和依赖图构建。

核心功能：
- parse_formula_dependencies(expr) — 从公式表达式中解析 TB/WP/REPORT/NOTE/PRIOR 依赖
- resolve_formula_anchor(anchor_key, table_data) — 解析语义或位置锚点到 (row_idx, col_idx)
- detect_anchor_conflicts(formulas, table_data) — 检测旧下标锚点与新语义锚点冲突
- build_dependency_graph(formulas) — 构建公式间依赖图

设计参考：
- 公式锚点升级为: section_id + table_id + row_id + col_id
- 旧 _formulas 位置锚点 (e.g., "0:1" = row 0 col 1) 继续有效
- 新语义锚点优先；与旧锚点冲突时记录 warning，保留旧结果，不静默覆盖

Validates: Requirements 4.1, 4.3, 4.5
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

VALID_DEPENDENCY_TYPES = frozenset({
    "trial_balance",
    "workpaper",
    "report",
    "note",
    "prior",
})

# 公式函数匹配正则
_TB_PATTERN = re.compile(
    r"""TB\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)""", re.IGNORECASE
)
_WP_PATTERN = re.compile(
    r"""WP\(\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*\)""", re.IGNORECASE
)
_REPORT_PATTERN = re.compile(
    r"""REPORT\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)""", re.IGNORECASE
)
_NOTE_PATTERN = re.compile(
    r"""NOTE\(\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*\)""", re.IGNORECASE
)
_PRIOR_PATTERN = re.compile(
    r"""PRIOR\(\s*'([^']+)'\s*,\s*'([^']+)'\s*""", re.IGNORECASE
)

# 位置锚点正则: "row_idx:col_idx" 格式
_POSITIONAL_ANCHOR_PATTERN = re.compile(r"^(\d+):(\d+)$")

# 语义锚点正则: "section.table.row.col" 格式 (至少 2 段以 . 分隔，无纯数字:数字)
_SEMANTIC_ANCHOR_PATTERN = re.compile(r"^[^:]+\.[^:]+")


# ---------------------------------------------------------------------------
# 1. parse_formula_dependencies
# ---------------------------------------------------------------------------


def parse_formula_dependencies(expr: str) -> list[dict[str, Any]]:
    """从公式表达式中解析 TB/WP/REPORT/NOTE/PRIOR 依赖引用。

    Args:
        expr: 公式表达式字符串，如 "WP('D2','附注披露表','within_1_year_closing')"

    Returns:
        依赖列表，每个元素为 dict：
        {
            "type": "trial_balance" | "workpaper" | "report" | "note" | "prior",
            ...type-specific fields...
        }
    """
    if not expr or not isinstance(expr, str):
        return []

    dependencies: list[dict[str, Any]] = []

    # TB('account_code', 'column')
    for match in _TB_PATTERN.finditer(expr):
        dependencies.append({
            "type": "trial_balance",
            "account_code": match.group(1),
            "column": match.group(2),
        })

    # WP('wp_code', 'sheet', 'field')
    for match in _WP_PATTERN.finditer(expr):
        dependencies.append({
            "type": "workpaper",
            "wp_code": match.group(1),
            "sheet": match.group(2),
            "field": match.group(3),
        })

    # REPORT('row_code', 'period')
    for match in _REPORT_PATTERN.finditer(expr):
        dependencies.append({
            "type": "report",
            "row_code": match.group(1),
            "period": match.group(2),
        })

    # NOTE('section', 'aggregate', 'period')
    for match in _NOTE_PATTERN.finditer(expr):
        dependencies.append({
            "type": "note",
            "section": match.group(1),
            "aggregate": match.group(2),
            "period": match.group(3),
        })

    # PRIOR('account_name', '期末'|'期初')
    for match in _PRIOR_PATTERN.finditer(expr):
        dependencies.append({
            "type": "prior",
            "account_name": match.group(1),
            "period": match.group(2),
        })

    return dependencies


# ---------------------------------------------------------------------------
# 2. resolve_formula_anchor
# ---------------------------------------------------------------------------


def resolve_formula_anchor(
    anchor_key: str, table_data: dict[str, Any]
) -> tuple[int, int] | None:
    """解析公式锚点（语义或位置）为 (row_idx, col_idx)。

    支持两种锚点格式：
    1. 位置锚点: "row_idx:col_idx" (如 "0:1")
    2. 语义锚点: "section_id.table_id.row_id.col_id" (如 "accounts_receivable.aging_analysis.within_1_year.closing_balance")

    Args:
        anchor_key: 锚点字符串
        table_data: disclosure_note.table_data 字典

    Returns:
        (row_idx, col_idx) 元组，解析失败返回 None
    """
    if not anchor_key or not isinstance(anchor_key, str):
        return None

    # 尝试位置锚点
    pos_match = _POSITIONAL_ANCHOR_PATTERN.match(anchor_key)
    if pos_match:
        return (int(pos_match.group(1)), int(pos_match.group(2)))

    # 尝试语义锚点: section_id.table_id.row_id.col_id
    parts = anchor_key.split(".")
    if len(parts) < 4:
        return None

    # section_id = parts[0], table_id = parts[1], row_id = parts[2], col_id = parts[3]
    target_table_id = parts[1]
    target_row_id = parts[2]
    target_col_id = parts[3]

    tables = table_data.get("_tables")
    if not isinstance(tables, list):
        return None

    for table in tables:
        if not isinstance(table, dict):
            continue
        if table.get("table_id") != target_table_id:
            continue

        # 找到目标表，解析 row_idx
        row_idx = _find_row_index(table, target_row_id)
        if row_idx is None:
            continue

        # 解析 col_idx
        col_idx = _find_col_index(table, target_col_id)
        if col_idx is None:
            continue

        return (row_idx, col_idx)

    return None


def _find_row_index(table: dict[str, Any], row_id: str) -> int | None:
    """在表中查找 row_id 对应的行索引。"""
    rows = table.get("rows")
    if not isinstance(rows, list):
        return None
    for idx, row in enumerate(rows):
        if isinstance(row, dict) and row.get("row_id") == row_id:
            return idx
    return None


def _find_col_index(table: dict[str, Any], col_id: str) -> int | None:
    """在表中查找 col_id 对应的列索引。"""
    columns = table.get("columns")
    if not isinstance(columns, list):
        return None
    for idx, col in enumerate(columns):
        if isinstance(col, dict) and col.get("col_id") == col_id:
            return idx
    return None


# ---------------------------------------------------------------------------
# 3. detect_anchor_conflicts
# ---------------------------------------------------------------------------


def detect_anchor_conflicts(
    formulas: dict[str, Any], table_data: dict[str, Any]
) -> list[dict[str, Any]]:
    """检测旧下标锚点与新语义锚点指向同一 cell 但公式不同的冲突。

    规则：
    - 新语义锚点优先
    - 若新旧同时命中同一 cell 且表达式不同 → 记录 warning，保留旧结果
    - 不静默覆盖

    Args:
        formulas: _formulas 字典 {anchor_key: formula_def}
        table_data: disclosure_note.table_data

    Returns:
        冲突列表，每项包含:
        {
            "cell": (row_idx, col_idx),
            "semantic_anchor": str,
            "positional_anchor": str,
            "semantic_expr": str,
            "positional_expr": str,
            "message": str,
        }
    """
    if not formulas or not isinstance(formulas, dict):
        return []

    # 分类锚点
    positional_formulas: dict[tuple[int, int], tuple[str, dict]] = {}
    semantic_formulas: dict[tuple[int, int], tuple[str, dict]] = {}

    for anchor_key, formula_def in formulas.items():
        if not isinstance(formula_def, dict):
            continue

        resolved = resolve_formula_anchor(anchor_key, table_data)
        if resolved is None:
            continue

        if _POSITIONAL_ANCHOR_PATTERN.match(anchor_key):
            positional_formulas[resolved] = (anchor_key, formula_def)
        else:
            semantic_formulas[resolved] = (anchor_key, formula_def)

    # 检测冲突：同一 cell 被两种锚点命中且表达式不同
    conflicts: list[dict[str, Any]] = []
    for cell, (sem_key, sem_def) in semantic_formulas.items():
        if cell in positional_formulas:
            pos_key, pos_def = positional_formulas[cell]
            sem_expr = sem_def.get("expr") or sem_def.get("expression", "")
            pos_expr = pos_def.get("expr") or pos_def.get("expression", "")

            if sem_expr != pos_expr:
                conflict = {
                    "cell": cell,
                    "semantic_anchor": sem_key,
                    "positional_anchor": pos_key,
                    "semantic_expr": sem_expr,
                    "positional_expr": pos_expr,
                    "message": (
                        f"锚点冲突：语义锚点 '{sem_key}' 和位置锚点 '{pos_key}' "
                        f"指向同一单元格 ({cell[0]}, {cell[1]})，表达式不同。"
                        f"保留旧位置锚点结果，不静默覆盖。"
                    ),
                }
                conflicts.append(conflict)
                logger.warning(
                    "公式锚点冲突: semantic=%s positional=%s cell=%s",
                    sem_key,
                    pos_key,
                    cell,
                )

    return conflicts


# ---------------------------------------------------------------------------
# 4. build_dependency_graph
# ---------------------------------------------------------------------------


def build_dependency_graph(formulas: dict[str, Any]) -> dict[str, Any]:
    """构建公式间依赖图，展示所有公式的外部依赖关系。

    Args:
        formulas: _formulas 字典 {anchor_key: formula_def}

    Returns:
        {
            "nodes": [
                {
                    "anchor": str,
                    "formula_id": str | None,
                    "expr": str,
                    "dependencies": [{"type": ..., ...}],
                }
            ],
            "edges": [
                {
                    "from": anchor_key,
                    "to": dependency_description,
                    "type": dependency_type,
                }
            ],
            "summary": {
                "total_formulas": int,
                "total_dependencies": int,
                "by_type": {"trial_balance": int, "workpaper": int, ...},
            }
        }
    """
    if not formulas or not isinstance(formulas, dict):
        return {
            "nodes": [],
            "edges": [],
            "summary": {"total_formulas": 0, "total_dependencies": 0, "by_type": {}},
        }

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    type_counts: dict[str, int] = {}
    total_deps = 0

    for anchor_key, formula_def in formulas.items():
        if not isinstance(formula_def, dict):
            continue

        expr = formula_def.get("expr") or formula_def.get("expression", "")
        formula_id = formula_def.get("formula_id")
        deps = parse_formula_dependencies(expr)

        nodes.append({
            "anchor": anchor_key,
            "formula_id": formula_id,
            "expr": expr,
            "dependencies": deps,
        })

        for dep in deps:
            dep_type = dep.get("type", "unknown")
            # 构建边的目标描述
            if dep_type == "trial_balance":
                target = f"TB:{dep.get('account_code', '')}:{dep.get('column', '')}"
            elif dep_type == "workpaper":
                target = f"WP:{dep.get('wp_code', '')}:{dep.get('sheet', '')}:{dep.get('field', '')}"
            elif dep_type == "report":
                target = f"REPORT:{dep.get('row_code', '')}:{dep.get('period', '')}"
            elif dep_type == "note":
                target = f"NOTE:{dep.get('section', '')}:{dep.get('aggregate', '')}:{dep.get('period', '')}"
            elif dep_type == "prior":
                target = f"PRIOR:{dep.get('account_name', '')}:{dep.get('period', '')}"
            else:
                target = f"UNKNOWN:{dep}"

            edges.append({
                "from": anchor_key,
                "to": target,
                "type": dep_type,
            })
            type_counts[dep_type] = type_counts.get(dep_type, 0) + 1
            total_deps += 1

    return {
        "nodes": nodes,
        "edges": edges,
        "summary": {
            "total_formulas": len(nodes),
            "total_dependencies": total_deps,
            "by_type": type_counts,
        },
    }
