"""
底稿精细化规则引擎

加载 wp_fine_rules/{code}.json 精细化规则，执行：
1. 精确提取审定表关键行数据（按固定行号+列号）
2. 执行交叉引用校验（审定表↔明细表↔余额调节表↔试算表↔报表）
3. 执行审计检查（余额核对/完整性/变动分析）
4. 生成结构化提取结果（供 parsed_data 和 AI 使用）
"""
import json
import logging
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from app.services.wp_fine_rule_checks import _run_audit_checks
from app.services.wp_fine_rule_util import _safe_num

logger = logging.getLogger(__name__)

_FINE_RULES_DIR = Path(__file__).parent.parent.parent / "data" / "wp_fine_rules"


def load_fine_rule(wp_code: str) -> Optional[dict]:
    """加载精细化规则文件"""
    # 精确匹配
    code = wp_code.upper().split("-")[0] if "-" in wp_code else wp_code.upper()
    for fp in _FINE_RULES_DIR.glob("*.json"):
        try:
            with open(fp, "r", encoding="utf-8-sig") as f:
                rule = json.load(f)
            if rule.get("wp_code", "").upper() == code:
                return rule
        except Exception:
            continue
    return None


def list_fine_rules() -> list[dict]:
    """列出所有精细化规则（含分类和质量等级）"""
    # 循环前缀 → 循环名称
    cycle_names = {
        "A": "完成阶段", "B": "风险评估", "C": "控制测试",
        "D": "收入循环", "E": "货币资金", "F": "存货循环",
        "G": "投资循环", "H": "固定资产", "I": "无形资产",
        "J": "薪酬", "K": "管理循环", "L": "债务循环",
        "M": "权益循环", "N": "所得税", "S": "特定项目", "T": "IPE测试",
    }
    rules = []
    if not _FINE_RULES_DIR.exists():
        return rules
    for fp in sorted(_FINE_RULES_DIR.glob("*.json")):
        try:
            with open(fp, "r", encoding="utf-8-sig") as f:
                rule = json.load(f)
            code = rule.get("wp_code", "")
            prefix = code[0] if code else "?"
            has_layout = any(s.get("layout") for s in rule.get("sheet_rules", []))
            has_key_rows = any(s.get("key_rows") for s in rule.get("sheet_rules", []))
            # 质量等级：A=精修 B=有layout C=有checks D=基础
            if has_layout and has_key_rows:
                quality = "A"
            elif has_layout:
                quality = "B"
            elif rule.get("audit_checks"):
                quality = "C"
            else:
                quality = "D"
            rules.append({
                "wp_code": code,
                "name": rule.get("name"),
                "cycle": cycle_names.get(prefix, "其他"),
                "cycle_prefix": prefix,
                "version": rule.get("version", ""),
                "quality": quality,
                "sheets": len(rule.get("sheet_rules", rule.get("sheets", []))),
                "checks": len(rule.get("audit_checks", [])),
                "cross_refs": len(rule.get("cross_references", [])),
                "account_codes": rule.get("account_codes", []),
                "file": fp.name,
            })
        except Exception:
            continue
    return rules


