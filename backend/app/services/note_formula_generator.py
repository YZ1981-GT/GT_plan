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


def _topological_sort_formulas(formulas: dict[str, dict], rows: list[dict]) -> list[str]:
    """拓扑排序公式：被引用的行先执行，引用方后执行。

    vertical_sum 类型的公式引用其他行，需要先算子项再算合计。
    其他类型（horizontal_balance/cross_table）无行间依赖，按原序。
    """
    import re

    keys = list(formulas.keys())
    # 构建依赖图：key → 依赖的 keys
    deps: dict[str, set[str]] = {k: set() for k in keys}

    for key, fdef in formulas.items():
        expr = fdef.get("expression", "")
        ftype = fdef.get("type", "")

        if ftype == "vertical_sum":
            # SUM(start:end, col) → 依赖 start~end 行的同列
            match = re.match(r"SUM\((\d+):(\d+),\s*(\d+)\)", expr)
            if match:
                start, end, col = int(match.group(1)), int(match.group(2)), int(match.group(3))
                for i in range(start, end + 1):
                    dep_key = f"{i}:{col}"
                    if dep_key in formulas:
                        deps[key].add(dep_key)

        elif ftype in ("horizontal_balance", "book_value"):
            # cell(row,col) → 依赖指定行列
            for m in re.finditer(r"cell\((\d+),(\d+)\)", expr):
                dep_key = f"{m.group(1)}:{m.group(2)}"
                if dep_key in formulas:
                    deps[key].add(dep_key)

    # Kahn's algorithm 拓扑排序
    in_degree = {k: len(deps[k]) for k in keys}
    queue = [k for k in keys if in_degree[k] == 0]
    sorted_result: list[str] = []

    while queue:
        node = queue.pop(0)
        sorted_result.append(node)
        for k in keys:
            if node in deps[k]:
                deps[k].discard(node)
                in_degree[k] -= 1
                if in_degree[k] == 0:
                    queue.append(k)

    # 如果有循环依赖，把剩余的追加到末尾
    remaining = [k for k in keys if k not in sorted_result]
    sorted_result.extend(remaining)

    return sorted_result


