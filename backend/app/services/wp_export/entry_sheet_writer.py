"""录入清单 sheet 渲染 — 导出产物侧（workpaper-import-export-lifecycle-closure Task 8）

## 定位

`entry_payload_reader` 负责**取**录入载荷，本模块负责把它**渲染成 xlsx sheet**
并**追加**到产物里。两者分开是为了让渲染可无 DB 单测。

## 🔴 只追加、绝不改写模板既有单元格（R2.3）

模板单元格回填需要 per-cycle 的「item_id → 单元格地址」映射，而真实库
`structure.json` **全库 0 个**、`item_id` 形态 **211 种** —— 没有可用的映射真源。
硬按顺序往模板里塞会把数据写到错误的格子（比"空模板"更糟：错数比无数更难发现）。
故本 spec 明确只做**附加 sheet**，模板既有 sheet 逐格不动。

## 三态渲染（R2.2 + 实测形态）

| 载荷形态 | 渲染 | 为什么 |
|---|---|---|
| `json_array` | 每 `item_id` 一区块：标题行 + 表头（**列名取载荷自身键集**）+ 数据行 | 这是真正的结构化录入，列名不能硬写 |
| `json_object` | `item_id` + 键 / 值 两列纵向 | 对象无天然行概念 |
| `plain_text` | `item_id` / 值 / 来源列 三列 | 与 R2.2 原始设想一致 |

## 与 R2.2 的偏离（已在 tasks.md 登记）

AC 字面要求「item_id / 值 / 结论 / 备注」四列。实测 `conclusion` 与 `remark`
是**同一载荷的两个候选存放列**（哪列非空用哪列），不是两个并列业务字段。
故渲染成「来源列」标注（`source_field`），由它承担 R2.8 的「数据来源」语义。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from app.services.wp_export.entry_payload_reader import (
    EntryPayload,
    EntryPayloadResult,
)

logger = logging.getLogger(__name__)

#: 清单 sheet 基名。`_` 前缀让它排在业务 sheet 之前，用户打开即见。
ENTRY_SHEET_BASE_NAME = "_录入内容"

#: openpyxl 的 sheet 名硬上限（Excel 规格）
_SHEET_NAME_MAX = 31

#: 来源列的中文表头 —— 承担 R2.8「数据来源」语义
_SOURCE_FIELD_HEADER = "来源列"

#: 各形态的中文标签（产物内展示，单一真源）
_SHAPE_LABELS: dict[str, str] = {
    "json_array": "结构化表格",
    "json_object": "键值记录",
    "plain_text": "文本",
}

_TITLE_FONT = Font(bold=True, size=12)
_HEADER_FONT = Font(bold=True)
_NOTE_FONT = Font(italic=True, color="808080")
_WARN_FONT = Font(bold=True, color="C00000")


def resolve_entry_sheet_name(existing: list[str]) -> str:
    """产出不与 `existing` 冲突的清单 sheet 名（R2.5）。

    冲突时后缀递增；且必须尊重 Excel 的 31 字符上限 —— 超限会被 openpyxl
    静默截断，截断后**可能又撞名**，所以要在截断后重新判重。
    """
    taken = set(existing)
    base = ENTRY_SHEET_BASE_NAME[:_SHEET_NAME_MAX]
    if base not in taken:
        return base
    for seq in range(2, 1000):
        suffix = str(seq)
        name = f"{ENTRY_SHEET_BASE_NAME[: _SHEET_NAME_MAX - len(suffix)]}{suffix}"
        if name not in taken:
            return name
    raise RuntimeError("无法为录入清单分配唯一 sheet 名（已尝试 1000 个后缀）")


def _write_row(ws: Any, row: int, values: list[Any], font: Font | None = None) -> None:
    for col, val in enumerate(values, start=1):
        cell = ws.cell(row=row, column=col, value=val)
        if font is not None:
            cell.font = font


def _render_json_array(ws: Any, row: int, p: EntryPayload) -> int:
    """区块式渲染：标题 → 表头（键集） → 数据行。返回下一个可写行号。"""
    rows = p.rows or []
    _write_row(
        ws,
        row,
        [f"{p.item_id}", f"（{_SHAPE_LABELS[p.shape]}，{len(rows)} 行）",
         f"{_SOURCE_FIELD_HEADER}：{p.source_field}"],
        _TITLE_FONT,
    )
    row += 1

    # 🔴 列名取载荷自身键集（保序：按首次出现顺序），不硬写
    keys: list[str] = []
    seen: set[str] = set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                keys.append(str(k))

    if not keys:
        _write_row(ws, row, ["（该表无列）"], _NOTE_FONT)
        return row + 2

    _write_row(ws, row, keys, _HEADER_FONT)
    row += 1
    for r in rows:
        _write_row(ws, row, [_flatten(r.get(k)) for k in keys])
        row += 1
    return row + 1  # 区块间空一行


def _render_json_object(ws: Any, row: int, p: EntryPayload) -> int:
    obj = p.obj or {}
    _write_row(
        ws,
        row,
        [f"{p.item_id}", f"（{_SHAPE_LABELS[p.shape]}，{len(obj)} 项）",
         f"{_SOURCE_FIELD_HEADER}：{p.source_field}"],
        _TITLE_FONT,
    )
    row += 1
    _write_row(ws, row, ["键", "值"], _HEADER_FONT)
    row += 1
    for k, v in obj.items():
        _write_row(ws, row, [str(k), _flatten(v)])
        row += 1
    return row + 1


def _flatten(value: Any) -> Any:
    """把嵌套结构压成单元格可承载的标量。

    openpyxl 无法写 dict / list，遇到就会抛 `ValueError: Cannot convert`。
    这里转 JSON 风格字符串而不是抛 —— 导出不该因一个嵌套字段整体失败。
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    try:
        import json

        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def write_entry_sheet(
    wb: Any,
    result: EntryPayloadResult,
    *,
    index: int = 1,
) -> str | None:
    """把录入载荷渲染成一张新 sheet 并插入 `wb`。

    Args:
        wb: openpyxl Workbook。
        result: `read_entry_payloads` 的产出。
        index: 插入位置（默认 1 = 紧随自证 sheet 之后）。

    Returns:
        新建的 sheet 名；**无录入内容时返回 `None` 且不建 sheet**（R2.6）。
    """
    if not result.has_content:
        return None  # R2.6：无非空录入 ⇒ 不产生清单 sheet

    name = resolve_entry_sheet_name(list(wb.sheetnames))
    ws = wb.create_sheet(title=name, index=index)

    row = 1
    _write_row(ws, row, ["底稿录入内容清单"], _TITLE_FONT)
    row += 1

    # R2.8：标注数据来源与导出时点，使其可与底稿界面交叉核对
    stamped = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    _write_row(
        ws,
        row,
        [f"数据来源：checklist_responses（{result.total_chars} 字符 / "
         f"{len(result.payloads)} 项）    导出时点：{stamped}"],
        _NOTE_FONT,
    )
    row += 1

    # 截断如实标注（R2.7）—— 不标注等于骗人
    if result.truncated:
        parts: list[str] = []
        if result.dropped_by_cap:
            parts.append(f"因超出上限丢弃 {result.dropped_by_cap} 项")
        n_cut = sum(1 for p in result.payloads if p.truncated)
        if n_cut:
            parts.append(f"{n_cut} 项正文过长已截断")
        _write_row(ws, row, [f"注意：本清单不完整 —— {'；'.join(parts)}"], _WARN_FONT)
        row += 1

    if result.parse_failures:
        _write_row(
            ws,
            row,
            [f"注意：{result.parse_failures} 项内容无法按结构解析，已按原文展示"],
            _WARN_FONT,
        )
        row += 1

    row += 1  # 与正文空一行

    plain: list[EntryPayload] = []
    for p in result.payloads:
        if p.shape == "json_array":
            row = _render_json_array(ws, row, p)
        elif p.shape == "json_object":
            row = _render_json_object(ws, row, p)
        else:
            plain.append(p)

    # 纯文本统一成三列表（R2.2 的原始设想在这一档成立）
    if plain:
        _write_row(ws, row, ["文本类录入"], _TITLE_FONT)
        row += 1
        _write_row(ws, row, ["item_id", "值", _SOURCE_FIELD_HEADER], _HEADER_FONT)
        row += 1
        for p in plain:
            text = p.text or ""
            if p.truncated:
                text = f"{text}…（已截断，原长 {p.raw_len} 字符）"
            _write_row(ws, row, [p.item_id, text, p.source_field])
            row += 1

    # 列宽：首列放 item_id 需要宽一些
    ws.column_dimensions["A"].width = 34
    for c in range(2, 9):
        ws.column_dimensions[get_column_letter(c)].width = 24

    logger.debug(
        "write_entry_sheet: sheet=%s payloads=%d truncated=%s",
        name, len(result.payloads), result.truncated,
    )
    return name


__all__ = [
    "ENTRY_SHEET_BASE_NAME",
    "resolve_entry_sheet_name",
    "write_entry_sheet",
]
