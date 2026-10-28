# -*- coding: utf-8 -*-
"""D2-6「关联方及交易检查表」—— 检查工作簿的第一张受管 sheet。

spec: d2-inspection-sync-coverage · Task 3.1

═══ 架构 ═══

D2-6 位于 ``D2-6至D2-13  应收账款 -检查（Leap应对措施-检查）.xlsx``，与审定表工作簿
（D2-1至D2-4）是**不同的** xlsx 文件。本 provider 声明该 sheet 的字段映射、
公式 mask 和 store projection 拆分。

最终将归入新 entry ``xlsx/gt-d2-inspection``（独立于现有
``xlsx/gt-d2-accounts-receivable``），因为模板不同、instrumentation 不共享、
契约 schema 只支持单模板。

═══ 模板几何（openpyxl 直读权威模板）═══

受管 sheet = ``关联方及交易检查表D2-6``，几何 31×14（A1:N31）：

* 表头行 12：关联方名称(A) / 关联关系(B) / 期初余额(C) / 借方发生(D) /
  贷方发生(E) / 期末余额(F) / 减：坏账准备(G) / 账面价值(H) /
  发生时间及账龄(I) / 发生原因(J) / 期后回款(K) / 索引号(L)
* 数据区：行 13~15（骨架 3 行）
* 合计行 16：``A16='合计'``，``C16=SUM(C13:C15)``…``H16=SUM(H13:H15)``
* 审计说明：行 17（A17='三、审计说明：'）
* 审计结论：行 21（A21='四、审计结论：'）
* 参考枚举（关联方类型）：行 23~31

═══ 公式列（2 列逐行有公式）═══

* ``F{r} = C{r}+D{r}-E{r}``（期末余额 = 期初+借方-贷方）
* ``H{r} = F{r}-G{r}``（账面价值 = 期末-坏账准备）

2 列数据行公式 + 合计行 6 列 SUM → formula_mask。

═══ store 映射 ═══

前端 ``useD2RelatedParty`` 使用 3 个 store key：
* ``D2-related-party-rows``：行数组 JSON（主数据）
* ``D2-related-party-note``：审计说明文本
* ``D2-related-party-conclusion``：审计结论文本

行身份：``rowId`` 字段，前缀 ``rp-``。

🔴 **按模板接前端字段**（spec oo-writeback-template-parity-closure R3 批 B2b）：
* J「发生原因（款项性质）」= 前端 ``transactionType``（原「交易类型」，占位「如销售商品」，表单改名）；
  原声明 ``transactionReason`` 前端没有，J 列两个方向都不通
* I「发生时间及账龄」/ K「期后回款」/ L「索引号」前端补 ``agingPeriod`` / ``postPayment`` / ``indexRef``；
  L 原接 ``remark``（前端「备注」）—— 备注写进了索引号列
* 前端「公允交易」``isArmsLength`` / 「备注」``remark`` 模板没有对应列，只在 HTML 侧
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final, Iterator, Mapping, Sequence

from app.services.workpaper_sync.contracts import FieldSpec, SyncContract
from app.services.workpaper_sync.models import SyncDomainError
from app.services.workpaper_sync.sheet_geometry import col_index, snake


class StorePayloadError(SyncDomainError):
    """D2-6 store 载荷形态不合法。"""

    error_code = "d26_store_payload_invalid"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量
# ═══════════════════════════════════════════════════════════════════════════

#: 检查工作簿的模板路径（与审定表工作簿不同）。
INSPECTION_TEMPLATE_RELATIVE_PATH: Final[str] = (
    "D/D2-6至D2-13  应收账款 -检查（Leap应对措施-检查）.xlsx"
)

#: 检查工作簿的 SHA256 哨兵。
INSPECTION_TEMPLATE_SHA256: Final[str] = (
    "d0e27f6fbff3ff6e7db05ce4a42796f94a3e253dabfaf49761b97400ad23bed2"
)

#: 受管 sheet 的真实 Excel tab 名。
MANAGED_SHEET_D26: Final[str] = "关联方及交易检查表D2-6"

#: instrumentation 的模板短码。
TEMPLATE_ID_D26: Final[str] = "D26"

#: 契约 sheet_key。
SHEET_KEY_D26: Final[str] = "d26-managed"

#: 单级表头（行 12）。
HEADER_ROW: Final[int] = 12

#: 数据区起止行。
FIRST_DATA_ROW: Final[int] = 13
LAST_DATA_ROW: Final[int] = 15

#: 合计行。
FOOTER_ROW: Final[int] = 16
FOOTER_MARKER: Final[str] = "合计"

#: 最后受管业务列 / 隐藏 UUID 列。
MANAGED_LAST_COL: Final[str] = "L"
UUID_COL: Final[str] = "M"

#: Table displayName。
TABLE_NAME: Final[str] = f"GT_{TEMPLATE_ID_D26}_ROWS"

#: 行表 key。
ROWS_TABLE_KEY: Final[str] = "related_party_rows"

#: HTML store item_id。
STORE_ITEM_ID: Final[str] = "D2-related-party-rows"

#: 行身份 JSON key。
ROW_IDENTITY_STORE_KEY: Final[str] = "rowId"

# ═══════════════════════════════════════════════════════════════════════════
# 2. 字段声明（Excel 列 → store JSON path）
# ═══════════════════════════════════════════════════════════════════════════

#: 12 个受管字段 = 10 editable + 2 formula。
#: (column_key, column_letter, mode, value_type, json_path, header_text)
#: json_path 一律是前端 ``RelatedPartyRow`` 实际存的键（见模块 docstring「按模板接前端字段」）。
FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    ("debtor_name", "A", "editable", "text", "debtorName", "关联方名称"),
    ("relation_type", "B", "editable", "text", "relationType", "关联关系"),
    ("prior_balance", "C", "editable", "amount", "priorBalance", "期初余额"),
    ("debit_amount", "D", "editable", "amount", "debitAmount", "借方发生"),
    ("credit_amount", "E", "editable", "amount", "creditAmount", "贷方发生"),
    ("end_balance", "F", "formula", "amount", "endBalance", "期末余额"),
    ("bad_debt_provision", "G", "editable", "amount", "badDebtProvision", "减：坏账准备"),
    ("book_value", "H", "formula", "amount", "bookValue", "账面价值"),
    ("aging_period", "I", "editable", "text", "agingPeriod", "发生时间及账龄"),
    ("transaction_reason", "J", "editable", "text", "transactionType", "发生原因（款项性质）"),
    ("post_payment", "K", "editable", "amount", "postPayment", "期后回款"),
    ("index_ref", "L", "editable", "text", "indexRef", "索引号"),
)

#: 公式列 → 行公式模板。
FORMULA_TEMPLATES: Final[Mapping[str, str]] = {
    "F": "=C{r}+D{r}-E{r}",
    "H": "=F{r}-G{r}",
}

#: formula_mask 区域。
FORMULA_MASK: Final[tuple[str, ...]] = (
    f"F{FIRST_DATA_ROW}:F{LAST_DATA_ROW}",
    f"H{FIRST_DATA_ROW}:H{LAST_DATA_ROW}",
)

#: 几何函数别名。
_col_index = col_index
_snake = snake


# ═══════════════════════════════════════════════════════════════════════════
# 3. 契约 payload
# ═══════════════════════════════════════════════════════════════════════════


def _src(cell: str) -> str:
    """source_ref 统一形态。"""
    return f"源xlsx!{MANAGED_SHEET_D26}!{cell}"


def stable_key_for(column_key: str, row_identity: str = "{row_uuid}") -> str:
    """stable_field_key 拼装。"""
    return f"{ROWS_TABLE_KEY}/{row_identity}/{column_key}"


def _rows_table_payload() -> dict[str, Any]:
    """D2-6 行表的契约 payload。"""
    fields: list[dict[str, Any]] = []
    for column_key, column, mode, value_type, json_path, header_text in FIELD_SPECS:
        spec: dict[str, Any] = {
            "stable_field_key": stable_key_for(column_key),
            "json_pointer": f"/rows/{{row_uuid}}/{json_path}",
            "column_key": column_key,
            "cell": {"column": column, "row_from": "row_identity"},
            "mode": mode,
            "value_type": value_type,
            "source_ref": _src(f"{column}{FIRST_DATA_ROW}"),
            "header_source_ref": _src(f"{column}{HEADER_ROW}"),
            "store_item_id": STORE_ITEM_ID,
            "header_text": header_text,
        }
        fields.append(spec)
    return {
        "table_key": ROWS_TABLE_KEY,
        "anchor": f"A{HEADER_ROW}",
        "header_rows": 1,
        "row_identity": {"kind": "field", "json_pointer": f"/rows/*/{ROW_IDENTITY_STORE_KEY}"},
        "delete_policy": "tombstone",
        "footer_anchor": {
            "marker": FOOTER_MARKER,
            "search_column": "A",
            "carries_total_formula": True,
            "note": (
                "合计行 A16，C16~H16 共 6 列 SUM(x13:x15)。"
                "声明为真使结构性插行有权按声明位移量扩张该区间"
            ),
        },
        "formula_mask": list(FORMULA_MASK),
        "fields": fields,
    }


def sheet_payload_d26() -> dict[str, Any]:
    """D2-6 的 sheet payload（将追加到检查 entry 的 build_contract_payload().sheets[]）。"""
    from app.services.workpaper_sync.excel_extract import TABLE_SHEET_ANCHOR

    return {
        "sheet_key": SHEET_KEY_D26,
        "excel_name": MANAGED_SHEET_D26,
        "locator": {"anchor": TABLE_SHEET_ANCHOR},
        "tables": [_rows_table_payload()],
    }


# ═══════════════════════════════════════════════════════════════════════════
# 4. Instrumentation spec
# ═══════════════════════════════════════════════════════════════════════════


def instrumentation_spec_d26(
    *, entry_id: str, template_relative_path: str
) -> Any:
    """返回 D2-6 的 ExcelInstrumentationSpec。"""
    from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec

    return ExcelInstrumentationSpec(
        entry_id=entry_id,
        template_id=TEMPLATE_ID_D26,
        template_relative_path=template_relative_path,
        managed_sheet=MANAGED_SHEET_D26,
        first_data_row=FIRST_DATA_ROW,
        last_data_row=LAST_DATA_ROW,
        footer_row=FOOTER_ROW,
        managed_last_col=MANAGED_LAST_COL,
        uuid_col=UUID_COL,
        table_name=TABLE_NAME,
        sheet_key=SHEET_KEY_D26,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 5. Mapping digest（契约漂移检测）
# ═══════════════════════════════════════════════════════════════════════════


def mapping_digest_payload() -> dict[str, Any]:
    """用于 digest 比对的字段映射 canonical payload。"""
    return {
        "sheet_key": SHEET_KEY_D26,
        "managed_sheet": MANAGED_SHEET_D26,
        "template_id": TEMPLATE_ID_D26,
        "first_data_row": FIRST_DATA_ROW,
        "last_data_row": LAST_DATA_ROW,
        "header_row": HEADER_ROW,
        "footer_row": FOOTER_ROW,
        "managed_last_col": MANAGED_LAST_COL,
        "uuid_col": UUID_COL,
        "fields": [
            {
                "column_key": ck,
                "column": col,
                "mode": mode,
                "value_type": vt,
                "json_path": jp,
            }
            for ck, col, mode, vt, jp, _label in FIELD_SPECS
        ],
        "formula_templates": dict(FORMULA_TEMPLATES),
    }


def compute_mapping_digest() -> str:
    """mapping_digest_payload 的 SHA256。"""
    payload_bytes = json.dumps(
        mapping_digest_payload(), sort_keys=True, ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(payload_bytes).hexdigest()


def assert_mapping_digest_d26() -> str:
    """断言字段映射未漂移。"""
    digest = compute_mapping_digest()
    if digest != _FROZEN_MAPPING_DIGEST:
        raise SyncDomainError(
            f"D2-6 字段映射 digest 已变: {digest} != {_FROZEN_MAPPING_DIGEST}。"
            "如果映射确实需要更新，请修改 _FROZEN_MAPPING_DIGEST。"
        )
    return digest


#: 冻结 digest。2026-10-28 批 B2b：J / L 改接前端 transactionType / indexRef（原 42e593f0…）。
_FROZEN_MAPPING_DIGEST: Final[str] = "3d5472663f1d69cb443882549e3edbb7ff3a73f72b9f6dfcadea4aeed42b43f9"


# ═══════════════════════════════════════════════════════════════════════════
# 6. Store projection（HTML store → stable field key 拆分）
# ═══════════════════════════════════════════════════════════════════════════


def store_row_identity(row: Mapping[str, Any], *, ordinal: int) -> str:
    """取一行的稳定行身份。"""
    raw = row.get(ROW_IDENTITY_STORE_KEY)
    if not isinstance(raw, str) or not raw.strip():
        raise StorePayloadError(
            f"{STORE_ITEM_ID} 第 {ordinal} 行缺少稳定行身份 "
            f"{ROW_IDENTITY_STORE_KEY!r}（实得 {raw!r}）"
        )
    return raw.strip()


def iter_store_rows(
    payload: str | bytes | Sequence[Any],
) -> Iterator[tuple[str, Mapping[str, Any]]]:
    """流式 yield (row_identity, row)；重复身份即抛。"""
    if isinstance(payload, (str, bytes, bytearray)):
        text = payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else payload
        try:
            rows: Any = json.loads(text)
        except ValueError as exc:
            raise StorePayloadError(
                f"{STORE_ITEM_ID} 的 remark 不是合法 JSON: {exc}"
            ) from exc
    else:
        rows = payload
    if not isinstance(rows, list):
        raise StorePayloadError(
            f"{STORE_ITEM_ID} 载荷必须是行对象数组，实得 {type(rows).__name__}"
        )
    seen: set[str] = set()
    for ordinal, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise StorePayloadError(
                f"{STORE_ITEM_ID} 第 {ordinal} 项不是对象，实得 {type(row).__name__}"
            )
        identity = store_row_identity(row, ordinal=ordinal)
        if identity in seen:
            raise StorePayloadError(
                f"{STORE_ITEM_ID} 出现重复行身份 {identity!r}（第 {ordinal} 项）"
            )
        seen.add(identity)
        yield identity, row


def _resolve_json_path(row: Mapping[str, Any], json_path: str) -> Any:
    """按 json_path 取值；缺失返回 None。"""
    cursor: Any = row
    for segment in json_path.split("/"):
        if not isinstance(cursor, Mapping):
            return None
        cursor = cursor.get(segment)
    return cursor


def split_store_row(
    row: Mapping[str, Any],
    *,
    row_identity: str,
    contract: SyncContract,
) -> Iterator[tuple[str, Any, FieldSpec]]:
    """一行 → 12 条 (stable_key, value, spec)。"""
    for column_key, _column, _mode, _vt, json_path, _label in FIELD_SPECS:
        spec = contract.field_by_stable_key(stable_key_for(column_key))
        yield (
            stable_key_for(column_key, row_identity),
            _resolve_json_path(row, json_path),
            spec,
        )


def build_d26_store_projection(
    payload: str | bytes | Sequence[Any],
    *,
    contract: SyncContract,
    limits: Any | None = None,
) -> Any:
    """D2-6 store → Projection（按 stable field key 拆分）。"""
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
        for stable_key, value, spec in split_store_row(
            row, row_identity=identity, contract=contract
        ):
            budget.add_field()
            values[stable_key] = FieldValue(
                stable_key=stable_key,
                value=value,
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
