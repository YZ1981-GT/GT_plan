# -*- coding: utf-8 -*-
"""D4-15/16 检查表 —— 追加受管 sheet（同 adapter `d4.revenue_detail`，同 workbook）。

spec: d4-inspection-writeback-formula-io · B1 后端 workpaper_sync provider

═══ 定位（与 IPO checklist provider 同族）═══

D4-13/14/15/16 前端同步宿主全部 `parent_duplicate`，父 entry = `xlsx/gt-d4-operating-revenue`
（capability=bidirectional），权威 workbook = ``D/D4 收入底稿.xlsx``（与 D4-2/25~28 同一 blob）。
本模块把 D4-15/16 作为**追加受管 sheet** 挂进同一 entry（照 `phase5_d4_ipo_checklist_sheets.py`
数据驱动范式：`_SHEETS` dict + mapping_digest 冻结 + rows_table_payload + build/merge 投影 +
instrumentation_spec）。

═══ 本组两张表的形态 ═══

* **D4-15 完整性检查**（两级表头 row11/12，三维嵌套）：物理 A=序号 / B:F=发货单 / G:K=发票 /
  L:P=记账凭证 / Q=所载信息是否一致√(X)。前端 store `CompletenessItem`（`D4-15-items`，行 id `c-`）
  的 delivery/invoice/voucher 三层用**嵌套 json_path**（`delivery/amount` 等，`json_path.py`
  支持 slash 嵌套段）。Q=isConsistent 逐行由前端 checkConsistency 重算 → 入 **formula_mask**。
  序号(A)/remark 无物理受管列，不进契约。数据区 13–25，footer A26「三、审计说明：」，UUID=R。
* **D4-16 出口口岸核对**（两级表头 row11/12，差异派生）：物理 A=账面 / B:F=电子口岸系统 /
  G:K=免抵退税申报数据。前端 store `ExportCheckRow`（`D4-16-rows`，行 id `r-`）扁平字段。
  差异列 D(口岸差异)/I(免抵退税差异) 由前端 calcChangeAmount 重算（源模板 D13=0/I13=0）→ 入
  **formula_mask**。🔴 建模差异（T1/B1 已登记）：物理有两「期间」(B/G) 两「索引」(F/K)，前端只
  建模单 portsPeriod + 单 taxIndex，口岸侧 G 期间/F 索引未建模 → provider 只映射前端已建模字段
  （保持前端 store 单一真源，不自造）。数据区 13–15，footer A16，UUID=L。

行身份 = `id`（前端稳定 key，禁下标兜底）。mapping_digest 冻结防列映射漂移。

D4-13（纯文本表）/ D4-14（32 列七维 + 计算 footer，超 IPO 范式）不在本模块 —— 见
`evidence/b1-provider-geometry.md`。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final, Iterator, Mapping

from app.services.workpaper_sync.json_path import (
    JsonPathMissingSegmentError,
    resolve_json_path,
    set_json_path,
)

# 与 phase5_d4_revenue_detail / phase5_d4_ipo_checklist_sheets 共享的模板身份（同 workbook）。
TEMPLATE_RELATIVE_PATH: Final[str] = "D/D4 收入底稿.xlsx"


class D4InspectionDigestError(ValueError):
    """D4 检查表 sheet mapping_digest 漂移（与列规格真源不一致）。"""


def _digest(payload: dict) -> str:
    canon = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _contract_fields_digest_shape(fields) -> list[dict]:
    return [
        {"col": c, "column_key": k, "header": h, "json_path": jp, "mode": m}
        for (k, c, m, _vt, jp, h) in fields
    ]


def _resolve_store_path(row: Mapping[str, Any], json_path: str) -> Any:
    try:
        return resolve_json_path(row, json_path)
    except JsonPathMissingSegmentError:
        return None


# ═══════════════════════════════════════════════════════════════════════════
# D4-15 完整性检查（两级表头，三维嵌套 delivery/invoice/voucher）
# ═══════════════════════════════════════════════════════════════════════════

MANAGED_SHEET_D415: Final[str] = "营业收入完整性检查表D4-15"
TEMPLATE_ID_D415: Final[str] = "D415"
SHEET_KEY_D415: Final[str] = "d4-15-managed"
ROWS_TABLE_KEY_D415: Final[str] = "completeness_check_rows"
STORE_ITEM_ID_D415: Final[str] = "D4-15-items"
ROW_IDENTITY_STORE_KEY_D415: Final[str] = "id"

HEADER_ROWS_D415: Final[tuple[int, int]] = (11, 12)
FIRST_DATA_ROW_D415: Final[int] = 13
LAST_DATA_ROW_D415: Final[int] = 25
FOOTER_ROW_D415: Final[int] = 26
FOOTER_MARKER_D415: Final[str] = "三、审计说明："
MANAGED_LAST_COL_D415: Final[str] = "Q"
UUID_COL_D415: Final[str] = "R"
TABLE_NAME_D415: Final[str] = f"GT_{TEMPLATE_ID_D415}_ROWS"

#: 16 列受管：三维各 5 字段（嵌套 json_path）+ Q 一致性（派生 mask，不在字段列表）。
#: 序号(A)/remark 无物理受管列，不进契约（前端 store 单一真源）。
MANAGED_FIELD_SPECS_D415: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    ("delivery_date", "B", "editable", "text", "delivery/date", "发货单日期"),
    ("delivery_number", "C", "editable", "text", "delivery/number", "发货单编号"),
    ("delivery_product", "D", "editable", "text", "delivery/productName", "发货单品名"),
    ("delivery_quantity", "E", "editable", "text", "delivery/quantity", "发货单数量"),
    ("delivery_amount", "F", "editable", "amount", "delivery/amount", "发货单金额"),
    ("invoice_date", "G", "editable", "text", "invoice/date", "发票日期"),
    ("invoice_number", "H", "editable", "text", "invoice/number", "发票编号"),
    ("invoice_product", "I", "editable", "text", "invoice/productName", "发票品名"),
    ("invoice_quantity", "J", "editable", "text", "invoice/quantity", "发票数量"),
    ("invoice_amount", "K", "editable", "amount", "invoice/amount", "发票金额"),
    ("voucher_date", "L", "editable", "text", "voucher/date", "记账凭证日期"),
    ("voucher_number", "M", "editable", "text", "voucher/number", "记账凭证编号"),
    ("voucher_product", "N", "editable", "text", "voucher/productName", "记账凭证品名"),
    ("voucher_quantity", "O", "editable", "text", "voucher/quantity", "记账凭证数量"),
    ("voucher_amount", "P", "editable", "amount", "voucher/amount", "记账凭证金额"),
    # Q = 所载信息是否一致√(X)：前端 checkConsistency 逐行重算 → mask，不映射
)
#: Q 一致性列由前端重算，projection 不得覆盖。
FORMULA_MASK_D415: Final[tuple[str, ...]] = (
    f"Q{FIRST_DATA_ROW_D415}:Q{LAST_DATA_ROW_D415}",
)
EXPECTED_MAPPING_DIGEST_D415: Final[str] = (
    "418b36299710ecd74b6268412aec0fe576156d378286137d19746dd3ee3d715b"
)


# ═══════════════════════════════════════════════════════════════════════════
# D4-16 出口口岸核对（两级表头，差异派生）
# ═══════════════════════════════════════════════════════════════════════════

MANAGED_SHEET_D416: Final[str] = "出口收入电子口岸系统核对D4-16"
TEMPLATE_ID_D416: Final[str] = "D416"
SHEET_KEY_D416: Final[str] = "d4-16-managed"
ROWS_TABLE_KEY_D416: Final[str] = "export_customs_check_rows"
STORE_ITEM_ID_D416: Final[str] = "D4-16-rows"
ROW_IDENTITY_STORE_KEY_D416: Final[str] = "id"

HEADER_ROWS_D416: Final[tuple[int, int]] = (11, 12)
FIRST_DATA_ROW_D416: Final[int] = 13
LAST_DATA_ROW_D416: Final[int] = 15
FOOTER_ROW_D416: Final[int] = 16
FOOTER_MARKER_D416: Final[str] = "三、审计说明："
MANAGED_LAST_COL_D416: Final[str] = "K"
UUID_COL_D416: Final[str] = "L"
TABLE_NAME_D416: Final[str] = f"GT_{TEMPLATE_ID_D416}_ROWS"

#: 物理 A=账面/B:F=电子口岸/G:K=免抵退税。前端只建模字段映射如下；差异列 D/I 入 mask。
#: 口岸侧 G 期间/F 索引前端未建模 → 不映射（保持前端 store 单一真源，不自造字段）。
MANAGED_FIELD_SPECS_D416: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    ("book_amount", "A", "editable", "amount", "bookAmount", "账面出口收入金额"),
    ("ports_period", "B", "editable", "text", "portsPeriod", "口岸期间"),
    ("ports_amount", "C", "editable", "amount", "portsAmount", "口岸结关金额"),
    # D = 口岸差异（派生 mask）
    ("ports_reason", "E", "editable", "text", "portsReason", "口岸差异原因"),
    # F = 口岸索引（前端未建模，不映射）
    # G = 免抵退税期间（前端未建模，不映射）
    ("tax_report_amount", "H", "editable", "amount", "taxReportAmount", "申报外营收入"),
    # I = 免抵退税差异（派生 mask）
    ("tax_reason", "J", "editable", "text", "taxReason", "申报差异原因"),
    ("tax_index", "K", "editable", "text", "taxIndex", "索引"),
)
#: 差异列 D/I 由前端 calcChangeAmount 重算 → projection 不得覆盖（源模板 D13=0/I13=0）。
FORMULA_MASK_D416: Final[tuple[str, ...]] = (
    f"D{FIRST_DATA_ROW_D416}:D{LAST_DATA_ROW_D416}",
    f"I{FIRST_DATA_ROW_D416}:I{LAST_DATA_ROW_D416}",
)
EXPECTED_MAPPING_DIGEST_D416: Final[str] = (
    "ca12093d0ca7065dbd2647f1f7732f6f54e8fd7efda903e246847aa8961aa51c"
)


# ── 每张表的静态描述（供 digest / 断言 / 契约构建）────────────────────────────
_SHEETS = {
    "D4-15": {
        "managed_sheet": MANAGED_SHEET_D415, "template_id": TEMPLATE_ID_D415,
        "sheet_key": SHEET_KEY_D415, "table_key": ROWS_TABLE_KEY_D415,
        "store_item_id": STORE_ITEM_ID_D415, "identity_key": ROW_IDENTITY_STORE_KEY_D415,
        "header_rows": list(HEADER_ROWS_D415), "first_data_row": FIRST_DATA_ROW_D415,
        "last_data_row": LAST_DATA_ROW_D415, "footer_row": FOOTER_ROW_D415,
        "footer_marker": FOOTER_MARKER_D415, "managed_last_col": MANAGED_LAST_COL_D415,
        "uuid_col": UUID_COL_D415, "table_name": TABLE_NAME_D415,
        "fields": MANAGED_FIELD_SPECS_D415, "formula_mask": FORMULA_MASK_D415,
        "expected_digest": EXPECTED_MAPPING_DIGEST_D415, "field_count": 15,
    },
    "D4-16": {
        "managed_sheet": MANAGED_SHEET_D416, "template_id": TEMPLATE_ID_D416,
        "sheet_key": SHEET_KEY_D416, "table_key": ROWS_TABLE_KEY_D416,
        "store_item_id": STORE_ITEM_ID_D416, "identity_key": ROW_IDENTITY_STORE_KEY_D416,
        "header_rows": list(HEADER_ROWS_D416), "first_data_row": FIRST_DATA_ROW_D416,
        "last_data_row": LAST_DATA_ROW_D416, "footer_row": FOOTER_ROW_D416,
        "footer_marker": FOOTER_MARKER_D416, "managed_last_col": MANAGED_LAST_COL_D416,
        "uuid_col": UUID_COL_D416, "table_name": TABLE_NAME_D416,
        "fields": MANAGED_FIELD_SPECS_D416, "formula_mask": FORMULA_MASK_D416,
        "expected_digest": EXPECTED_MAPPING_DIGEST_D416, "field_count": 7,
    },
}


def mapping_digest_payload(sheet_code: str) -> dict[str, Any]:
    s = _SHEETS[sheet_code]
    return {
        "contract_fields": _contract_fields_digest_shape(s["fields"]),
        "first_data_row": s["first_data_row"],
        "footer_marker_exact": s["footer_marker"],
        "footer_row": s["footer_row"],
        "header_rows": s["header_rows"],
        "last_data_row": s["last_data_row"],
        "managed_sheet": s["managed_sheet"],
        "template_relative_path": TEMPLATE_RELATIVE_PATH,
    }


def compute_mapping_digest(sheet_code: str) -> str:
    return _digest(mapping_digest_payload(sheet_code))


def assert_mapping_digest(sheet_code: str) -> str:
    s = _SHEETS[sheet_code]
    got = compute_mapping_digest(sheet_code)
    if got != s["expected_digest"]:
        raise D4InspectionDigestError(
            f"{sheet_code} mapping_digest 漂移：现算={got} 冻结={s['expected_digest']}"
        )
    n = len(s["fields"])
    if n != s["field_count"]:
        raise D4InspectionDigestError(
            f"{sheet_code} 契约字段数须为 {s['field_count']}，实得 {n}"
        )
    return got


def assert_all_inspection_mapping_digests() -> dict[str, str]:
    return {code: assert_mapping_digest(code) for code in _SHEETS}


def stable_key_for(sheet_code: str, column_key: str, row_identity: str = "{row_uuid}") -> str:
    return f"{_SHEETS[sheet_code]['table_key']}/{row_identity}/{column_key}"


def rows_table_payload(sheet_code: str) -> dict[str, Any]:
    s = _SHEETS[sheet_code]
    managed_sheet = s["managed_sheet"]
    header_row = s["header_rows"][0]

    def _src(cell: str) -> str:
        return f"源xlsx!{managed_sheet}!{cell}"

    fields: list[dict[str, Any]] = []
    for column_key, column, mode, value_type, json_path, header_text in s["fields"]:
        fields.append(
            {
                "stable_field_key": stable_key_for(sheet_code, column_key),
                "json_pointer": f"/rows/{{row_uuid}}/{json_path}",
                "column_key": column_key,
                "cell": {"column": column, "row_from": "row_identity"},
                "mode": mode,
                "value_type": value_type,
                "source_ref": _src(f"{column}{s['first_data_row']}"),
                "header_source_ref": _src(f"{column}{s['header_rows'][-1]}"),
                "store_item_id": s["store_item_id"],
                "header_text": header_text,
            }
        )
    return {
        "table_key": s["table_key"],
        "anchor": f"A{header_row}",
        "header_rows": len(s["header_rows"]),
        "row_identity": {
            "kind": "field",
            "json_pointer": f"/rows/*/{s['identity_key']}",
        },
        "delete_policy": "tombstone",
        "footer_anchor": {
            "marker": s["footer_marker"],
            "search_column": "A",
            "carries_total_formula": False,
            "note": (
                f"{sheet_code} 动态行；A{s['footer_row']}「{s['footer_marker']}」是受管区下边界"
                f"（插行须下移）。UUID 用 {s['uuid_col']}（数据止 {s['managed_last_col']}）。"
            ),
        },
        "formula_mask": list(s["formula_mask"]),
        "fields": fields,
    }


def sheet_payload(sheet_code: str) -> dict[str, Any]:
    """instrumentation managed_sheets[] 的一项。"""
    s = _SHEETS[sheet_code]
    return {
        "sheet_key": s["sheet_key"],
        "excel_name": s["managed_sheet"],
        "template_id": s["template_id"],
        "locator": {"anchor": "excel_table_sheet_association"},
        "tables": [rows_table_payload(sheet_code)],
    }


def instrumentation_spec(sheet_code: str, *, entry_id: str, template_relative_path: str):
    from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec

    s = _SHEETS[sheet_code]
    return ExcelInstrumentationSpec(
        entry_id=entry_id,
        template_id=s["template_id"],
        template_relative_path=template_relative_path,
        managed_sheet=s["managed_sheet"],
        first_data_row=s["first_data_row"],
        last_data_row=s["last_data_row"],
        footer_row=s["footer_row"],
        managed_last_col=s["managed_last_col"],
        uuid_col=s["uuid_col"],
        table_name=s["table_name"],
        sheet_key=s["sheet_key"],
    )


# ═══════════════════════════════════════════════════════════════════════════
# store projection（HTML store JSON → FieldValue projection）+ merge（projection → rows）
# ═══════════════════════════════════════════════════════════════════════════


def _iter_store_rows(payload, *, identity_key: str, item_id: str):
    """行对象数组迭代（稳定身份，禁下标兜底、禁重复）。"""
    if isinstance(payload, (str, bytes, bytearray)):
        text = payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else payload
        try:
            rows = json.loads(text)
        except ValueError as exc:
            raise D4InspectionDigestError(f"{item_id} remark 非合法 JSON: {exc}") from exc
    else:
        rows = payload
    if not isinstance(rows, list):
        raise D4InspectionDigestError(
            f"{item_id} 载荷必须是行对象数组，实得 {type(rows).__name__}"
        )
    seen: set[str] = set()
    for ordinal, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise D4InspectionDigestError(f"{item_id} 第 {ordinal} 项不是对象")
        raw = row.get(identity_key)
        if not isinstance(raw, str) or not raw.strip():
            raise D4InspectionDigestError(
                f"{item_id} 第 {ordinal} 行缺稳定行身份 {identity_key!r}（禁下标兜底）"
            )
        identity = raw.strip()
        if identity in seen:
            raise D4InspectionDigestError(f"{item_id} 重复行身份 {identity!r}")
        seen.add(identity)
        yield identity, row


def build_store_projection(sheet_code: str, payload, *, contract, limits=None):
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection
    from app.services.workpaper_sync.excel_extract import StreamingProjectionBudget
    from app.services.workpaper_sync.limits import load_limits

    s = _SHEETS[sheet_code]
    lim = limits or load_limits()
    budget = StreamingProjectionBudget(lim)
    values: dict[str, FieldValue] = {}
    row_keys: list[str] = []
    for identity, row in _iter_store_rows(
        payload, identity_key=s["identity_key"], item_id=s["store_item_id"]
    ):
        budget.add_row(s["table_key"])
        row_keys.append(identity)
        for column_key, _c, _m, _vt, json_path, _h in s["fields"]:
            spec = contract.field_by_stable_key(stable_key_for(sheet_code, column_key))
            budget.add_field()
            sk = stable_key_for(sheet_code, column_key, identity)
            raw = _resolve_store_path(row, json_path)
            values[sk] = FieldValue(
                stable_key=sk,
                value=raw,
                value_type=spec.value_type,
                mode=spec.mode,
                row_key=identity,
            )
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys={s["table_key"]: tuple(row_keys)},
    )


def merge_projection_into_rows(
    sheet_code: str, *, projection: Any, base_rows: list[Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], int, int, set[str]]:
    """projection → rows（按稳定 id merge；嵌套 json_path 由 set_json_path 建中间 dict）。"""
    s = _SHEETS[sheet_code]
    table_key = s["table_key"]
    identity_key = s["identity_key"]
    field_to_path = {spec[0]: spec[4] for spec in s["fields"]}
    prefix = f"{table_key}/"

    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in base_rows:
        rid = str(row.get(identity_key) or "").strip()
        if not rid:
            continue
        by_id[rid] = dict(row)
        order.append(rid)

    applied = visited = 0
    touched: set[str] = set()
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
            target = {identity_key: str(rid)}
            by_id[str(rid)] = target
            order.append(str(rid))
        json_path = field_to_path.get(sk.rsplit("/", 1)[-1])
        if not json_path:
            continue
        visited += 1
        # 嵌套 json_path（delivery/amount）：set_json_path 自动建中间 dict。
        if set_json_path(target, json_path, getattr(fv, "value", None)):
            applied += 1
            touched.add(str(rid))
    return [by_id[rid] for rid in order], applied, visited, touched


# ── 供 phase5_d4_revenue_detail 集成用的清单 ────────────────────────────────
INSPECTION_SHEET_CODES: Final[tuple[str, ...]] = ("D4-15", "D4-16")
STORE_ITEM_ID_BY_CODE: Final[dict[str, str]] = {
    c: _SHEETS[c]["store_item_id"] for c in INSPECTION_SHEET_CODES
}
SHEET_KEY_BY_CODE: Final[dict[str, str]] = {
    c: _SHEETS[c]["sheet_key"] for c in INSPECTION_SHEET_CODES
}
