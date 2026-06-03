"""审定表（audit-sheet）行项目提取服务

从底稿 xlsx 模板的「审定表」sheet（class_code=`F-审定表`，如 应收票据「审定表D1-1」）
解析出结构化的行项目列表 AuditSheetRow，供前端 GtAuditSheet.vue 渲染可编辑表格。

动机（spec `audit-sheet-editable`）：审定表从只读 GtGridSheet（HTML 死网格）升级为
结构化可编辑表，行项目需从模板动态解析——不同科目（应收票据/固定资产/无形资产）
自动展示对应的行结构（分节 / 明细 / 小计 / 合计），并支持层级缩进。

解析策略（与模板布局解耦，避免硬编码行号）：
- 定位表头行 = 项目列（通常 A 列）值为「项目」/「科目」的行；
- 跳过子表头行（未审数/账项调整/审定数 等——项目列为空）；
- 数据行 = 表头行之后、项目列非空的行，直至首个空行（截断 审计说明/结论 等说明区）；
- 缩进：优先取前导空格 / 全角「　」推断，无前导空格时按「分节内的明细行」结构兜底缩进 1 级；
- 分节行：项目名以中文数字序号「一、二、三…」开头 → isSection=True, bold=True；
- 合计行：项目名含「合计」/「小计」 → isComputed=True, bold=True。

输出对齐 design 的 AuditSheetRow 后端结构（TB 取数列不在此处填，见组④ Task 13）。

纯函数无 DB 副作用，便于单测。文件不存在 / 解析失败 → 返回 []（降级，不抛异常）。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 表头行项目列关键词（命中其一即认定为表头行）
_HEADER_KEYWORDS = ("项目", "科目")

# 分节行：以中文数字序号开头（一、 二、 三．等），允许序号后接顿号/点/句点
_SECTION_PATTERN = re.compile(r"^[一二三四五六七八九十百零]+\s*[、.．)）]")

# 合计行关键词
_TOTAL_KEYWORDS = ("合计", "小计")

# 全角空格 / 半角空格 / 制表符（用于前导缩进推断）
_INDENT_CHARS = (" ", "\u3000", "\t")


def _cell_text(value: Any) -> str:
    """单元格值 → 去首尾空白的字符串（None → ''）。"""
    if value is None:
        return ""
    return str(value).strip()


def _is_section(item: str) -> bool:
    """是否分节标题行（中文数字序号开头）。"""
    return bool(_SECTION_PATTERN.match(item.strip()))


def _is_total(item: str) -> bool:
    """是否合计/小计行。"""
    stripped = item.strip()
    return any(kw in stripped for kw in _TOTAL_KEYWORDS)


def _leading_indent(raw_item: str) -> int:
    """从前导空格 / 全角空格推断缩进层级。

    规则：全角「　」每个计 1 级；半角空格每 2 个计 1 级；制表符每个计 1 级。
    """
    full = 0
    half = 0
    tab = 0
    for ch in raw_item:
        if ch == "\u3000":
            full += 1
        elif ch == " ":
            half += 1
        elif ch == "\t":
            tab += 1
        else:
            break
    return full + tab + (half // 2)


def extract_audit_rows_from_sheet(ws: Any) -> list[dict]:
    """从 openpyxl worksheet 提取审定表行项目列表。

    Returns:
        list[dict]: 每个元素对齐 design 的 AuditSheetRow 后端结构：
        {
            "id": "row-{n}",
            "item": str,                 # 项目名（去前导空格）
            "indent": int,               # 缩进层级（0/1/2…）
            "bold": bool,                # 是否粗体（分节/合计强制 True）
            "isSection": bool,           # 是否分节标题行（一、二、三）
            "isComputed": bool,          # 是否合计/小计行
            "account_code": None,        # 科目编码（TB 取数映射，组④ Task 13 填）
            "adj_amount": None,          # 账项调整（用户编辑，初始 None）
            "reclass_amount": None,      # 重分类调整（用户编辑，初始 None）
            "reason": "",                # 原因分析（用户编辑，初始空）
        }
    """
    max_row = ws.max_row or 0
    max_col = ws.max_column or 0
    if max_row == 0 or max_col == 0:
        return []

    # ─── 1. 定位表头行（项目列值为「项目」/「科目」）+ 项目列 ────────────
    header_row: int | None = None
    item_col = 1
    for r in range(1, min(max_row, 60) + 1):
        for c in range(1, min(max_col, 5) + 1):
            if _cell_text(ws.cell(row=r, column=c).value) in _HEADER_KEYWORDS:
                header_row = r
                item_col = c
                break
        if header_row is not None:
            break

    if header_row is None:
        return []

    # ─── 2. 定位数据起始行（跳过项目列为空的子表头行）────────────────────
    data_start = header_row + 1
    while data_start <= max_row and not _cell_text(ws.cell(row=data_start, column=item_col).value):
        data_start += 1

    # ─── 3. 逐行提取（项目列非空，遇首个空行截断说明/结论区）──────────────
    rows: list[dict] = []
    section_active = False
    n = 0
    for r in range(data_start, max_row + 1):
        cell = ws.cell(row=r, column=item_col)
        raw = "" if cell.value is None else str(cell.value)
        item = raw.strip()

        if not item:
            if rows:
                break  # 已收集到行 → 首个空行视为表体结束（截断说明区）
            continue

        is_section = _is_section(item)
        is_total = _is_total(item)

        # 缩进：优先前导空格推断；无前导缩进时，分节内明细行结构兜底缩进 1 级
        indent = _leading_indent(raw)
        if indent == 0 and not is_section and not is_total and section_active:
            indent = 1
        if is_section:
            section_active = True

        try:
            font_bold = bool(cell.font and cell.font.bold)
        except Exception:
            font_bold = False

        n += 1
        rows.append({
            "id": f"row-{n}",
            "item": item,
            "indent": indent,
            "bold": font_bold or is_section or is_total,
            "isSection": is_section,
            "isComputed": is_total,
            "account_code": None,
            "adj_amount": None,
            "reclass_amount": None,
            "reason": "",
        })

    return rows


def extract_audit_rows(file_path: str | Path, sheet_name: str) -> list[dict]:
    """读取 xlsx 文件指定 sheet，提取审定表行项目列表（纯函数，无 DB）。

    文件不存在 / 空 / sheet 缺失 / 解析失败 → 返回 []（降级，不抛异常）。
    """
    import openpyxl

    fp = Path(file_path)
    if not fp.exists() or fp.stat().st_size == 0:
        return []

    try:
        wb = openpyxl.load_workbook(str(fp), read_only=False, data_only=True)
    except Exception as e:
        logger.warning("extract_audit_rows: 加载 xlsx 失败 %s: %s", fp, e)
        return []

    try:
        if sheet_name not in wb.sheetnames:
            return []
        ws = wb[sheet_name]
        return extract_audit_rows_from_sheet(ws)
    except Exception as e:
        logger.warning("extract_audit_rows: 解析 sheet 失败 %s/%s: %s", fp, sheet_name, e)
        return []
    finally:
        wb.close()
