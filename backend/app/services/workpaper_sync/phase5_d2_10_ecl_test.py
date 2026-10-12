# -*- coding: utf-8 -*-
"""D2-10「预期信用损失的计量测试」—— 检查 entry 的 sibling sheet。

spec: d2-inspection-sync-coverage

═══ 模板几何 ═══

受管 sheet = ``预期信用损失的计量测试D2-10``，110×10（A1:J110）。

极复杂——4 大节 7 个表区。本 provider 只受管 **(一) 单项 ECL 率区**（R11~R20），
其余 6 个表区（历史损失率 3 种方法 / 前瞻性调整 / 组合 ECL 率 3 种方法）保留 OO-only。

单项区结构：
* 两级表头 R11/R12
* 两组数据行（每组各一个债务人 + 实际利率 + 合计行）
  - 第一组：R13-16（3 行场景 + 合计）
  - 第二组：R17-20（3 行场景 + 合计）
* 字段：A=单项名称 / B=账面余额 / C=未来现金流1年 / D=折现值1年 / E=折现值2年 /
  F=发生概率 / G=概率加权(公式=D×F或E×F) / H=预期信用损失率

本 provider 受管第一组（R13-16）的 3 行场景行。R16 是合计行（公式）。
第二组结构完全相同，作为后续扩容。

前端 store: ``D2-ecl-discount-rows``（折现法单项 ECL 行）。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final, Iterator, Mapping, Sequence

from app.services.workpaper_sync.contracts import FieldSpec, SyncContract
from app.services.workpaper_sync.models import SyncDomainError


class StorePayloadError(SyncDomainError):
    error_code = "d210_store_payload_invalid"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量
# ═══════════════════════════════════════════════════════════════════════════

MANAGED_SHEET_D210: Final[str] = "预期信用损失的计量测试D2-10"
TEMPLATE_ID_D210: Final[str] = "D210"
SHEET_KEY_D210: Final[str] = "d210-managed"

STORE_ITEM_ID: Final[str] = "D2-ecl-discount-rows"
ROWS_TABLE_KEY: Final[str] = "ecl_discount_rows"
ROW_IDENTITY_STORE_KEY: Final[str] = "rowId"

#: 单项区第一组（R13 场景开始，R16 合计＝footer）
HEADER_ROW: Final[int] = 11
FIRST_DATA_ROW: Final[int] = 13
LAST_DATA_ROW: Final[int] = 15
FOOTER_ROW: Final[int] = 16
FOOTER_MARKER: Final[str] = "实际利率"

MANAGED_LAST_COL: Final[str] = "H"
UUID_COL: Final[str] = "J"  # I 列有提示文字，UUID 用 J
TABLE_NAME: Final[str] = "GT_D210_DISC_ROWS"

#: 单项 ECL 场景行字段（7 列，G 是公式）。
FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    ("scenario_name", "A", "editable", "text", "scenarioName", "情景"),
    ("balance", "B", "editable", "amount", "balance", "账面余额"),
    ("cashflow_y1", "C", "editable", "amount", "cashflowY1", "未来现金流量-1年"),
    ("pv_y1", "D", "editable", "amount", "pvY1", "折现值-1年"),
    ("pv_y2", "E", "editable", "amount", "pvY2", "折现值-2年"),
    ("probability", "F", "editable", "amount", "probability", "发生概率"),
    ("weighted", "G", "formula", "amount", "weighted", "概率加权"),
    ("ecl_rate", "H", "editable", "amount", "expectedLossRate", "预期信用损失率"),
)

FORMULA_MASK: Final[tuple[str, ...]] = (
    f"G{FIRST_DATA_ROW}:G{LAST_DATA_ROW}",
)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 契约 payload
# ═══════════════════════════════════════════════════════════════════════════

def _src(cell: str) -> str:
    return f"源xlsx!{MANAGED_SHEET_D210}!{cell}"

def stable_key_for(column_key: str, row_id: str = "{row_uuid}") -> str:
    return f"{ROWS_TABLE_KEY}/{row_id}/{column_key}"

def _rows_table_payload() -> dict[str, Any]:
    fields = []
    for ck, col, mode, vt, jp, label in FIELD_SPECS:
        fields.append({
            "stable_field_key": stable_key_for(ck),
            "json_pointer": f"/rows/{{row_uuid}}/{jp}",
            "column_key": ck,
            "cell": {"column": col, "row_from": "row_identity"},
            "mode": mode, "value_type": vt,
            "source_ref": _src(f"{col}{FIRST_DATA_ROW}"),
            "header_source_ref": _src(f"{col}{HEADER_ROW}"),
            "store_item_id": STORE_ITEM_ID,
            "header_text": label,
        })
    return {
        "table_key": ROWS_TABLE_KEY,
        "anchor": f"A{HEADER_ROW}",
        "header_rows": 2,
        "row_identity": {"kind": "field", "json_pointer": f"/rows/*/{ROW_IDENTITY_STORE_KEY}"},
        "delete_policy": "tombstone",
        "footer_anchor": {"marker": FOOTER_MARKER, "search_column": "A", "carries_total_formula": True},
        "formula_mask": list(FORMULA_MASK),
        "fields": fields,
    }

def sheet_payload_d210() -> dict[str, Any]:
    from app.services.workpaper_sync.excel_extract import TABLE_SHEET_ANCHOR
    return {
        "sheet_key": SHEET_KEY_D210,
        "excel_name": MANAGED_SHEET_D210,
        "locator": {"anchor": TABLE_SHEET_ANCHOR},
        "tables": [_rows_table_payload()],
    }

# ═══════════════════════════════════════════════════════════════════════════
# 3. Instrumentation spec
# ═══════════════════════════════════════════════════════════════════════════

def instrumentation_spec_d210(*, entry_id: str, template_relative_path: str) -> Any:
    from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec
    return ExcelInstrumentationSpec(
        entry_id=entry_id, template_id=TEMPLATE_ID_D210,
        template_relative_path=template_relative_path,
        managed_sheet=MANAGED_SHEET_D210,
        first_data_row=FIRST_DATA_ROW, last_data_row=LAST_DATA_ROW,
        footer_row=FOOTER_ROW, managed_last_col=MANAGED_LAST_COL,
        uuid_col=UUID_COL, table_name=TABLE_NAME, sheet_key=SHEET_KEY_D210,
    )

# ═══════════════════════════════════════════════════════════════════════════
# 4. Mapping digest
# ═══════════════════════════════════════════════════════════════════════════

def mapping_digest_payload() -> dict[str, Any]:
    return {
        "sheet_key": SHEET_KEY_D210,
        "fields": [{"column_key": ck, "column": col, "mode": m, "value_type": vt, "json_path": jp}
                   for ck, col, m, vt, jp, _ in FIELD_SPECS],
    }

def compute_mapping_digest() -> str:
    return hashlib.sha256(json.dumps(mapping_digest_payload(), sort_keys=True, ensure_ascii=False).encode()).hexdigest()

_FROZEN_MAPPING_DIGEST: Final[str] = "fd8642dffef5080e77991428c541d5a87d48df7044f60af83b06d2990c568db3"

def assert_mapping_digest_d210() -> str:
    d = compute_mapping_digest()
    if _FROZEN_MAPPING_DIGEST and d != _FROZEN_MAPPING_DIGEST:
        raise SyncDomainError(f"D2-10 mapping digest drift: {d} != {_FROZEN_MAPPING_DIGEST}")
    return d

# ═══════════════════════════════════════════════════════════════════════════
# 5. Store projection
# ═══════════════════════════════════════════════════════════════════════════

def _iter(payload: str | bytes | Sequence[Any]) -> Iterator[tuple[str, Mapping[str, Any]]]:
    if isinstance(payload, (str, bytes, bytearray)):
        text = payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else payload
        try: rows: Any = json.loads(text)
        except ValueError as exc: raise StorePayloadError(f"{STORE_ITEM_ID} JSON: {exc}") from exc
    else: rows = payload
    if not isinstance(rows, list): raise StorePayloadError(f"{STORE_ITEM_ID} 必须是数组")
    seen: set[str] = set()
    for i, row in enumerate(rows):
        if not isinstance(row, Mapping): raise StorePayloadError(f"{STORE_ITEM_ID}[{i}] 不是对象")
        rid = row.get(ROW_IDENTITY_STORE_KEY)
        if not isinstance(rid, str) or not rid.strip(): raise StorePayloadError(f"{STORE_ITEM_ID}[{i}] 缺 rowId")
        rid = rid.strip()
        if rid in seen: raise StorePayloadError(f"{STORE_ITEM_ID} 重复 {rid!r}")
        seen.add(rid); yield rid, row

def _resolve(row: Mapping[str, Any], jp: str) -> Any:
    cur: Any = row
    for seg in jp.split("/"): cur = cur.get(seg) if isinstance(cur, Mapping) else None
    return cur

def build_d210_store_projection(payload: str | bytes | Sequence[Any], *, contract: SyncContract, limits: Any | None = None) -> Any:
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection
    from app.services.workpaper_sync.excel_extract import StreamingProjectionBudget
    from app.services.workpaper_sync.limits import load_limits
    lim = limits or load_limits(); budget = StreamingProjectionBudget(lim)
    values: dict[str, Any] = {}; rk: list[str] = []
    for identity, row in _iter(payload):
        budget.add_row(ROWS_TABLE_KEY); rk.append(identity)
        for ck, _c, _m, _vt, jp, _l in FIELD_SPECS:
            budget.add_field()
            sk = stable_key_for(ck, identity)
            spec = contract.field_by_stable_key(stable_key_for(ck))
            values[sk] = FieldValue(stable_key=sk, value=_resolve(row, jp), value_type=spec.value_type, mode=spec.mode, row_key=identity)
    return Projection(contract_id=contract.contract_id, semantic_version=contract.semantic_version,
                      document_type=contract.document_type, values=values, row_keys={ROWS_TABLE_KEY: tuple(rk)})
