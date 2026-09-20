# -*- coding: utf-8 -*-
"""D4-34 其他业务收入合同测算表双向回写 provider（批次B 第九张，同 sheet 双动态区 · dict store）。

共享 D4 revenue entry `xlsx/gt-d4-operating-revenue`。同一受管 sheet 上 **2 个 dynamic 动态行区**
（房屋租赁 / 咨询业务），单 dict store `D4-34-data`（{rentals[], consults[]}），参照 D4-9（本期/上期
双区 dict store）+ D4-20（同 sheet 多区 instrumentation）。

几何（openpyxl 直读 `D/D4 收入底稿.xlsx` sheet `其他业务收入合同测算表D4-34`，A1:K29）：
  · 区1 房屋租赁（dynamic，header R12，数据 R13-17 种子 5 行）：A 序号(模板自增,不入契约) /
    B 承租方 / C 租赁期间 / D 租赁面积 / E 合同单价 / F 合同索引 / G 本期实际租赁月数 /
    H 本期应计收入 / I 本期实计收入 / J 差异(=H-I formula) / K 索引号。UUID 列 **L**。
    footer marker = `2.咨询业务`（本区数据正下方 section 标题）。
  · 区2 咨询业务（dynamic，header R19，数据 R20-24 种子 5 行）：A 序号 / B 委托方(B:C merged,
    值写 B) / D 咨询项目 / E 委托期限 / F 合同金额 / G 合同索引 / H 本期应计收入 /
    I 本期实计收入 / J 差异(=H-I formula) / K 索引号。UUID 列 **M**（≠ L，同 sheet 双区须唯一）。
    footer marker = `三、审计说明：`。
  · 文本区 审计说明/审计结论 HTML-only，不入契约。

前端真源：`D4TabOtherContract.vue`，store `D4-34-data` remark = `{rentals: RentalRow[], consults: ConsultRow[]}`。
  RentalRow = {id(rt-), tenant, period, area, unitPrice, contractRef, actualMonths, expectedRevenue,
               actualRevenue, diff(前端派生,不受管), indexRef}
  ConsultRow = {id(cs-), client, project, duration, contractAmount, contractRef, expectedRevenue,
                actualRevenue, diff(前端派生), indexRef}
  J 差异列为 Excel/前端派生 → formula_mask，不回写。
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Final

ENTRY_ID: Final[str] = "xlsx/gt-d4-operating-revenue"
TEMPLATE_RELATIVE_PATH: Final[str] = "D/D4 收入底稿.xlsx"
MANAGED_SHEET_D434: Final[str] = "其他业务收入合同测算表D4-34"
SHEET_KEY_D434: Final[str] = "d434-managed"
STORE_ITEM_ID_D434: Final[str] = "D4-34-data"

# ── 区1 房屋租赁（rentals，dynamic） ────────────────────────────────────────
TABLE_KEY_RENTAL: Final[str] = "d4_34_rentals"
TEMPLATE_ID_RENTAL: Final[str] = "D434RENT"
HEADER_ROW_RENTAL: Final[int] = 12
FIRST_ROW_RENTAL: Final[int] = 13
LAST_ROW_RENTAL: Final[int] = 17
FOOTER_ROW_RENTAL: Final[int] = 18
UUID_COL_RENTAL: Final[str] = "L"
MANAGED_LAST_COL_RENTAL: Final[str] = "K"
FOOTER_MARKER_RENTAL: Final[str] = "2.咨询业务"
#: (store 字段, 列标, value_type, 表头文本)。序号 A 模板自增不入契约；J 差异 formula。
FIELDS_RENTAL: Final[tuple[tuple[str, str, str, str], ...]] = (
    ("tenant", "B", "text", "承租方"),
    ("period", "C", "text", "租赁期间"),
    ("area", "D", "text", "租赁面积"),
    ("unitPrice", "E", "amount", "合同单价"),
    ("contractRef", "F", "text", "合同索引"),
    ("actualMonths", "G", "amount", "本期实际租赁月数"),
    ("expectedRevenue", "H", "amount", "本期应计收入"),
    ("actualRevenue", "I", "amount", "本期实计收入"),
    # J 差异 = H-I（formula_mask）
    ("indexRef", "K", "text", "索引号"),
)
FORMULA_MASK_RENTAL: Final[tuple[str, ...]] = tuple(
    f"J{r}" for r in range(FIRST_ROW_RENTAL, LAST_ROW_RENTAL + 1)
)

# ── 区2 咨询业务（consults，dynamic） ───────────────────────────────────────
TABLE_KEY_CONSULT: Final[str] = "d4_34_consults"
TEMPLATE_ID_CONSULT: Final[str] = "D434CONS"
HEADER_ROW_CONSULT: Final[int] = 19
FIRST_ROW_CONSULT: Final[int] = 20
LAST_ROW_CONSULT: Final[int] = 24
FOOTER_ROW_CONSULT: Final[int] = 25
UUID_COL_CONSULT: Final[str] = "M"
MANAGED_LAST_COL_CONSULT: Final[str] = "K"
FOOTER_MARKER_CONSULT: Final[str] = "三、审计说明："
#: 委托方 B:C merged（值写 B）；咨询项目 D / 委托期限 E / 合同金额 F / 合同索引 G。J 差异 formula。
FIELDS_CONSULT: Final[tuple[tuple[str, str, str, str], ...]] = (
    ("client", "B", "text", "委托方"),
    ("project", "D", "text", "咨询项目"),
    ("duration", "E", "text", "委托期限"),
    ("contractAmount", "F", "amount", "合同金额"),
    ("contractRef", "G", "text", "合同索引"),
    ("expectedRevenue", "H", "amount", "本期应计收入"),
    ("actualRevenue", "I", "amount", "本期实计收入"),
    # J 差异 = H-I（formula_mask）
    ("indexRef", "K", "text", "索引号"),
)
FORMULA_MASK_CONSULT: Final[tuple[str, ...]] = tuple(
    f"J{r}" for r in range(FIRST_ROW_CONSULT, LAST_ROW_CONSULT + 1)
)

#: 每区：(table_key, store_key, template_id, header_row, first_row, last_row, footer_row,
#:        uuid_col, managed_last_col, fields, formula_mask, footer_marker)
_REGIONS: Final[tuple[tuple, ...]] = (
    (TABLE_KEY_RENTAL, "rentals", TEMPLATE_ID_RENTAL, HEADER_ROW_RENTAL, FIRST_ROW_RENTAL,
     LAST_ROW_RENTAL, FOOTER_ROW_RENTAL, UUID_COL_RENTAL, MANAGED_LAST_COL_RENTAL,
     FIELDS_RENTAL, FORMULA_MASK_RENTAL, FOOTER_MARKER_RENTAL),
    (TABLE_KEY_CONSULT, "consults", TEMPLATE_ID_CONSULT, HEADER_ROW_CONSULT, FIRST_ROW_CONSULT,
     LAST_ROW_CONSULT, FOOTER_ROW_CONSULT, UUID_COL_CONSULT, MANAGED_LAST_COL_CONSULT,
     FIELDS_CONSULT, FORMULA_MASK_CONSULT, FOOTER_MARKER_CONSULT),
)

#: table_key → store 数组键（rentals/consults），merge 分流用。
_TABLE_TO_STORE_KEY: Final[dict[str, str]] = {r[0]: r[1] for r in _REGIONS}


def _snake(field: str) -> str:
    import re

    return re.sub(r"([A-Z])", lambda m: "_" + m.group(1).lower(), field)


def _dyn_stable_key(table_key: str, field: str, identity: str = "{row_uuid}") -> str:
    return f"{table_key}/{identity}/{_snake(field)}"


def _src(cell: str) -> str:
    return f"源xlsx!{MANAGED_SHEET_D434}!{cell}"


def _dyn_sheet_table(*, table_key, header_row, first_row, fields, formula_mask, uuid_col, footer_marker, store_key) -> dict[str, Any]:
    field_specs = [
        {
            "stable_field_key": _dyn_stable_key(table_key, f[0]),
            "json_pointer": f"/{store_key}/{{row_uuid}}/{f[0]}",
            "column_key": _snake(f[0]),
            "cell": {"column": f[1], "row_from": "row_identity"},
            "mode": "editable",
            "value_type": f[2],
            "source_ref": _src(f"{f[1]}{first_row}"),
            "header_source_ref": _src(f"{f[1]}{header_row}"),
            "store_item_id": STORE_ITEM_ID_D434,
            "header_text": f[3],
        }
        for f in fields
    ]
    return {
        "table_key": table_key,
        "anchor": f"A{first_row - 1}",
        "header_rows": 1,
        "row_identity": {"kind": "field", "json_pointer": f"/{store_key}/*/id"},
        "delete_policy": "tombstone",
        "uuid_col": uuid_col,
        "footer_anchor": {"marker": footer_marker, "search_column": "A", "carries_total_formula": False},
        "formula_mask": list(formula_mask),
        "fields": field_specs,
    }


def _dyn_instrumentation(*, template_id, first_row, last_row, footer_row, uuid_col, managed_last_col, entry_id, template_relative_path):
    from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec

    return ExcelInstrumentationSpec(
        entry_id=entry_id,
        template_id=template_id,
        template_relative_path=template_relative_path,
        managed_sheet=MANAGED_SHEET_D434,
        first_data_row=first_row,
        last_data_row=last_row,
        footer_row=footer_row,
        managed_last_col=managed_last_col,
        uuid_col=uuid_col,
        table_name=f"GT_{template_id}_ROWS",
        sheet_key=SHEET_KEY_D434,
    )


def mapping_digest_d434() -> str:
    payload = json.dumps(
        {
            "sheet": MANAGED_SHEET_D434,
            "regions": [(r[0], r[1], r[3], r[4], r[7], [f[0] for f in r[9]]) for r in _REGIONS],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sheet_payload_d434() -> dict[str, Any]:
    tables = []
    for table_key, store_key, _tid, header_row, first_row, _last, _footer, uuid_col, _mlc, fields, fmask, footer_marker in _REGIONS:
        tables.append(
            _dyn_sheet_table(
                table_key=table_key, header_row=header_row, first_row=first_row,
                fields=fields, formula_mask=fmask, uuid_col=uuid_col,
                footer_marker=footer_marker, store_key=store_key,
            )
        )
    return {
        "sheet_key": SHEET_KEY_D434,
        "excel_name": MANAGED_SHEET_D434,
        "template_id": "D434",
        "locator": {"anchor": "excel_table_sheet_association"},
        "tables": tables,
    }


def instrumentation_specs_d434(*, entry_id: str = ENTRY_ID, template_relative_path: str = TEMPLATE_RELATIVE_PATH) -> tuple[Any, ...]:
    specs = []
    for _tk, _sk, template_id, _hdr, first_row, last_row, footer_row, uuid_col, mlc, _fields, _fmask, _fm in _REGIONS:
        specs.append(
            _dyn_instrumentation(
                template_id=template_id, first_row=first_row, last_row=last_row, footer_row=footer_row,
                uuid_col=uuid_col, managed_last_col=mlc, entry_id=entry_id, template_relative_path=template_relative_path,
            )
        )
    return tuple(specs)


def _decode(payload: Any) -> Any:
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8")
    if isinstance(payload, str):
        return json.loads(payload) if payload.strip() else {}
    return payload


def _rows_of(data: Mapping[str, Any], store_key: str) -> list[tuple[str, Mapping[str, Any]]]:
    """从 dict store 取某区数组，校验 id 存在/不重复（缺/重 raise，非 list 容差返空）。"""
    arr = data.get(store_key) if isinstance(data, Mapping) else None
    if not isinstance(arr, list):
        return []
    out: list[tuple[str, Mapping[str, Any]]] = []
    seen: set[str] = set()
    for ordinal, row in enumerate(arr):
        if not isinstance(row, Mapping):
            raise ValueError(f"{STORE_ITEM_ID_D434}.{store_key}[{ordinal}] 不是对象")
        rid = str(row.get("id") or "").strip()
        if not rid:
            raise ValueError(f"{STORE_ITEM_ID_D434}.{store_key}[{ordinal}] 缺少 id")
        if rid in seen:
            raise ValueError(f"{STORE_ITEM_ID_D434}.{store_key} 行身份 {rid!r} 重复")
        seen.add(rid)
        out.append((rid, row))
    return out


def build_store_projection_d434(payload: Any, *, contract, limits=None):
    """单 dict store（{rentals[], consults[]}）→ 双区投影。"""
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection

    data = _decode(payload)
    data = data if isinstance(data, Mapping) else {}
    values: dict[str, FieldValue] = {}
    row_keys: dict[str, tuple[str, ...]] = {}
    for table_key, store_key, _tid, _hdr, _fr, _lr, _foot, _uuid, _mlc, fields, _fmask, _fm in _REGIONS:
        keys: list[str] = []
        for identity, row in _rows_of(data, store_key):
            keys.append(identity)
            for field, _col, _vt, _label in fields:
                sk = _dyn_stable_key(table_key, field, identity)
                spec = contract.field_by_stable_key(_dyn_stable_key(table_key, field))
                values[sk] = FieldValue(stable_key=sk, value=row.get(field), value_type=spec.value_type, mode=spec.mode, row_key=identity)
        row_keys[table_key] = tuple(keys)
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys=row_keys,
    )


def merge_projection_into_d434_store(*, projection, base_state):
    """投影合并回 dict store {rentals[], consults[]}，按 table_key 分流两区。

    dict store：返回 (merged_dict, applied, visited) 3-tuple（同 D4-9/D4-35 oo_to_html dict 块约定）。
    保留 id / diff（前端派生）/ 未受管字段与其它顶层键；两区 id 各自唯一不串区。
    """
    data = _decode(base_state)
    out = dict(data) if isinstance(data, Mapping) else {}
    applied = 0
    visited = 0

    # 每区：id → row dict（保留原字段），order 保序
    for table_key, store_key, _tid, _hdr, _fr, _lr, _foot, _uuid, _mlc, fields, _fmask, _fm in _REGIONS:
        base_arr = out.get(store_key)
        base_arr = base_arr if isinstance(base_arr, list) else []
        rows = [(str(r.get("id")), dict(r)) for r in base_arr if isinstance(r, Mapping) and r.get("id")]
        by_id = {i: r for i, r in rows}
        order = [i for i, _ in rows]
        snake_to_field = {_snake(f[0]): f[0] for f in fields}
        prefix = table_key + "/"
        for sk in projection.stable_keys():
            s = str(sk)
            if not s.startswith(prefix):
                continue
            visited += 1
            fv = projection.get(sk)
            identity = getattr(fv, "row_key", None)
            if not identity:
                continue
            parts = s.split("/")
            if len(parts) < 3:
                continue
            field = snake_to_field.get(parts[2])
            target = by_id.get(identity)
            if field is None or target is None:
                continue
            new_val = getattr(fv, "value", None)
            if target.get(field) != new_val:
                target[field] = new_val
                applied += 1
        out[store_key] = [by_id[i] for i in order]

    return out, applied, visited


def merge_d434_from_projection(*, projection, base_state):
    """oo_to_html 专用 dict 块门面（同 merge_d49_from_projection）。返回 (merged_dict, applied, visited)。"""
    return merge_projection_into_d434_store(projection=projection, base_state=base_state)


def store_item_id_d434() -> str:
    return STORE_ITEM_ID_D434
