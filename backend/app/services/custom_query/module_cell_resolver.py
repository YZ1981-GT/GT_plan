"""跨模块单元格级查询 — Module_Cell_Resolver

统一 source 命名空间路由器，把 4 模块（report / note / adj / tb）的 cell 级查询
路由到对应的 _query_*_cells 提取器，返回统一形态 {cell_ref, value, formula, sheet_name, module}。

Source URI 格式：
  report:{report_type}|{cell_range}   — e.g. report:balance_sheet|C5:C10
  note:{section_id}|{cell_range}      — e.g. note:五-1-1|C3:D8
  adj:{adjustment_type}|{cell_range}  — e.g. adj:aje|B2:E10
  tb:{aux_dim}|{cell_range}           — e.g. tb:detail|C1:C50

虚拟 sheet 列映射：
  report → A=row_code, B=row_name, C=current_period_amount, D=prior_period_amount, E=formula
  note   → A=code, B=name, C=year_end, D=year_begin, E=formula
  adj    → A=entry_no, B=account_code, C=account_name, D=debit_amount, E=credit_amount, F=description
  tb     → A=account_code, B=account_name, C=opening_balance, D=debit_amount, E=credit_amount, F=closing_balance, G=audited_amount
"""

import logging
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ─── Source URI 解析 / 序列化 ─────────────────────────────────────────────────

# 支持的模块前缀
_MODULE_PREFIXES = ("report:", "note:", "adj:", "tb:")


def parse_source_uri(source: str) -> dict | None:
    """解析 source URI 为结构化字典。

    Returns:
        {module, qualifier, cell_range} 或 None（无法解析时）

    Examples:
        parse_source_uri("report:balance_sheet|C5:C10")
        → {"module": "report", "qualifier": "balance_sheet", "cell_range": "C5:C10"}

        parse_source_uri("note:五-1-1|C3:D8")
        → {"module": "note", "qualifier": "五-1-1", "cell_range": "C3:D8"}
    """
    if not source or not isinstance(source, str):
        return None

    for prefix in _MODULE_PREFIXES:
        if source.startswith(prefix):
            tail = source[len(prefix):]
            module = prefix.rstrip(":")
            if "|" in tail:
                qualifier, cell_range = tail.split("|", 1)
                return {"module": module, "qualifier": qualifier, "cell_range": cell_range}
            else:
                # 无 cell_range 时 qualifier 是整个 tail
                return {"module": module, "qualifier": tail, "cell_range": None}

    # workpaper: 前缀也支持（兼容）
    if source.startswith("workpaper:"):
        tail = source[len("workpaper:"):]
        parts = tail.split("|")
        if len(parts) == 3:
            return {"module": "workpaper", "qualifier": parts[0], "sheet_name": parts[1], "cell_range": parts[2]}
        elif len(parts) == 2:
            return {"module": "workpaper", "qualifier": parts[0], "sheet_name": parts[1], "cell_range": None}
        else:
            return {"module": "workpaper", "qualifier": tail, "sheet_name": None, "cell_range": None}

    return None


def format_source_uri(parsed: dict) -> str:
    """从结构化字典重新序列化为 source URI 字符串。

    Inverse of parse_source_uri — round-trip property: format(parse(uri)) == uri
    """
    module = parsed.get("module", "")
    qualifier = parsed.get("qualifier", "")
    cell_range = parsed.get("cell_range")

    if module == "workpaper":
        sheet_name = parsed.get("sheet_name")
        if sheet_name and cell_range:
            return f"workpaper:{qualifier}|{sheet_name}|{cell_range}"
        elif sheet_name:
            return f"workpaper:{qualifier}|{sheet_name}"
        else:
            return f"workpaper:{qualifier}"

    if cell_range:
        return f"{module}:{qualifier}|{cell_range}"
    else:
        return f"{module}:{qualifier}"


def is_module_cell_source(source: str) -> bool:
    """判断 source 是否属于 4 模块 cell 级查询命名空间（含 cell_range）"""
    parsed = parse_source_uri(source)
    if not parsed:
        return False
    return parsed["module"] in ("report", "note", "adj", "tb") and parsed.get("cell_range") is not None


# ─── 虚拟 sheet 列映射 ───────────────────────────────────────────────────────

_REPORT_COLUMNS = ["row_code", "row_name", "current_period_amount", "prior_period_amount", "formula"]
_NOTE_COLUMNS = ["code", "name", "year_end", "year_begin", "formula"]
_ADJ_COLUMNS = ["entry_no", "account_code", "account_name", "debit_amount", "credit_amount", "description"]
_TB_COLUMNS = ["account_code", "account_name", "opening_balance", "debit_amount", "credit_amount", "closing_balance", "audited_amount"]


