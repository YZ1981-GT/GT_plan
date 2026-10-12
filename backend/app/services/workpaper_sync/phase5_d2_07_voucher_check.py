# -*- coding: utf-8 -*-
"""D2-7「应收账款检查表」—— 检查 entry 的 sibling sheet。

spec: d2-inspection-sync-coverage · Task 3.4

═══ 模板几何 ═══

受管 sheet = ``应收账款检查表D2-7``，52×17（A1:Q52）。

**双区双级表头**：
* 区一「本期增减变动检查」：
  - 两级表头 R14(组)/R15(叶)
  - 数据 R16~R30（15 行骨架）
  - 合计 R31：G31=SUM(G16:G30)、H31=SUM(H16:H30)
* 区二「期后收款、调整检查」：
  - 两级表头 R33(组)/R34(叶)——与区一结构完全相同
  - 数据 R35~R42（8 行骨架）
  - 合计 R43：G43=SUM(G35:G42)、H43=SUM(H35:H42)

数据行**无公式列**。公式仅在合计行（SUM）和审计说明区（跨 sheet 引用 D2-2）。

═══ 字段（17 列，两级表头）═══

| 列 | 组标题(R14) | 叶标题(R15) | 前端字段 |
|----|-----------|-----------|---------|
| A | 客户名称 | — | customerName |
| B | 记账凭证(组) | 日期 | voucherDate |
| C | | 凭证编号 | voucherNo |
| D | | 业务内容 | businessContent |
| E | | 对方科目 | counterpartAccount |
| F | | 对方明细科目 | counterpartDetail |
| G | | 借方金额 | debitAmount |
| H | | 贷方金额 | creditAmount |
| I | 支持性文件 | — | supportingDoc |
| J | 核对内容(组) | 1 | check1 |
| K | | 2 | check2 |
| L | | 3 | check3 |
| M | | 4 | check4 |
| N | | 5 | check5 |
| O | 索引号 | — | indexRef |
| P | 是否异常 | — | isAbnormal |
| Q | 备注说明 | — | remark |

═══ store 映射 ═══

前端 ``useD2VoucherCheckEnhanced``：
* ``D2-vc-current-rows``（本期区）
* ``D2-vc-post-rows``（期后区）
行身份：``rowId``，前缀 ``vcr-``。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final, Iterator, Mapping, Sequence

from app.services.workpaper_sync.contracts import FieldSpec, SyncContract
from app.services.workpaper_sync.models import SyncDomainError


class StorePayloadError(SyncDomainError):
    error_code = "d27_store_payload_invalid"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量
# ═══════════════════════════════════════════════════════════════════════════

MANAGED_SHEET_D27: Final[str] = "应收账款检查表D2-7"
TEMPLATE_ID_D27: Final[str] = "D27"
SHEET_KEY_D27: Final[str] = "d27-managed"

#: 两级表头行。
HEADER_GROUP_ROW: Final[int] = 14
HEADER_LEAF_ROW: Final[int] = 15

# ── 区一：本期变动检查 ──────────────────────────────────────────────────────
STORE_ITEM_ID_CURRENT: Final[str] = "D2-vc-current-rows"
ROWS_TABLE_KEY_CURRENT: Final[str] = "vc_current_rows"
FIRST_DATA_ROW_CURRENT: Final[int] = 16
LAST_DATA_ROW_CURRENT: Final[int] = 30
FOOTER_ROW_CURRENT: Final[int] = 31
UUID_COL_CURRENT: Final[str] = "R"
TABLE_NAME_CURRENT: Final[str] = "GT_D27_CUR_ROWS"

# ── 区二：期后收款检查 ──────────────────────────────────────────────────────
STORE_ITEM_ID_POST: Final[str] = "D2-vc-post-rows"
ROWS_TABLE_KEY_POST: Final[str] = "vc_post_rows"
#: 区二有自己的两级表头 R33/R34。
HEADER_GROUP_ROW_POST: Final[int] = 33
HEADER_LEAF_ROW_POST: Final[int] = 34
FIRST_DATA_ROW_POST: Final[int] = 35
LAST_DATA_ROW_POST: Final[int] = 42
FOOTER_ROW_POST: Final[int] = 43
UUID_COL_POST: Final[str] = "S"
TABLE_NAME_POST: Final[str] = "GT_D27_POST_ROWS"

MANAGED_LAST_COL: Final[str] = "Q"
FOOTER_MARKER: Final[str] = "合计"
ROW_IDENTITY_STORE_KEY: Final[str] = "rowId"

# ═══════════════════════════════════════════════════════════════════════════
# 2. 字段声明（17 列，两区共用同一列布局）
# ═══════════════════════════════════════════════════════════════════════════

#: (column_key, column, mode, value_type, json_path, header_text)
FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    ("customer_name", "A", "editable", "text", "customerName", "客户名称"),
    ("voucher_date", "B", "editable", "text", "voucherDate", "日期"),
    ("voucher_no", "C", "editable", "text", "voucherNo", "凭证编号"),
    ("business_content", "D", "editable", "text", "businessContent", "业务内容"),
    ("counterpart_account", "E", "editable", "text", "counterpartAccount", "对方科目"),
    ("counterpart_detail", "F", "editable", "text", "counterpartDetail", "对方明细科目"),
    ("debit_amount", "G", "editable", "amount", "debitAmount", "借方金额"),
    ("credit_amount", "H", "editable", "amount", "creditAmount", "贷方金额"),
    ("supporting_doc", "I", "editable", "text", "supportingDoc", "支持性文件"),
    ("check1", "J", "editable", "text", "check1", "核对1"),
    ("check2", "K", "editable", "text", "check2", "核对2"),
    ("check3", "L", "editable", "text", "check3", "核对3"),
    ("check4", "M", "editable", "text", "check4", "核对4"),
    ("check5", "N", "editable", "text", "check5", "核对5"),
    ("index_ref", "O", "editable", "text", "indexRef", "索引号"),
    ("is_abnormal", "P", "editable", "text", "isAbnormal", "是否异常"),
    ("remark", "Q", "editable", "text", "remark", "备注说明"),
)


# ═══════════════════════════════════════════════════════════════════════════
# 3. 契约 payload
# ═══════════════════════════════════════════════════════════════════════════


def _src(cell: str) -> str:
    return f"源xlsx!{MANAGED_SHEET_D27}!{cell}"


def _stable_key(table_key: str, ck: str, rid: str = "{row_uuid}") -> str:
    return f"{table_key}/{rid}/{ck}"


def _rows_table_payload(
    *, table_key: str, header_row: int, first_data_row: int, last_data_row: int,
    footer_row: int, uuid_col: str, table_name: str, store_item_id: str,
) -> dict[str, Any]:
    fields = []
    for ck, col, mode, vt, jp, label in FIELD_SPECS:
        fields.append({
            "stable_field_key": _stable_key(table_key, ck),
            "json_pointer": f"/rows/{{row_uuid}}/{jp}",
            "column_key": ck,
            "cell": {"column": col, "row_from": "row_identity"},
            "mode": mode,
            "value_type": vt,
            "source_ref": _src(f"{col}{first_data_row}"),
            "header_source_ref": _src(f"{col}{header_row + 1}"),
            "store_item_id": store_item_id,
            "header_text": label,
        })
    return {
        "table_key": table_key,
        "anchor": f"A{header_row}",
        "header_rows": 2,
        "row_identity": {"kind": "field", "json_pointer": f"/rows/*/{ROW_IDENTITY_STORE_KEY}"},
        "delete_policy": "tombstone",
        "footer_anchor": {
            "marker": FOOTER_MARKER,
            "search_column": "A",
            "carries_total_formula": True,
        },
        "formula_mask": [],
        "fields": fields,
    }


def sheet_payload_d27() -> dict[str, Any]:
    from app.services.workpaper_sync.excel_extract import TABLE_SHEET_ANCHOR

    return {
        "sheet_key": SHEET_KEY_D27,
        "excel_name": MANAGED_SHEET_D27,
        "locator": {"anchor": TABLE_SHEET_ANCHOR},
        "tables": [
            _rows_table_payload(
                table_key=ROWS_TABLE_KEY_CURRENT,
                header_row=HEADER_GROUP_ROW,
                first_data_row=FIRST_DATA_ROW_CURRENT,
                last_data_row=LAST_DATA_ROW_CURRENT,
                footer_row=FOOTER_ROW_CURRENT,
                uuid_col=UUID_COL_CURRENT,
                table_name=TABLE_NAME_CURRENT,
                store_item_id=STORE_ITEM_ID_CURRENT,
            ),
            _rows_table_payload(
                table_key=ROWS_TABLE_KEY_POST,
                header_row=HEADER_GROUP_ROW_POST,
                first_data_row=FIRST_DATA_ROW_POST,
                last_data_row=LAST_DATA_ROW_POST,
                footer_row=FOOTER_ROW_POST,
                uuid_col=UUID_COL_POST,
                table_name=TABLE_NAME_POST,
                store_item_id=STORE_ITEM_ID_POST,
            ),
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════
# 4. Instrumentation spec
# ═══════════════════════════════════════════════════════════════════════════


def instrumentation_spec_d27(*, entry_id: str, template_relative_path: str) -> Any:
    from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec

    return ExcelInstrumentationSpec(
        entry_id=entry_id,
        template_id=TEMPLATE_ID_D27,
        template_relative_path=template_relative_path,
        managed_sheet=MANAGED_SHEET_D27,
        first_data_row=FIRST_DATA_ROW_CURRENT,
        last_data_row=LAST_DATA_ROW_CURRENT,
        footer_row=FOOTER_ROW_CURRENT,
        managed_last_col=MANAGED_LAST_COL,
        uuid_col=UUID_COL_CURRENT,
        table_name=TABLE_NAME_CURRENT,
        sheet_key=SHEET_KEY_D27,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 5. Mapping digest
# ═══════════════════════════════════════════════════════════════════════════


def mapping_digest_payload() -> dict[str, Any]:
    return {
        "sheet_key": SHEET_KEY_D27,
        "regions": [
            {"table_key": ROWS_TABLE_KEY_CURRENT, "first": FIRST_DATA_ROW_CURRENT, "last": LAST_DATA_ROW_CURRENT},
            {"table_key": ROWS_TABLE_KEY_POST, "first": FIRST_DATA_ROW_POST, "last": LAST_DATA_ROW_POST},
        ],
        "fields": [
            {"column_key": ck, "column": col, "mode": m, "value_type": vt, "json_path": jp}
            for ck, col, m, vt, jp, _ in FIELD_SPECS
        ],
    }


def compute_mapping_digest() -> str:
    return hashlib.sha256(
        json.dumps(mapping_digest_payload(), sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


_FROZEN_MAPPING_DIGEST: Final[str] = "171c69eac14a5c314f4dffc4b5622a70eac0ad98e690735447fe1b0b3170038d"


def assert_mapping_digest_d27() -> str:
    d = compute_mapping_digest()
    if _FROZEN_MAPPING_DIGEST and d != _FROZEN_MAPPING_DIGEST:
        raise SyncDomainError(f"D2-7 mapping digest drift: {d} != {_FROZEN_MAPPING_DIGEST}")
    return d


# ═══════════════════════════════════════════════════════════════════════════
# 6. Store projection
# ═══════════════════════════════════════════════════════════════════════════


def _iter_rows(payload: str | bytes | Sequence[Any], *, sid: str) -> Iterator[tuple[str, Mapping[str, Any]]]:
    if isinstance(payload, (str, bytes, bytearray)):
        text = payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else payload
        try:
            rows: Any = json.loads(text)
        except ValueError as exc:
            raise StorePayloadError(f"{sid} JSON: {exc}") from exc
    else:
        rows = payload
    if not isinstance(rows, list):
        raise StorePayloadError(f"{sid} 必须是数组")
    seen: set[str] = set()
    for i, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise StorePayloadError(f"{sid}[{i}] 不是对象")
        rid = row.get(ROW_IDENTITY_STORE_KEY)
        if not isinstance(rid, str) or not rid.strip():
            raise StorePayloadError(f"{sid}[{i}] 缺 {ROW_IDENTITY_STORE_KEY}")
        rid = rid.strip()
        if rid in seen:
            raise StorePayloadError(f"{sid} 重复 {rid!r}")
        seen.add(rid)
        yield rid, row


def _resolve(row: Mapping[str, Any], jp: str) -> Any:
    cur: Any = row
    for seg in jp.split("/"):
        if not isinstance(cur, Mapping):
            return None
        cur = cur.get(seg)
    return cur


def _region_proj(
    payload: str | bytes | Sequence[Any], *, table_key: str, sid: str,
    contract: SyncContract, limits: Any | None = None,
) -> tuple[dict[str, Any], dict[str, tuple[str, ...]]]:
    from app.services.workpaper_sync.adapters.base import FieldValue
    from app.services.workpaper_sync.excel_extract import StreamingProjectionBudget
    from app.services.workpaper_sync.limits import load_limits

    lim = limits or load_limits()
    budget = StreamingProjectionBudget(lim)
    values: dict[str, Any] = {}
    rk: list[str] = []
    for identity, row in _iter_rows(payload, sid=sid):
        budget.add_row(table_key)
        rk.append(identity)
        for ck, _c, _m, _vt, jp, _l in FIELD_SPECS:
            budget.add_field()
            sk = _stable_key(table_key, ck, identity)
            spec = contract.field_by_stable_key(_stable_key(table_key, ck))
            values[sk] = FieldValue(
                stable_key=sk, value=_resolve(row, jp),
                value_type=spec.value_type, mode=spec.mode, row_key=identity,
            )
    return values, {table_key: tuple(rk)}


def build_d27_store_projection(
    payloads: Mapping[str, Any], *, contract: SyncContract, limits: Any | None = None,
) -> Any:
    from app.services.workpaper_sync.adapters.base import Projection

    cur_v, cur_k = _region_proj(
        payloads.get(STORE_ITEM_ID_CURRENT, "[]"),
        table_key=ROWS_TABLE_KEY_CURRENT, sid=STORE_ITEM_ID_CURRENT,
        contract=contract, limits=limits,
    )
    post_v, post_k = _region_proj(
        payloads.get(STORE_ITEM_ID_POST, "[]"),
        table_key=ROWS_TABLE_KEY_POST, sid=STORE_ITEM_ID_POST,
        contract=contract, limits=limits,
    )
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values={**cur_v, **post_v},
        row_keys={**cur_k, **post_k},
    )