def extract_with_fine_rule(
    file_path: str,
    wp_code: str,
    project_id: str = "",
    year: int = 0,
) -> dict[str, Any]:
    """使用精细化规则从底稿Excel提取结构化数据

    返回：
    {
        "wp_code": "E1",
        "sheets": {
            "E1-1": {
                "rows": {"cash": {"closing_audited": 1000, ...}, "total": {...}},
                "raw_data": [...],
            },
            "E1-2": {...},
        },
        "summary": {"total_closing_audited": 1000, ...},
        "checks": [{"code": "E1-CHK-01", "passed": true, ...}],
        "cross_refs": [{"from": "...", "to": "...", "matched": true}],
    }
    """
    from app.services.xlsx_read_adapter import list_sheet_names, read_sheet_values

    rule = load_fine_rule(wp_code)
    if not rule:
        return {"error": f"No fine rule for {wp_code}"}

    fp = Path(file_path)
    if not fp.exists():
        return {"error": f"File not found: {file_path}"}

    # 收集所有需要打开的文件（主文件 + source_file 指定的其他文件）
    files_to_open: dict[str, Path] = {"_main": fp}
    base_dir = fp.parent
    for sr in rule.get("sheet_rules", []):
        sf = sr.get("source_file", "")
        if sf and sf not in files_to_open:
            sf_path = base_dir / sf
            if not sf_path.exists():
                # 尝试在模板目录中查找
                sf_path = base_dir.parent / sf
            if sf_path.exists():
                files_to_open[sf] = sf_path

    # 获取所有工作簿的 sheet 名列表
    workbook_sheets: dict[str, list[str]] = {}
    for key, path in files_to_open.items():
        try:
            workbook_sheets[key] = list_sheet_names(path)
        except Exception as e:
            logger.warning("Cannot list sheets from %s: %s", path, e)
            workbook_sheets[key] = []

    result: dict[str, Any] = {
        "wp_code": rule["wp_code"],
        "name": rule.get("name", rule.get("wp_name", rule["wp_code"])),
        "sheets": {},
        "summary": {},
        "checks": [],
        "cross_refs": [],
    }

    # 遍历规则中的每个Sheet
    for sheet_rule in rule.get("sheet_rules", rule.get("sheets", [])):
        code = sheet_rule.get("code", sheet_rule.get("exact_name", ""))
        # 优先用 exact_name 精确匹配
        exact_name = sheet_rule.get("exact_name", "")
        pattern = exact_name or sheet_rule.get("sheet_pattern", sheet_rule.get("name_pattern", ""))
        sheet_type = sheet_rule.get("type", "")

        # 确定在哪个工作簿中查找
        source_file = sheet_rule.get("source_file", "")
        wb_key = source_file if source_file in workbook_sheets else "_main"
        wb_path = files_to_open.get(wb_key) or files_to_open.get("_main")
        available_sheets = workbook_sheets.get(wb_key, [])

        if not wb_path or not available_sheets:
            result["sheets"][code] = {"found": False, "reason": "workbook not available"}
            continue

        # 匹配Sheet名
        matched_sheet = _find_sheet_name(available_sheets, pattern)
        if not matched_sheet:
            result["sheets"][code] = {"found": False}
            continue

        # 读取 sheet 数据为 grid
        try:
            grid = read_sheet_values(wb_path, matched_sheet)
        except Exception as e:
            logger.warning("Cannot read sheet %s from %s: %s", matched_sheet, wb_path, e)
            result["sheets"][code] = {"found": False, "reason": str(e)}
            continue

        sheet_data: dict[str, Any] = {"found": True, "type": sheet_type, "rows": {}}

        # 按类型提取 — 兼容新旧两种列定义格式
        effective_rule = sheet_rule
        if "layout" in sheet_rule and "columns" not in sheet_rule:
            effective_rule = {**sheet_rule, "columns": sheet_rule["layout"]["columns"]}

        if sheet_type == "summary" and "key_rows" in effective_rule:
            sheet_data["rows"] = _extract_summary_rows_grid(grid, effective_rule)
        elif sheet_type == "detail":
            sheet_data["detail_rows"] = _extract_detail_rows_grid(grid, effective_rule)
        elif sheet_type == "adjustment":
            sheet_data["adjustments"] = _extract_adjustments_grid(grid, effective_rule)

        result["sheets"][code] = sheet_data

    # 构建摘要
    summary_code = f"{rule['wp_code']}-1"
    summary_sheet = result["sheets"].get(summary_code, {})
    summary_rows = summary_sheet.get("rows", {})
    total_row = summary_rows.get("total", {})
    result["summary"] = {
        "closing_audited": total_row.get("closing_audited") or total_row.get("closing_balance"),
        "opening_audited": total_row.get("opening_audited"),
        "change_amount": total_row.get("change_amount"),
        # 保留所有提取的行数据（含动态发现的明细行），供附注填充使用
        "rows": summary_rows,
    }

    # 执行审计检查（实际校验）
    result["checks"] = _run_audit_checks(rule, result["sheets"], result["summary"])

    logger.info("extract_with_fine_rule: %s → %d sheets extracted, %d checks",
                wp_code, sum(1 for s in result["sheets"].values() if s.get("found")),
                len(result["checks"]))
    return result


