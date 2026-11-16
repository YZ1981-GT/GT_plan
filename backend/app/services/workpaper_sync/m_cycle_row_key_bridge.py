# -*- coding: utf-8 -*-
"""M 循环明细行 → 契约字段的键名桥（spec `m-cycle-key-naming-unification` 任务 5）。

═══ 为什么需要这个模块（2026-11-16 现算，不是推测）═══

`phase5_m_cycle_common._build_store_projection` 的 `_emit_row_array` 有两个独立缺陷，
任一条都足以让明细行的值**一格都进不了 OO**：

1. **键名空间错配**：它拿契约的 `column_key`（下划线，如 `shareholder_name`）
   去匹配前端行对象的键（驼峰，如 `shareholderName`）。现算 M1 前端 24 个行键里
   只有 `remark` 一个能命中（24 → 1）；M2 同理（14 → 1）。
2. **行身份字段错配**：它按 `rowId` / `row_uuid` / `id` 取行身份，而 M 循环前端行
   只有 `key`（`m1-detail-<ts>-<rand>`）⇒ 每一行都被 `continue` 跳过，**零行产出**。

两者叠加的实际效果：即使任务 4 把「整表 JSON」通路删掉、逐行 JSON 成为唯一来源，
投影层仍然只产出「容器键当标量」的伪字段（`M1-M1-2-row-0-data = {...}`），
而它不在契约受管字段里 ⇒ 物化时无处可写。

═══ 修法的唯一权威来源 ═══

契约字段**同时**带两套名字：

* `column_key` —— 模板列语义（下划线），用于 stable_field_key；
* `json_pointer` 的末段 —— provider 声明的**前端 json_key**（驼峰）。

所以桥不需要新造映射表，只需要「用 json_pointer 末段去认前端行的键」。
`MFieldSpec.json_key` 是这两者的同一真源（`_field_to_contract_payload` 里
`json_key` 同时进 `json_pointer` 与 `header_*` 之外的字段声明），因此
**认 json_pointer 末段 == 认 provider 声明的前端键**，不是第二份口径。

行身份同理：M 循环的明细行是「固定行 / 动态行」两种，前端一律用 `key` 作稳定
行身份（`rowIdentityKey` 在契约里也登记成 `rowId` 之外的形态）。本模块按
「声明顺序」取第一个非空的行身份字段，并把取到的值当作 row_uuid 段。
"""
from __future__ import annotations

from typing import Any, Final, Mapping

#: 行身份字段候选，**按优先级**。M 循环前端明细行用 `key`；
#: `rowId` / `row_uuid` / `id` 保留给其他循环与将来迁移的行。
#: 🔴 顺序有意义：`key` 必须在前，否则 M 循环的固定行会被判成「无身份」而整行丢弃。
ROW_IDENTITY_KEYS: Final[tuple[str, ...]] = ("key", "rowId", "row_uuid", "id")


class MRowKeyBridgeError(ValueError):
    """前端行键与契约字段对不上时抛（fail closed，不静默丢数据）。"""


def row_identity_of(row: Mapping[str, Any]) -> str:
    """取一行的稳定行身份。缺失即抛 —— **绝不**退回数组下标（那会让行身份随行序漂移）。"""
    for key in ROW_IDENTITY_KEYS:
        raw = row.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        if raw is not None and not isinstance(raw, (dict, list)):
            text = str(raw).strip()
            if text:
                return text
    raise MRowKeyBridgeError(
        f"明细行缺少稳定行身份（尝试过 {ROW_IDENTITY_KEYS}）—— 实得键 {sorted(row)}。"
        "不得退回数组下标作身份：行序变化会让同一行被认成新行。"
    )


def build_field_index(contract: Any) -> dict[str, dict[str, dict]]:
    """契约 → `{table_key: {前端键: field}}`。

    前端键取 `json_pointer` 末段（= provider 声明的 `json_key`）；同时把
    `column_key` 也登记进去，让「后端自产的 flat 形态载荷」仍然可命中
    （两种写法都指向同一个 field，不存在歧义）。
    """
    index: dict[str, dict[str, dict]] = {}
    payload = getattr(contract, "canonical_payload", None) or {}
    for sheet in payload.get("sheets") or ():
        for table in sheet.get("tables") or ():
            table_key = table.get("table_key") or ""
            if not table_key:
                continue
            bucket = index.setdefault(table_key, {})
            for field in table.get("fields") or ():
                pointer = field.get("json_pointer") or ""
                tail = pointer.rsplit("/", 1)[-1] if pointer else ""
                if tail:
                    bucket.setdefault(tail, field)
                column_key = field.get("column_key") or ""
                if column_key:
                    bucket.setdefault(column_key, field)
    return index


def split_detail_row(
    row: Mapping[str, Any],
    *,
    field_index: Mapping[str, Mapping[str, dict]],
) -> list[tuple[str, Any, dict]]:
    """一行前端明细行 → `[(stable_field_key, raw_value, field_spec), …]`。

    只产出契约声明过的列（前端多出来的列静默忽略 —— 它们本来就不该写进模板）；
    未匹配到任何字段时返回空列表，由调用方决定是否报错。
    """
    identity = row_identity_of(row)
    emitted: list[tuple[str, Any, dict]] = []
    for raw_key, raw_value in row.items():
        if raw_key in ROW_IDENTITY_KEYS:
            continue
        for table_key, bucket in field_index.items():
            spec = bucket.get(raw_key)
            if spec is None:
                continue
            column_key = spec.get("column_key") or ""
            if not column_key:
                continue
            emitted.append((f"{table_key}/{identity}/{column_key}", raw_value, spec))
    return emitted


def has_row_table_fields(contract: Any) -> bool:
    """契约是否声明了行表（有 `row_identity` 的表）——决定走行数组还是 flat。"""
    payload = getattr(contract, "canonical_payload", None) or {}
    for sheet in payload.get("sheets") or ():
        for table in sheet.get("tables") or ():
            if (table.get("row_identity") or {}).get("kind"):
                return True
    return False
