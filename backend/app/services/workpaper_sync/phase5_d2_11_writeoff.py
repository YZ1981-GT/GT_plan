# -*- coding: utf-8 -*-
"""D2-11「坏账准备转回/核销检查表」—— 检查 entry 的 sibling sheet。

spec: d2-inspection-sync-coverage · Task 3.2

═══ 模板几何（openpyxl 直读）═══

受管 sheet = ``坏账准备转回（收回）、核销检查表D2-11``，29×8（A1:H29）。

**双区结构**（与 D2-3 坏账准备的单 sheet 双区同型）：

* 区一「转回检查」：表头 R12 / 数据 R13-15 / 合计 R16
  字段：单位名称(A) / 转回原因(B) / 收回方式(C) / 原确定坏账准备的依据(D) /
  收回或转回金额(E) / 收回前累计已计提(F) / 合理性分析(G) / 索引号(H)
* 区二「核销检查」：表头 R18 / 数据 R19-21 / 合计 R22
  字段：单位名称(A) / 应收账款性质(B) / 核销金额(C) / 核销原因(D) /
  履行的核销程序(E) / 是否由关联交易产生(F) / 合理性分析(G) / 索引号(H)

两区的表头文本不同但列位置相同（A~H）。数据行**无公式列**。
合计行仅金额列有 SUM：转回区 E16/F16，核销区 C22。

═══ store 映射 ═══

前端 ``useD2WriteoffCheck`` 使用 2 个 store key：
* ``D2-writeoff-reversal-rows``（转回区）
* ``D2-writeoff-writeoff-rows``（核销区）

行身份：``rowId``，前缀 ``wo-``。

前端 ``WriteoffRow.section`` = ``'reversal'`` 或 ``'writeoff'``，用于区分归属。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final, Iterator, Mapping, Sequence

from app.services.workpaper_sync.contracts import FieldSpec, SyncContract
from app.services.workpaper_sync.models import SyncDomainError
from app.services.workpaper_sync.sheet_geometry import col_index, snake


class StorePayloadError(SyncDomainError):
    error_code = "d211_store_payload_invalid"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量
# ═══════════════════════════════════════════════════════════════════════════

MANAGED_SHEET_D211: Final[str] = "坏账准备转回（收回）、核销检查表D2-11"
TEMPLATE_ID_D211: Final[str] = "D211"
SHEET_KEY_D211: Final[str] = "d211-managed"

# ── 区一：转回 ──────────────────────────────────────────────────────────────
STORE_ITEM_ID_REVERSAL: Final[str] = "D2-writeoff-reversal-rows"
ROWS_TABLE_KEY_REVERSAL: Final[str] = "writeoff_reversal_rows"
HEADER_ROW_REVERSAL: Final[int] = 12
FIRST_DATA_ROW_REVERSAL: Final[int] = 13
LAST_DATA_ROW_REVERSAL: Final[int] = 15
FOOTER_ROW_REVERSAL: Final[int] = 16
UUID_COL_REVERSAL: Final[str] = "I"
TABLE_NAME_REVERSAL: Final[str] = "GT_D211_REV_ROWS"

# ── 区二：核销 ──────────────────────────────────────────────────────────────
STORE_ITEM_ID_WRITEOFF: Final[str] = "D2-writeoff-writeoff-rows"
ROWS_TABLE_KEY_WRITEOFF: Final[str] = "writeoff_writeoff_rows"
HEADER_ROW_WRITEOFF: Final[int] = 18
FIRST_DATA_ROW_WRITEOFF: Final[int] = 19
LAST_DATA_ROW_WRITEOFF: Final[int] = 21
FOOTER_ROW_WRITEOFF: Final[int] = 22
UUID_COL_WRITEOFF: Final[str] = "J"
TABLE_NAME_WRITEOFF: Final[str] = "GT_D211_WO_ROWS"

MANAGED_LAST_COL: Final[str] = "H"
FOOTER_MARKER: Final[str] = "合计"
ROW_IDENTITY_STORE_KEY: Final[str] = "rowId"

# ═══════════════════════════════════════════════════════════════════════════
# 2. 字段声明
# ═══════════════════════════════════════════════════════════════════════════

#: 转回区 8 字段（全 editable，无公式列）。
#: 🔴 G「合理性分析」两区同接前端 ``auditorComment``（表单「合理性分析」文本列）；原声明
#:    ``reasonableness`` 前端没有，转回区 G 列两个方向都不通（spec oo-writeback-template-parity-closure
#:    R3 批 B2b）。C / D / F 与核销区 B / F 前端随本批补列。
REVERSAL_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    ("debtor_name", "A", "editable", "text", "debtorName", "单位名称"),
    ("reversal_reason", "B", "editable", "text", "reason", "转回原因"),
    ("recovery_method", "C", "editable", "text", "recoveryMethod", "收回方式"),
    ("original_basis", "D", "editable", "text", "originalBasis", "原确定坏账准备的依据"),
    ("recovery_amount", "E", "editable", "amount", "amount", "收回或转回金额"),
    ("cumulative_provision", "F", "editable", "amount", "cumulativeProvision", "收回或转回前累计已计提坏账准备金额"),
    ("reasonableness", "G", "editable", "text", "auditorComment", "合理性分析"),
    ("index_ref", "H", "editable", "text", "indexRef", "索引号"),
)

#: 核销区 8 字段（全 editable，无公式列）。
WRITEOFF_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    ("debtor_name", "A", "editable", "text", "debtorName", "单位名称"),
    ("receivable_type", "B", "editable", "text", "receivableType", "应收账款性质"),
    ("writeoff_amount", "C", "editable", "amount", "amount", "核销金额"),
    ("writeoff_reason", "D", "editable", "text", "reason", "核销原因"),
    ("writeoff_procedure", "E", "editable", "text", "approvalDoc", "履行的核销程序"),
    ("is_related_party", "F", "editable", "text", "isRelatedParty", "是否由关联交易产生"),
    ("reasonableness", "G", "editable", "text", "auditorComment", "合理性分析"),
    ("index_ref", "H", "editable", "text", "indexRef", "索引号"),
)


# ═══════════════════════════════════════════════════════════════════════════
# 3. 契约 payload
# ═══════════════════════════════════════════════════════════════════════════


def _src(cell: str) -> str:
    return f"源xlsx!{MANAGED_SHEET_D211}!{cell}"


def _stable_key(table_key: str, column_key: str, row_id: str = "{row_uuid}") -> str:
    return f"{table_key}/{row_id}/{column_key}"


def _rows_table_payload(
    *,
    table_key: str,
    header_row: int,
    first_data_row: int,
    last_data_row: int,
    footer_row: int,
    uuid_col: str,
    table_name: str,
    store_item_id: str,
    field_specs: tuple[tuple[str, str, str, str, str, str], ...],
) -> dict[str, Any]:
    fields = []
    for ck, col, mode, vt, jp, label in field_specs:
        fields.append({
            "stable_field_key": _stable_key(table_key, ck),
            "json_pointer": f"/rows/{{row_uuid}}/{jp}",
            "column_key": ck,
            "cell": {"column": col, "row_from": "row_identity"},
            "mode": mode,
            "value_type": vt,
            "source_ref": _src(f"{col}{first_data_row}"),
            "header_source_ref": _src(f"{col}{header_row}"),
            "store_item_id": store_item_id,
            "header_text": label,
        })
    return {
        "table_key": table_key,
        "anchor": f"A{header_row}",
        "header_rows": 1,
        "row_identity": {"kind": "field", "json_pointer": f"/rows/*/{ROW_IDENTITY_STORE_KEY}"},
        "delete_policy": "tombstone",
        "uuid_col": uuid_col,
        "footer_anchor": {
            "marker": FOOTER_MARKER,
            "search_column": "A",
            "carries_total_formula": True,
        },
        "formula_mask": [],
        "fields": fields,
    }


def sheet_payload_d211() -> dict[str, Any]:
    from app.services.workpaper_sync.excel_extract import TABLE_SHEET_ANCHOR

    return {
        "sheet_key": SHEET_KEY_D211,
        "excel_name": MANAGED_SHEET_D211,
        "locator": {"anchor": TABLE_SHEET_ANCHOR},
        "tables": [
            _rows_table_payload(
                table_key=ROWS_TABLE_KEY_REVERSAL,
                header_row=HEADER_ROW_REVERSAL,
                first_data_row=FIRST_DATA_ROW_REVERSAL,
                last_data_row=LAST_DATA_ROW_REVERSAL,
                footer_row=FOOTER_ROW_REVERSAL,
                uuid_col=UUID_COL_REVERSAL,
                table_name=TABLE_NAME_REVERSAL,
                store_item_id=STORE_ITEM_ID_REVERSAL,
                field_specs=REVERSAL_FIELD_SPECS,
            ),
            _rows_table_payload(
                table_key=ROWS_TABLE_KEY_WRITEOFF,
                header_row=HEADER_ROW_WRITEOFF,
                first_data_row=FIRST_DATA_ROW_WRITEOFF,
                last_data_row=LAST_DATA_ROW_WRITEOFF,
                footer_row=FOOTER_ROW_WRITEOFF,
                uuid_col=UUID_COL_WRITEOFF,
                table_name=TABLE_NAME_WRITEOFF,
                store_item_id=STORE_ITEM_ID_WRITEOFF,
                field_specs=WRITEOFF_FIELD_SPECS,
            ),
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════
# 4. Instrumentation spec
# ═══════════════════════════════════════════════════════════════════════════


def instrumentation_spec_d211(*, entry_id: str, template_relative_path: str) -> tuple:
    """D2-11 双区 instrumentation spec（同 sheet，转回/核销各自行段+UUID 列）。"""
    from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec

    reversal = ExcelInstrumentationSpec(
        entry_id=entry_id,
        template_id=TEMPLATE_ID_D211 + "REV",
        template_relative_path=template_relative_path,
        managed_sheet=MANAGED_SHEET_D211,
        first_data_row=FIRST_DATA_ROW_REVERSAL,
        last_data_row=LAST_DATA_ROW_REVERSAL,
        footer_row=FOOTER_ROW_REVERSAL,
        managed_last_col=MANAGED_LAST_COL,
        uuid_col=UUID_COL_REVERSAL,
        table_name=TABLE_NAME_REVERSAL,
        sheet_key=SHEET_KEY_D211,
    )
    writeoff = ExcelInstrumentationSpec(
        entry_id=entry_id,
        template_id=TEMPLATE_ID_D211 + "WO",
        template_relative_path=template_relative_path,
        managed_sheet=MANAGED_SHEET_D211,
        first_data_row=FIRST_DATA_ROW_WRITEOFF,
        last_data_row=LAST_DATA_ROW_WRITEOFF,
        footer_row=FOOTER_ROW_WRITEOFF,
        managed_last_col=MANAGED_LAST_COL,
        uuid_col=UUID_COL_WRITEOFF,
        table_name=TABLE_NAME_WRITEOFF,
        sheet_key=SHEET_KEY_D211,
    )
    return (reversal, writeoff)


# ═══════════════════════════════════════════════════════════════════════════
# 5. Mapping digest
# ═══════════════════════════════════════════════════════════════════════════


def mapping_digest_payload() -> dict[str, Any]:
    return {
        "sheet_key": SHEET_KEY_D211,
        "regions": [
            {
                "table_key": ROWS_TABLE_KEY_REVERSAL,
                "fields": [
                    {"column_key": ck, "column": col, "mode": m, "value_type": vt, "json_path": jp}
                    for ck, col, m, vt, jp, _ in REVERSAL_FIELD_SPECS
                ],
            },
            {
                "table_key": ROWS_TABLE_KEY_WRITEOFF,
                "fields": [
                    {"column_key": ck, "column": col, "mode": m, "value_type": vt, "json_path": jp}
                    for ck, col, m, vt, jp, _ in WRITEOFF_FIELD_SPECS
                ],
            },
        ],
    }


def compute_mapping_digest() -> str:
    return hashlib.sha256(
        json.dumps(mapping_digest_payload(), sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


#: 2026-10-28 批 B2b：转回区 G 改接 auditorComment（原 72364e49…）。
_FROZEN_MAPPING_DIGEST: Final[str] = "ad8144c23a8e8ba14df51254e47d22dae0c1498912ef2be9af9e00579e9c55dd"


def assert_mapping_digest_d211() -> str:
    d = compute_mapping_digest()
    if _FROZEN_MAPPING_DIGEST and d != _FROZEN_MAPPING_DIGEST:
        raise SyncDomainError(f"D2-11 mapping digest drift: {d} != {_FROZEN_MAPPING_DIGEST}")
    return d


# ═══════════════════════════════════════════════════════════════════════════
# 6. Store projection
# ═══════════════════════════════════════════════════════════════════════════


def _iter_store_rows(
    payload: str | bytes | Sequence[Any],
    *,
    store_item_id: str,
) -> Iterator[tuple[str, Mapping[str, Any]]]:
    if isinstance(payload, (str, bytes, bytearray)):
        text = payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else payload
        try:
            rows: Any = json.loads(text)
        except ValueError as exc:
            raise StorePayloadError(f"{store_item_id} JSON 非法: {exc}") from exc
    else:
        rows = payload
    if not isinstance(rows, list):
        raise StorePayloadError(f"{store_item_id} 必须是数组，实得 {type(rows).__name__}")
    seen: set[str] = set()
    for i, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise StorePayloadError(f"{store_item_id} 第 {i} 项不是对象")
        rid = row.get(ROW_IDENTITY_STORE_KEY)
        if not isinstance(rid, str) or not rid.strip():
            raise StorePayloadError(f"{store_item_id} 第 {i} 行缺 {ROW_IDENTITY_STORE_KEY}")
        rid = rid.strip()
        if rid in seen:
            raise StorePayloadError(f"{store_item_id} 重复行身份 {rid!r}")
        seen.add(rid)
        yield rid, row


def _resolve(row: Mapping[str, Any], jp: str) -> Any:
    cur: Any = row
    for seg in jp.split("/"):
        if not isinstance(cur, Mapping):
            return None
        cur = cur.get(seg)
    return cur


def _build_region_projection(
    payload: str | bytes | Sequence[Any],
    *,
    table_key: str,
    store_item_id: str,
    field_specs: tuple[tuple[str, str, str, str, str, str], ...],
    contract: SyncContract,
    limits: Any | None = None,
) -> tuple[dict[str, Any], dict[str, tuple[str, ...]]]:
    from app.services.workpaper_sync.adapters.base import FieldValue
    from app.services.workpaper_sync.excel_extract import StreamingProjectionBudget
    from app.services.workpaper_sync.limits import load_limits

    lim = limits or load_limits()
    budget = StreamingProjectionBudget(lim)
    values: dict[str, Any] = {}
    row_keys: list[str] = []
    for identity, row in _iter_store_rows(payload, store_item_id=store_item_id):
        budget.add_row(table_key)
        row_keys.append(identity)
        for ck, _col, _m, _vt, jp, _label in field_specs:
            budget.add_field()
            sk = _stable_key(table_key, ck, identity)
            spec = contract.field_by_stable_key(_stable_key(table_key, ck))
            values[sk] = FieldValue(
                stable_key=sk,
                value=_resolve(row, jp),
                value_type=spec.value_type,
                mode=spec.mode,
                row_key=identity,
            )
    return values, {table_key: tuple(row_keys)}


def build_d211_store_projection(
    payloads: Mapping[str, Any],
    *,
    contract: SyncContract,
    limits: Any | None = None,
) -> Any:
    from app.services.workpaper_sync.adapters.base import Projection

    rev_payload = payloads.get(STORE_ITEM_ID_REVERSAL, "[]")
    wo_payload = payloads.get(STORE_ITEM_ID_WRITEOFF, "[]")

    rev_vals, rev_keys = _build_region_projection(
        rev_payload, table_key=ROWS_TABLE_KEY_REVERSAL,
        store_item_id=STORE_ITEM_ID_REVERSAL,
        field_specs=REVERSAL_FIELD_SPECS, contract=contract, limits=limits,
    )
    wo_vals, wo_keys = _build_region_projection(
        wo_payload, table_key=ROWS_TABLE_KEY_WRITEOFF,
        store_item_id=STORE_ITEM_ID_WRITEOFF,
        field_specs=WRITEOFF_FIELD_SPECS, contract=contract, limits=limits,
    )

    all_values = {**rev_vals, **wo_vals}
    all_row_keys = {**rev_keys, **wo_keys}

    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=all_values,
        row_keys=all_row_keys,
    )