def _col_letter_to_index(letter: str) -> int:
    """A→1, B→2, ..., Z→26, AA→27"""
    n = 0
    for ch in letter.upper():
        n = n * 26 + (ord(ch) - 64)
    return n


def _index_to_col_letter(idx: int) -> str:
    """1→A, 2→B, ..., 26→Z, 27→AA"""
    letters = ""
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _parse_cell_ranges(spec: str) -> list[tuple[int, int, int, int]]:
    """解析 cell_range 字符串为 (r1, c1, r2, c2) 元组列表（1-indexed）

    支持：'A1:C3' / 'B5' / 'A1:A10,C1:C5' / 'A:A' / 'A:C'
    """
    INTEGER_COL_LIMIT = 100

    out: list[tuple[int, int, int, int]] = []
    for part in spec.split(","):
        part = part.strip().upper()
        if not part:
            continue
        # 单 cell 'B5'
        m = re.match(r"^([A-Z]+)(\d+)$", part)
        if m:
            col = _col_letter_to_index(m.group(1))
            r = int(m.group(2))
            out.append((r, col, r, col))
            continue
        # 整列 'A:A' / 'A:C'
        m = re.match(r"^([A-Z]+):([A-Z]+)$", part)
        if m:
            c1 = _col_letter_to_index(m.group(1))
            c2 = _col_letter_to_index(m.group(2))
            out.append((1, min(c1, c2), INTEGER_COL_LIMIT, max(c1, c2)))
            continue
        # 矩形 'A1:C3'
        m = re.match(r"^([A-Z]+)(\d+):([A-Z]+)(\d+)$", part)
        if m:
            c1 = _col_letter_to_index(m.group(1))
            r1 = int(m.group(2))
            c2 = _col_letter_to_index(m.group(3))
            r2 = int(m.group(4))
            out.append((min(r1, r2), min(c1, c2), max(r1, r2), max(c1, c2)))
            continue
    return out


def _extract_cells_from_virtual_sheet(
    rows_data: list[dict],
    columns: list[str],
    cell_range: str,
    sheet_name: str,
    module: str,
) -> list[dict]:
    """从虚拟 sheet 数据中按 cell_range 提取 cell 结果。

    虚拟 sheet 规则：
      - 第 1 行是表头（columns 名称）
      - 第 2 行起是数据行（rows_data[0] 对应第 2 行）
      - 列 A=columns[0], B=columns[1], ...

    Returns:
        [{cell_ref, value, formula, sheet_name, module}, ...]
    """
    ranges = _parse_cell_ranges(cell_range)
    if not ranges:
        return []

    MAX_CELLS = 500
    results: list[dict] = []
    idx = 0

    for (r1, c1, r2, c2) in ranges:
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                if idx >= MAX_CELLS:
                    break
                idx += 1
                cell_ref = f"{_index_to_col_letter(c)}{r}"

                # 第 1 行 = 表头
                if r == 1:
                    col_idx = c - 1
                    value = columns[col_idx] if col_idx < len(columns) else ""
                    results.append({
                        "cell_ref": cell_ref,
                        "value": value,
                        "formula": None,
                        "sheet_name": sheet_name,
                        "module": module,
                    })
                    continue

                # 第 2 行起 = 数据行
                data_row_idx = r - 2  # rows_data[0] = 第 2 行
                col_idx = c - 1

                if data_row_idx < 0 or data_row_idx >= len(rows_data):
                    results.append({
                        "cell_ref": cell_ref,
                        "value": "",
                        "formula": None,
                        "sheet_name": sheet_name,
                        "module": module,
                    })
                    continue

                row = rows_data[data_row_idx]
                col_name = columns[col_idx] if col_idx < len(columns) else None

                if col_name is None:
                    value = ""
                    formula = None
                else:
                    value = row.get(col_name)
                    if value is None:
                        value = ""
                    elif isinstance(value, (int, float)):
                        pass  # keep numeric
                    else:
                        value = str(value)
                    # formula 字段：仅当列名是 "formula" 时取值
                    formula = row.get("formula") if col_name == "formula" else None

                results.append({
                    "cell_ref": cell_ref,
                    "value": value,
                    "formula": formula,
                    "sheet_name": sheet_name,
                    "module": module,
                })
            if idx >= MAX_CELLS:
                break
        if idx >= MAX_CELLS:
            break

    return results


# ─── 4 模块 cell 提取器 ──────────────────────────────────────────────────────


