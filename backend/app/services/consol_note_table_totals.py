"""合并附注表格行组装与合计重算 —— 明细映射拉数与节点子树汇总共用。

spec: consol-note-header-library-and-node-reaggregate（Task 9，从 ``consol_note_detail_apply_service`` 抽出）

骨架行（行名, 行类型）+ 每行逐列金额 → 写入用的二维行：
- 数据行写金额（两位小数，ROUND_HALF_UP）；
- 合计 / 小计 = 本表数据行之和（表内计算，不取来源合计）：小计只加到上一个合计 / 小计为止，合计加全部
  数据行；整列都没有数据保持空白；
- 手工 / 锁定单元格保留原值并回报。
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Sequence

__all__ = ["TOTAL_ROW_TYPES", "build_table_rows", "existing_cell", "fmt_amount", "to_decimal"]

TOTAL_ROW_TYPES = ("total", "subtotal")


def to_decimal(value: Any) -> Decimal | None:
    """单元格 → Decimal；空、占位符、非数值 → None（不参与加总）。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float) and value != value:  # NaN
        return None
    if isinstance(value, dict):  # 带元数据的单元格
        return to_decimal(value.get("value", value.get("manual_value")))
    s = str(value).strip().replace(",", "").replace("，", "")
    if not s or s in ("-", "—", "－"):
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def fmt_amount(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def existing_cell(rows: Sequence[Any], row_idx: int, col_idx: int) -> str:
    """从已保存行中安全取值（二维行或 ``{values|cells: {列号: 值}}`` 对象行）。"""
    if row_idx >= len(rows):
        return ""
    row = rows[row_idx]
    if isinstance(row, (list, tuple)):
        return str(row[col_idx]) if col_idx < len(row) else ""
    if isinstance(row, dict):
        vals = row.get("values") or row.get("cells") or {}
        if isinstance(vals, dict):
            return str(vals.get(str(col_idx), vals.get(col_idx, "")))
    return ""


def build_table_rows(
    skeleton: Sequence[tuple[str, str | None]],
    amounts: dict[int, dict[int, Decimal]],
    *,
    width: int,
    protected: set[tuple[int, int]],
    existing_rows: Sequence[Any],
) -> tuple[list[list[str]], list[dict[str, Any]], list[dict[str, Any]]]:
    """返回 (新行, 写入的单元格, 保留的手工 / 锁定单元格)。

    ``skeleton[i]`` = (行名, 行类型)；``amounts[i][col]`` = 第 i 行第 col 列金额（col ≥ 1）。
    合计 / 小计行不写来源金额，按本表已组装的数据行重算。
    """
    new_rows: list[list[str]] = []
    filled: list[dict[str, Any]] = []
    kept: list[dict[str, Any]] = []
    for i, (name, row_type) in enumerate(skeleton):
        row = [""] * width
        if width:
            row[0] = name
        if row_type not in TOTAL_ROW_TYPES:
            row_amounts = amounts.get(i) or {}
            for col in range(1, width):
                if (i, col) in protected:
                    # 手工 / 锁定格一律保留（来源这一格没数也不清空）；来源有数时回报「保留了手工值」
                    old = existing_cell(existing_rows, i, col)
                    row[col] = old
                    if col in row_amounts:
                        kept.append({"row": i, "col": col, "kept_value": old})
                elif col in row_amounts:
                    formatted = fmt_amount(row_amounts[col])
                    row[col] = formatted
                    filled.append({"row": i, "col": col, "value": formatted, "target_name": name})
        else:
            for col in range(1, width):
                if (i, col) in protected:
                    row[col] = existing_cell(existing_rows, i, col)
                    continue
                total, has_value = Decimal("0"), False
                for j in range(len(new_rows) - 1, -1, -1):
                    if skeleton[j][1] in TOTAL_ROW_TYPES:
                        if row_type == "subtotal":
                            break
                        continue
                    cell = to_decimal(new_rows[j][col])
                    if cell is not None:
                        total += cell
                        has_value = True
                if has_value:
                    row[col] = fmt_amount(total)
        new_rows.append(row)
    return new_rows, filled, kept
