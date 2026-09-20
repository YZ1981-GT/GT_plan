# -*- coding: utf-8 -*-
"""D4-10 重要客户销售价格分析双向回写 provider（批次B 第六张）。

单张受管 sheet、单张动态行 table，共享 D4 revenue entry `xlsx/gt-d4-operating-revenue`。
store 是**对象**（`{rows, totalAmount, totalQuantity, ...}`，同 D4-9 dict 形态），行在 `rows`。

几何（openpyxl 直读 `D/D4 收入底稿.xlsx` sheet `重要客户销售价格分析D4-10`，A1:T49）：
  · 两级表头 row 11-12（A 序号 / B 客户 / C 产品 / D 销售金额 / E 占比 / F 销售数量 /
    G 占比 / H 销售单价 / I 年度均价 / J 与均价差异 / K 差异原因 / L 市场价格 / M 与市场差异 /
    N 差异原因）
  · 数据 row 13-33；合计行 row 34（本期销售总额，`$D$34`/`$F$34` = 占比分母）
  · footer marker A34「本期销售总额」（数据区正下方）
  · A 序号非受管；受管列 B/C/D/F/H/I/K/L/N（9 列）
  · formula_mask：E/G（占比 =D/$D$34）+ J/M（差异率），前端 computedRows 派生
  · 行身份 = `rowId`（前端本轮新增 + backfill）；模板数据宽到 N，注入列 P

前端真源：`D4TabCustomerPrice.vue` + store item `D4-10-data`（{rows,...} 对象）。
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Final

from app.services.workpaper_sync.json_path import resolve_json_path

ENTRY_ID: Final[str] = "xlsx/gt-d4-operating-revenue"
TEMPLATE_RELATIVE_PATH: Final[str] = "D/D4 收入底稿.xlsx"

MANAGED_SHEET_D410: Final[str] = "重要客户销售价格分析D4-10"
TEMPLATE_ID_D410: Final[str] = "D410"
SHEET_KEY_D410: Final[str] = "d410-managed"
STORE_ITEM_ID_D410: Final[str] = "D4-10-data"
TABLE_KEY_D410: Final[str] = "d4_10_rows"
ROW_IDENTITY_KEY_D410: Final[str] = "rowId"

HEADER_ROW_D410: Final[int] = 12
FIRST_DATA_ROW_D410: Final[int] = 13
LAST_DATA_ROW_D410: Final[int] = 33
FOOTER_ROW_D410: Final[int] = 34
FOOTER_MARKER_D410: Final[str] = "本期销售总额"
MANAGED_LAST_COL_D410: Final[str] = "N"
UUID_COL_D410: Final[str] = "P"

#: 受管字段：E/G/J/M（占比/差异率）是派生列 → formula_mask；A 序号非受管。
MANAGED_FIELD_SPECS_D410: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    ("customer", "B", "editable", "text", "customer", "客户名称"),
    ("product", "C", "editable", "text", "product", "产品种类"),
    ("amount", "D", "editable", "amount", "amount", "销售金额"),
    ("quantity", "F", "editable", "amount", "quantity", "销售数量"),
    ("unitPrice", "H", "editable", "amount", "unitPrice", "销售单价"),
    ("avgPrice", "I", "editable", "amount", "avgPrice", "年度均价"),
    ("avgReason", "K", "editable", "text", "avgReason", "与均价差异原因"),
    ("marketPrice", "L", "editable", "amount", "marketPrice", "市场价格"),
    ("marketReason", "N", "editable", "text", "marketReason", "与市场差异原因"),
)

#: formula_mask：E/G（占比）+ J/M（差异率）13-33 行。
_FORMULA_MASK_D410: Final[tuple[str, ...]] = tuple(
    f"{col}{row}"
    for row in range(FIRST_DATA_ROW_D410, LAST_DATA_ROW_D410 + 1)
    for col in ("E", "G", "J", "M")
)


def _snake(field: str) -> str:
    import re

    return re.sub(r"([A-Z])", lambda m: "_" + m.group(1).lower(), field)


def stable_key_for_d410(field: str, identity: str = "{row_uuid}") -> str:
    return f"{TABLE_KEY_D410}/{identity}/{_snake(field)}"


def formula_mask_cells_d410() -> tuple[str, ...]:
    return _FORMULA_MASK_D410


def mapping_digest_payload_d410() -> dict[str, Any]:
    return {
        "managed_sheet": MANAGED_SHEET_D410,
        "template_relative_path": TEMPLATE_RELATIVE_PATH,
        "header_row": HEADER_ROW_D410,
        "first_data_row": FIRST_DATA_ROW_D410,
        "last_data_row": LAST_DATA_ROW_D410,
        "footer_row": FOOTER_ROW_D410,
        "footer_marker": FOOTER_MARKER_D410,
        "uuid_col": UUID_COL_D410,
        "fields": list(MANAGED_FIELD_SPECS_D410),
        "formula_mask": list(_FORMULA_MASK_D410),
    }


def mapping_digest_d410() -> str:
    payload = json.dumps(mapping_digest_payload_d410(), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sheet_payload_d410() -> dict[str, Any]:
    def _src(cell: str) -> str:
        return f"源xlsx!{MANAGED_SHEET_D410}!{cell}"

    fields = [
        {
            "stable_field_key": stable_key_for_d410(f[0]),
            "json_pointer": f"/rows/{{row_uuid}}/{f[4]}",
            "column_key": _snake(f[0]),
            "cell": {"column": f[1], "row_from": "row_identity"},
            "mode": f[2],
            "value_type": f[3],
            "source_ref": _src(f"{f[1]}{FIRST_DATA_ROW_D410}"),
            "header_source_ref": _src(f"{f[1]}{HEADER_ROW_D410}"),
            "store_item_id": STORE_ITEM_ID_D410,
            "header_text": f[5],
        }
        for f in MANAGED_FIELD_SPECS_D410
    ]
    return {
        "sheet_key": SHEET_KEY_D410,
        "excel_name": MANAGED_SHEET_D410,
        "template_id": TEMPLATE_ID_D410,
        "locator": {"anchor": "excel_table_sheet_association"},
        "tables": [
            {
                "table_key": TABLE_KEY_D410,
                "anchor": f"A{FIRST_DATA_ROW_D410 - 1}",
                "header_rows": 1,
                "row_identity": {
                    "kind": "field",
                    "json_pointer": f"/rows/*/{ROW_IDENTITY_KEY_D410}",
                },
                "delete_policy": "tombstone",
                "footer_anchor": {
                    "marker": FOOTER_MARKER_D410,
                    "search_column": "A",
                    "carries_total_formula": False,
                },
                "formula_mask": list(_FORMULA_MASK_D410),
                "fields": fields,
            }
        ],
    }


def instrumentation_spec_d410(
    *, entry_id: str = ENTRY_ID, template_relative_path: str = TEMPLATE_RELATIVE_PATH
):
    from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec

    return ExcelInstrumentationSpec(
        entry_id=entry_id,
        template_id=TEMPLATE_ID_D410,
        template_relative_path=template_relative_path,
        managed_sheet=MANAGED_SHEET_D410,
        first_data_row=FIRST_DATA_ROW_D410,
        last_data_row=LAST_DATA_ROW_D410,
        footer_row=FOOTER_ROW_D410,
        managed_last_col=MANAGED_LAST_COL_D410,
        uuid_col=UUID_COL_D410,
        table_name=f"GT_{TEMPLATE_ID_D410}_ROWS",
        sheet_key=SHEET_KEY_D410,
    )


def _decode(payload: Any) -> Any:
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8")
    if isinstance(payload, str):
        return json.loads(payload) if payload.strip() else {}
    return payload


def _rows(payload: Any) -> list[tuple[str, Mapping[str, Any]]]:
    """从 D4-10-data 对象取 rows 数组 → (rowId, row)。

    容差：bare list（legacy）或 dict 皆取 rows；非法整体形态返回空（不打挂全 entry，同 D4-9）。
    """
    value = _decode(payload)
    if isinstance(value, Mapping):
        rows = value.get("rows", [])
    else:
        # legacy bare list（早于 {rows,...} dict 模型）或其它非对象：视为空载荷，
        # 不 fail-closed 打挂全共享 entry（同 D4-9 legacy 容差）。前端 persistData 下次以
        # 正确 {rows,...} dict 覆盖自然迁移。
        return []
    if not isinstance(rows, list):
        return []
    out: list[tuple[str, Mapping[str, Any]]] = []
    seen: set[str] = set()
    for ordinal, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"D4-10-data.rows[{ordinal}] 不是对象")
        rid = str(row.get(ROW_IDENTITY_KEY_D410) or "").strip()
        if not rid:
            raise ValueError(f"D4-10-data.rows[{ordinal}] 缺少 {ROW_IDENTITY_KEY_D410}")
        if rid in seen:
            raise ValueError(f"D4-10-data.rows 行身份 {rid!r} 重复")
        seen.add(rid)
        out.append((rid, row))
    return out


def build_store_projection_d410(payload: Any, *, contract: Any, limits: Any | None = None):
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection

    values: dict[str, FieldValue] = {}
    row_keys: list[str] = []
    for identity, row in _rows(payload):
        row_keys.append(identity)
        for field, _col, mode, value_type, path, _label in MANAGED_FIELD_SPECS_D410:
            value = resolve_json_path(row, path) if "/" in path else row.get(path)
            sk = stable_key_for_d410(field, identity)
            values[sk] = FieldValue(
                stable_key=sk, value=value, value_type=value_type, mode=mode, row_key=identity
            )
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys={TABLE_KEY_D410: tuple(row_keys)},
    )


def merge_projection_into_d410_rows(*, projection: Any, base_payload: Any) -> Any:
    """把投影合并回 store 对象 {rows,...}（保留 totalAmount 等表级标量）。"""
    base = _decode(base_payload)
    if isinstance(base, Mapping):
        out_obj = dict(base)
        container = base.get("rows", [])
    else:
        out_obj = {"rows": []}
        container = base if isinstance(base, list) else []
    rows = [
        (str(r.get(ROW_IDENTITY_KEY_D410)), dict(r))
        for r in (container if isinstance(container, list) else [])
        if isinstance(r, Mapping) and r.get(ROW_IDENTITY_KEY_D410)
    ]
    by_id = {i: r for i, r in rows}
    order = [i for i, _ in rows]
    prefix = TABLE_KEY_D410 + "/"
    snake_to_path = {_snake(s[0]): s[4] for s in MANAGED_FIELD_SPECS_D410}

    for sk in projection.stable_keys():
        if not str(sk).startswith(prefix):
            continue
        fv = projection.get(sk)
        identity = getattr(fv, "row_key", None)
        if not identity:
            continue
        parts = str(sk).split("/")
        if len(parts) < 3:
            continue
        path = snake_to_path.get(parts[2])
        target = by_id.get(identity)
        if path is None or target is None:
            continue
        target[path] = getattr(fv, "value", None)

    out_obj["rows"] = [by_id[i] for i in order]
    return out_obj


def store_item_id_d410() -> str:
    return STORE_ITEM_ID_D410