async def _query_report_cells(
    db: AsyncSession,
    project_id: str,
    year: int | None,
    report_type: str,
    cell_range: str,
) -> list[dict]:
    """从 report_snapshot.data JSONB 提取 cell。

    虚拟 sheet 列映射：A=row_code, B=row_name, C=current_period_amount, D=prior_period_amount, E=formula
    """
    sheet_name = f"report_{report_type}"

    if not project_id or not year:
        return []

    try:
        result = await db.execute(text("""
            SELECT data FROM report_snapshot
            WHERE project_id = :pid AND year = :y AND report_type = :rt
            ORDER BY generated_at DESC
            LIMIT 1
        """), {"pid": project_id, "y": year, "rt": report_type})
        snap_row = result.first()
    except Exception as e:
        logger.warning("_query_report_cells failed: %s", e)
        return []

    if not snap_row or not isinstance(snap_row[0], dict):
        return []

    data = snap_row[0]
    rows_arr = data.get("rows") if isinstance(data, dict) else None
    if not isinstance(rows_arr, list):
        return []

    # 转换为虚拟 sheet 行格式
    virtual_rows: list[dict] = []
    for item in rows_arr:
        if not isinstance(item, dict):
            continue
        virtual_rows.append({
            "row_code": item.get("row_code", ""),
            "row_name": item.get("row_name", ""),
            "current_period_amount": item.get("current_period_amount"),
            "prior_period_amount": item.get("prior_period_amount"),
            "formula": item.get("formula"),
        })

    return _extract_cells_from_virtual_sheet(
        virtual_rows, _REPORT_COLUMNS, cell_range, sheet_name, "report"
    )


async def _query_note_cells(
    db: AsyncSession,
    project_id: str,
    year: int | None,
    section_id: str,
    cell_range: str,
) -> list[dict]:
    """从 consol_note_data.data JSONB 提取 cell。

    虚拟 sheet 列映射：A=code, B=name, C=year_end, D=year_begin, E=formula
    """
    sheet_name = f"note_{section_id}"

    if not project_id or not year:
        return []

    try:
        result = await db.execute(text("""
            SELECT data FROM consol_note_data
            WHERE project_id = :pid AND year = :y AND section_id = :sid
            LIMIT 1
        """), {"pid": project_id, "y": year, "sid": section_id})
        note_row = result.first()
    except Exception as e:
        logger.warning("_query_note_cells failed: %s", e)
        return []

    if not note_row or not isinstance(note_row[0], dict):
        return []

    data = note_row[0]
    rows_arr = data.get("rows") if isinstance(data, dict) else None
    if not isinstance(rows_arr, list):
        return []

    # 转换为虚拟 sheet 行格式
    virtual_rows: list[dict] = []
    for item in rows_arr:
        if isinstance(item, dict):
            virtual_rows.append({
                "code": item.get("code", ""),
                "name": item.get("name", ""),
                "year_end": item.get("year_end"),
                "year_begin": item.get("year_begin"),
                "formula": item.get("formula"),
            })
        elif isinstance(item, list):
            # 兼容 rows 为二维数组格式 [[col1, col2, ...], ...]
            virtual_rows.append({
                "code": item[0] if len(item) > 0 else "",
                "name": item[1] if len(item) > 1 else "",
                "year_end": item[2] if len(item) > 2 else None,
                "year_begin": item[3] if len(item) > 3 else None,
                "formula": item[4] if len(item) > 4 else None,
            })

    return _extract_cells_from_virtual_sheet(
        virtual_rows, _NOTE_COLUMNS, cell_range, sheet_name, "note"
    )


async def _query_adj_cells(
    db: AsyncSession,
    project_id: str,
    year: int | None,
    adjustment_type: str,
    cell_range: str,
) -> list[dict]:
    """从 adjustments 表拼虚拟 sheet。

    虚拟 sheet 列映射：A=entry_no, B=account_code, C=account_name, D=debit_amount, E=credit_amount, F=description
    """
    adj_type_map = {"aje": "AJE", "rcl": "RCL", "rje": "RJE"}
    adj_type = adj_type_map.get(adjustment_type.lower(), adjustment_type.upper())
    sheet_name = f"adj_{adjustment_type}"

    if not project_id or not year:
        return []

    try:
        result = await db.execute(text("""
            SELECT adjustment_no, account_code, account_name, debit_amount, credit_amount, description
            FROM adjustments
            WHERE project_id = :pid AND year = :y AND adjustment_type = :at AND is_deleted = false
            ORDER BY adjustment_no, account_code
            LIMIT 500
        """), {"pid": project_id, "y": year, "at": adj_type})
        rows = result.fetchall()
    except Exception as e:
        logger.warning("_query_adj_cells failed: %s", e)
        return []

    virtual_rows: list[dict] = []
    for r in rows:
        virtual_rows.append({
            "entry_no": r[0] or "",
            "account_code": r[1] or "",
            "account_name": r[2] or "",
            "debit_amount": float(r[3]) if r[3] is not None else None,
            "credit_amount": float(r[4]) if r[4] is not None else None,
            "description": r[5] or "",
        })

    return _extract_cells_from_virtual_sheet(
        virtual_rows, _ADJ_COLUMNS, cell_range, sheet_name, "adj"
    )