async def execute_note_formulas(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    note_section: str,
) -> dict[str, Any]:
    """执行附注表格中的自动运算公式，回填计算结果。

    支持的公式语法：
    - 表内引用: cell(row,col), SUM(start:end, col)
    - 跨表引用: REPORT('BS-002','期末'), TB('1001','审定数'), NOTE('五、3','合计','期末')

    流程：
    1. 加载附注数据
    2. 从 _formulas 中读取公式定义
    3. 预加载跨表数据（报表/试算表/其他附注）
    4. 按依赖顺序执行公式
    5. 将计算结果写回 table_data.rows[].values[]
    6. 只更新 mode=auto 的单元格

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

    # 预加载跨表数据
    cross_table_data = await _load_cross_table_data(db, project_id, year)

    executed = 0
    updated = 0
    exec_results: list[dict] = []  # 每个公式的执行结果

    # 依赖排序：先执行被引用的行（子项），再执行引用方（合计行）
    sorted_keys = _topological_sort_formulas(formulas, rows)

    for key in sorted_keys:
        formula_def = formulas[key]
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
        expression = formula_def.get("expression", "")
        calc_value = None

        if formula_type == "vertical_sum":
            calc_value = _exec_vertical_sum(rows, expression, col_idx)
        elif formula_type in ("horizontal_balance", "book_value"):
            calc_value = _exec_horizontal(rows, expression)
        elif formula_type == "cross_table":
            calc_value = _exec_cross_table(expression, cross_table_data)
        else:
            # 通用公式：尝试解析跨表引用
            calc_value = _exec_generic(expression, rows, cross_table_data)

        if calc_value is not None:
            # 确保 values 列表足够长
            while len(values) <= col_idx:
                values.append(None)
            old_value = values[col_idx]
            values[col_idx] = float(calc_value)
            row["values"] = values
            updated += 1
            exec_results.append({
                "cell": key, "type": formula_def.get("type"),
                "old": old_value, "new": float(calc_value), "status": "ok",
            })
        else:
            exec_results.append({
                "cell": key, "type": formula_def.get("type"),
                "old": None, "new": None, "status": "skipped",
                "reason": "计算结果为空",
            })

        executed += 1

    note.table_data = td
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(note, "table_data")
    await db.flush()

    # 异常检测：合计行为0但子项有数据
    anomalies = []
    for r in exec_results:
        if r["status"] == "ok" and r["new"] == 0 and r.get("type") == "vertical_sum":
            anomalies.append({"cell": r["cell"], "message": "合计行为0，请检查子项是否有数据"})

    return {"executed": executed, "updated": updated, "results": exec_results, "anomalies": anomalies}


# ---------------------------------------------------------------------------
# 跨表数据加载
# ---------------------------------------------------------------------------

async def _load_cross_table_data(db: AsyncSession, project_id: UUID, year: int) -> dict[str, Any]:
    """预加载跨表数据供公式引用。

    Returns: {
        "report": {"BS-002": {"current": 1000, "prior": 900}, ...},
        "tb": {"1001": {"audited": 500, "unadjusted": 480, "opening": 450}, ...},
        "notes": {"五、3": {"total_closing": 1200, "total_opening": 1100}, ...},
    }
    """
    from app.models.report_models import FinancialReport
    from app.models.audit_platform_models import TrialBalance

    cross_data: dict[str, Any] = {"report": {}, "tb": {}, "notes": {}}

    # 加载报表数据
    try:
        result = await db.execute(
            sa.select(
                FinancialReport.row_code,
                FinancialReport.current_period_amount,
                FinancialReport.prior_period_amount,
            ).where(
                FinancialReport.project_id == project_id,
                FinancialReport.year == year,
                FinancialReport.is_deleted == sa.false(),
            )
        )
        for row_code, current, prior in result.all():
            cross_data["report"][row_code] = {
                "current": float(current) if current else 0,
                "prior": float(prior) if prior else 0,
            }
    except Exception:
        pass

    # 加载试算表数据
    try:
        result = await db.execute(
            sa.select(
                TrialBalance.standard_account_code,
                TrialBalance.audited_amount,
                TrialBalance.unadjusted_amount,
                TrialBalance.opening_balance,
            ).where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.is_deleted == sa.false(),
            )
        )
        for code, audited, unadjusted, opening in result.all():
            cross_data["tb"][code] = {
                "audited": float(audited) if audited else 0,
                "unadjusted": float(unadjusted) if unadjusted else 0,
                "opening": float(opening) if opening else 0,
            }
    except Exception:
        pass

    # 加载其他附注合计值
    try:
        result = await db.execute(
            sa.select(DisclosureNote).where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == year,
            )
        )
        for note in result.scalars().all():
            if note.table_data and isinstance(note.table_data, dict):
                rows = note.table_data.get("rows") or []
                # 取最后一个合计行的第一列数值作为 total
                total_rows = [r for r in rows if r.get("is_total")]
                if total_rows:
                    values = total_rows[-1].get("values") or []
                    cross_data["notes"][note.note_section] = {
                        "total_closing": float(values[0]) if values and values[0] else 0,
                        "total_opening": float(values[1]) if len(values) > 1 and values[1] else 0,
                    }
    except Exception:
        pass

    return cross_data


def _exec_cross_table(expression: str, cross_data: dict[str, Any]) -> float | None:
    """执行跨表引用公式。

    支持语法：
    - REPORT('BS-002','期末') → cross_data["report"]["BS-002"]["current"]
    - REPORT('BS-002','期初') → cross_data["report"]["BS-002"]["prior"]
    - TB('1001','审定数') → cross_data["tb"]["1001"]["audited"]
    - TB('1001','未审数') → cross_data["tb"]["1001"]["unadjusted"]
    - TB('1001','期初') → cross_data["tb"]["1001"]["opening"]
    - NOTE('五、3','合计','期末') → cross_data["notes"]["五、3"]["total_closing"]
    """
    import re

    try:
        # REPORT('row_code','period')
        report_match = re.search(r"REPORT\('([^']+)','([^']+)'\)", expression)
        if report_match:
            row_code = report_match.group(1)
            period = report_match.group(2)
            report_data = cross_data.get("report", {}).get(row_code, {})
            if "期末" in period or "current" in period:
                return report_data.get("current", 0)
            elif "期初" in period or "prior" in period:
                return report_data.get("prior", 0)

        # TB('account_code','column')
        tb_match = re.search(r"TB\('([^']+)','([^']+)'\)", expression)
        if tb_match:
            account_code = tb_match.group(1)
            column = tb_match.group(2)
            tb_data = cross_data.get("tb", {}).get(account_code, {})
            if "审定" in column or "audited" in column:
                return tb_data.get("audited", 0)
            elif "未审" in column or "unadjusted" in column:
                return tb_data.get("unadjusted", 0)
            elif "期初" in column or "opening" in column:
                return tb_data.get("opening", 0)
            elif "期末" in column:
                return tb_data.get("audited", 0)  # 期末余额=审定数

        # NOTE('section','合计','period')
        note_match = re.search(r"NOTE\('([^']+)','[^']*','([^']+)'\)", expression)
        if note_match:
            section = note_match.group(1)
            period = note_match.group(2)
            note_data = cross_data.get("notes", {}).get(section, {})
            if "期末" in period:
                return note_data.get("total_closing", 0)
            elif "期初" in period:
                return note_data.get("total_opening", 0)

        return None
    except Exception:
        return None


def _exec_generic(expression: str, rows: list[dict], cross_data: dict[str, Any]) -> float | None:
    """通用公式执行：支持混合引用（表内+跨表）"""
    import re

    # 先尝试跨表引用
    cross_result = _exec_cross_table(expression, cross_data)
    if cross_result is not None:
        return cross_result

    # 再尝试表内引用
    horizontal_result = _exec_horizontal(rows, expression)
    if horizontal_result is not None:
        return horizontal_result

    return None


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