def _find_sheet_name(sheet_names: list[str], pattern: str) -> str | None:
    """根据精确名称或模式匹配Sheet名。"""
    import re
    # 优先精确匹配
    for name in sheet_names:
        if name == pattern:
            return name
    # 降级模式匹配
    parts = pattern.split("|")
    for name in sheet_names:
        for p in parts:
            if p in name or re.search(p, name, re.IGNORECASE):
                return name
    return None


def _find_sheet(wb, pattern: str):
    """根据精确名称或模式匹配Sheet（旧 openpyxl 接口，保留用于 _run_audit_checks 等）"""
    import re
    # 优先精确匹配
    for ws in wb.worksheets:
        if ws.title == pattern:
            return ws
    # 降级模式匹配
    parts = pattern.split("|")
    for ws in wb.worksheets:
        title = ws.title
        for p in parts:
            if p in title or re.search(p, title, re.IGNORECASE):
                return ws
    return None


def _grid_cell(grid: list[list], row: int, col: int) -> Any:
    """1-based row/col access into grid."""
    ri, ci = row - 1, col - 1
    if ri < 0 or ri >= len(grid):
        return None
    row_data = grid[ri] or []
    if ci < 0 or ci >= len(row_data):
        return None
    return row_data[ci]


def _extract_summary_rows_grid(grid: list[list], sheet_rule: dict) -> dict[str, dict]:
    """从审定表 grid 提取关键行数据（替代 _extract_summary_rows）。"""
    key_rows = sheet_rule.get("key_rows", {})
    columns = sheet_rule.get("layout", {}).get("columns", sheet_rule.get("columns", {}))
    detail_discovery = sheet_rule.get("detail_discovery", {})
    result = {}

    for key, row_def in key_rows.items():
        if isinstance(row_def, int):
            row_num = row_def
            row_data: dict[str, Any] = {
                "label": str(_grid_cell(grid, row_num, 1) or ""),
                "row": row_num,
                "is_total": "total" in key.lower(),
            }
            for col_key, col_def in columns.items():
                if col_key == "label":
                    continue
                col_num = col_def.get("col", 0) if isinstance(col_def, dict) else 0
                if col_num > 0:
                    row_data[col_key] = _safe_num(_grid_cell(grid, row_num, col_num))
            result[key] = row_data
            continue

        if isinstance(row_def, list):
            for i, rn in enumerate(row_def):
                if not isinstance(rn, int):
                    continue
                item_key = f"{key}_{i}"
                item_data: dict[str, Any] = {
                    "label": str(_grid_cell(grid, rn, 1) or ""),
                    "row": rn,
                }
                for col_key, col_def in columns.items():
                    if col_key == "label":
                        continue
                    col_num = col_def.get("col", 0) if isinstance(col_def, dict) else 0
                    if col_num > 0:
                        item_data[col_key] = _safe_num(_grid_cell(grid, rn, col_num))
                result[item_key] = item_data
            continue

        if not isinstance(row_def, dict):
            continue
        row_num = row_def.get("row", 0)
        if row_num <= 0:
            continue

        row_data = {
            "label": row_def.get("label", ""),
            "row": row_num,
            "is_total": row_def.get("is_total", False),
            "account_code": row_def.get("account_code", ""),
        }
        if row_def.get("report_row"):
            row_data["report_row"] = row_def["report_row"]

        for col_key, col_def in columns.items():
            if col_key == "label":
                continue
            col_num = col_def.get("col", 0) if isinstance(col_def, dict) else 0
            if col_num > 0:
                row_data[col_key] = _safe_num(_grid_cell(grid, row_num, col_num))

        result[key] = row_data

    # 动态发现明细行
    if detail_discovery.get("mode") == "auto":
        start_row = detail_discovery.get("start_row", 7)
        total_row = None
        for val in result.values():
            if isinstance(val, dict) and val.get("is_total"):
                total_row = val.get("row")
                break
        end_row = (total_row - 1) if total_row else start_row + 50

        detail_idx = 0
        for row_num in range(start_row, end_row + 1):
            if any(isinstance(v, dict) and v.get("row") == row_num for v in result.values()):
                continue
            label = str(_grid_cell(grid, row_num, 1) or "").strip()
            if not label:
                continue
            detail_data: dict[str, Any] = {
                "label": label,
                "row": row_num,
                "is_detail": True,
            }
            for col_key, col_def in columns.items():
                if col_key == "label":
                    continue
                col_num = col_def.get("col", 0) if isinstance(col_def, dict) else 0
                if col_num > 0:
                    detail_data[col_key] = _safe_num(_grid_cell(grid, row_num, col_num))
            result[f"detail_{detail_idx}"] = detail_data
            detail_idx += 1

    return result


