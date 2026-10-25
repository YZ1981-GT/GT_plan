# -*- coding: utf-8 -*-
"""D4-3「其他业务收入明细表」—— 第二受管 sheet（同 adapter `d4.revenue_detail`）。

spec: d-cycle-sheet-bidirectional-expansion · Task 3
T01 mapping_digest =
``b3186632300c84d14c4c9c3c947cbff0cdcaaf807ce2e5f9848d42195513637f``

═══ BP-21 与 T01 last_data_row ═══

T01 digest_payload 把 ``last_data_row=19``（A19 ``……``）写进了冻结 digest。
按 BP-21 / D2·H1 先例，受管业务末行必须排除排版占位行：

* :data:`LAST_DATA_ROW_D43` = **18**（出租…投资性房地产，6 行业务）
* :data:`TEMPLATE_PHYSICAL_LAST_ROW_D43` = **19**（含 ``……``）
* :data:`FOOTER_ROW_D43` = **20**（合计）

:func:`mapping_digest_payload_d43` 仍按 **T01 原样**（last_data_row=19）重算，
以锁死字段映射与 template sha；引擎几何用 18。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final, Mapping

#: 与 phase5_d4_revenue_detail 共享的模板身份（同 workbook）。
TEMPLATE_RELATIVE_PATH: Final[str] = "D/D4 收入底稿.xlsx"
TEMPLATE_SHA256: Final[str] = (
    "b8fb92d4c22cd5d639e415403a12cb61650639153f136a5330c930b880167b5f"
)

MANAGED_SHEET_D43: Final[str] = "其他业务收入明细表D4-3"
TEMPLATE_ID_D43: Final[str] = "D43"
SHEET_KEY_D43: Final[str] = f"{TEMPLATE_ID_D43.lower()}-managed"

HEADER_ROWS_D43: Final[tuple[int, int]] = (11, 12)
FIRST_DATA_ROW_D43: Final[int] = 13
#: BP-21：A19 为 ``……`` 排版占位，不进受管区（T01 仍记 last_data_row=19）。
TEMPLATE_TYPOGRAPHY_TAIL_ROWS_D43: Final[int] = 1
LAST_DATA_ROW_D43: Final[int] = 18
TEMPLATE_PHYSICAL_LAST_ROW_D43: Final[int] = (
    LAST_DATA_ROW_D43 + TEMPLATE_TYPOGRAPHY_TAIL_ROWS_D43
)
FOOTER_ROW_D43: Final[int] = TEMPLATE_PHYSICAL_LAST_ROW_D43 + 1  # 20
FOOTER_MARKER_D43: Final[str] = "合计"

MANAGED_LAST_COL_D43: Final[str] = "N"
UUID_COL_D43: Final[str] = "O"
TABLE_NAME_D43: Final[str] = f"GT_{TEMPLATE_ID_D43}_ROWS"

STORE_ITEM_ID_D43: Final[str] = "D4-3-rows"
ROWS_TABLE_KEY_D43: Final[str] = "other_revenue_detail_rows"
ROW_IDENTITY_STORE_KEY_D43: Final[str] = "rowId"

#: T01 冻结（evidence/T01-d43-column-field-mapping.json）。
EXPECTED_MAPPING_DIGEST_D43: Final[str] = (
    "b3186632300c84d14c4c9c3c947cbff0cdcaaf807ce2e5f9848d42195513637f"
)

#: 6 个契约字段：`(column_key, 列标, mode, value_type, store json 路径, 表头文本)`。
MANAGED_FIELD_SPECS_D43: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    ("item", "A", "editable", "text", "item", "项目"),
    ("current_unadjusted", "B", "editable", "amount", "currentUnadjusted", "本期未审数"),
    ("current_adjustment", "C", "editable", "amount", "currentAdjustment", "账项调整"),
    ("prior_unadjusted", "G", "editable", "amount", "priorUnadjusted", "上期未审数"),
    ("prior_adjustment", "H", "editable", "amount", "priorAdjustment", "账项调整"),
    ("remark", "N", "editable", "text", "remark", "备注"),
)

#: D/E/F/I/J/K/L/M —— 重分类写 0 或模板公式，projection 不得覆盖。
FORMULA_MASK_D43: Final[tuple[str, ...]] = (
    f"D{FIRST_DATA_ROW_D43}:D{LAST_DATA_ROW_D43}",
    f"E{FIRST_DATA_ROW_D43}:E{LAST_DATA_ROW_D43}",
    f"F{FIRST_DATA_ROW_D43}:F{LAST_DATA_ROW_D43}",
    f"I{FIRST_DATA_ROW_D43}:I{LAST_DATA_ROW_D43}",
    f"J{FIRST_DATA_ROW_D43}:J{LAST_DATA_ROW_D43}",
    f"K{FIRST_DATA_ROW_D43}:K{LAST_DATA_ROW_D43}",
    f"L{FIRST_DATA_ROW_D43}:L{LAST_DATA_ROW_D43}",
    f"M{FIRST_DATA_ROW_D43}:M{LAST_DATA_ROW_D43}",
)


def mapping_digest_payload_d43() -> dict[str, Any]:
    """与 T01 ``digest_payload`` 同形（含 last_data_row=19）—— 锁定映射未漂移。"""
    return {
        "managed_sheet": MANAGED_SHEET_D43,
        "header_rows": list(HEADER_ROWS_D43),
        "first_data_row": FIRST_DATA_ROW_D43,
        "last_data_row": TEMPLATE_PHYSICAL_LAST_ROW_D43,  # T01: 19
        "footer_row": FOOTER_ROW_D43,
        "footer_marker_exact": FOOTER_MARKER_D43,
        "contract_fields": [
            {"col": col, "store_key": json_path, "value_type": value_type}
            for _ck, col, _mode, value_type, json_path, _hdr in MANAGED_FIELD_SPECS_D43
        ],
        "mask_cols": ["D", "E", "F", "I", "J", "K", "L", "M"],
        "template_sha256": TEMPLATE_SHA256,
    }


def compute_mapping_digest_d43() -> str:
    canon = json.dumps(
        mapping_digest_payload_d43(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def assert_mapping_digest_d43() -> str:
    got = compute_mapping_digest_d43()
    if got != EXPECTED_MAPPING_DIGEST_D43:
        raise ValueError(
            f"D4-3 mapping_digest 漂移：现算={got} 冻结={EXPECTED_MAPPING_DIGEST_D43} —— "
            "与 evidence/T01-d43-column-field-mapping.json 不一致"
        )
    if len(MANAGED_FIELD_SPECS_D43) != 6:
        raise ValueError(
            f"D4-3 契约字段数必须为 6，实得 {len(MANAGED_FIELD_SPECS_D43)}"
        )
    return got


def stable_key_for_d43(column_key: str, row_identity: str = "{row_uuid}") -> str:
    return f"{ROWS_TABLE_KEY_D43}/{row_identity}/{column_key}"


def rows_table_payload_d43(*, excel_name: str = MANAGED_SHEET_D43) -> dict[str, Any]:
    """契约 ``sheets[].tables[]`` 条目（header_rows=2）。"""

    def _src(cell: str) -> str:
        return f"源xlsx!{excel_name}!{cell}"

    fields: list[dict[str, Any]] = []
    for column_key, column, mode, value_type, json_path, header_text in MANAGED_FIELD_SPECS_D43:
        fields.append(
            {
                "stable_field_key": stable_key_for_d43(column_key),
                "json_pointer": f"/rows/{{row_uuid}}/{json_path}",
                "column_key": column_key,
                "cell": {"column": column, "row_from": "row_identity"},
                "mode": mode,
                "value_type": value_type,
                "source_ref": _src(f"{column}{FIRST_DATA_ROW_D43}"),
                "header_source_ref": _src(f"{column}{HEADER_ROWS_D43[1]}"),
                "store_item_id": STORE_ITEM_ID_D43,
                "header_text": header_text,
            }
        )
    return {
        "table_key": ROWS_TABLE_KEY_D43,
        "anchor": f"A{HEADER_ROWS_D43[0]}",
        "header_rows": 2,
        "row_identity": {
            "kind": "field",
            "json_pointer": f"/rows/*/{ROW_IDENTITY_STORE_KEY_D43}",
        },
        "delete_policy": "tombstone",
        "footer_anchor": {
            "marker": FOOTER_MARKER_D43,
            "search_column": "A",
            "carries_total_formula": True,
            "note": (
                "footer 行 A20「合计」（纯两字）。A19「……」为排版占位（BP-21），"
                "受管区 13..18；D/I 重分类不进契约（mask/写 0）。"
            ),
        },
        "formula_mask": list(FORMULA_MASK_D43),
        "fields": fields,
    }


def _resolve_d43_store_path(row: Mapping[str, Any], json_path: str) -> Any:
    from app.services.workpaper_sync.json_path import (
        JsonPathMissingSegmentError,
        resolve_json_path,
    )

    try:
        return resolve_json_path(row, json_path)
    except JsonPathMissingSegmentError:
        return None


def split_store_row_d43(
    row: Mapping[str, Any], *, row_identity: str, contract: Any
) -> Iterator[tuple[str, Any, Any]]:
    """按 D4-3 六字段拆行 → ``(stable_key, value, FieldSpec)``。"""
    for column_key, _column, _mode, _vt, json_path, _label in MANAGED_FIELD_SPECS_D43:
        spec = contract.field_by_stable_key(stable_key_for_d43(column_key))
        yield (
            stable_key_for_d43(column_key, row_identity),
            _resolve_d43_store_path(row, json_path),
            spec,
        )


def merge_projection_into_d43_store_rows(
    *,
    projection: Any,
    base_rows: list[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], int, int, set[str]]:
    """把 extract projection 合进 D4-3-rows（扁平字段，无 months）。"""
    from app.services.workpaper_sync.json_path import set_json_path

    field_to_path = {spec[0]: spec[4] for spec in MANAGED_FIELD_SPECS_D43}
    prefix = f"{ROWS_TABLE_KEY_D43}/"
    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in base_rows:
        rid = str(row.get(ROW_IDENTITY_STORE_KEY_D43) or "").strip()
        if not rid:
            continue
        by_id[rid] = dict(row)
        order.append(rid)

    applied = 0
    visited = 0
    touched_rows: set[str] = set()
    for key in projection.stable_keys():
        sk = str(key)
        if not sk.startswith(prefix):
            continue
        fv = projection.get(key)
        if fv is None or getattr(fv, "is_protected", False):
            continue
        rid = getattr(fv, "row_key", None)
        if not rid:
            continue
        target = by_id.get(str(rid))
        if target is None:
            target = {ROW_IDENTITY_STORE_KEY_D43: str(rid), "item": ""}
            by_id[str(rid)] = target
            order.append(str(rid))
        field_id = sk.rsplit("/", 1)[-1]
        json_path = field_to_path.get(field_id)
        if not json_path:
            continue
        visited += 1
        new_val = getattr(fv, "value", None)
        if set_json_path(target, json_path, new_val):
            applied += 1
            touched_rows.add(str(rid))

    return [by_id[rid] for rid in order], applied, visited, touched_rows


def instrumentation_spec_d43(*, entry_id: str, template_relative_path: str):
    from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec

    return ExcelInstrumentationSpec(
        entry_id=entry_id,
        template_id=TEMPLATE_ID_D43,
        template_relative_path=template_relative_path,
        managed_sheet=MANAGED_SHEET_D43,
        first_data_row=FIRST_DATA_ROW_D43,
        last_data_row=LAST_DATA_ROW_D43,
        footer_row=FOOTER_ROW_D43,
        managed_last_col=MANAGED_LAST_COL_D43,
        uuid_col=UUID_COL_D43,
        table_name=TABLE_NAME_D43,
    )
