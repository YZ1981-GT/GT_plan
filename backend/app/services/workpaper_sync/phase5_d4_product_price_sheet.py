# -*- coding: utf-8 -*-
"""D4-11 产品销售价格分析双向回写 provider（批次B 第五张）。

单张受管 sheet、单张动态行 table，共享 D4 revenue entry `xlsx/gt-d4-operating-revenue`。

几何（openpyxl 直读 `D/D4 收入底稿.xlsx` sheet `产品销售价格分析D4-11`，A1:O27）：
  · 单级表头 row 11（A 序号 / B 客户名称 / C 品种规格 / D 销售单价 / E 销售数量 /
    F 开票日期 / G 销售订单 / H 订单日期 / I 定价表单价 / J 与定价差异 / K 同期市场价 /
    L 与市价差异 / M 差异原因 / N 市价来源）
  · 数据 row 12 起；footer marker A22「三、审计说明」
  · A 序号是显示序号（非受管，materialize 由行序渲染）；受管列 B-I,K,M,N,O（12 列）
  · formula_mask：J（与定价差异 =(D-I)/I）/ L（与市价差异 =(D-K)/K），前端 computedRows 派生
  · 行身份 = `rowId`（前端 PriceRow.rowId，本轮新增 + backfill）；模板 O 列后空 → 注入列 P

前端真源：`D4TabProductPrice.vue` + store item `D4-11-data`（JSON 数组）。
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Final

from app.services.workpaper_sync.json_path import resolve_json_path

ENTRY_ID: Final[str] = "xlsx/gt-d4-operating-revenue"
TEMPLATE_RELATIVE_PATH: Final[str] = "D/D4 收入底稿.xlsx"

MANAGED_SHEET_D411: Final[str] = "产品销售价格分析D4-11"
TEMPLATE_ID_D411: Final[str] = "D411"
SHEET_KEY_D411: Final[str] = "d411-managed"
STORE_ITEM_ID_D411: Final[str] = "D4-11-data"
TABLE_KEY_D411: Final[str] = "d4_11_rows"
ROW_IDENTITY_KEY_D411: Final[str] = "rowId"

HEADER_ROW_D411: Final[int] = 11
FIRST_DATA_ROW_D411: Final[int] = 12
LAST_DATA_ROW_D411: Final[int] = 21
FOOTER_ROW_D411: Final[int] = 22
FOOTER_MARKER_D411: Final[str] = "三、审计说明"
MANAGED_LAST_COL_D411: Final[str] = "O"
UUID_COL_D411: Final[str] = "P"

#: 受管字段：J/L（差异率）是派生列，不入受管；A 序号非受管。
MANAGED_FIELD_SPECS_D411: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    ("customer", "B", "editable", "text", "customer", "客户名称"),
    ("product", "C", "editable", "text", "product", "品种/规格"),
    ("unitPrice", "D", "editable", "amount", "unitPrice", "销售单价"),
    ("quantity", "E", "editable", "amount", "quantity", "销售数量"),
    ("invoiceDate", "F", "editable", "text", "invoiceDate", "开票日期"),
    ("orderNo", "G", "editable", "text", "orderNo", "销售订单"),
    ("orderDate", "H", "editable", "text", "orderDate", "订单日期"),
    ("listPrice", "I", "editable", "amount", "listPrice", "商品销售价格表所列单价"),
    ("marketPrice", "K", "editable", "amount", "marketPrice", "同期市场价格"),
    ("reason", "M", "editable", "text", "reason", "差异原因分析"),
    ("priceSource", "N", "editable", "text", "priceSource", "同期市场价格来源"),
    ("remark", "O", "editable", "text", "remark", "备注"),
)

#: formula_mask：J / L 列（差异率派生）12-21 行。
_FORMULA_MASK_D411: Final[tuple[str, ...]] = tuple(
    f"{col}{row}"
    for row in range(FIRST_DATA_ROW_D411, LAST_DATA_ROW_D411 + 1)
    for col in ("J", "L")
)


def _snake(field: str) -> str:
    import re

    return re.sub(r"([A-Z])", lambda m: "_" + m.group(1).lower(), field)


def stable_key_for_d411(field: str, identity: str = "{row_uuid}") -> str:
    return f"{TABLE_KEY_D411}/{identity}/{_snake(field)}"


def formula_mask_cells_d411() -> tuple[str, ...]:
    return _FORMULA_MASK_D411


def mapping_digest_payload_d411() -> dict[str, Any]:
    return {
        "managed_sheet": MANAGED_SHEET_D411,
        "template_relative_path": TEMPLATE_RELATIVE_PATH,
        "header_row": HEADER_ROW_D411,
        "first_data_row": FIRST_DATA_ROW_D411,
        "last_data_row": LAST_DATA_ROW_D411,
        "footer_row": FOOTER_ROW_D411,
        "footer_marker": FOOTER_MARKER_D411,
        "uuid_col": UUID_COL_D411,
        "fields": list(MANAGED_FIELD_SPECS_D411),
        "formula_mask": list(_FORMULA_MASK_D411),
    }


def mapping_digest_d411() -> str:
    payload = json.dumps(mapping_digest_payload_d411(), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sheet_payload_d411() -> dict[str, Any]:
    def _src(cell: str) -> str:
        return f"源xlsx!{MANAGED_SHEET_D411}!{cell}"

    fields = [
        {
            "stable_field_key": stable_key_for_d411(f[0]),
            "json_pointer": f"/rows/{{row_uuid}}/{f[4]}",
            "column_key": _snake(f[0]),
            "cell": {"column": f[1], "row_from": "row_identity"},
            "mode": f[2],
            "value_type": f[3],
            "source_ref": _src(f"{f[1]}{FIRST_DATA_ROW_D411}"),
            "header_source_ref": _src(f"{f[1]}{HEADER_ROW_D411}"),
            "store_item_id": STORE_ITEM_ID_D411,
            "header_text": f[5],
        }
        for f in MANAGED_FIELD_SPECS_D411
    ]
    return {
        "sheet_key": SHEET_KEY_D411,
        "excel_name": MANAGED_SHEET_D411,
        "template_id": TEMPLATE_ID_D411,
        "locator": {"anchor": "excel_table_sheet_association"},
        "tables": [
            {
                "table_key": TABLE_KEY_D411,
                "anchor": f"A{FIRST_DATA_ROW_D411 - 1}",
                "header_rows": 1,
                "row_identity": {
                    "kind": "field",
                    "json_pointer": f"/rows/*/{ROW_IDENTITY_KEY_D411}",
                },
                "delete_policy": "tombstone",
                "footer_anchor": {
                    "marker": FOOTER_MARKER_D411,
                    "search_column": "A",
                    "carries_total_formula": False,
                },
                "formula_mask": list(_FORMULA_MASK_D411),
                "fields": fields,
            }
        ],
    }


def instrumentation_spec_d411(
    *, entry_id: str = ENTRY_ID, template_relative_path: str = TEMPLATE_RELATIVE_PATH
):
    from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec

    return ExcelInstrumentationSpec(
        entry_id=entry_id,
        template_id=TEMPLATE_ID_D411,
        template_relative_path=template_relative_path,
        managed_sheet=MANAGED_SHEET_D411,
        first_data_row=FIRST_DATA_ROW_D411,
        last_data_row=LAST_DATA_ROW_D411,
        footer_row=FOOTER_ROW_D411,
        managed_last_col=MANAGED_LAST_COL_D411,
        uuid_col=UUID_COL_D411,
        table_name=f"GT_{TEMPLATE_ID_D411}_ROWS",
        sheet_key=SHEET_KEY_D411,
    )


def _decode(payload: Any) -> Any:
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8")
    if isinstance(payload, str):
        return json.loads(payload) if payload.strip() else []
    return payload


def _rows(payload: Any) -> list[tuple[str, Mapping[str, Any]]]:
    value = _decode(payload)
    if not isinstance(value, list):
        raise ValueError("D4-11-data 必须是数组")
    out: list[tuple[str, Mapping[str, Any]]] = []
    seen: set[str] = set()
    for ordinal, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise ValueError(f"D4-11-data[{ordinal}] 不是对象")
        rid = str(row.get(ROW_IDENTITY_KEY_D411) or "").strip()
        if not rid:
            raise ValueError(f"D4-11-data[{ordinal}] 缺少 {ROW_IDENTITY_KEY_D411}")
        if rid in seen:
            raise ValueError(f"D4-11-data 行身份 {rid!r} 重复")
        seen.add(rid)
        out.append((rid, row))
    return out


def build_store_projection_d411(payload: Any, *, contract: Any, limits: Any | None = None):
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection
    from app.services.workpaper_sync.contracts import FieldMode, ValueType

    values: dict[str, FieldValue] = {}
    row_keys: list[str] = []
    for identity, row in _rows(payload):
        row_keys.append(identity)
        for field, _col, mode, value_type, path, _label in MANAGED_FIELD_SPECS_D411:
            value = resolve_json_path(row, path) if "/" in path else row.get(path)
            sk = stable_key_for_d411(field, identity)
            # 🔴 2026-09-21 修复既有 bug（同 phase5_d4_ipo_interview_sheets.py）：value_type/
            # mode 此前是字段元组里的裸字符串，未经枚举转换。
            values[sk] = FieldValue(
                stable_key=sk, value=value, value_type=ValueType(value_type), mode=FieldMode(mode), row_key=identity
            )
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys={TABLE_KEY_D411: tuple(row_keys)},
    )


def merge_projection_into_d411_rows(*, projection: Any, base_payload: Any) -> Any:
    base = _decode(base_payload)
    container = base if isinstance(base, list) else []
    rows = [
        (str(r.get(ROW_IDENTITY_KEY_D411)), dict(r))
        for r in container
        if isinstance(r, Mapping) and r.get(ROW_IDENTITY_KEY_D411)
    ]
    by_id = {i: r for i, r in rows}
    order = [i for i, _ in rows]
    prefix = TABLE_KEY_D411 + "/"
    snake_to_path = {_snake(s[0]): s[4] for s in MANAGED_FIELD_SPECS_D411}

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

    return [by_id[i] for i in order]


def store_item_id_d411() -> str:
    return STORE_ITEM_ID_D411