def _extract_detail_rows_grid(grid: list[list], sheet_rule: dict) -> list[dict]:
    """从明细表 grid 提取数据行（替代 _extract_detail_rows）。"""
    data_start = sheet_rule.get("data_start_row", 1)
    columns = sheet_rule.get("layout", {}).get("columns", sheet_rule.get("columns", {}))
    max_row = len(grid)
    rows = []

    for r in range(data_start, min(max_row + 1, data_start + 200)):
        row_data = {}
        has_data = False
        for col_key, col_def in columns.items():
            col_num = col_def.get("col", 0) if isinstance(col_def, dict) else 0
            if col_num > 0:
                val = _grid_cell(grid, r, col_num)
                if val is not None:
                    has_data = True
                row_data[col_key] = val
        if has_data:
            row_data["_row"] = r
            rows.append(row_data)

    return rows


def _extract_adjustments_grid(grid: list[list], sheet_rule: dict) -> list[dict]:
    """从调整分录表 grid 提取（替代 _extract_adjustments）。"""
    data_start = sheet_rule.get("data_start_row", 1)
    columns = sheet_rule.get("layout", {}).get("columns", sheet_rule.get("columns", {}))
    max_row = len(grid)
    items = []

    for r in range(data_start, min(max_row + 1, data_start + 100)):
        row_data = {}
        has_data = False
        for col_key, col_def in columns.items():
            col_num = col_def.get("col", 0) if isinstance(col_def, dict) else 0
            if col_num > 0:
                val = _grid_cell(grid, r, col_num)
                if val is not None:
                    has_data = True
                row_data[col_key] = val
        if has_data:
            items.append(row_data)

    return items


