# -*- coding: utf-8 -*-
"""D4-17 营业收入截止测试（账到单据）双向回写 provider（批次B 第二张）。

与 phase5_d4_ipo_interview_sheets / phase5_d4_indicator_sheet 同构：单张受管 sheet、
单张动态行 table、共享 D4 revenue entry `xlsx/gt-d4-operating-revenue`。

几何（openpyxl 直读权威模板 `D/D4 收入底稿.xlsx` sheet `营业收入截止测试（账到单据）D4-17`）：
  · 两级表头 row 11（组：记账凭证 A-E / 发货单 F-J / 是否跨期 K）+ row 12（子表头
    日期/编号/品名/数量/金额 ×2 + √(×)）
  · 数据 row 13 起（动态行）
  · footer marker：A36「三、审计说明」
  · 受管可编辑列 A-J（10 列）：凭证 日期/编号/品名/数量/金额 + 发货单 日期/编号/品名/数量/金额
  · formula_mask：K 列（是否跨期 √/×，前端 isCrossPeriodForward 派生，OO 不采信/不覆盖）
  · 行身份 = `id`（前端 CutoffForwardRow.id 稳定键）；模板无空 UUID 列 → 注入列 L
  · remark（前端字段）无模板列 → 不受管（元数据保留）

前端真源：`D4TabCutoffForward.vue` + store item `D4-17-rows`（JSON 数组）。
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Final

from app.services.workpaper_sync.json_path import resolve_json_path

ENTRY_ID: Final[str] = "xlsx/gt-d4-operating-revenue"
TEMPLATE_RELATIVE_PATH: Final[str] = "D/D4 收入底稿.xlsx"

MANAGED_SHEET_D417: Final[str] = "营业收入截止测试（账到单据）D4-17"
TEMPLATE_ID_D417: Final[str] = "D417"
SHEET_KEY_D417: Final[str] = "d417-managed"
STORE_ITEM_ID_D417: Final[str] = "D4-17-rows"
TABLE_KEY_D417: Final[str] = "d4_17_rows"
ROW_IDENTITY_KEY_D417: Final[str] = "id"

HEADER_ROW_D417: Final[int] = 12
FIRST_DATA_ROW_D417: Final[int] = 13
LAST_DATA_ROW_D417: Final[int] = 23
FOOTER_ROW_D417: Final[int] = 36
FOOTER_MARKER_D417: Final[str] = "三、审计说明"
MANAGED_LAST_COL_D417: Final[str] = "J"
UUID_COL_D417: Final[str] = "L"

#: 受管字段：`(field_key, 列标, mode, value_type, store_path, 表头文本)`。
MANAGED_FIELD_SPECS_D417: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    ("voucherDate", "A", "editable", "text", "voucherDate", "记账凭证日期"),
    ("voucherNo", "B", "editable", "text", "voucherNo", "记账凭证编号"),
    ("voucherProduct", "C", "editable", "text", "voucherProduct", "记账凭证品名"),
    ("voucherQty", "D", "editable", "text", "voucherQty", "记账凭证数量"),
    ("voucherAmount", "E", "editable", "amount", "voucherAmount", "记账凭证金额"),
    ("deliveryDate", "F", "editable", "text", "deliveryDate", "发货单日期"),
    ("deliveryNo", "G", "editable", "text", "deliveryNo", "发货单编号"),
    ("deliveryProduct", "H", "editable", "text", "deliveryProduct", "发货单品名"),
    ("deliveryQty", "I", "editable", "text", "deliveryQty", "发货单数量"),
    ("deliveryAmount", "J", "editable", "amount", "deliveryAmount", "发货单金额"),
)

#: formula_mask：K 列（是否跨期）13-23 行，前端派生 √/×，OO 不采信/不覆盖。
_FORMULA_MASK_D417: Final[tuple[str, ...]] = tuple(
    f"K{row}" for row in range(FIRST_DATA_ROW_D417, LAST_DATA_ROW_D417 + 1)
)


def _snake(field: str) -> str:
    import re

    return re.sub(r"([A-Z])", lambda m: "_" + m.group(1).lower(), field)


def stable_key_for_d417(field: str, identity: str = "{row_uuid}") -> str:
    return f"{TABLE_KEY_D417}/{identity}/{_snake(field)}"


def formula_mask_cells_d417() -> tuple[str, ...]:
    return _FORMULA_MASK_D417


def mapping_digest_payload_d417() -> dict[str, Any]:
    return {
        "managed_sheet": MANAGED_SHEET_D417,
        "template_relative_path": TEMPLATE_RELATIVE_PATH,
        "header_row": HEADER_ROW_D417,
        "first_data_row": FIRST_DATA_ROW_D417,
        "last_data_row": LAST_DATA_ROW_D417,
        "footer_row": FOOTER_ROW_D417,
        "footer_marker": FOOTER_MARKER_D417,
        "uuid_col": UUID_COL_D417,
        "fields": list(MANAGED_FIELD_SPECS_D417),
        "formula_mask": list(_FORMULA_MASK_D417),
    }


def mapping_digest_d417() -> str:
    payload = json.dumps(mapping_digest_payload_d417(), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sheet_payload_d417() -> dict[str, Any]:
    def _src(cell: str) -> str:
        return f"源xlsx!{MANAGED_SHEET_D417}!{cell}"

    fields = [
        {
            "stable_field_key": stable_key_for_d417(f[0]),
            "json_pointer": f"/rows/{{row_uuid}}/{f[4]}",
            "column_key": _snake(f[0]),
            "cell": {"column": f[1], "row_from": "row_identity"},
            "mode": f[2],
            "value_type": f[3],
            "source_ref": _src(f"{f[1]}{FIRST_DATA_ROW_D417}"),
            "header_source_ref": _src(f"{f[1]}{HEADER_ROW_D417}"),
            "store_item_id": STORE_ITEM_ID_D417,
            "header_text": f[5],
        }
        for f in MANAGED_FIELD_SPECS_D417
    ]
    return {
        "sheet_key": SHEET_KEY_D417,
        "excel_name": MANAGED_SHEET_D417,
        "template_id": TEMPLATE_ID_D417,
        "locator": {"anchor": "excel_table_sheet_association"},
        "tables": [
            {
                "table_key": TABLE_KEY_D417,
                "anchor": f"A{FIRST_DATA_ROW_D417 - 1}",
                "header_rows": 1,
                "row_identity": {
                    "kind": "field",
                    "json_pointer": f"/rows/*/{ROW_IDENTITY_KEY_D417}",
                },
                "delete_policy": "tombstone",
                "footer_anchor": {
                    "marker": FOOTER_MARKER_D417,
                    "search_column": "A",
                    "carries_total_formula": False,
                },
                "formula_mask": list(_FORMULA_MASK_D417),
                "fields": fields,
            }
        ],
    }


def instrumentation_spec_d417(
    *, entry_id: str = ENTRY_ID, template_relative_path: str = TEMPLATE_RELATIVE_PATH
):
    from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec

    return ExcelInstrumentationSpec(
        entry_id=entry_id,
        template_id=TEMPLATE_ID_D417,
        template_relative_path=template_relative_path,
        managed_sheet=MANAGED_SHEET_D417,
        first_data_row=FIRST_DATA_ROW_D417,
        last_data_row=LAST_DATA_ROW_D417,
        footer_row=FOOTER_ROW_D417,
        managed_last_col=MANAGED_LAST_COL_D417,
        uuid_col=UUID_COL_D417,
        table_name=f"GT_{TEMPLATE_ID_D417}_ROWS",
        sheet_key=SHEET_KEY_D417,
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
        raise ValueError("D4-17-rows 必须是数组")
    out: list[tuple[str, Mapping[str, Any]]] = []
    seen: set[str] = set()
    for ordinal, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise ValueError(f"D4-17-rows[{ordinal}] 不是对象")
        rid = str(row.get(ROW_IDENTITY_KEY_D417) or "").strip()
        if not rid:
            raise ValueError(f"D4-17-rows[{ordinal}] 缺少 {ROW_IDENTITY_KEY_D417}")
        if rid in seen:
            raise ValueError(f"D4-17-rows 行身份 {rid!r} 重复")
        seen.add(rid)
        out.append((rid, row))
    return out


def build_store_projection_d417(payload: Any, *, contract: Any, limits: Any | None = None):
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection
    from app.services.workpaper_sync.contracts import FieldMode, ValueType

    values: dict[str, FieldValue] = {}
    row_keys: list[str] = []
    for identity, row in _rows(payload):
        row_keys.append(identity)
        for field, _col, mode, value_type, path, _label in MANAGED_FIELD_SPECS_D417:
            value = resolve_json_path(row, path) if "/" in path else row.get(path)
            sk = stable_key_for_d417(field, identity)
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
        row_keys={TABLE_KEY_D417: tuple(row_keys)},
    )


def merge_projection_into_d417_rows(*, projection: Any, base_payload: Any) -> Any:
    base = _decode(base_payload)
    container = base if isinstance(base, list) else []
    rows = [
        (str(r.get(ROW_IDENTITY_KEY_D417)), dict(r))
        for r in container
        if isinstance(r, Mapping) and r.get(ROW_IDENTITY_KEY_D417)
    ]
    by_id = {i: r for i, r in rows}
    order = [i for i, _ in rows]
    prefix = TABLE_KEY_D417 + "/"
    snake_to_path = {_snake(s[0]): s[4] for s in MANAGED_FIELD_SPECS_D417}

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


def store_item_id_d417() -> str:
    return STORE_ITEM_ID_D417
