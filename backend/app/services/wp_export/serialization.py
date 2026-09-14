"""确定性序列化与快照哈希

提供 Round-Trip 一致性所需的确定性序列化函数和 SHA-256 快照哈希计算。
同时提供对称的反序列化函数（deserialize_cell_value / parse_sheet_data），
确保导出→导入 Round-Trip 一致性。

规则：
- 列顺序固定（由 render_schema columns 定义顺序决定）
- 数值精度固定：Decimal(20,4)，四舍五入
- 日期格式固定：ISO-8601 (YYYY-MM-DD)
- 空值处理固定：None → 空字符串（文本列）/ None（数值列）
- SHA-256 哈希：sheet 按名称字母序、row 按原始序

Requirements: 10.2, 10.3, 1.5, 4.1
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

NUMERIC_PRECISION = 4  # decimal(20,4)
DATE_FORMAT = "%Y-%m-%d"


def serialize_cell_value(value: Any, col_type: str) -> Any:
    """确定性单元格值序列化

    根据列类型将单元格值转换为确定性表示，保证同内容多次序列化结果一致。

    Args:
        value: 原始单元格值（可为 None、数值、日期、字符串等）
        col_type: 列类型标识，取值 "number" | "date" | "text" 或其他

    Returns:
        序列化后的值：
        - number 类型: float（精度 4 位小数）或 None
        - date 类型: ISO-8601 日期字符串 或 空字符串
        - 其他类型: 字符串 或 空字符串
    """
    if value is None:
        return None if col_type == "number" else ""

    if col_type == "number":
        try:
            quantized = Decimal(str(value)).quantize(
                Decimal(f"0.{'0' * NUMERIC_PRECISION}")
            )
            return float(quantized)
        except (InvalidOperation, ValueError):
            # 无法转换为数值时返回 None
            return None

    if col_type == "date":
        if isinstance(value, (date, datetime)):
            return value.strftime(DATE_FORMAT)
        return str(value)

    return str(value)


def compute_snapshot_hash(workbook_data: dict[str, list[list]]) -> str:
    """计算底稿全部 sheet 内容的 SHA-256 哈希

    用于导出时生成快照哈希，导入时比对检测内容是否实质变更。

    规则：
    - sheet 按名称字母序排列（确保相同内容不同插入顺序产生相同哈希）
    - 每个 sheet 内 rows 按原始顺序
    - 每个 row 通过 json.dumps(sort_keys=True) 序列化为字符串
    - 连接 sheet_name + 各 row 字符串后计算 SHA-256

    Args:
        workbook_data: {sheet_name: [[cell, cell, ...], ...]} 格式的底稿数据，
                       cell 值应已经过 serialize_cell_value 处理

    Returns:
        64 字符的 SHA-256 十六进制哈希字符串
    """
    hasher = hashlib.sha256()

    for sheet_name in sorted(workbook_data.keys()):
        hasher.update(sheet_name.encode("utf-8"))
        for row in workbook_data[sheet_name]:
            row_str = json.dumps(row, ensure_ascii=False, sort_keys=True)
            hasher.update(row_str.encode("utf-8"))

    return hasher.hexdigest()


# ─── 反序列化（导入解析）──────────────────────────────────────────────────────


def deserialize_cell_value(value: Any, col_type: str) -> Any:
    """反序列化单元格值（与 serialize_cell_value 对称）。

    将从 xlsx 读取的 cell value 转换回标准内部表示，
    确保 serialize → deserialize round-trip 一致性。

    Args:
        value: xlsx 单元格原始值（openpyxl 读取）
        col_type: 列类型标识，取值 "number" | "date" | "text" 或其他

    Returns:
        反序列化后的值：
        - number 类型: float（精度 4 位小数）或 None
        - date 类型: ISO-8601 日期字符串 或 空字符串
        - 其他类型: 字符串 或 空字符串
    """
    if value is None:
        return None if col_type == "number" else ""

    if col_type == "number":
        # 空字符串视为 None
        if isinstance(value, str) and value.strip() == "":
            return None
        try:
            quantized = Decimal(str(value)).quantize(
                Decimal(f"0.{'0' * NUMERIC_PRECISION}")
            )
            return float(quantized)
        except (InvalidOperation, ValueError):
            return None

    if col_type == "date":
        if isinstance(value, (date, datetime)):
            return value.strftime(DATE_FORMAT)
        if isinstance(value, str) and value.strip() == "":
            return ""
        return str(value)

    # text 或其他
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return str(value)


def parse_sheet_data(ws: Any, schema: dict) -> dict:
    """按 schema 列映射解析 sheet 数据（导入时使用）。

    使用与导出相同的列映射规则确保双向一致。

    Args:
        ws: openpyxl Worksheet 对象
        schema: sheet 的结构定义 dict，包含 dynamic_table.columns 和 start_row。
                columns 格式: {col_letter: {field: str, type: str}} 或
                             {col_letter: str}（简写，type 默认 text）

    Returns:
        dict with:
          - rows: list[dict] — 解析出的数据行（跳过全空行）
    """
    table_schema = schema.get("dynamic_table", {})
    columns = table_schema.get("columns", {})
    start_row = table_schema.get("start_row", 1)

    rows: list[dict] = []
    max_row = ws.max_row or 0

    for row_idx in range(start_row, max_row + 1):
        row_data: dict[str, Any] = {}
        has_data = False

        for col_letter, col_def in columns.items():
            # 解析列定义
            if isinstance(col_def, dict):
                field = col_def.get("field", "")
                col_type = col_def.get("type", "text")
            else:
                field = str(col_def)
                col_type = "text"

            cell_ref = f"{col_letter}{row_idx}"
            cell = ws[cell_ref]
            cell_value = cell.value if hasattr(cell, "value") else cell

            value = deserialize_cell_value(cell_value, col_type)

            if value is not None and value != "":
                has_data = True

            # 支持嵌套字段（如 "account.code"）
            _set_nested(row_data, field, value)

        if has_data:
            rows.append(row_data)

    return {"rows": rows}


def _set_nested(data: dict, field: str, value: Any) -> None:
    """设置嵌套字段值（支持 'parent.child' 点分路径）。

    Args:
        data: 目标字典
        field: 字段路径（如 "account.code" 或 "name"）
        value: 要设置的值
    """
    if not field:
        return

    parts = field.split(".")
    current = data
    for part in parts[:-1]:
        if part not in current:
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value