def _extract_summary_rows(ws, sheet_rule: dict) -> dict[str, dict]:
    """从审定表提取关键行数据

    支持三种模式：
    1. key_rows 固定行（结构性行：合计/小计/减：/试算/差异）
    2. detail_discovery 动态发现（从 start_row 到合计行之间自动识别明细行）
    3. 兼容旧格式（整数行号、数组行号）
    """
    key_rows = sheet_rule.get("key_rows", {})
    columns = sheet_rule.get("layout", {}).get("columns", sheet_rule.get("columns", {}))
    detail_discovery = sheet_rule.get("detail_discovery", {})
    result = {}

    # ── 1. 提取结构性行（key_rows 中定义的固定行）──
    for key, row_def in key_rows.items():
        # 兼容新格式：值为整数（单行号）
        if isinstance(row_def, int):
            row_num = row_def
            row_data: dict[str, Any] = {
                "label": str(ws.cell(row_num, 1).value or ""),
                "row": row_num,
                "is_total": "total" in key.lower(),
            }
            for col_key, col_def in columns.items():
                if col_key == "label":
                    continue
                col_num = col_def.get("col", 0) if isinstance(col_def, dict) else 0
                if col_num > 0:
                    row_data[col_key] = _safe_num(ws.cell(row_num, col_num).value)
            result[key] = row_data
            continue

        # 兼容新格式：值为数组（多行号）
        if isinstance(row_def, list):
            for i, rn in enumerate(row_def):
                if not isinstance(rn, int):
                    continue
                item_key = f"{key}_{i}"
                item_data: dict[str, Any] = {
                    "label": str(ws.cell(rn, 1).value or ""),
                    "row": rn,
                }
                for col_key, col_def in columns.items():
                    if col_key == "label":
                        continue
                    col_num = col_def.get("col", 0) if isinstance(col_def, dict) else 0
                    if col_num > 0:
                        item_data[col_key] = _safe_num(ws.cell(rn, col_num).value)
                result[item_key] = item_data
            continue

        # 旧格式：值为字典
        if not isinstance(row_def, dict):
            continue
        row_num = row_def.get("row", 0)
        if row_num <= 0:
            continue

        row_data = {
            "label": row_def.get("label", ""),
            "row": row_num,
            "is_total": row_def.get("is_total", False),
            "account_code": row_def.get("account_code", ""),
        }
        if row_def.get("report_row"):
            row_data["report_row"] = row_def["report_row"]

        for col_key, col_def in columns.items():
            if col_key == "label":
                continue
            col_num = col_def.get("col", 0) if isinstance(col_def, dict) else 0
            if col_num > 0:
                row_data[col_key] = _safe_num(ws.cell(row_num, col_num).value)

        result[key] = row_data

    # ── 2. 动态发现明细行（detail_discovery）──
    if detail_discovery.get("mode") == "auto":
        start_row = detail_discovery.get("start_row", 7)
        # 找到第一个合计行的行号作为结束边界
        total_row = None
        for val in result.values():
            if isinstance(val, dict) and val.get("is_total"):
                total_row = val.get("row")
                break
        end_row = (total_row - 1) if total_row else start_row + 50  # 安全上限

        detail_idx = 0
        for row_num in range(start_row, end_row + 1):
            # 跳过已在 key_rows 中定义的行
            if any(isinstance(v, dict) and v.get("row") == row_num for v in result.values()):
                continue
            label = str(ws.cell(row_num, 1).value or "").strip()
            if not label or detail_discovery.get("skip_empty", True) and not label:
                continue
            # 提取该行数据
            detail_data: dict[str, Any] = {
                "label": label,
                "row": row_num,
                "is_detail": True,
            }
            for col_key, col_def in columns.items():
                if col_key == "label":
                    continue
                col_num = col_def.get("col", 0) if isinstance(col_def, dict) else 0
                if col_num > 0:
                    detail_data[col_key] = _safe_num(ws.cell(row_num, col_num).value)
            result[f"detail_{detail_idx}"] = detail_data
            detail_idx += 1

    return result


def _extract_detail_rows(ws, sheet_rule: dict) -> list[dict]:
    """从明细表提取数据行"""
    data_start = sheet_rule.get("data_start_row", 1)
    columns = sheet_rule.get("layout", {}).get("columns", sheet_rule.get("columns", {}))
    max_row = ws.max_row or 100
    rows = []

    for r in range(data_start, min(max_row + 1, data_start + 200)):
        row_data = {}
        has_data = False
        for col_key, col_def in columns.items():
            col_num = col_def.get("col", 0) if isinstance(col_def, dict) else 0
            if col_num > 0:
                val = ws.cell(r, col_num).value
                if val is not None:
                    has_data = True
                row_data[col_key] = val
        if has_data:
            row_data["_row"] = r
            rows.append(row_data)

    return rows


def _extract_adjustments(ws, sheet_rule: dict) -> list[dict]:
    """从调整分录表提取"""
    data_start = sheet_rule.get("data_start_row", 1)
    columns = sheet_rule.get("layout", {}).get("columns", sheet_rule.get("columns", {}))
    max_row = ws.max_row or 50
    items = []

    for r in range(data_start, min(max_row + 1, data_start + 100)):
        row_data = {}
        has_data = False
        for col_key, col_def in columns.items():
            col_num = col_def.get("col", 0)
            if col_num > 0:
                val = ws.cell(r, col_num).value
                if val is not None:
                    has_data = True
                row_data[col_key] = val
        if has_data:
            items.append(row_data)

    return items
