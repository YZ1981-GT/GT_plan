"""导入时每个 sheet 用哪套列映射：用户在列映射页确认的映射优先，没有才用自动识别。

spec citar-case-chain-fetch-fixes R1：确认映射以 ``mapping_entries[]``（按列号）提交，pipeline 原来读
``mappings`` 字典 ⇒ 确认映射从未生效；前端提交的 ``file_name`` 带上传存储前缀（``00_xxx.xlsx``），
pipeline 用 manifest 原名拼 key 也对不上。这里统一解析：

- 找确认项：文件名全等 → 去掉 ``NN_`` 存储前缀后全等 → 同 sheet 名且只有一项；
- 表头按 ``generate_canonical_headers`` 去重（两列都叫「公司代码」时不再互相覆盖）；
- ``mapping_entries`` 按 ``column_index`` 映射到去重后的表头；旧的 ``mappings`` 字典照旧兼容；
- 确认项给了表类型（非 unknown）以确认的为准。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .confirmed_mapping_dto import generate_canonical_headers

#: 自动识别列映射的最低置信度（低于此值的列不映射，进 raw_extra）
AUTO_MIN_CONFIDENCE = 50
#: 合并单元格向下填充的列（科目编码 / 名称常被合并）
_FORWARD_FILL_FIELDS = ("account_code", "account_name")
_STORE_PREFIX = re.compile(r"^\d{2}_")


@dataclass
class SheetPlan:
    table_type: str
    headers: list[str]
    col_mapping: dict[str, str]  # 去重后表头 → 标准字段
    ff_cols: list[int] = field(default_factory=list)
    source: str = "auto"  # confirmed / auto


def strip_store_prefix(name: str) -> str:
    return _STORE_PREFIX.sub("", name or "", count=1)


def mapping_locate_key(file_name: str | None, sheet_name: str | None, column_index: Any) -> str:
    """确认映射里某一列的定位键（文件 | sheet | 列序号）：账务查询来源卡片的链接与导入记录详情的行用同一个键。

    ``file_name`` 新旧导入有带 / 不带 ``NN_`` 存储前缀两种写法，先剥前缀（spec citar-cell-source-hover R9）。
    """
    return f"{strip_store_prefix(file_name or '')}|{sheet_name or ''}|{'' if column_index is None else column_index}"


def find_confirmed(filename: str, sheet_name: str, confirmed: list[dict[str, Any]] | None) -> dict | None:
    items = [m for m in (confirmed or []) if (m.get("sheet_name") or "") == sheet_name]
    if not items:
        return None
    for m in items:
        if (m.get("file_name") or "") == filename:
            return m
    plain = strip_store_prefix(filename)
    for m in items:
        if strip_store_prefix(m.get("file_name") or "") == plain:
            return m
    return items[0] if len(items) == 1 else None


def _raw_headers(sheet) -> list[str]:
    headers = sheet.detection_evidence.get("header_cells") or []
    if not headers and sheet.preview_rows:
        headers = sheet.preview_rows[0]
    return ["" if h is None else str(h) for h in headers]


def resolve_sheet_mapping(sheet, filename: str, confirmed: list[dict[str, Any]] | None) -> SheetPlan:
    """``sheet``：identify 后的 SheetDetection。"""
    raw = _raw_headers(sheet)
    headers = generate_canonical_headers(raw)
    item = find_confirmed(filename, sheet.sheet_name, confirmed)

    col_mapping: dict[str, str] = {}
    field_by_index: dict[int, str] = {}
    source = "auto"
    table_type = sheet.table_type
    if item is not None:
        entries = item.get("mapping_entries") or []
        legacy = item.get("mappings") or {}
        for e in entries:
            idx, std = e.get("column_index"), e.get("standard_field")
            if isinstance(idx, int) and 0 <= idx < len(headers) and std:
                field_by_index[idx] = std
        if not entries and isinstance(legacy, dict):
            for header, std in legacy.items():
                if std and header in raw:
                    field_by_index[raw.index(header)] = std
        confirmed_type = item.get("table_type")
        if confirmed_type and confirmed_type != "unknown":
            table_type = confirmed_type
        if field_by_index or entries:
            source = "confirmed"
    if source == "auto":
        for cm in sheet.column_mappings:
            if cm.standard_field and cm.confidence >= AUTO_MIN_CONFIDENCE and cm.column_index < len(headers):
                field_by_index[cm.column_index] = cm.standard_field

    for idx, std in sorted(field_by_index.items()):
        col_mapping[headers[idx]] = std
    ff_cols = [idx for idx, std in sorted(field_by_index.items()) if std in _FORWARD_FILL_FIELDS]
    return SheetPlan(table_type, headers, col_mapping, ff_cols, source)


#: 能说明「这一行是某个科目下的一条明细」的字段：有任一值才把合并的科目编码 / 名称向下填充
_ROW_IDENTITY_FIELDS = frozenset({
    "aux_dimensions", "aux_type", "aux_code", "aux_name",
    "voucher_no", "voucher_date", "voucher_type", "summary", "entry_seq", "counterpart_account", "preparer",
})


class ForwardFill:
    """合并单元格向下填充（科目编码 / 名称），跨 chunk 保持上一行的值。

    科目编码、名称都为空、且没有任何明细标识（辅助核算 / 凭证号 / 摘要…）的行是合计 / 小计行，不填：
    SAP 余额表末尾的合计行科目为空，原先被填成上一行科目（6711030000），多出借贷各 1.58 亿的一行
    （spec citar-case-chain-fetch-fixes R3）。不填时由校验按「关键列为空」跳过。
    """

    def __init__(self, plan: SheetPlan) -> None:
        self.fill = [plan.headers[i] for i in plan.ff_cols if i < len(plan.headers)]
        self.identity = [h for h, f in plan.col_mapping.items() if f in _ROW_IDENTITY_FIELDS]
        self.prev: dict[str, Any] = {}

    @staticmethod
    def _blank(v: Any) -> bool:
        return v is None or (isinstance(v, str) and not v.strip())

    def apply(self, rows: list[dict[str, Any]]) -> None:
        if not self.fill:
            return
        for row in rows:
            if all(self._blank(row.get(h)) for h in self.fill) and all(self._blank(row.get(h)) for h in self.identity):
                continue
            for h in self.fill:
                if self._blank(row.get(h)):
                    if h in self.prev:
                        row[h] = self.prev[h]
                else:
                    self.prev[h] = row[h]


__all__ = [
    "SheetPlan", "ForwardFill", "find_confirmed", "mapping_locate_key", "resolve_sheet_mapping", "strip_store_prefix",
    "AUTO_MIN_CONFIDENCE",
]
