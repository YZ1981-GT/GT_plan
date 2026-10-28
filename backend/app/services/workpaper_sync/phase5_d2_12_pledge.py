# -*- coding: utf-8 -*-
"""D2-12「应收账款质押出售情况检查表」—— 检查 entry 的 sibling sheet。

spec: d2-inspection-sync-coverage · Task 3.3

═══ 模板几何 ═══

受管 sheet = ``应收账款质押出售情况检查表D2-12``，43×12（A1:L43）。

**双区 + 差异表结构**：
* 区一「质押」：表头 R15 / 数据 R16-18 / 合计 R19
  字段(9列)：客户名称(A) / 期末余额(B) / 质押金额(C) / 质权人(D) / 质押原因(E) /
  质押条件(F) / 质押期限(G) / 质押协议(H) / 索引号(I)
* 区二「出售」：表头 R21 / 数据 R22-24（空骨架）/ 无合计行
  字段(11列)：客户名称(A) / 出售前余额(B) / 出售前坏账准备(C) / 出售时间(D) /
  出售金额(E) / 受让人(F) / 出售原因(G) / 合同条款(H) / 终止确认分析(I) /
  转移方式(J) / 索引号(K)
* 差异表（R27~R32）：5 行差异公式 E=D-C（审计说明区）→ 不作为受管行表

本 provider 受管质押区（区一）。出售区较复杂（11列且无明确数据区边界），
暂作为后续扩容。差异表不受管（属于审计说明区域）。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final, Iterator, Mapping, Sequence

from app.services.workpaper_sync.contracts import FieldSpec, SyncContract
from app.services.workpaper_sync.models import SyncDomainError


class StorePayloadError(SyncDomainError):
    error_code = "d212_store_payload_invalid"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量
# ═══════════════════════════════════════════════════════════════════════════

MANAGED_SHEET_D212: Final[str] = "应收账款质押出售情况检查表D2-12"
TEMPLATE_ID_D212: Final[str] = "D212"
SHEET_KEY_D212: Final[str] = "d212-managed"

#: 质押区
STORE_ITEM_ID_PLEDGE: Final[str] = "D2-pledge-rows"
ROWS_TABLE_KEY_PLEDGE: Final[str] = "pledge_rows"
HEADER_ROW_PLEDGE: Final[int] = 15
FIRST_DATA_ROW_PLEDGE: Final[int] = 16
LAST_DATA_ROW_PLEDGE: Final[int] = 18
FOOTER_ROW_PLEDGE: Final[int] = 19
UUID_COL_PLEDGE: Final[str] = "J"
TABLE_NAME_PLEDGE: Final[str] = "GT_D212_PL_ROWS"
MANAGED_LAST_COL_PLEDGE: Final[str] = "I"

FOOTER_MARKER: Final[str] = "合计"
ROW_IDENTITY_STORE_KEY: Final[str] = "rowId"

#: 质押区字段（9 列，全 editable，无公式）。
#: 🔴 B「期末余额」原与 C「质押金额」同接 ``pledgeAmount``（两列一个键：HTML → OO 期末余额恒等于质押
#:    金额，OO 侧两格改得不一样时回写互相覆盖）⇒ 改接前端新增的 ``endBalance``；F 质押条件 / H 质押协议
#:    前端随本批补列（spec oo-writeback-template-parity-closure R3 批 B2b，守卫
#:    ``test_contract_no_duplicate_field_binding``）。
PLEDGE_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    ("debtor_name", "A", "editable", "text", "debtorName", "客户名称"),
    ("end_balance", "B", "editable", "amount", "endBalance", "期末余额"),
    ("pledge_amount", "C", "editable", "amount", "pledgeAmount", "质押金额"),
    ("pledgee", "D", "editable", "text", "pledgee", "质权人"),
    ("pledge_reason", "E", "editable", "text", "pledgePurpose", "质押原因"),
    ("pledge_condition", "F", "editable", "text", "pledgeCondition", "质押条件"),
    ("pledge_period", "G", "editable", "text", "expiryDate", "质押期限"),
    ("pledge_agreement", "H", "editable", "text", "pledgeAgreement", "质押协议"),
    ("index_ref", "I", "editable", "text", "indexRef", "索引号"),
)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 契约 payload
# ═══════════════════════════════════════════════════════════════════════════


def _src(cell: str) -> str:
    return f"源xlsx!{MANAGED_SHEET_D212}!{cell}"


def stable_key_for(column_key: str, row_id: str = "{row_uuid}") -> str:
    return f"{ROWS_TABLE_KEY_PLEDGE}/{row_id}/{column_key}"


def _rows_table_payload() -> dict[str, Any]:
    fields = []
    for ck, col, mode, vt, jp, label in PLEDGE_FIELD_SPECS:
        fields.append({
            "stable_field_key": stable_key_for(ck),
            "json_pointer": f"/rows/{{row_uuid}}/{jp}",
            "column_key": ck,
            "cell": {"column": col, "row_from": "row_identity"},
            "mode": mode,
            "value_type": vt,
            "source_ref": _src(f"{col}{FIRST_DATA_ROW_PLEDGE}"),
            "header_source_ref": _src(f"{col}{HEADER_ROW_PLEDGE}"),
            "store_item_id": STORE_ITEM_ID_PLEDGE,
            "header_text": label,
        })
    return {
        "table_key": ROWS_TABLE_KEY_PLEDGE,
        "anchor": f"A{HEADER_ROW_PLEDGE}",
        "header_rows": 1,
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


def sheet_payload_d212() -> dict[str, Any]:
    from app.services.workpaper_sync.excel_extract import TABLE_SHEET_ANCHOR

    return {
        "sheet_key": SHEET_KEY_D212,
        "excel_name": MANAGED_SHEET_D212,
        "locator": {"anchor": TABLE_SHEET_ANCHOR},
        "tables": [_rows_table_payload()],
    }


# ═══════════════════════════════════════════════════════════════════════════
# 3. Instrumentation spec
# ═══════════════════════════════════════════════════════════════════════════


def instrumentation_spec_d212(*, entry_id: str, template_relative_path: str) -> Any:
    from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec

    return ExcelInstrumentationSpec(
        entry_id=entry_id,
        template_id=TEMPLATE_ID_D212,
        template_relative_path=template_relative_path,
        managed_sheet=MANAGED_SHEET_D212,
        first_data_row=FIRST_DATA_ROW_PLEDGE,
        last_data_row=LAST_DATA_ROW_PLEDGE,
        footer_row=FOOTER_ROW_PLEDGE,
        managed_last_col=MANAGED_LAST_COL_PLEDGE,
        uuid_col=UUID_COL_PLEDGE,
        table_name=TABLE_NAME_PLEDGE,
        sheet_key=SHEET_KEY_D212,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 4. Mapping digest
# ═══════════════════════════════════════════════════════════════════════════


def mapping_digest_payload() -> dict[str, Any]:
    return {
        "sheet_key": SHEET_KEY_D212,
        "fields": [
            {"column_key": ck, "column": col, "mode": m, "value_type": vt, "json_path": jp}
            for ck, col, m, vt, jp, _ in PLEDGE_FIELD_SPECS
        ],
    }


def compute_mapping_digest() -> str:
    return hashlib.sha256(
        json.dumps(mapping_digest_payload(), sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


#: 2026-10-28 批 B2b：B 期末余额改接 endBalance（原与 C 同接 pledgeAmount，097318c5…）。
_FROZEN_MAPPING_DIGEST: Final[str] = "5a146f1d3fe8d7f4085722a727611148f3584bc0fea40ab654d97c9e111ddb2d"


def assert_mapping_digest_d212() -> str:
    d = compute_mapping_digest()
    if _FROZEN_MAPPING_DIGEST and d != _FROZEN_MAPPING_DIGEST:
        raise SyncDomainError(f"D2-12 mapping digest drift: {d} != {_FROZEN_MAPPING_DIGEST}")
    return d


# ═══════════════════════════════════════════════════════════════════════════
# 5. Store projection
# ═══════════════════════════════════════════════════════════════════════════


def iter_store_rows(payload: str | bytes | Sequence[Any]) -> Iterator[tuple[str, Mapping[str, Any]]]:
    if isinstance(payload, (str, bytes, bytearray)):
        text = payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else payload
        try:
            rows: Any = json.loads(text)
        except ValueError as exc:
            raise StorePayloadError(f"{STORE_ITEM_ID_PLEDGE} JSON 非法: {exc}") from exc
    else:
        rows = payload
    if not isinstance(rows, list):
        raise StorePayloadError(f"{STORE_ITEM_ID_PLEDGE} 必须是数组")
    seen: set[str] = set()
    for i, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise StorePayloadError(f"{STORE_ITEM_ID_PLEDGE} 第 {i} 项不是对象")
        rid = row.get(ROW_IDENTITY_STORE_KEY)
        if not isinstance(rid, str) or not rid.strip():
            raise StorePayloadError(f"{STORE_ITEM_ID_PLEDGE} 第 {i} 行缺 {ROW_IDENTITY_STORE_KEY}")
        rid = rid.strip()
        if rid in seen:
            raise StorePayloadError(f"{STORE_ITEM_ID_PLEDGE} 重复行身份 {rid!r}")
        seen.add(rid)
        yield rid, row


def _resolve(row: Mapping[str, Any], jp: str) -> Any:
    cur: Any = row
    for seg in jp.split("/"):
        if not isinstance(cur, Mapping):
            return None
        cur = cur.get(seg)
    return cur


def build_d212_store_projection(
    payload: str | bytes | Sequence[Any],
    *,
    contract: SyncContract,
    limits: Any | None = None,
) -> Any:
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection
    from app.services.workpaper_sync.excel_extract import StreamingProjectionBudget
    from app.services.workpaper_sync.limits import load_limits

    lim = limits or load_limits()
    budget = StreamingProjectionBudget(lim)
    values: dict[str, Any] = {}
    row_keys: list[str] = []
    for identity, row in iter_store_rows(payload):
        budget.add_row(ROWS_TABLE_KEY_PLEDGE)
        row_keys.append(identity)
        for ck, _col, _m, _vt, jp, _label in PLEDGE_FIELD_SPECS:
            budget.add_field()
            sk = stable_key_for(ck, identity)
            spec = contract.field_by_stable_key(stable_key_for(ck))
            values[sk] = FieldValue(
                stable_key=sk,
                value=_resolve(row, jp),
                value_type=spec.value_type,
                mode=spec.mode,
                row_key=identity,
            )
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys={ROWS_TABLE_KEY_PLEDGE: tuple(row_keys)},
    )
