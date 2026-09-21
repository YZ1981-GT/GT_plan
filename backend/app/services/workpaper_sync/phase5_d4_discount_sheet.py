# -*- coding: utf-8 -*-
"""D4-19 销售折扣与折让检查双向回写 provider（批次B 第四张）。

单张受管 sheet、单张动态行 table，共享 D4 revenue entry `xlsx/gt-d4-operating-revenue`。

几何（openpyxl 直读 `D/D4 收入底稿.xlsx` sheet `销售折扣与折让检查D4-19`，A1:P36）：
  · 两级表头 row 11（客户名称 A / 折扣类型 B / 收入金额 C / 折让金额 D / 比例 E / 原因 F /
    记账凭证 G-L 组 / 审批单 M-N 组）+ row 12 子表头（G-N）
  · 数据 row 13 起；footer marker A24「三、审计说明」
  · 受管列 A-D + F-N（13 列）：E 折扣比例是前端 calcRate 派生 → formula_mask
  · 行身份 = `id`；模板无空 UUID 列 → 注入列 P；remark 无模板列 → 不受管

前端真源：`D4TabDiscount.vue` + store item `D4-19-rows`（JSON 数组）。
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Final

from app.services.workpaper_sync.json_path import resolve_json_path

ENTRY_ID: Final[str] = "xlsx/gt-d4-operating-revenue"
TEMPLATE_RELATIVE_PATH: Final[str] = "D/D4 收入底稿.xlsx"

MANAGED_SHEET_D419: Final[str] = "销售折扣与折让检查D4-19"
TEMPLATE_ID_D419: Final[str] = "D419"
SHEET_KEY_D419: Final[str] = "d419-managed"
STORE_ITEM_ID_D419: Final[str] = "D4-19-rows"
TABLE_KEY_D419: Final[str] = "d4_19_rows"
ROW_IDENTITY_KEY_D419: Final[str] = "id"

HEADER_ROW_D419: Final[int] = 12
FIRST_DATA_ROW_D419: Final[int] = 13
LAST_DATA_ROW_D419: Final[int] = 23
FOOTER_ROW_D419: Final[int] = 24
FOOTER_MARKER_D419: Final[str] = "三、审计说明"
MANAGED_LAST_COL_D419: Final[str] = "N"
UUID_COL_D419: Final[str] = "P"

#: 受管字段：E 折扣比例是派生（formula_mask），不入受管字段。
MANAGED_FIELD_SPECS_D419: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    ("customerName", "A", "editable", "text", "customerName", "客户名称"),
    ("discountType", "B", "editable", "text", "discountType", "折扣或折让类型"),
    ("revenueAmount", "C", "editable", "amount", "revenueAmount", "收入金额"),
    ("discountAmount", "D", "editable", "amount", "discountAmount", "折扣或折让金额"),
    ("reason", "F", "editable", "text", "reason", "折扣或折让原因"),
    ("voucherDate", "G", "editable", "text", "voucherDate", "记账凭证日期"),
    ("voucherNo", "H", "editable", "text", "voucherNo", "记账凭证编号"),
    ("accountSubject", "I", "editable", "text", "accountSubject", "会计科目"),
    ("detailSubject", "J", "editable", "text", "detailSubject", "明细科目"),
    ("debitAmount", "K", "editable", "amount", "debitAmount", "借方金额"),
    ("creditAmount", "L", "editable", "amount", "creditAmount", "贷方金额"),
    ("approvalDate", "M", "editable", "text", "approvalDate", "审批单日期"),
    ("approver", "N", "editable", "text", "approver", "审批人"),
)

#: formula_mask：E 列（折扣比例）13-23 行，前端 calcRate 派生，OO 不采信/不覆盖。
_FORMULA_MASK_D419: Final[tuple[str, ...]] = tuple(
    f"E{row}" for row in range(FIRST_DATA_ROW_D419, LAST_DATA_ROW_D419 + 1)
)


def _snake(field: str) -> str:
    import re

    return re.sub(r"([A-Z])", lambda m: "_" + m.group(1).lower(), field)


def stable_key_for_d419(field: str, identity: str = "{row_uuid}") -> str:
    return f"{TABLE_KEY_D419}/{identity}/{_snake(field)}"


def formula_mask_cells_d419() -> tuple[str, ...]:
    return _FORMULA_MASK_D419


def mapping_digest_payload_d419() -> dict[str, Any]:
    return {
        "managed_sheet": MANAGED_SHEET_D419,
        "template_relative_path": TEMPLATE_RELATIVE_PATH,
        "header_row": HEADER_ROW_D419,
        "first_data_row": FIRST_DATA_ROW_D419,
        "last_data_row": LAST_DATA_ROW_D419,
        "footer_row": FOOTER_ROW_D419,
        "footer_marker": FOOTER_MARKER_D419,
        "uuid_col": UUID_COL_D419,
        "fields": list(MANAGED_FIELD_SPECS_D419),
        "formula_mask": list(_FORMULA_MASK_D419),
    }


def mapping_digest_d419() -> str:
    payload = json.dumps(mapping_digest_payload_d419(), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sheet_payload_d419() -> dict[str, Any]:
    def _src(cell: str) -> str:
        return f"源xlsx!{MANAGED_SHEET_D419}!{cell}"

    fields = [
        {
            "stable_field_key": stable_key_for_d419(f[0]),
            "json_pointer": f"/rows/{{row_uuid}}/{f[4]}",
            "column_key": _snake(f[0]),
            "cell": {"column": f[1], "row_from": "row_identity"},
            "mode": f[2],
            "value_type": f[3],
            "source_ref": _src(f"{f[1]}{FIRST_DATA_ROW_D419}"),
            "header_source_ref": _src(f"{f[1]}{HEADER_ROW_D419}"),
            "store_item_id": STORE_ITEM_ID_D419,
            "header_text": f[5],
        }
        for f in MANAGED_FIELD_SPECS_D419
    ]
    return {
        "sheet_key": SHEET_KEY_D419,
        "excel_name": MANAGED_SHEET_D419,
        "template_id": TEMPLATE_ID_D419,
        "locator": {"anchor": "excel_table_sheet_association"},
        "tables": [
            {
                "table_key": TABLE_KEY_D419,
                "anchor": f"A{FIRST_DATA_ROW_D419 - 1}",
                "header_rows": 1,
                "row_identity": {
                    "kind": "field",
                    "json_pointer": f"/rows/*/{ROW_IDENTITY_KEY_D419}",
                },
                "delete_policy": "tombstone",
                "footer_anchor": {
                    "marker": FOOTER_MARKER_D419,
                    "search_column": "A",
                    "carries_total_formula": False,
                },
                "formula_mask": list(_FORMULA_MASK_D419),
                "fields": fields,
            }
        ],
    }


def instrumentation_spec_d419(
    *, entry_id: str = ENTRY_ID, template_relative_path: str = TEMPLATE_RELATIVE_PATH
):
    from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec

    return ExcelInstrumentationSpec(
        entry_id=entry_id,
        template_id=TEMPLATE_ID_D419,
        template_relative_path=template_relative_path,
        managed_sheet=MANAGED_SHEET_D419,
        first_data_row=FIRST_DATA_ROW_D419,
        last_data_row=LAST_DATA_ROW_D419,
        footer_row=FOOTER_ROW_D419,
        managed_last_col=MANAGED_LAST_COL_D419,
        uuid_col=UUID_COL_D419,
        table_name=f"GT_{TEMPLATE_ID_D419}_ROWS",
        sheet_key=SHEET_KEY_D419,
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
        raise ValueError("D4-19-rows 必须是数组")
    out: list[tuple[str, Mapping[str, Any]]] = []
    seen: set[str] = set()
    for ordinal, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise ValueError(f"D4-19-rows[{ordinal}] 不是对象")
        rid = str(row.get(ROW_IDENTITY_KEY_D419) or "").strip()
        if not rid:
            raise ValueError(f"D4-19-rows[{ordinal}] 缺少 {ROW_IDENTITY_KEY_D419}")
        if rid in seen:
            raise ValueError(f"D4-19-rows 行身份 {rid!r} 重复")
        seen.add(rid)
        out.append((rid, row))
    return out


def build_store_projection_d419(payload: Any, *, contract: Any, limits: Any | None = None):
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection
    from app.services.workpaper_sync.contracts import FieldMode, ValueType

    values: dict[str, FieldValue] = {}
    row_keys: list[str] = []
    for identity, row in _rows(payload):
        row_keys.append(identity)
        for field, _col, mode, value_type, path, _label in MANAGED_FIELD_SPECS_D419:
            value = resolve_json_path(row, path) if "/" in path else row.get(path)
            sk = stable_key_for_d419(field, identity)
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
        row_keys={TABLE_KEY_D419: tuple(row_keys)},
    )


def merge_projection_into_d419_rows(*, projection: Any, base_payload: Any) -> Any:
    base = _decode(base_payload)
    container = base if isinstance(base, list) else []
    rows = [
        (str(r.get(ROW_IDENTITY_KEY_D419)), dict(r))
        for r in container
        if isinstance(r, Mapping) and r.get(ROW_IDENTITY_KEY_D419)
    ]
    by_id = {i: r for i, r in rows}
    order = [i for i, _ in rows]
    prefix = TABLE_KEY_D419 + "/"
    snake_to_path = {_snake(s[0]): s[4] for s in MANAGED_FIELD_SPECS_D419}

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


def store_item_id_d419() -> str:
    return STORE_ITEM_ID_D419
