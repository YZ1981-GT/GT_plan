# -*- coding: utf-8 -*-
"""D4-36 其他业务收入截止性测试双向回写 provider（批次B 第十张，同 sheet 双动态区 · dict store）。

共享 D4 revenue entry `xlsx/gt-d4-operating-revenue`。同一受管 sheet 上 **2 个 dynamic 动态行区**
（账到单据 forward / 单据到账 backward），单 dict store `D4-36-data`
（{forward[], backward[], cutoffDate, daysBefore, daysAfter, amountThreshold}）。
架构同 D4-34（双区 dict store）+ D4-17/18（cutoff 测试范式）。

几何（openpyxl 直读 `D/D4 收入底稿.xlsx` sheet `其他业务收入截止性测试D4-36`，A1:M59）：
  · 区1 账到单据 forward（dynamic）：2 行表头 R14-15，数据 R16-23（8 行种子），boundary R24 `截止日期`。
    列 A-E 记账凭证(日期/编号/品名/数量/金额=voucher*)，F-J 发货单(日期/编号/品名/数量/金额=doc*)，
    K 是否跨期(isCrossing √/×，前端 autoJudge 派生但模板无 Excel 公式→editable 可回写)。UUID 列 **L**。
    footer marker = `（二）单据到账`（R33，唯一）。
  · 区2 单据到账 backward（dynamic）：2 行表头 R34-35，数据 R36-43（8 行），boundary R44。
    同 11 列（store 字段名一致：A-E→voucher*，F-J→doc*，K→isCrossing）。UUID 列 **M**（≠L）。
    footer marker = `三、审计说明：`（R53，唯一）。
  · 参数 cutoffDate/daysBefore/daysAfter/amountThreshold（顶层标量）+ 截止日期文本行 R24/R44 +
    审计说明/结论 R53/R56 —— HTML-only，不入契约（保留在 merge 输出的顶层键）。

前端真源：`D4TabOtherCutoff.vue`，store `D4-36-data`；CutoffRow = {id(ct-), voucherDate, voucherNo,
  voucherProduct, voucherQty, voucherAmount, docDate, docNo, docProduct, docQty, docAmount, isCrossing}。
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Final

ENTRY_ID: Final[str] = "xlsx/gt-d4-operating-revenue"
TEMPLATE_RELATIVE_PATH: Final[str] = "D/D4 收入底稿.xlsx"
MANAGED_SHEET_D436: Final[str] = "其他业务收入截止性测试D4-36"
SHEET_KEY_D436: Final[str] = "d436-managed"
STORE_ITEM_ID_D436: Final[str] = "D4-36-data"

#: 两区共享 11 字段：(store 字段, 列标, value_type, 表头文本)。金额 amount，其余 text。
_CUTOFF_FIELDS: Final[tuple[tuple[str, str, str, str], ...]] = (
    ("voucherDate", "A", "text", "记账凭证日期"),
    ("voucherNo", "B", "text", "记账凭证编号"),
    ("voucherProduct", "C", "text", "记账凭证品名"),
    ("voucherQty", "D", "text", "记账凭证数量"),
    ("voucherAmount", "E", "amount", "记账凭证金额"),
    ("docDate", "F", "text", "单据日期"),
    ("docNo", "G", "text", "单据编号"),
    ("docProduct", "H", "text", "单据品名"),
    ("docQty", "I", "text", "单据数量"),
    ("docAmount", "J", "amount", "单据金额"),
    ("isCrossing", "K", "text", "是否跨期"),  # √/× 手工标记（前端派生），无 Excel 公式 → editable
)

# ── 区1 账到单据 forward ────────────────────────────────────────────────────
TABLE_KEY_FWD: Final[str] = "d4_36_forward"
TEMPLATE_ID_FWD: Final[str] = "D436FWD"
HEADER_ROW_FWD: Final[int] = 15
FIRST_ROW_FWD: Final[int] = 16
LAST_ROW_FWD: Final[int] = 23
FOOTER_ROW_FWD: Final[int] = 24
UUID_COL_FWD: Final[str] = "L"
#: 本区数据正下方 `截止日期：202X年12月31日` 行（R24，模板字面量，openpyxl 实测全文）。
#: footer marker 匹配是**精确等值**（text.strip()==marker），故用整格全文而非前缀。
#: 两区同 marker 文本，靠各区 first_row 作搜索下限消歧（forward first_row=16 命中 R24）。
FOOTER_MARKER_FWD: Final[str] = "截止日期：202X年12月31日"

# ── 区2 单据到账 backward ───────────────────────────────────────────────────
TABLE_KEY_BWD: Final[str] = "d4_36_backward"
TEMPLATE_ID_BWD: Final[str] = "D436BWD"
HEADER_ROW_BWD: Final[int] = 35
FIRST_ROW_BWD: Final[int] = 36
LAST_ROW_BWD: Final[int] = 43
FOOTER_ROW_BWD: Final[int] = 44
UUID_COL_BWD: Final[str] = "M"
#: 本区数据正下方 `截止日期：202X年12月31日` 行（R44，全文精确）。backward first_row=36 起搜命中 R44 而非 R24。
FOOTER_MARKER_BWD: Final[str] = "截止日期：202X年12月31日"

MANAGED_LAST_COL: Final[str] = "K"

#: 每区：(table_key, store_key, template_id, header_row, first_row, last_row, footer_row,
#:        uuid_col, footer_marker)
_REGIONS: Final[tuple[tuple, ...]] = (
    (TABLE_KEY_FWD, "forward", TEMPLATE_ID_FWD, HEADER_ROW_FWD, FIRST_ROW_FWD,
     LAST_ROW_FWD, FOOTER_ROW_FWD, UUID_COL_FWD, FOOTER_MARKER_FWD),
    (TABLE_KEY_BWD, "backward", TEMPLATE_ID_BWD, HEADER_ROW_BWD, FIRST_ROW_BWD,
     LAST_ROW_BWD, FOOTER_ROW_BWD, UUID_COL_BWD, FOOTER_MARKER_BWD),
)


def _snake(field: str) -> str:
    import re

    return re.sub(r"([A-Z])", lambda m: "_" + m.group(1).lower(), field)


def _dyn_stable_key(table_key: str, field: str, identity: str = "{row_uuid}") -> str:
    return f"{table_key}/{identity}/{_snake(field)}"


def _src(cell: str) -> str:
    return f"源xlsx!{MANAGED_SHEET_D436}!{cell}"


def _dyn_sheet_table(*, table_key, header_row, first_row, uuid_col, footer_marker, store_key) -> dict[str, Any]:
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
            "store_item_id": STORE_ITEM_ID_D436,
            "header_text": f[3],
        }
        for f in _CUTOFF_FIELDS
    ]
    return {
        "table_key": table_key,
        "anchor": f"A{first_row - 1}",
        "header_rows": 1,
        "row_identity": {"kind": "field", "json_pointer": f"/{store_key}/*/id"},
        "delete_policy": "tombstone",
        "uuid_col": uuid_col,
        "footer_anchor": {"marker": footer_marker, "search_column": "A", "carries_total_formula": False},
        "formula_mask": [],  # K 跨期为手工 √/× 标记（前端派生），非 Excel 公式，不进 mask
        "fields": field_specs,
    }


def _dyn_instrumentation(*, template_id, first_row, last_row, footer_row, uuid_col, entry_id, template_relative_path):
    from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec

    return ExcelInstrumentationSpec(
        entry_id=entry_id,
        template_id=template_id,
        template_relative_path=template_relative_path,
        managed_sheet=MANAGED_SHEET_D436,
        first_data_row=first_row,
        last_data_row=last_row,
        footer_row=footer_row,
        managed_last_col=MANAGED_LAST_COL,
        uuid_col=uuid_col,
        table_name=f"GT_{template_id}_ROWS",
        sheet_key=SHEET_KEY_D436,
    )


def mapping_digest_d436() -> str:
    payload = json.dumps(
        {
            "sheet": MANAGED_SHEET_D436,
            "regions": [(r[0], r[1], r[3], r[4], r[7]) for r in _REGIONS],
            "fields": [f[0] for f in _CUTOFF_FIELDS],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sheet_payload_d436() -> dict[str, Any]:
    tables = []
    for table_key, store_key, _tid, header_row, first_row, _last, _footer, uuid_col, footer_marker in _REGIONS:
        tables.append(
            _dyn_sheet_table(
                table_key=table_key, header_row=header_row, first_row=first_row,
                uuid_col=uuid_col, footer_marker=footer_marker, store_key=store_key,
            )
        )
    return {
        "sheet_key": SHEET_KEY_D436,
        "excel_name": MANAGED_SHEET_D436,
        "template_id": "D436",
        "locator": {"anchor": "excel_table_sheet_association"},
        "tables": tables,
    }


def instrumentation_specs_d436(*, entry_id: str = ENTRY_ID, template_relative_path: str = TEMPLATE_RELATIVE_PATH) -> tuple[Any, ...]:
    specs = []
    for _tk, _sk, template_id, _hdr, first_row, last_row, footer_row, uuid_col, _fm in _REGIONS:
        specs.append(
            _dyn_instrumentation(
                template_id=template_id, first_row=first_row, last_row=last_row, footer_row=footer_row,
                uuid_col=uuid_col, entry_id=entry_id, template_relative_path=template_relative_path,
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
    arr = data.get(store_key) if isinstance(data, Mapping) else None
    if not isinstance(arr, list):
        return []
    out: list[tuple[str, Mapping[str, Any]]] = []
    seen: set[str] = set()
    for ordinal, row in enumerate(arr):
        if not isinstance(row, Mapping):
            raise ValueError(f"{STORE_ITEM_ID_D436}.{store_key}[{ordinal}] 不是对象")
        rid = str(row.get("id") or "").strip()
        if not rid:
            raise ValueError(f"{STORE_ITEM_ID_D436}.{store_key}[{ordinal}] 缺少 id")
        if rid in seen:
            raise ValueError(f"{STORE_ITEM_ID_D436}.{store_key} 行身份 {rid!r} 重复")
        seen.add(rid)
        out.append((rid, row))
    return out


def build_store_projection_d436(payload: Any, *, contract, limits=None):
    """单 dict store（{forward[], backward[], ...params}）→ 双区投影。"""
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection

    data = _decode(payload)
    data = data if isinstance(data, Mapping) else {}
    values: dict[str, FieldValue] = {}
    row_keys: dict[str, tuple[str, ...]] = {}
    for table_key, store_key, _tid, _hdr, _fr, _lr, _foot, _uuid, _fm in _REGIONS:
        keys: list[str] = []
        for identity, row in _rows_of(data, store_key):
            keys.append(identity)
            for field, _col, _vt, _label in _CUTOFF_FIELDS:
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


def merge_projection_into_d436_store(*, projection, base_state):
    """投影合并回 dict store，按 table_key 分流两区。返回 (merged_dict, applied, visited) 3-tuple。

    保留 id / 参数标量（cutoffDate/days*/amountThreshold）/ 未受管字段与其它顶层键；两区 id 不串。
    """
    data = _decode(base_state)
    out = dict(data) if isinstance(data, Mapping) else {}
    applied = 0
    visited = 0
    snake_to_field = {_snake(f[0]): f[0] for f in _CUTOFF_FIELDS}

    for table_key, store_key, _tid, _hdr, _fr, _lr, _foot, _uuid, _fm in _REGIONS:
        base_arr = out.get(store_key)
        base_arr = base_arr if isinstance(base_arr, list) else []
        rows = [(str(r.get("id")), dict(r)) for r in base_arr if isinstance(r, Mapping) and r.get("id")]
        by_id = {i: r for i, r in rows}
        order = [i for i, _ in rows]
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


def merge_d436_from_projection(*, projection, base_state):
    """oo_to_html 专用 dict 块门面（同 merge_d434_from_projection）。返回 (merged_dict, applied, visited)。"""
    return merge_projection_into_d436_store(projection=projection, base_state=base_state)


def store_item_id_d436() -> str:
    return STORE_ITEM_ID_D436
