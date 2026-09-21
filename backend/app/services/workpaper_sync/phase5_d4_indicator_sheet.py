# -*- coding: utf-8 -*-
"""D4-6 重要指标分析表的结构化投影 provider（批次B 从零第一张）。

与 phase5_d4_ipo_interview_sheets 同构：单张受管 sheet、单张动态行 table、
共享 D4 revenue entry `xlsx/gt-d4-operating-revenue`。这里只负责 store projection /
merge 与受管 sheet 声明（contract sheet payload + instrumentation spec）。

几何（openpyxl 直读权威模板 `D/D4 收入底稿.xlsx` sheet `重要指标分析D4-6`，
evidence 见 mapping_digest）：
  · 表头 row 11：指标名称/本期/上期/差异1/分析1/同行业均值/差异2/分析2（A-H）
  · 数据 row 13-24（12 个固定指标，顺序即 DEFAULT_INDICATORS）
  · 受管可编辑列：B 本期 / C 上期 / E 分析1 / F 同行业均值 / H 分析2
  · formula_mask 列：D 差异1(=IF(C=0,0,(B-C)/C)) / G 差异2(=IF(F=0,0,(B-F)/F))
  · footer marker：A25「三、审计说明」
  · 行身份 = `key`（前端 DEFAULT_INDICATORS 的稳定键 ar-to-assets 等，12 个固定；
    模板 col A 是中文指标名，属固定模板文本不受管）
  · 模板无空 UUID 列 → 注入列用 **I**（I/J 列实测空）

前端真源：`D4TabIndicator.vue` + store item `D4-6-indicators-v2`（单 JSON 数组）。
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Final

from app.services.workpaper_sync.json_path import resolve_json_path

# ── 身份常量 ────────────────────────────────────────────────────────────────
ENTRY_ID: Final[str] = "xlsx/gt-d4-operating-revenue"
TEMPLATE_RELATIVE_PATH: Final[str] = "D/D4 收入底稿.xlsx"

MANAGED_SHEET_D46: Final[str] = "重要指标分析D4-6"
TEMPLATE_ID_D46: Final[str] = "D46"
SHEET_KEY_D46: Final[str] = "d46-managed"
STORE_ITEM_ID_D46: Final[str] = "D4-6-indicators-v2"
TABLE_KEY_D46: Final[str] = "d4_6_indicators"
ROW_IDENTITY_KEY_D46: Final[str] = "key"

HEADER_ROW_D46: Final[int] = 11
FIRST_DATA_ROW_D46: Final[int] = 13
LAST_DATA_ROW_D46: Final[int] = 24
FOOTER_ROW_D46: Final[int] = 25
FOOTER_MARKER_D46: Final[str] = "三、审计说明"
MANAGED_LAST_COL_D46: Final[str] = "H"
UUID_COL_D46: Final[str] = "I"

#: 受管字段：`(field_key, 列标, mode, value_type, store_path, 表头文本)`。
#: D/G（差异 1/2）是 Excel 内部公式，进 formula_mask，不入受管字段。
#: name/formula/source 是模板固定元数据，不受管（不投影、不回写）。
MANAGED_FIELD_SPECS_D46: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    ("current", "B", "editable", "amount", "current", "本期"),
    ("prior", "C", "editable", "amount", "prior", "上期"),
    ("analysis1", "E", "editable", "text", "analysis1", "变化原因及合理性分析1"),
    ("industryAvg", "F", "editable", "amount", "industryAvg", "同行业公司平均值"),
    ("analysis2", "H", "editable", "text", "analysis2", "变化原因及合理性分析2"),
)

#: formula_mask：D/G 列 12 数据行（差异率内部公式，materialize 不覆盖 / extract 不采信）。
_FORMULA_MASK_D46: Final[tuple[str, ...]] = tuple(
    f"{col}{row}"
    for row in range(FIRST_DATA_ROW_D46, LAST_DATA_ROW_D46 + 1)
    for col in ("D", "G")
)


def _snake(field: str) -> str:
    import re

    return re.sub(r"([A-Z])", lambda m: "_" + m.group(1).lower(), field)


def stable_key_for_d46(field: str, identity: str = "{row_uuid}") -> str:
    return f"{TABLE_KEY_D46}/{identity}/{_snake(field)}"


def formula_mask_cells_d46() -> tuple[str, ...]:
    return _FORMULA_MASK_D46


def mapping_digest_payload_d46() -> dict[str, Any]:
    return {
        "managed_sheet": MANAGED_SHEET_D46,
        "template_relative_path": TEMPLATE_RELATIVE_PATH,
        "header_row": HEADER_ROW_D46,
        "first_data_row": FIRST_DATA_ROW_D46,
        "last_data_row": LAST_DATA_ROW_D46,
        "footer_row": FOOTER_ROW_D46,
        "footer_marker": FOOTER_MARKER_D46,
        "uuid_col": UUID_COL_D46,
        "fields": list(MANAGED_FIELD_SPECS_D46),
        "formula_mask": list(_FORMULA_MASK_D46),
    }


def mapping_digest_d46() -> str:
    payload = json.dumps(mapping_digest_payload_d46(), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sheet_payload_d46() -> dict[str, Any]:
    """契约 sheet payload：单张动态行 table（行身份=key，固定 12 行）。"""
    def _src(cell: str) -> str:
        return f"源xlsx!{MANAGED_SHEET_D46}!{cell}"

    fields = [
        {
            "stable_field_key": stable_key_for_d46(f[0]),
            "json_pointer": f"/rows/{{row_uuid}}/{f[4]}",
            "column_key": _snake(f[0]),
            "cell": {"column": f[1], "row_from": "row_identity"},
            "mode": f[2],
            "value_type": f[3],
            "source_ref": _src(f"{f[1]}{FIRST_DATA_ROW_D46}"),
            "header_source_ref": _src(f"{f[1]}{HEADER_ROW_D46}"),
            "store_item_id": STORE_ITEM_ID_D46,
            "header_text": f[5],
        }
        for f in MANAGED_FIELD_SPECS_D46
    ]
    return {
        "sheet_key": SHEET_KEY_D46,
        "excel_name": MANAGED_SHEET_D46,
        "template_id": TEMPLATE_ID_D46,
        "locator": {"anchor": "excel_table_sheet_association"},
        "tables": [
            {
                "table_key": TABLE_KEY_D46,
                "anchor": f"A{FIRST_DATA_ROW_D46 - 1}",
                "header_rows": 1,
                "row_identity": {
                    "kind": "field",
                    "json_pointer": f"/rows/*/{ROW_IDENTITY_KEY_D46}",
                },
                "delete_policy": "tombstone",
                "footer_anchor": {
                    "marker": FOOTER_MARKER_D46,
                    "search_column": "A",
                    "carries_total_formula": False,
                },
                "formula_mask": list(_FORMULA_MASK_D46),
                "fields": fields,
            }
        ],
    }


def instrumentation_spec_d46(
    *, entry_id: str = ENTRY_ID, template_relative_path: str = TEMPLATE_RELATIVE_PATH
):
    from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec

    return ExcelInstrumentationSpec(
        entry_id=entry_id,
        template_id=TEMPLATE_ID_D46,
        template_relative_path=template_relative_path,
        managed_sheet=MANAGED_SHEET_D46,
        first_data_row=FIRST_DATA_ROW_D46,
        last_data_row=LAST_DATA_ROW_D46,
        footer_row=FOOTER_ROW_D46,
        managed_last_col=MANAGED_LAST_COL_D46,
        uuid_col=UUID_COL_D46,
        table_name=f"GT_{TEMPLATE_ID_D46}_ROWS",
        sheet_key=SHEET_KEY_D46,
    )


def _decode(payload: Any) -> Any:
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8")
    if isinstance(payload, str):
        return json.loads(payload) if payload.strip() else []
    return payload


def _rows(payload: Any) -> list[tuple[str, Mapping[str, Any]]]:
    """从 store（D4-6-indicators-v2 数组）取 (identity, row)。行身份=key。"""
    value = _decode(payload)
    if not isinstance(value, list):
        raise ValueError("D4-6-indicators-v2 必须是数组")
    out: list[tuple[str, Mapping[str, Any]]] = []
    seen: set[str] = set()
    for ordinal, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise ValueError(f"D4-6-indicators-v2[{ordinal}] 不是对象")
        rid = str(row.get(ROW_IDENTITY_KEY_D46) or "").strip()
        if not rid:
            raise ValueError(f"D4-6-indicators-v2[{ordinal}] 缺少 {ROW_IDENTITY_KEY_D46}")
        if rid in seen:
            raise ValueError(f"D4-6-indicators-v2 行身份 {rid!r} 重复")
        seen.add(rid)
        out.append((rid, row))
    return out


def build_store_projection_d46(payload: Any, *, contract: Any, limits: Any | None = None):
    """把 store 数组投影成 Projection（受管字段，跳过 formula/元数据）。

    签名与 phase5_d4_ipo_interview_sheets.build_store_projection 对齐（供
    phase5_d4_revenue_detail.build_combined_store_projection 统一合并）。
    """
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection
    from app.services.workpaper_sync.contracts import FieldMode, ValueType

    values: dict[str, FieldValue] = {}
    row_keys: list[str] = []
    for identity, row in _rows(payload):
        row_keys.append(identity)
        for field, _col, mode, value_type, path, _label in MANAGED_FIELD_SPECS_D46:
            value = resolve_json_path(row, path) if "/" in path else row.get(path)
            sk = stable_key_for_d46(field, identity)
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
        row_keys={TABLE_KEY_D46: tuple(row_keys)},
    )


def merge_projection_into_d46_rows(*, projection: Any, base_payload: Any) -> Any:
    """把 OO→HTML Projection 合并回 store 数组（按 key 定位，只覆盖受管字段，保元数据）。"""
    base = _decode(base_payload)
    container = base if isinstance(base, list) else []
    rows = [
        (str(r.get(ROW_IDENTITY_KEY_D46)), dict(r))
        for r in container
        if isinstance(r, Mapping) and r.get(ROW_IDENTITY_KEY_D46)
    ]
    by_id = {i: r for i, r in rows}
    order = [i for i, _ in rows]
    prefix = TABLE_KEY_D46 + "/"
    snake_to_path = {_snake(s[0]): s[4] for s in MANAGED_FIELD_SPECS_D46}

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


def store_item_id_d46() -> str:
    return STORE_ITEM_ID_D46
