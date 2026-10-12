# -*- coding: utf-8 -*-
"""D2-9「应收坏账准备测算」—— 检查 entry 的 sibling sheet。

spec: d2-inspection-sync-coverage

═══ 模板几何（openpyxl 直读）═══

受管 sheet = ``应收坏账准备测算D2-9``，50×14（A1:N50）。

三区结构（单项 + 2 个账龄组合）：
* 区一「单项」：表头 R12/R13 / 数据 R14-18 / 小计 R19
* 区二「组合1」：表头 R21/R22 / 数据 R24-29 / 小计 R30
* 区三「组合2」：数据 R32-37 / 小计 R38 / 合计 R39

字段(6列，三区共用)：
  A=债务人/账龄 / B=审定余额 / C=预期损失率 / D=应计提(公式B×C) /
  E=账面余额 / F=差异(公式D-E) / G=计提依据(仅单项) / H=索引号(仅单项)

公式列：D（=B×C）和 F（=D-E）。

本 provider 只受管**单项区**（R14-18）——它与前端 ``useD2Ecl`` 的
``D2-ecl-single-rows`` store 直接对应。组合区的数据来自前端 ``D2-ecl-migration-matrix``
的计算结果，行身份是预设账龄段（非动态行），适合静态区但本轮先不覆盖。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final, Iterator, Mapping, Sequence

from app.services.workpaper_sync.contracts import FieldSpec, SyncContract
from app.services.workpaper_sync.models import SyncDomainError


class StorePayloadError(SyncDomainError):
    error_code = "d29_store_payload_invalid"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量
# ═══════════════════════════════════════════════════════════════════════════

MANAGED_SHEET_D29: Final[str] = "应收坏账准备测算D2-9"
TEMPLATE_ID_D29: Final[str] = "D29"
SHEET_KEY_D29: Final[str] = "d29-managed"

#: 单项区
STORE_ITEM_ID: Final[str] = "D2-ecl-single-rows"
ROWS_TABLE_KEY: Final[str] = "ecl_single_rows"
ROW_IDENTITY_STORE_KEY: Final[str] = "rowId"

HEADER_ROW: Final[int] = 12
FIRST_DATA_ROW: Final[int] = 14
LAST_DATA_ROW: Final[int] = 18
FOOTER_ROW: Final[int] = 19
FOOTER_MARKER: Final[str] = "小计"

MANAGED_LAST_COL: Final[str] = "H"
UUID_COL: Final[str] = "I"
TABLE_NAME: Final[str] = "GT_D29_SINGLE_ROWS"

#: 单项区字段（8 列：6 共用 + G 计提依据 + H 索引号）。
FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    ("debtor_name", "A", "editable", "text", "debtorName", "债务人名称"),
    ("audited_balance", "B", "editable", "amount", "auditedBalance", "审定账面余额"),
    ("expected_loss_rate", "C", "editable", "amount", "expectedLossRate", "预期信用损失率"),
    ("should_provision", "D", "formula", "amount", "shouldProvision", "期末应计提坏账准备"),
    ("actual_balance", "E", "editable", "amount", "actualBalance", "期末坏账准备账面余额"),
    ("difference", "F", "formula", "amount", "difference", "差异"),
    ("basis", "G", "editable", "text", "basis", "计提依据及文件"),
    ("index_ref", "H", "editable", "text", "indexRef", "索引号"),
)

FORMULA_TEMPLATES: Final[Mapping[str, str]] = {
    "D": "=B{r}*C{r}",
    "F": "=D{r}-E{r}",
}

FORMULA_MASK: Final[tuple[str, ...]] = (
    f"D{FIRST_DATA_ROW}:D{LAST_DATA_ROW}",
    f"F{FIRST_DATA_ROW}:F{LAST_DATA_ROW}",
)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 契约 payload
# ═══════════════════════════════════════════════════════════════════════════

def _src(cell: str) -> str:
    return f"源xlsx!{MANAGED_SHEET_D29}!{cell}"

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
            "mode": mode,
            "value_type": vt,
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

def sheet_payload_d29() -> dict[str, Any]:
    from app.services.workpaper_sync.excel_extract import TABLE_SHEET_ANCHOR
    return {
        "sheet_key": SHEET_KEY_D29,
        "excel_name": MANAGED_SHEET_D29,
        "locator": {"anchor": TABLE_SHEET_ANCHOR},
        "tables": [_rows_table_payload()],
    }

# ═══════════════════════════════════════════════════════════════════════════
# 3. Instrumentation spec
# ═══════════════════════════════════════════════════════════════════════════

def instrumentation_spec_d29(*, entry_id: str, template_relative_path: str) -> Any:
    from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec
    return ExcelInstrumentationSpec(
        entry_id=entry_id, template_id=TEMPLATE_ID_D29,
        template_relative_path=template_relative_path,
        managed_sheet=MANAGED_SHEET_D29,
        first_data_row=FIRST_DATA_ROW, last_data_row=LAST_DATA_ROW,
        footer_row=FOOTER_ROW, managed_last_col=MANAGED_LAST_COL,
        uuid_col=UUID_COL, table_name=TABLE_NAME, sheet_key=SHEET_KEY_D29,
    )

# ═══════════════════════════════════════════════════════════════════════════
# 4. Mapping digest
# ═══════════════════════════════════════════════════════════════════════════

def mapping_digest_payload() -> dict[str, Any]:
    return {
        "sheet_key": SHEET_KEY_D29,
        "fields": [{"column_key": ck, "column": col, "mode": m, "value_type": vt, "json_path": jp}
                   for ck, col, m, vt, jp, _ in FIELD_SPECS],
        "formula_templates": dict(FORMULA_TEMPLATES),
    }

def compute_mapping_digest() -> str:
    return hashlib.sha256(json.dumps(mapping_digest_payload(), sort_keys=True, ensure_ascii=False).encode()).hexdigest()

_FROZEN_MAPPING_DIGEST: Final[str] = "dfa1f449c236d961438a28233196fbb241598ce4cf913fa8b27233ca3b0f003e"

def assert_mapping_digest_d29() -> str:
    d = compute_mapping_digest()
    if _FROZEN_MAPPING_DIGEST and d != _FROZEN_MAPPING_DIGEST:
        raise SyncDomainError(f"D2-9 mapping digest drift: {d} != {_FROZEN_MAPPING_DIGEST}")
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

def build_d29_store_projection(payload: str | bytes | Sequence[Any], *, contract: SyncContract, limits: Any | None = None) -> Any:
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
