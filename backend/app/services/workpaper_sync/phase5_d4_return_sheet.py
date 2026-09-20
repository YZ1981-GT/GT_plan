# -*- coding: utf-8 -*-
"""D4-20 销售退货检查表双向回写 provider（批次B 第七张，4 region 同 sheet）。

共享 D4 revenue entry `xlsx/gt-d4-operating-revenue`。同一受管 sheet 上 **4 个受管区**
（1 static 固定行 + 3 dynamic 动态行），参照 D4-9（3 region）+ D4-1（多 spec 同 sheet）。

几何（openpyxl 直读 `D/D4 收入底稿.xlsx` sheet `销售退货检查表 D4-20`，A1:O61）：
  · 区1 退货总体情况（static，行 15-16 数据 + 17 合计）：A 分类(模板文本固定) / B 本期退货 /
    C 本期收入 / D 比例(formula) / E 上期退货 / F 上期收入 / G 比例(formula)。store `D4-20-summary`
    （固定 3 行：贸易商/终端用户/合计）。→ static_row 模式（参 D4-5 fixed_table）。
  · 区2 重新测算（dynamic，行 25-29+）：A 产品名 / B 计提基数 / C 计提比例 / D 应计提(=B*C formula) /
    E 账面已计提 / F 差异(formula) / G 差异原因。store `D4-20-provision`（id）。header 24，uuid 列 H。
  · 区3 本期退货（dynamic，行 34+）：15 列 A-O。store `D4-20-current-returns`（id）。header 32-33，uuid 列 P。
  · 区4 期后退货（dynamic，行 40+）：同 15 列。store `D4-20-post-returns`（id）。header 38-39，uuid 列 P。
  · footer marker：`检查内容说明：`(A43)。
  · 文本区 policy/assessment/note/conclusion HTML-only，不入契约。

本 provider 只实现 **3 个 dynamic 区 + 1 个 static 区** 的 contract sheet payload / instrumentation
（每 dynamic 区一个 spec）/ store projection / merge。static 区用 static_row cell 映射。
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Final

from app.services.workpaper_sync.json_path import resolve_json_path

ENTRY_ID: Final[str] = "xlsx/gt-d4-operating-revenue"
TEMPLATE_RELATIVE_PATH: Final[str] = "D/D4 收入底稿.xlsx"
MANAGED_SHEET_D420: Final[str] = "销售退货检查表 D4-20"
SHEET_KEY_D420: Final[str] = "d420-managed"
FOOTER_MARKER_D420: Final[str] = "检查内容说明："

# ── 区2 重新测算（provision，dynamic） ──────────────────────────────────────
STORE_ITEM_ID_PROV: Final[str] = "D4-20-provision"
TABLE_KEY_PROV: Final[str] = "d4_20_provision"
TEMPLATE_ID_PROV: Final[str] = "D420PROV"
HEADER_ROW_PROV: Final[int] = 24
FIRST_ROW_PROV: Final[int] = 25
LAST_ROW_PROV: Final[int] = 29
UUID_COL_PROV: Final[str] = "H"
FOOTER_ROW_PROV: Final[int] = 31
FOOTER_MARKER_PROV: Final[str] = "5.检查本期产品退货情况"  # 本区数据正下方 section 标题
FIELDS_PROV: Final[tuple[tuple[str, str, str, str], ...]] = (
    ("productName", "A", "text", "产品名称"),
    ("base", "B", "amount", "计提基数"),
    ("rate", "C", "amount", "计提比例"),
    # D 应计提=B*C（formula_mask）
    ("alreadyProvided", "E", "amount", "账面已计提金额"),
    # F 差异（formula_mask）
    ("diffReason", "G", "text", "差异原因"),
)
FORMULA_MASK_PROV: Final[tuple[str, ...]] = tuple(
    f"{col}{r}" for r in range(FIRST_ROW_PROV, LAST_ROW_PROV + 1) for col in ("D", "F")
)

# ── 区3/区4 退货检查（current / post，dynamic，15 列同布局） ───────────────────
_RETURN_FIELDS: Final[tuple[tuple[str, str, str, str], ...]] = (
    ("voucherDate", "A", "text", "记账凭证日期"),
    ("voucherNo", "B", "text", "记账凭证编号"),
    ("bizContent", "C", "text", "业务内容"),
    ("subjectName", "D", "text", "科目名称"),
    ("detailSubject", "E", "text", "二级明细"),
    ("debitAmount", "F", "amount", "借方金额"),
    ("creditAmount", "G", "amount", "贷方金额"),
    ("customerName", "H", "text", "客户名称"),
    ("productName", "I", "text", "产品名称"),
    ("returnQty", "J", "text", "退货数量"),
    ("returnAmount", "K", "amount", "退货金额"),
    ("returnReason", "L", "text", "退货原因"),
    ("hasLitigation", "M", "text", "是否涉及诉讼"),
    ("isAbnormal", "N", "text", "是否异常"),
    ("indexRef", "O", "text", "索引号"),
)
STORE_ITEM_ID_CUR: Final[str] = "D4-20-current-returns"
TABLE_KEY_CUR: Final[str] = "d4_20_current_returns"
TEMPLATE_ID_CUR: Final[str] = "D420CUR"
HEADER_ROW_CUR: Final[int] = 33
FIRST_ROW_CUR: Final[int] = 34
LAST_ROW_CUR: Final[int] = 36
UUID_COL_CUR: Final[str] = "P"
FOOTER_ROW_CUR: Final[int] = 37
FOOTER_MARKER_CUR: Final[str] = "6.检查期后产品退货情况"

STORE_ITEM_ID_POST: Final[str] = "D4-20-post-returns"
TABLE_KEY_POST: Final[str] = "d4_20_post_returns"
TEMPLATE_ID_POST: Final[str] = "D420POST"
HEADER_ROW_POST: Final[int] = 39
FIRST_ROW_POST: Final[int] = 40
LAST_ROW_POST: Final[int] = 42
UUID_COL_POST: Final[str] = "Q"  # 与 current(P) 区分：同 sheet 双区 UUID 列须唯一（alignment 要求）
FOOTER_ROW_POST: Final[int] = 43
FOOTER_MARKER_POST: Final[str] = "检查内容说明："

# ── 区1 退货总体情况（summary，static 固定 2 行 + 合计） ──────────────────────
STORE_ITEM_ID_SUMMARY: Final[str] = "D4-20-summary"
TABLE_KEY_SUMMARY: Final[str] = "d4_20_summary"
#: 固定 2 数据行（贸易商 R15 / 终端用户 R16）× 受管列 B/C/E/F（D/G 比例为 formula）。
SUMMARY_ROWS: Final[tuple[tuple[int, str], ...]] = ((15, "贸易商"), (16, "终端用户"))
SUMMARY_FIELDS: Final[tuple[tuple[str, str, str, str], ...]] = (
    ("currentReturn", "B", "amount", "本期退货金额"),
    ("currentRevenue", "C", "amount", "本期收入金额"),
    ("priorReturn", "E", "amount", "上期退货金额"),
    ("priorRevenue", "F", "amount", "上期收入金额"),
)
#: summary D/G 比例 + 合计行 17（B-G）为 Excel 内部公式。
FORMULA_MASK_SUMMARY: Final[tuple[str, ...]] = tuple(
    f"{col}{r}" for r in (15, 16) for col in ("D", "G")
) + tuple(f"{col}17" for col in ("B", "C", "D", "E", "F", "G"))


def _snake(field: str) -> str:
    import re

    return re.sub(r"([A-Z])", lambda m: "_" + m.group(1).lower(), field)


# ═══════════════════════════════════════════════════════════════════════════
# dynamic 区通用助手（provision / current / post 共用）
# ═══════════════════════════════════════════════════════════════════════════
def _dyn_stable_key(table_key: str, field: str, identity: str = "{row_uuid}") -> str:
    return f"{table_key}/{identity}/{_snake(field)}"


def _dyn_sheet_table(
    *, table_key: str, header_row: int, first_row: int, fields, formula_mask, store_item_id: str, uuid_col: str, footer_marker: str
) -> dict[str, Any]:
    def _src(cell: str) -> str:
        return f"源xlsx!{MANAGED_SHEET_D420}!{cell}"

    field_specs = [
        {
            "stable_field_key": _dyn_stable_key(table_key, f[0]),
            "json_pointer": f"/rows/{{row_uuid}}/{f[0]}",
            "column_key": _snake(f[0]),
            "cell": {"column": f[1], "row_from": "row_identity"},
            "mode": "editable",
            "value_type": f[2],
            "source_ref": _src(f"{f[1]}{first_row}"),
            "header_source_ref": _src(f"{f[1]}{header_row}"),
            "store_item_id": store_item_id,
            "header_text": f[3],
        }
        for f in fields
    ]
    return {
        "table_key": table_key,
        "anchor": f"A{first_row - 1}",
        "header_rows": 1,
        "row_identity": {"kind": "field", "json_pointer": "/rows/*/id"},
        "delete_policy": "tombstone",
        "uuid_col": uuid_col,  # 同 sheet 多区靠此列把 spec 与 table 一一配对（alignment 读 payload）
        "footer_anchor": {"marker": footer_marker, "search_column": "A", "carries_total_formula": False},
        "formula_mask": list(formula_mask),
        "fields": field_specs,
    }


def _dyn_instrumentation(*, template_id: str, first_row: int, last_row: int, footer_row: int, uuid_col: str, sheet_key: str, table_name: str, managed_last_col: str, entry_id: str, template_relative_path: str):
    from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec

    return ExcelInstrumentationSpec(
        entry_id=entry_id,
        template_id=template_id,
        template_relative_path=template_relative_path,
        managed_sheet=MANAGED_SHEET_D420,
        first_data_row=first_row,
        last_data_row=last_row,
        footer_row=footer_row,
        managed_last_col=managed_last_col,
        uuid_col=uuid_col,
        table_name=table_name,
        sheet_key=sheet_key,
    )


def _decode(payload: Any) -> Any:
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8")
    if isinstance(payload, str):
        return json.loads(payload) if payload.strip() else []
    return payload


def _dyn_rows(payload: Any, store_item_id: str) -> list[tuple[str, Mapping[str, Any]]]:
    value = _decode(payload)
    if not isinstance(value, list):
        return []  # legacy 容差：非数组视为空，不打挂全 entry
    out: list[tuple[str, Mapping[str, Any]]] = []
    seen: set[str] = set()
    for ordinal, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise ValueError(f"{store_item_id}[{ordinal}] 不是对象")
        rid = str(row.get("id") or "").strip()
        if not rid:
            raise ValueError(f"{store_item_id}[{ordinal}] 缺少 id")
        if rid in seen:
            raise ValueError(f"{store_item_id} 行身份 {rid!r} 重复")
        seen.add(rid)
        out.append((rid, row))
    return out


def _dyn_projection(payload, *, contract, table_key, fields, store_item_id):
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection

    values: dict[str, FieldValue] = {}
    row_keys: list[str] = []
    for identity, row in _dyn_rows(payload, store_item_id):
        row_keys.append(identity)
        for field, _col, _value_type, _label in fields:
            value = resolve_json_path(row, field) if "/" in field else row.get(field)
            sk = _dyn_stable_key(table_key, field, identity)
            # value_type / mode 取契约解析后的枚举（非原始字符串），与 commit 侧一致
            spec = contract.field_by_stable_key(_dyn_stable_key(table_key, field))
            values[sk] = FieldValue(stable_key=sk, value=value, value_type=spec.value_type, mode=spec.mode, row_key=identity)
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys={table_key: tuple(row_keys)},
    )


def _dyn_merge(*, projection, base_payload, table_key, fields):
    base = _decode(base_payload)
    container = base if isinstance(base, list) else []
    rows = [(str(r.get("id")), dict(r)) for r in container if isinstance(r, Mapping) and r.get("id")]
    by_id = {i: r for i, r in rows}
    order = [i for i, _ in rows]
    prefix = table_key + "/"
    snake_to_field = {_snake(f[0]): f[0] for f in fields}
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
        field = snake_to_field.get(parts[2])
        target = by_id.get(identity)
        if field is None or target is None:
            continue
        target[field] = getattr(fv, "value", None)
    return [by_id[i] for i in order]


# ═══════════════════════════════════════════════════════════════════════════
# static 区（summary）
# ═══════════════════════════════════════════════════════════════════════════
def _summary_stable_key(field: str, ordinal: int) -> str:
    return f"{TABLE_KEY_SUMMARY}/row{ordinal}/{_snake(field)}"


def _summary_table_payload() -> dict[str, Any]:
    def _src(cell: str) -> str:
        return f"源xlsx!{MANAGED_SHEET_D420}!{cell}"

    field_specs: list[dict[str, Any]] = []
    for ordinal, (row, _label) in enumerate(SUMMARY_ROWS):
        for field, col, value_type, header in SUMMARY_FIELDS:
            field_specs.append(
                {
                    "stable_field_key": _summary_stable_key(field, ordinal),
                    "json_pointer": f"/{ordinal}/{field}",
                    "column_key": f"{_snake(field)}_{ordinal}",
                    "cell": {"column": col, "row_from": row},
                    "mode": "editable",
                    "value_type": value_type,
                    "source_ref": _src(f"{col}{row}"),
                    "header_source_ref": _src(f"{col}14"),
                    "store_item_id": STORE_ITEM_ID_SUMMARY,
                    "header_text": header,
                }
            )
    # static 表：无 row_identity / delete_policy / footer_anchor（参 D4-5 fixed_table_payload_d45）。
    return {
        "table_key": TABLE_KEY_SUMMARY,
        "anchor": "A13",
        "header_rows": 2,
        "formula_mask": list(FORMULA_MASK_SUMMARY),
        "fields": field_specs,
    }


def build_summary_projection(payload, *, contract, limits=None):
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection

    data = _decode(payload)
    rows = data if isinstance(data, list) else []
    values: dict[str, FieldValue] = {}
    for ordinal, (_row, _label) in enumerate(SUMMARY_ROWS):
        src = rows[ordinal] if ordinal < len(rows) and isinstance(rows[ordinal], Mapping) else {}
        for field, _col, value_type, _header in SUMMARY_FIELDS:
            sk = _summary_stable_key(field, ordinal)
            spec = contract.field_by_stable_key(sk)
            value = src.get(field)
            # amount 缺失归一为 0（与 materialize 空金额格反读一致，防 RoundtripEquivalenceError）
            if value is None and value_type == "amount":
                value = 0
            values[sk] = FieldValue(stable_key=sk, value=value, value_type=spec.value_type, mode=spec.mode, row_key=None)
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys={TABLE_KEY_SUMMARY: ()},
    )


def merge_summary_projection(*, projection, base_payload):
    data = _decode(base_payload)
    rows = [dict(r) if isinstance(r, Mapping) else {} for r in (data if isinstance(data, list) else [])]
    while len(rows) < len(SUMMARY_ROWS) + 1:  # 保留合计行占位（第 3 行）
        rows.append({})
    prefix = TABLE_KEY_SUMMARY + "/row"
    for sk in projection.stable_keys():
        s = str(sk)
        if not s.startswith(prefix):
            continue
        parts = s.split("/")
        if len(parts) < 3:
            continue
        try:
            ordinal = int(parts[1].replace("row", ""))
        except ValueError:
            continue
        field_snake = parts[2]
        field = next((f[0] for f in SUMMARY_FIELDS if _snake(f[0]) == field_snake), None)
        if field is None or ordinal >= len(rows):
            continue
        rows[ordinal][field] = getattr(projection.get(sk), "value", None)
    return rows


# ═══════════════════════════════════════════════════════════════════════════
# 对外 API（4 区聚合）
# ═══════════════════════════════════════════════════════════════════════════
#: 每区元组：(table_key, store_item_id, template_id, header_row, first_row, last_row, footer_row,
#:            uuid_col, managed_last_col, fields, formula_mask, footer_marker)
_DYN_REGIONS = (
    (TABLE_KEY_PROV, STORE_ITEM_ID_PROV, TEMPLATE_ID_PROV, HEADER_ROW_PROV, FIRST_ROW_PROV, LAST_ROW_PROV, FOOTER_ROW_PROV, UUID_COL_PROV, "G", FIELDS_PROV, FORMULA_MASK_PROV, FOOTER_MARKER_PROV),
    (TABLE_KEY_CUR, STORE_ITEM_ID_CUR, TEMPLATE_ID_CUR, HEADER_ROW_CUR, FIRST_ROW_CUR, LAST_ROW_CUR, FOOTER_ROW_CUR, UUID_COL_CUR, "O", _RETURN_FIELDS, (), FOOTER_MARKER_CUR),
    (TABLE_KEY_POST, STORE_ITEM_ID_POST, TEMPLATE_ID_POST, HEADER_ROW_POST, FIRST_ROW_POST, LAST_ROW_POST, FOOTER_ROW_POST, UUID_COL_POST, "O", _RETURN_FIELDS, (), FOOTER_MARKER_POST),
)


def mapping_digest_d420() -> str:
    payload = json.dumps(
        {
            "sheet": MANAGED_SHEET_D420,
            "dynamic": [(r[0], r[3], r[4], r[7], [f[0] for f in r[9]]) for r in _DYN_REGIONS],
            "summary": [(_r, _l) for _r, _l in SUMMARY_ROWS],
            "summary_fields": [f[0] for f in SUMMARY_FIELDS],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sheet_payload_d420() -> dict[str, Any]:
    tables = [_summary_table_payload()]
    for table_key, store_item_id, _tid, header_row, first_row, _last, _footer, uuid_col, _mlc, fields, fmask, footer_marker in _DYN_REGIONS:
        tables.append(
            _dyn_sheet_table(
                table_key=table_key, header_row=header_row, first_row=first_row,
                fields=fields, formula_mask=fmask, store_item_id=store_item_id, uuid_col=uuid_col,
                footer_marker=footer_marker,
            )
        )
    return {
        "sheet_key": SHEET_KEY_D420,
        "excel_name": MANAGED_SHEET_D420,
        "template_id": "D420",
        "locator": {"anchor": "excel_table_sheet_association"},
        "tables": tables,
    }


def instrumentation_specs_d420(*, entry_id: str = ENTRY_ID, template_relative_path: str = TEMPLATE_RELATIVE_PATH) -> tuple[Any, ...]:
    specs = []
    for table_key, _store, template_id, _hdr, first_row, last_row, footer_row, uuid_col, mlc, _fields, _fmask, _fm in _DYN_REGIONS:
        specs.append(
            _dyn_instrumentation(
                template_id=template_id, first_row=first_row, last_row=last_row, footer_row=footer_row,
                uuid_col=uuid_col, sheet_key=SHEET_KEY_D420, table_name=f"GT_{template_id}_ROWS",
                managed_last_col=mlc, entry_id=entry_id, template_relative_path=template_relative_path,
            )
        )
    return tuple(specs)


def build_store_projection_d420(payloads: Mapping[str, Any], *, contract, limits=None):
    """4 区合并投影。payloads = {store_item_id: payload}。"""
    from app.services.workpaper_sync.adapters.base import Projection

    projs = [build_summary_projection(payloads.get(STORE_ITEM_ID_SUMMARY, []), contract=contract, limits=limits)]
    for table_key, store_item_id, _tid, _hdr, _fr, _lr, _foot, _uuid, _mlc, fields, _fmask, _fm in _DYN_REGIONS:
        projs.append(
            _dyn_projection(payloads.get(store_item_id, []), contract=contract, table_key=table_key, fields=fields, store_item_id=store_item_id)
        )
    values: dict[str, Any] = {}
    row_keys: dict[str, Any] = {}
    for p in projs:
        values.update(p.values)
        row_keys.update(dict(p.row_keys))
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys=row_keys,
    )


def merge_projection_into_d420_stores(*, projection, base_by_item: Mapping[str, Any]) -> dict[str, Any]:
    """把投影合并回 4 个 store item。返回 {store_item_id: 新载荷}。"""
    out: dict[str, Any] = {
        STORE_ITEM_ID_SUMMARY: merge_summary_projection(
            projection=projection, base_payload=base_by_item.get(STORE_ITEM_ID_SUMMARY, [])
        )
    }
    for table_key, store_item_id, _tid, _hdr, _fr, _lr, _foot, _uuid, _mlc, fields, _fmask, _fm in _DYN_REGIONS:
        out[store_item_id] = _dyn_merge(
            projection=projection, base_payload=base_by_item.get(store_item_id, []), table_key=table_key, fields=fields
        )
    return out


def store_item_ids_d420() -> tuple[str, ...]:
    return (STORE_ITEM_ID_SUMMARY, STORE_ITEM_ID_PROV, STORE_ITEM_ID_CUR, STORE_ITEM_ID_POST)
