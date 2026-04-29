"""附注公式自动生成器

根据附注模板的 check_presets 和 table_template 结构，
自动生成每个单元格的计算公式，供前端"应用自动运算"时执行。

公式类型：
- vertical_sum: 合计行 = 上方明细行之和
- horizontal_balance: 期初 + 增加 - 减少 = 期末
- book_value: 原值 - 累计折旧/摊销 - 减值准备 = 账面价值
- balance_check: 报表数 = 附注合计数

生成的公式存储在 DisclosureNote.table_data._formulas 中：
{
  "row_idx:col_idx": {
    "type": "vertical_sum",
    "expression": "SUM(0:3, col)",  // 第0-3行同列求和
    "description": "合计 = 子项之和",
    "category": "auto_calc"
  }
}
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import DisclosureNote

logger = logging.getLogger(__name__)


def generate_formulas_for_table(table_template: dict, check_presets: list[str]) -> dict[str, dict]:
    """根据表格模板和校验预设，自动生成单元格公式。

    Returns: {"row_idx:col_idx": {"type": ..., "expression": ..., "description": ..., "category": ...}}
    """
    formulas: dict[str, dict] = {}
    headers = table_template.get("headers") or []
    rows = table_template.get("rows") or []

    if not rows or not headers:
        return formulas

    num_cols = len(headers) - 1  # 第0列是标签列

    # 1. 纵向合计公式（sub_item 预设）
    if "sub_item" in check_presets or "balance" in check_presets:
        total_indices = [i for i, r in enumerate(rows) if r.get("is_total")]
        for total_idx in total_indices:
            # 合计行上方的非合计行
            detail_start = 0
            for prev_total in total_indices:
                if prev_total < total_idx:
                    detail_start = prev_total + 1
            detail_end = total_idx - 1

            for col in range(num_cols):
                key = f"{total_idx}:{col}"
                formulas[key] = {
                    "type": "vertical_sum",
                    "expression": f"SUM({detail_start}:{detail_end}, {col})",
                    "description": f"合计 = 第{detail_start+1}~{detail_end+1}行之和",
                    "category": "auto_calc",
                    "source": "check_presets.sub_item",
                }

    # 2. 横向公式（movement 预设：期初+增加-减少=期末）
    if "movement" in check_presets:
        # 检测表头中是否有"期初""增加""减少""期末"
        col_map = _detect_movement_columns(headers)
        if col_map:
            for row_idx, row in enumerate(rows):
                if row.get("is_total"):
                    continue
                # 期末 = 期初 + 增加 - 减少
                if "closing" in col_map and "opening" in col_map:
                    closing_col = col_map["closing"]
                    key = f"{row_idx}:{closing_col}"
                    parts = []
                    if "opening" in col_map:
                        parts.append(f"cell({row_idx},{col_map['opening']})")
                    if "increase" in col_map:
                        parts.append(f"cell({row_idx},{col_map['increase']})")
                    if "decrease" in col_map:
                        parts.append(f"-cell({row_idx},{col_map['decrease']})")
                    formulas[key] = {
                        "type": "horizontal_balance",
                        "expression": " + ".join(parts) if parts else "",
                        "description": "期末 = 期初 + 增加 - 减少",
                        "category": "auto_calc",
                        "source": "check_presets.movement",
                    }

    # 3. 账面价值公式（book_value 预设）
    if "book_value" in check_presets:
        # 检测是否有"账面价值"行
        for row_idx, row in enumerate(rows):
            label = row.get("label", "")
            if "账面价值" in label and "期末" in label:
                # 找原值行和折旧行
                original_idx = _find_row_by_keyword(rows, "原值期末")
                depreciation_idx = _find_row_by_keyword(rows, "累计折旧期末") or _find_row_by_keyword(rows, "累计摊销期末")
                impairment_idx = _find_row_by_keyword(rows, "减值准备期末") or _find_row_by_keyword(rows, "减值准备")

                for col in range(num_cols):
                    parts = []
                    if original_idx is not None:
                        parts.append(f"cell({original_idx},{col})")
                    if depreciation_idx is not None:
                        parts.append(f"-cell({depreciation_idx},{col})")
                    if impairment_idx is not None:
                        parts.append(f"-cell({impairment_idx},{col})")
                    if parts:
                        key = f"{row_idx}:{col}"
                        formulas[key] = {
                            "type": "book_value",
                            "expression": " + ".join(parts),
                            "description": "账面价值 = 原值 - 累计折旧/摊销 - 减值准备",
                            "category": "auto_calc",
                            "source": "check_presets.book_value",
                        }

    return formulas


def _detect_movement_columns(headers: list[str]) -> dict[str, int]:
    """检测变动表列（期初/增加/减少/期末）"""
    col_map: dict[str, int] = {}
    for i, h in enumerate(headers[1:], start=0):  # 跳过第0列标签
        h_str = str(h)
        if "期初" in h_str or "年初" in h_str:
            col_map["opening"] = i
        elif "增加" in h_str or "本期增加" in h_str:
            col_map["increase"] = i
        elif "减少" in h_str or "本期减少" in h_str or "摊销" in h_str or "计提" in h_str:
            col_map["decrease"] = i
        elif "期末" in h_str:
            col_map["closing"] = i
    return col_map


def _find_row_by_keyword(rows: list[dict], keyword: str) -> int | None:
    """按关键词查找行索引"""
    for i, r in enumerate(rows):
        if keyword in (r.get("label") or ""):
            return i
    return None


async def execute_note_formulas(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    note_section: str,
) -> dict[str, Any]:
    """执行附注表格中的自动运算公式，回填计算结果。

    流程：
    1. 加载附注数据
    2. 从 _formulas 中读取公式定义
    3. 按依赖顺序执行公式
    4. 将计算结果写回 table_data.rows[].values[]
    5. 只更新 mode=auto 的单元格

    Returns: {"executed": N, "updated": M}
    """
    result_q = await db.execute(
        sa.select(DisclosureNote).where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == year,
            DisclosureNote.note_section == note_section,
        )
    )
    note = result_q.scalar_one_or_none()
    if not note or not note.table_data:
        return {"executed": 0, "updated": 0}

    td = note.table_data
    rows = td.get("rows") or []
    formulas = td.get("_formulas") or {}

    if not formulas:
        # 尝试从模板自动生成
        check_presets = td.get("_check_presets") or []
        table_template = {"headers": td.get("headers", []), "rows": rows}
        formulas = generate_formulas_for_table(table_template, check_presets)
        if formulas:
            td["_formulas"] = formulas

    executed = 0
    updated = 0

    for key, formula_def in formulas.items():
        parts = key.split(":")
        if len(parts) != 2:
            continue
        row_idx, col_idx = int(parts[0]), int(parts[1])

        if row_idx >= len(rows):
            continue

        row = rows[row_idx]
        values = row.get("values") or []
        cell_modes = row.get("_cell_modes") or {}

        # 只更新 auto 模式的单元格
        mode = cell_modes.get(str(col_idx), "auto")
        if mode != "auto":
            continue

        # 执行公式
        formula_type = formula_def.get("type")
        calc_value = None

        if formula_type == "vertical_sum":
            calc_value = _exec_vertical_sum(rows, formula_def.get("expression", ""), col_idx)
        elif formula_type == "horizontal_balance":
            calc_value = _exec_horizontal(rows, formula_def.get("expression", ""))
        elif formula_type == "book_value":
            calc_value = _exec_horizontal(rows, formula_def.get("expression", ""))

        if calc_value is not None:
            # 确保 values 列表足够长
            while len(values) <= col_idx:
                values.append(None)
            values[col_idx] = float(calc_value)
            row["values"] = values
            updated += 1

        executed += 1

    note.table_data = td
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(note, "table_data")
    await db.flush()

    return {"executed": executed, "updated": updated}


def _exec_vertical_sum(rows: list[dict], expression: str, col_idx: int) -> float | None:
    """执行纵向求和：SUM(start:end, col)"""
    try:
        # 解析 SUM(0:3, 0)
        inner = expression.replace("SUM(", "").rstrip(")")
        parts = inner.split(",")
        range_part = parts[0].strip()
        start, end = [int(x.strip()) for x in range_part.split(":")]

        total = 0.0
        for i in range(start, end + 1):
            if i < len(rows):
                values = rows[i].get("values") or []
                if col_idx < len(values) and values[col_idx] is not None:
                    total += float(values[col_idx])
        return total
    except Exception:
        return None


def _exec_horizontal(rows: list[dict], expression: str) -> float | None:
    """执行横向公式：cell(row,col) + cell(row,col) - cell(row,col)"""
    try:
        import re
        result = 0.0
        # 匹配 cell(row,col) 和前面的 +/-
        tokens = re.findall(r'([+-]?)\s*cell\((\d+),(\d+)\)', expression)
        for sign, row_s, col_s in tokens:
            row_idx, col_idx = int(row_s), int(col_s)
            if row_idx < len(rows):
                values = rows[row_idx].get("values") or []
                if col_idx < len(values) and values[col_idx] is not None:
                    val = float(values[col_idx])
                    if sign == "-":
                        result -= val
                    else:
                        result += val
        return result
    except Exception:
        return None
