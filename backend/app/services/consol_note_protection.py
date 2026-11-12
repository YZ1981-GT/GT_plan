"""合并附注人工保护格解析。

本模块提供合并附注 ``ConsolNoteData`` 人工保护元数据的单一解析来源，供所有
自动/手工写入方统一使用。解析为严格模式：坐标缺失、非整数、布尔值、负数、
容器类型错误一律抛出 ``ProtectionMetadataError``，由调用方按各自通道回报。

公共 API
--------
* ``ProtectionMetadataError`` — 保护元数据无效，``status=422``，消息含项序号。
* ``parse_manual_cells(data)`` — 解析 ``data.manual_cells``。
* ``parse_locked_cells(record)`` — 解析 ``record.locked_cells``。
* ``section_locked(record)`` — 判断 ``record.cell_state == 'locked'``。
* ``protected_cells(record, data)`` — 自动写入方使用的保护坐标并集入口。
"""
from __future__ import annotations

from typing import Any


class ProtectionMetadataError(ValueError):
    """合并附注保护元数据无法解析。

    ``status`` 固定为 422，供路由层映射到 HTTP 状态码。
    """

    status: int = 422

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _is_int_like(value: Any) -> bool:
    """判断 value 是否为整数，但排除布尔值。"""
    return isinstance(value, int) and not isinstance(value, bool)


def _to_non_negative_int(value: Any, name: str, *, allow_numeric_text: bool = False) -> int:
    """校验非负整数；仅 ``row:col`` 字符串的分段允许从文本解析。"""
    if isinstance(value, bool):
        raise ValueError(f"{name} 不能是布尔值")
    if isinstance(value, str) and allow_numeric_text:
        try:
            number = int(value.strip())
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} 必须是整数") from exc
    elif _is_int_like(value):
        number = value
    else:
        raise ValueError(f"{name} 必须是整数")
    if number < 0:
        raise ValueError(f"{name} 不能为负数")
    return number


def _parse_coord_pair(
    item: Any,
    index: int,
    row_key: str,
    col_key: str,
    *,
    allow_list_tuple: bool = True,
    allow_string: bool = True,
) -> tuple[int, int]:
    """解析单个坐标项为 (row, col)。

    支持 dict（row_key/col_key）、list/tuple、[row, col]、"row:col" 字符串。
    """
    row_value: Any
    col_value: Any

    if isinstance(item, dict):
        if row_key not in item or col_key not in item:
            raise ProtectionMetadataError(
                f"人工保护标记第 {index} 项无效：缺少 {row_key} 或 {col_key}，本章节未写入"
            )
        row_value, col_value = item[row_key], item[col_key]
    elif allow_list_tuple and isinstance(item, (list, tuple)) and len(item) == 2:
        row_value, col_value = item[0], item[1]
    elif allow_string and isinstance(item, str):
        if ":" not in item:
            raise ProtectionMetadataError(
                f"人工保护标记第 {index} 项无效：字符串项必须使用「行:列」格式，本章节未写入"
            )
        row_part, col_part = item.split(":", 1)
        row_value, col_value = row_part, col_part
    else:
        raise ProtectionMetadataError(
            f"人工保护标记第 {index} 项无效：应为字典、长度为 2 的序列或「行:列」字符串，本章节未写入"
        )

    try:
        allow_numeric_text = isinstance(item, str)
        row = _to_non_negative_int(row_value, "行坐标", allow_numeric_text=allow_numeric_text)
        col = _to_non_negative_int(col_value, "列坐标", allow_numeric_text=allow_numeric_text)
    except ValueError as exc:
        raise ProtectionMetadataError(
            f"人工保护标记第 {index} 项无效：{exc}，本章节未写入"
        ) from exc

    return row, col


def parse_manual_cells(data: Any) -> set[tuple[int, int]]:
    """解析 ``data.manual_cells`` 坐标集合。

    合法写法：``{"row": 1, "col": 2}``、``[1, 2]``、``"1:2"``。
    返回 ``set[(row, col)]``；缺失或 ``None`` 时返回空集。
    """
    raw = data.get("manual_cells") if isinstance(data, dict) else None
    if raw is None:
        return set()
    if not isinstance(raw, list):
        raise ProtectionMetadataError(
            "manual_cells 必须是数组，本章节未写入"
        )

    out: set[tuple[int, int]] = set()
    for index, item in enumerate(raw, start=1):
        out.add(
            _parse_coord_pair(
                item,
                index,
                "row",
                "col",
                allow_list_tuple=True,
                allow_string=True,
            )
        )
    return out


def parse_locked_cells(record: Any) -> set[tuple[int, int]]:
    """解析 ``record.locked_cells`` 坐标集合。

    合法写法：``{"row_index": 1, "col_index": 2}``。
    返回 ``set[(row, col)]``；缺失或 ``None`` 时返回空集。
    """
    raw = getattr(record, "locked_cells", None)
    if raw is None:
        return set()
    if not isinstance(raw, list):
        raise ProtectionMetadataError(
            "locked_cells 必须是数组，本章节未写入"
        )

    out: set[tuple[int, int]] = set()
    for index, item in enumerate(raw, start=1):
        out.add(
            _parse_coord_pair(
                item,
                index,
                "row_index",
                "col_index",
                allow_list_tuple=False,
                allow_string=False,
            )
        )
    return out


def section_locked(record: Any) -> bool:
    """判断整节是否被锁定。"""
    return getattr(record, "cell_state", None) == "locked"


# 用于标识整节锁定的特殊坐标；普通 (row, col) 不会出现该值。
_SECTION_LOCKED_SENTINEL: tuple[int, int] = (-1, -1)


def protected_cells(record: Any, data: Any) -> set[tuple[int, int]]:
    """返回自动写入方应保留的保护坐标并集。

    包含 ``manual_cells``、``locked_cells`` 以及整节锁定时的整节保护占位。
    因整节锁定的语义是「所有格均保护」，调用方在循环写入时应跳过整章写入。
    """
    protected = parse_manual_cells(data) | parse_locked_cells(record)
    if section_locked(record):
        # 整节锁定：返回一个不可与普通坐标混淆的占位，方便调用方统一检测。
        protected.add(_SECTION_LOCKED_SENTINEL)
    return protected


__all__ = [
    "ProtectionMetadataError",
    "parse_manual_cells",
    "parse_locked_cells",
    "section_locked",
    "protected_cells",
]
