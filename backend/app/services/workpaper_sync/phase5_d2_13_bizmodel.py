# -*- coding: utf-8 -*-
"""D2-13「应收账款业务模式分析」—— 检查 entry 的 sibling sheet。

spec: d2-inspection-sync-coverage · Task 3.2

═══ 模板几何 ═══

受管 sheet = ``应收账款业务模式分析D2-13``，30×5（A1:E30）。

**双结构**：
* (一) 业务模式分组表（行12表头/13-15数据，无合计行）
  字段(5列)：组合名称(A) / 管理业务模式(B) / 具体依据(C) / 索引号(D) / 备注(E)
* (二) 分类判断矩阵（行17-23，含复杂 IF 公式）
  行 17 是列表头（B17~D17 = 三个组合名称）
  行 18-21 是判断问题（A 列问题，B/C/D 列答案「是/否」）
  行 22 是公式列 =IF(AND(...),...) 确定业务模式
  行 23 是公式列 =IF(B22=...) 确定报表项目

分类判断矩阵是**列向**结构（每列一个组合，不是行向），
且含复杂嵌套 IF 公式 → 作为 formula_mask 整体保护。

本 provider 只受管分组表（行 12~15），判断矩阵留在 OO 内直接编辑。

═══ store 映射 ═══

前端 ``useD2BizModel``：
* ``D2-bizmodel-judgments``（固定问题列表，questionId 作身份）→ 对应矩阵区
* ``D2-bizmodel-groups``（动态行，rowId=bm-*）→ 对应分组表区
* note + conclusion

本 provider 只接管 ``D2-bizmodel-groups``（分组表），judgments 走 HTML-only。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final, Iterator, Mapping, Sequence

from app.services.workpaper_sync.contracts import FieldSpec, SyncContract
from app.services.workpaper_sync.models import SyncDomainError


class StorePayloadError(SyncDomainError):
    error_code = "d213_store_payload_invalid"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量
# ═══════════════════════════════════════════════════════════════════════════

MANAGED_SHEET_D213: Final[str] = "应收账款业务模式分析D2-13"
TEMPLATE_ID_D213: Final[str] = "D213"
SHEET_KEY_D213: Final[str] = "d213-managed"

STORE_ITEM_ID: Final[str] = "D2-bizmodel-groups"
ROWS_TABLE_KEY: Final[str] = "bizmodel_group_rows"
ROW_IDENTITY_STORE_KEY: Final[str] = "rowId"

HEADER_ROW: Final[int] = 12
FIRST_DATA_ROW: Final[int] = 13
LAST_DATA_ROW: Final[int] = 15
#: 分组表没有合计行。行 16 = "(二) 应收账款分类判断"，不是 footer。
#: 但 ExcelInstrumentationSpec 要求 footer_row > last_data_row。
#: 把「(二)」标题行当作 footer locator 占位：它在数据区之后且不是数据行。
FOOTER_ROW: Final[int] = 16
FOOTER_MARKER: Final[str] = "（二）应收账款分类判断"

MANAGED_LAST_COL: Final[str] = "E"
UUID_COL: Final[str] = "F"
TABLE_NAME: Final[str] = "GT_D213_GRP_ROWS"

#: 分组表字段（5 列，全 editable，无公式）。
FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    ("group_name", "A", "editable", "text", "groupName", "组合名称"),
    ("biz_model", "B", "editable", "text", "bizModel", "被审计单位管理应收票据业务模式"),
    ("basis", "C", "editable", "text", "basis", "具体依据"),
    ("index_ref", "D", "editable", "text", "indexRef", "索引号"),
    ("remark", "E", "editable", "text", "remark", "备注"),
)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 契约 payload
# ═══════════════════════════════════════════════════════════════════════════


def _src(cell: str) -> str:
    return f"源xlsx!{MANAGED_SHEET_D213}!{cell}"


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
        "header_rows": 1,
        "row_identity": {"kind": "field", "json_pointer": f"/rows/*/{ROW_IDENTITY_STORE_KEY}"},
        "delete_policy": "tombstone",
        "footer_anchor": {
            "marker": FOOTER_MARKER,
            "search_column": "A",
            "carries_total_formula": False,
        },
        "formula_mask": [],
        "fields": fields,
    }


def sheet_payload_d213() -> dict[str, Any]:
    from app.services.workpaper_sync.excel_extract import TABLE_SHEET_ANCHOR

    return {
        "sheet_key": SHEET_KEY_D213,
        "excel_name": MANAGED_SHEET_D213,
        "locator": {"anchor": TABLE_SHEET_ANCHOR},
        "tables": [_rows_table_payload()],
    }


# ═══════════════════════════════════════════════════════════════════════════
# 3. Instrumentation spec
# ═══════════════════════════════════════════════════════════════════════════


def instrumentation_spec_d213(*, entry_id: str, template_relative_path: str) -> Any:
    from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec

    return ExcelInstrumentationSpec(
        entry_id=entry_id,
        template_id=TEMPLATE_ID_D213,
        template_relative_path=template_relative_path,
        managed_sheet=MANAGED_SHEET_D213,
        first_data_row=FIRST_DATA_ROW,
        last_data_row=LAST_DATA_ROW,
        footer_row=FOOTER_ROW,
        managed_last_col=MANAGED_LAST_COL,
        uuid_col=UUID_COL,
        table_name=TABLE_NAME,
        sheet_key=SHEET_KEY_D213,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 4. Mapping digest
# ═══════════════════════════════════════════════════════════════════════════


def mapping_digest_payload() -> dict[str, Any]:
    return {
        "sheet_key": SHEET_KEY_D213,
        "fields": [
            {"column_key": ck, "column": col, "mode": m, "value_type": vt, "json_path": jp}
            for ck, col, m, vt, jp, _ in FIELD_SPECS
        ],
    }


def compute_mapping_digest() -> str:
    return hashlib.sha256(
        json.dumps(mapping_digest_payload(), sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


_FROZEN_MAPPING_DIGEST: Final[str] = "4846ef371a7ae080b6774c73e8b61809f2818583ffaefabd453eb03a926d7bd6"


def assert_mapping_digest_d213() -> str:
    d = compute_mapping_digest()
    if _FROZEN_MAPPING_DIGEST and d != _FROZEN_MAPPING_DIGEST:
        raise SyncDomainError(f"D2-13 mapping digest drift: {d} != {_FROZEN_MAPPING_DIGEST}")
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
            raise StorePayloadError(f"{STORE_ITEM_ID} JSON 非法: {exc}") from exc
    else:
        rows = payload
    if not isinstance(rows, list):
        raise StorePayloadError(f"{STORE_ITEM_ID} 必须是数组，实得 {type(rows).__name__}")
    seen: set[str] = set()
    for i, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise StorePayloadError(f"{STORE_ITEM_ID} 第 {i} 项不是对象")
        rid = row.get(ROW_IDENTITY_STORE_KEY)
        if not isinstance(rid, str) or not rid.strip():
            raise StorePayloadError(f"{STORE_ITEM_ID} 第 {i} 行缺 {ROW_IDENTITY_STORE_KEY}")
        rid = rid.strip()
        if rid in seen:
            raise StorePayloadError(f"{STORE_ITEM_ID} 重复行身份 {rid!r}")
        seen.add(rid)
        yield rid, row


def _resolve(row: Mapping[str, Any], jp: str) -> Any:
    cur: Any = row
    for seg in jp.split("/"):
        if not isinstance(cur, Mapping):
            return None
        cur = cur.get(seg)
    return cur


def build_d213_store_projection(
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
        budget.add_row(ROWS_TABLE_KEY)
        row_keys.append(identity)
        for ck, _col, _m, _vt, jp, _label in FIELD_SPECS:
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
        row_keys={ROWS_TABLE_KEY: tuple(row_keys)},
    )
