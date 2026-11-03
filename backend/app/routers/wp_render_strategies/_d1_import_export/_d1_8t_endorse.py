# -*- coding: utf-8 -*-
"""D1-8T「已背书尚未到期票据检查表」导入导出列（按模板 D1-8（二）R24）。

spec oo-writeback-template-parity-closure R3 批 B2b：原 D1-8T 与 D1-8 贴现表共用 16 列表头和转换函数，
背书表模板的 F 前手 / K 背书转让单位 / L 背书转让日期 / M 说明 导不出也导不进（表单同时补了这 4 列）。

兼容旧文件：旧 D1-8T 文件是贴现表列 —— 新四列导入时可缺；旧文件 F / K / L / M 位置上的
已计利息 / 贴现银行 / 贴现金额 / 贴现息 仍读进行里原键（表单不再显示，但不丢）。
"""
from __future__ import annotations

from typing import Any
from uuid import uuid4

#: 模板（二）列序；与贴现表同位的 12 列沿用贴现表表头写法（两表对照、旧文件可认）。
D1_8T_HEADERS: list[str] = [
    "票据种类", "收到日期", "出票人", "票据号", "汇票金额", "前手",
    "出票日", "到期日", "承兑银行", "信用等级", "背书转让单位", "背书转让日期",
    "说明", "是否终止确认", "会计处理是否正确", "索引号",
]

#: 旧文件没有的 4 列：导入校验不要求。
D1_8T_OPTIONAL_HEADERS: frozenset[str] = frozenset({"前手", "背书转让单位", "背书转让日期", "说明"})

#: 表头 → 行字段（文本 / 金额）。旧文件列只在导入时读。
_TEXT: dict[str, str] = {
    "票据种类": "noteType", "收到日期": "receivedDate", "出票人": "issuer", "票据号": "noteNumber",
    "前手": "endorser", "出票日": "issueDate", "到期日": "maturityDate", "承兑银行": "acceptorBank",
    "信用等级": "creditRating", "背书转让单位": "endorsedTo", "背书转让日期": "endorsedDate",
    "说明": "description", "是否终止确认": "isDerecognized", "会计处理是否正确": "isCorrect",
    "索引号": "indexRef",
}
_AMOUNT: dict[str, str] = {"汇票金额": "billAmount"}
_LEGACY_TEXT: dict[str, str] = {"贴现银行": "discountBank"}
_LEGACY_AMOUNT: dict[str, str] = {
    "已计利息": "accruedInterest", "贴现金额": "discountAmount", "贴现息": "discountInterest",
}


def _text(val: Any) -> str:
    return "" if val is None else str(val).strip()


def _amount(val: Any) -> float:
    try:
        return 0.0 if val is None else float(val)
    except (TypeError, ValueError):
        return 0.0


def export_d1_8t_row(data: dict) -> list:
    """一行背书表 → 按 :data:`D1_8T_HEADERS` 列序的值。"""
    out: list[Any] = []
    for header in D1_8T_HEADERS:
        if header in _AMOUNT:
            out.append(_amount(data.get(_AMOUNT[header])))
        else:
            out.append(_text(data.get(_TEXT[header], "")))
    return out


def parse_d1_8t_row(row: tuple, actual_headers: list[str]) -> dict:
    """导入一行：按表头名取值；表头里没有的列取空（新列可缺、旧列照读）。"""

    def cell(name: str) -> Any:
        if name not in actual_headers:
            return None
        idx = actual_headers.index(name)
        return row[idx] if idx < len(row) else None

    parsed: dict[str, Any] = {"rowId": str(uuid4()), "rowType": "dynamic"}
    for header, key in (*_TEXT.items(), *_LEGACY_TEXT.items()):
        parsed[key] = _text(cell(header))
    for header, key in (*_AMOUNT.items(), *_LEGACY_AMOUNT.items()):
        parsed[key] = _amount(cell(header))
    return parsed