async def _query_tb_cells(
    db: AsyncSession,
    project_id: str,
    year: int | None,
    aux_dim: str,
    cell_range: str,
) -> list[dict]:
    """从 trial_balance 表拼虚拟 sheet。

    虚拟 sheet 列映射：A=account_code, B=account_name, C=opening_balance, D=debit_amount, E=credit_amount, F=closing_balance, G=audited_amount

    aux_dim: 'detail' (明细) / 'summary' (汇总)
    """
    sheet_name = f"tb_{aux_dim}"

    if not project_id or not year:
        return []

    # trial_balance 表使用 standard_account_code 作为 account_code
    # closing_balance 需要计算：unadjusted_amount + aje_adjustment + rje_adjustment
    try:
        result = await db.execute(text("""
            SELECT standard_account_code, account_name, opening_balance,
                   COALESCE(aje_adjustment, 0) + COALESCE(rje_adjustment, 0) as debit_amount,
                   0 as credit_amount,
                   COALESCE(unadjusted_amount, 0) + COALESCE(aje_adjustment, 0) + COALESCE(rje_adjustment, 0) as closing_balance,
                   audited_amount
            FROM trial_balance
            WHERE project_id = :pid AND year = :y AND is_deleted = false
            ORDER BY standard_account_code
            LIMIT 500
        """), {"pid": project_id, "y": year})
        rows = result.fetchall()
    except Exception as e:
        logger.warning("_query_tb_cells failed: %s", e)
        return []

    virtual_rows: list[dict] = []
    for r in rows:
        virtual_rows.append({
            "account_code": r[0] or "",
            "account_name": r[1] or "",
            "opening_balance": float(r[2]) if r[2] is not None else None,
            "debit_amount": float(r[3]) if r[3] is not None else None,
            "credit_amount": float(r[4]) if r[4] is not None else None,
            "closing_balance": float(r[5]) if r[5] is not None else None,
            "audited_amount": float(r[6]) if r[6] is not None else None,
        })

    return _extract_cells_from_virtual_sheet(
        virtual_rows, _TB_COLUMNS, cell_range, sheet_name, "tb"
    )


# ─── 主路由器 ────────────────────────────────────────────────────────────────


class ModuleCellResolver:
    """跨模块 cell 级查询路由器。

    按 source 命名空间前缀路由到对应模块的 _query_*_cells 提取器。
    """

    async def resolve(
        self,
        db: AsyncSession,
        source: str,
        project_id: str | None,
        year: int | None = None,
    ) -> dict:
        """按 source 命名空间路由到 4 个 _query_*_cells。

        Returns:
            {rows: [...], columns: [...], total: int, source: str, module: str}
        """
        parsed = parse_source_uri(source)
        if not parsed:
            return {"rows": [], "columns": [], "total": 0, "error": f"无法解析 source URI: {source}"}

        module = parsed["module"]
        qualifier = parsed.get("qualifier", "")
        cell_range = parsed.get("cell_range")

        if not cell_range:
            return {"rows": [], "columns": [], "total": 0, "error": "缺少 cell_range"}

        if not project_id:
            return {"rows": [], "columns": [], "total": 0, "error": "跨模块 cell 查询需要 project_id"}

        cells: list[dict] = []

        if module == "report":
            cells = await _query_report_cells(db, project_id, year, qualifier, cell_range)
        elif module == "note":
            cells = await _query_note_cells(db, project_id, year, qualifier, cell_range)
        elif module == "adj":
            cells = await _query_adj_cells(db, project_id, year, qualifier, cell_range)
        elif module == "tb":
            cells = await _query_tb_cells(db, project_id, year, qualifier, cell_range)
        else:
            return {"rows": [], "columns": [], "total": 0, "error": f"不支持的模块: {module}"}

        # 统一输出
        columns = ["cell_ref", "value", "formula", "sheet_name", "module"]
        return {
            "rows": cells,
            "columns": columns,
            "total": len(cells),
            "source": "jsonb_direct",
            "module": module,
        }


# 模块级单例
module_cell_resolver = ModuleCellResolver()
