"""附注空表判定（纯函数，无 IO）。

**为什么需要**：非房地产企业的附注里会出现三张空白的「开发成本」「开发产品」「周转房」，
非数据资源企业会出现空白的「确认为存货的数据资源」——模板 seed 生成的骨架有行标签但无
数据，看起来像"没做完"。判定为空表后由消费方决定折叠 / 标注「本期无此情形」/ 导出时省略。

**输入契约 = 投影后的表**（`note_sub_table_projector.project_sub_tables` 的输出）：

    rows    = [{"label": str, "values": [...], "is_total": bool}]
    columns = [ColumnDef]  # 含标签列；values[j] 对应去掉标签列后的第 j 个

之所以以投影结果为输入而非 `sub_table_data` 原始行，是为了让模块页 / Word 导出 /
批量导出三个消费方用**同一口径**（design.md Property 7 的同一动机）。

**判定规则**（design.md Property 8）：

1. 行标签**不参与**判断 —— 模板骨架恒有标签（「原材料」「在产品」…），若算进去则永不为空
2. 合计行不参与判断 —— 合计是派生值，本身不代表业务发生
3. 段标题行 / 假表头行不参与判断（`row_type` 为 `section` / `header_label`）
4. 数值列（`format == "amount"`）：`None` / 空串 / `0` 视为空
5. 其余列按文本：`strip()` 后为空视为空
6. 任一非空 → 表非空；全空（含无行）→ 空表

Spec: .kiro/specs/disclosure-note-follow-actual-content/ R4.1 / Task 1.1
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "is_empty_table",
    "empty_table_names",
    "AMOUNT_FORMATS",
    "SKIP_ROW_TYPES",
]

# 视为"数值列"的 format 值：空值与 0 都算空
AMOUNT_FORMATS = frozenset({"amount", "percent", "number"})

# 不参与空表判定的行类型（派生行 / 结构行 / 可扩位行）
# `expandable` = 源模板留的可扩位（`……` / `可无限量添加行`），零可见内容。
# spec: note-template-columns-and-legacy-snapshot-closure Property 33
SKIP_ROW_TYPES = frozenset(
    {"total", "subtotal", "section", "header_label", "expandable"}
)

# 数值零容差：附注金额保留 2 位小数，绝对值小于半分即视为零
_ZERO_EPS = 0.005


def _is_label_def(d: Any) -> bool:
    return isinstance(d, dict) and bool(d.get("is_label"))


def _value_defs(columns: Any) -> list[dict[str, Any]]:
    """与投影器同规则取出「非标签列」，顺序即 values 的位置序。

    投影器 `_pick_label_def` 的规则：优先 `is_label`，否则取第一列。此处对齐：
    没有任何列标 `is_label` 时，把第一列当标签列剔除。
    """
    defs = [d for d in (columns or []) if isinstance(d, dict)]
    if not defs:
        return []
    if any(_is_label_def(d) for d in defs):
        return [d for d in defs if not _is_label_def(d)]
    return defs[1:]


def _is_amount_col(d: dict[str, Any]) -> bool:
    return str(d.get("format") or "") in AMOUNT_FORMATS


def _skip_row(row: dict[str, Any]) -> bool:
    if row.get("is_total"):
        return True
    return str(row.get("row_type") or "") in SKIP_ROW_TYPES


def _amount_is_blank(v: Any) -> bool:
    """数值列的空判定：None / 空串 / 0（含 "0" / "0.00" / Decimal("0")）都算空。"""
    if v is None:
        return True
    if isinstance(v, bool):
        # bool 是 int 子类；True 表达"有内容"
        return not v
    if isinstance(v, (int, float)):
        return abs(float(v)) < _ZERO_EPS
    s = str(v).strip()
    if not s:
        return True
    # 允许千分符 / 全角逗号 / 括号负数
    cleaned = s.replace(",", "").replace("，", "").replace(" ", "")
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = "-" + cleaned[1:-1]
    try:
        return abs(float(cleaned)) < _ZERO_EPS
    except (TypeError, ValueError):
        # 数值列里出现非数值文本（如「不适用」）→ 视为有内容，不当空
        return False


def _text_is_blank(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, bool):
        return not v
    if isinstance(v, (int, float)):
        # 文本列里出现数值：0 也算填了内容（可能是"数量 0"这类有意义的填写）
        return False
    return not str(v).strip()


def is_empty_table(rows: Any, columns: Any = None) -> bool:
    """该表本期是否无业务内容。

    Args:
        rows: 投影后的行列表（`[{"label","values","is_total"}]`）。
        columns: 列定义（含标签列）。缺省时全部按文本列判定。

    Returns:
        True 表示空表（可折叠 / 标注「本期无此情形」）。
    """
    if not isinstance(rows, list) or not rows:
        return True

    vdefs = _value_defs(columns)

    for row in rows:
        if not isinstance(row, dict):
            continue
        if _skip_row(row):
            continue
        values = row.get("values")
        if not isinstance(values, list):
            continue
        for j, v in enumerate(values):
            col = vdefs[j] if j < len(vdefs) else None
            blank = (
                _amount_is_blank(v)
                if (col is not None and _is_amount_col(col))
                else _text_is_blank(v)
            )
            if not blank:
                return False
    return True


def empty_table_names(tables: Any) -> list[str]:
    """批量：从投影后的 `_tables[]` 中挑出空表名（保持原顺序）。"""
    out: list[str] = []
    for t in tables or []:
        if not isinstance(t, dict):
            continue
        if is_empty_table(t.get("rows"), t.get("columns")):
            out.append(str(t.get("name") or ""))
    return out
