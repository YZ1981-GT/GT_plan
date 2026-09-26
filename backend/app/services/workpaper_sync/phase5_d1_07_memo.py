# -*- coding: utf-8 -*-
"""D1-7「应收票据备查簿核对表」—— sheet 层声明 + **provider 专用 dict merge**。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 29 · Requirements 5.1

═══ 为什么有专用 merge 而不走框架层通用路径 ═══

前端 `useD1MemoReconciliation.ts` 的 store 键 `D1-memo-rows` 存嵌套 dict
`{bankRows:[MemoRow...], commercialRows:[MemoRow...]}` —— 框架层
`build_store_projection`/`merge_projection_into_store_rows` 严格要求顶层是 list，
对 dict 载荷会在 `iter_store_rows` 直接抛 `RowTableStorePayloadError`。

本模块参照 D4-9 的已验证路径：手写 build/merge 函数 → `DedicatedStoreItem` 注册 →
`oo_to_html._mirror_dedicated_dict_stores` 按注册表分派。D1-7 比 D4-9 简单：只有两段行
（无 totals 静态标量），两段列结构完全相同（银行承兑 R13-R17 + 商业承兑 R19-R23）。

═══ 几何（openpyxl 直读实测，2026-09-26）═══

31 列 A-AE（含公式区 Q-T）。两级表头 R11-R12。
| 区 | 标题 | 数据行 | footer | 公式列 | UUID 列 |
|---|---|---|---|---|---|
| 银行承兑 | R11 "备查簿信息" | R13-R17 (5行) | R18 `银行承兑汇票小计` | Q/R/S/T | Y |
| 商业承兑 | — (连续) | R19-R23 (5行) | R24 `商业承兑汇票小计` | Q/R/S/T | Z |

R25 `合计` 是两区的总计行（公式引用 Q18+Q24 等）。
R28-R34 是核对区（备查簿/明细账/差异 + 贴现/背书分类汇总），全部是公式格，不受管。

🔴 公式区 Q-T（审计核对区）在**数据区内**有行级公式（Q=IF(YEAR(C)=YEAR($B$10)-1,H,0) /
R=H-Q / S=IF(K="背书",H,0) / T=IF(K="到期承兑",H,0)），声明为 formula。

🔴 `row_identity_key = "rowId"`（与 D1-3/D1-8 一致）。
🔴 footer marker 不同于两区合计 —— 银行承兑用 `银行承兑汇票小计`，商业承兑用 `商业承兑汇票小计`。
🔴 store 键 `D1-memo-rows` 是 dict 形态（`StoreKind.dict`）。
"""
from __future__ import annotations

import json
from typing import Any, Final, Iterator, Mapping

from app.services.workpaper_sync.contracts import SyncContract
from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_D107_BANK",
    "SPEC_D107_COMMERCIAL",
    "SPECS_D107",
    "MANAGED_SHEET_D107",
    "STORE_ITEM_ID_D107",
    "build_d17_bank_projection",
    "build_d17_commercial_projection",
    "build_d17_store_projection",
    "merge_projection_into_d17_store",
    "merge_projection_into_d17_store_state",
]

MANAGED_SHEET_D107: Final[str] = "应收票据备查簿核对D1-7"
TEMPLATE_ID_D107: Final[str] = "D17"
SHEET_KEY_D107: Final[str] = f"{TEMPLATE_ID_D107.lower()}-managed"
STORE_ITEM_ID_D107: Final[str] = "D1-memo-rows"
ROW_IDENTITY_KEY: Final[str] = "rowId"

#: 银行承兑（区一）
ROWS_TABLE_KEY_BANK: Final[str] = "memo_bank_rows"
FIRST_DATA_ROW_BANK: Final[int] = 13
LAST_DATA_ROW_BANK: Final[int] = 17
FOOTER_ROW_BANK: Final[int] = 18
FOOTER_MARKER_BANK: Final[str] = "银行承兑汇票小计"

#: 商业承兑（区二）
ROWS_TABLE_KEY_COMMERCIAL: Final[str] = "memo_commercial_rows"
FIRST_DATA_ROW_COMMERCIAL: Final[int] = 19
LAST_DATA_ROW_COMMERCIAL: Final[int] = 23
FOOTER_ROW_COMMERCIAL: Final[int] = 24
FOOTER_MARKER_COMMERCIAL: Final[str] = "商业承兑汇票小计"

HEADER_GROUP_ROW_D107: Final[int] = 11
HEADER_LEAF_ROW_D107: Final[int] = 12

#: 两区共用列结构（16 editable A-P + 4 formula Q-T = 20 受管列；U-AE 审定区额外 8 列）。
#: 前端 MemoRow 共 31+ 字段，但 Excel 受管列取 A-T（备查簿信息+审计核对）。
#: U-AE 区（审定区 8 列）的映射留给后续灰度开启时根据实测确认是否也进受管。
#: 🔴 现阶段只声明 A-P（备查簿基本信息 16 列），Q-T（审计核对公式区 4 列声明 formula）。
_FIELD_SPECS_D107: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("note_type", "A", "editable", "text", "noteType", "票据类型", ""),
    ("note_number", "B", "editable", "text", "noteNumber", "票据号", ""),
    ("received_date", "C", "editable", "text", "receivedDate", "收到票据日期", ""),
    ("endorser", "D", "editable", "text", "endorser", "票据前手名称", ""),
    ("issue_date", "E", "editable", "text", "issueDate", "出票日期", ""),
    ("issuer", "F", "editable", "text", "issuer", "出票人名称", ""),
    ("acceptor", "G", "editable", "text", "acceptor", "承兑人名称", ""),
    ("amount", "H", "editable", "amount", "amount", "票据金额", ""),
    ("maturity_date", "I", "editable", "text", "maturityDate", "票据到期日", ""),
    ("transfer_date", "J", "editable", "text", "transferDate", "票据流转日期", ""),
    ("status", "K", "editable", "text", "status", "票据状态", ""),
    ("endorsee", "L", "editable", "text", "endorsee", "被背书人名称", ""),
    ("discount_bank", "M", "editable", "text", "discountBank", "贴现银行", ""),
    ("discount_interest", "N", "editable", "amount", "discountInterest", "贴现息", ""),
    ("is_pledged", "O", "editable", "text", "isPledged", "是否质押", ""),
    ("is_discounted_endorsed", "P", "editable", "text", "isDiscountedEndorsed", "审计日已贴现、背书", ""),
    ("beginning_balance", "Q", "formula", "amount", "beginningBalance", "年初余额", ""),
    ("current_received", "R", "formula", "amount", "currentReceived", "本期收到", ""),
    ("current_endorsed", "S", "formula", "amount", "currentEndorsed", "本期背书", ""),
    ("current_matured", "T", "formula", "amount", "currentMatured", "本期到期承兑", ""),
)

_FORMULA_COLUMNS_D107: Final[tuple[str, ...]] = ("Q", "R", "S", "T")
_FORMULA_TEMPLATES_BANK: Final[dict[str, str]] = {
    "Q": "=IF(YEAR(C{r})=YEAR($B$10)-1,H{r},0)",
    "R": "=H{r}-Q{r}",
    "S": '=IF(K{r}="背书",H{r},0)',
    "T": '=IF(K{r}="到期承兑",H{r},0)',
}
_FORMULA_TEMPLATES_COMMERCIAL: Final[dict[str, str]] = _FORMULA_TEMPLATES_BANK  # 同构


SPEC_D107_BANK: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_D107,
    sheet_key=SHEET_KEY_D107,
    table_key=ROWS_TABLE_KEY_BANK,
    template_id=f"{TEMPLATE_ID_D107}BANK",
    table_name=f"GT_{TEMPLATE_ID_D107}_BANK_ROWS",
    uuid_col="Y",
    first_data_row=FIRST_DATA_ROW_BANK,
    last_data_row=LAST_DATA_ROW_BANK,
    footer_row=FOOTER_ROW_BANK,
    header_group_row=HEADER_GROUP_ROW_D107,
    header_leaf_row=HEADER_LEAF_ROW_D107,
    store_item_id=STORE_ITEM_ID_D107,
    empty_payload="{}",
    row_identity_key=ROW_IDENTITY_KEY,
    store_kind=StoreKind.dict,
    field_specs=_FIELD_SPECS_D107,
    formula_columns=_FORMULA_COLUMNS_D107,
    formula_templates=_FORMULA_TEMPLATES_BANK,
    footer_marker=FOOTER_MARKER_BANK,
    error_label="D1-7 银行承兑",
)

SPEC_D107_COMMERCIAL: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_D107,
    sheet_key=SHEET_KEY_D107,
    table_key=ROWS_TABLE_KEY_COMMERCIAL,
    template_id=f"{TEMPLATE_ID_D107}COMM",
    table_name=f"GT_{TEMPLATE_ID_D107}_COMMERCIAL_ROWS",
    uuid_col="Z",
    first_data_row=FIRST_DATA_ROW_COMMERCIAL,
    last_data_row=LAST_DATA_ROW_COMMERCIAL,
    footer_row=FOOTER_ROW_COMMERCIAL,
    header_group_row=HEADER_GROUP_ROW_D107,
    header_leaf_row=HEADER_LEAF_ROW_D107,
    store_item_id=STORE_ITEM_ID_D107,
    empty_payload="{}",
    row_identity_key=ROW_IDENTITY_KEY,
    store_kind=StoreKind.dict,
    field_specs=_FIELD_SPECS_D107,
    formula_columns=_FORMULA_COLUMNS_D107,
    formula_templates=_FORMULA_TEMPLATES_COMMERCIAL,
    footer_marker=FOOTER_MARKER_COMMERCIAL,
    error_label="D1-7 商业承兑",
)

SPECS_D107: Final[tuple[RowTableSheetSpec, ...]] = (SPEC_D107_BANK, SPEC_D107_COMMERCIAL)


# ═══════════════════════════════════════════════════════════════════════════
# provider 专用 dict store 投影/合并（参照 D4-9 `phase5_d4_customer_structure`）
# ═══════════════════════════════════════════════════════════════════════════


class D17StorePayloadError(ValueError):
    """D1-7 dict store 载荷形态不合法。"""


def _parse_payload(payload: str | bytes | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(payload, Mapping):
        return payload
    text = payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else str(payload)
    try:
        data = json.loads(text or "{}")
    except ValueError as exc:
        raise D17StorePayloadError(f"{STORE_ITEM_ID_D107} JSON 非法: {exc}") from exc
    if isinstance(data, Mapping):
        return data
    if isinstance(data, list):
        return {}  # legacy 容差（同 D4-9 处置）
    raise D17StorePayloadError(f"{STORE_ITEM_ID_D107} 载荷须为对象，实得 {type(data).__name__}")


def _iter_region_rows(
    region: Any, *, region_name: str
) -> Iterator[tuple[str, Mapping[str, Any]]]:
    if region is None or not isinstance(region, list):
        return
    seen: set[str] = set()
    for i, row in enumerate(region):
        if not isinstance(row, Mapping):
            raise D17StorePayloadError(f"{STORE_ITEM_ID_D107}.{region_name}[{i}] 非对象")
        rid = row.get(ROW_IDENTITY_KEY)
        if not isinstance(rid, str) or not rid.strip():
            raise D17StorePayloadError(f"{STORE_ITEM_ID_D107}.{region_name}[{i}] 缺行身份")
        rid = rid.strip()
        if rid in seen:
            raise D17StorePayloadError(f"{STORE_ITEM_ID_D107}.{region_name} 重复行身份 {rid!r}")
        seen.add(rid)
        yield rid, row


def _build_region_projection(
    data: Mapping[str, Any],
    *,
    region_name: str,
    spec: RowTableSheetSpec,
    contract: SyncContract,
    budget: Any,
) -> tuple[dict[str, Any], list[str]]:
    from app.services.workpaper_sync.adapters.base import FieldValue
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        managed_field_specs,
        stable_key_for,
    )

    values: dict[str, FieldValue] = {}
    row_keys: list[str] = []
    for rid, row in _iter_region_rows(data.get(region_name), region_name=region_name):
        budget.add_row(spec.table_key)
        row_keys.append(rid)
        for col_key, _col, _mode, _vt, json_key, _lbl, _gh in managed_field_specs(spec):
            sk = stable_key_for(spec, col_key, rid)
            fspec = contract.field_by_stable_key(stable_key_for(spec, col_key))
            budget.add_field()
            values[sk] = FieldValue(
                stable_key=sk,
                value=row.get(json_key),
                value_type=fspec.value_type,
                mode=fspec.mode,
                row_key=rid,
            )
    return values, row_keys


def build_d17_bank_projection(payload, *, contract: SyncContract, limits=None):
    from app.services.workpaper_sync.adapters.base import Projection
    from app.services.workpaper_sync.excel_extract import StreamingProjectionBudget
    from app.services.workpaper_sync.limits import load_limits

    budget = StreamingProjectionBudget(limits or load_limits())
    data = _parse_payload(payload)
    values, row_keys = _build_region_projection(
        data, region_name="bankRows", spec=SPEC_D107_BANK, contract=contract, budget=budget
    )
    return Projection(
        contract_id=contract.contract_id, semantic_version=contract.semantic_version,
        document_type=contract.document_type, values=values,
        row_keys={ROWS_TABLE_KEY_BANK: tuple(row_keys)},
    )


def build_d17_commercial_projection(payload, *, contract: SyncContract, limits=None):
    from app.services.workpaper_sync.adapters.base import Projection
    from app.services.workpaper_sync.excel_extract import StreamingProjectionBudget
    from app.services.workpaper_sync.limits import load_limits

    budget = StreamingProjectionBudget(limits or load_limits())
    data = _parse_payload(payload)
    values, row_keys = _build_region_projection(
        data, region_name="commercialRows", spec=SPEC_D107_COMMERCIAL, contract=contract, budget=budget
    )
    return Projection(
        contract_id=contract.contract_id, semantic_version=contract.semantic_version,
        document_type=contract.document_type, values=values,
        row_keys={ROWS_TABLE_KEY_COMMERCIAL: tuple(row_keys)},
    )


def build_d17_store_projection(payload, *, contract: SyncContract, limits=None):
    """D1-7 单 store item 的完整投影（bank + commercial 合并）。"""
    from app.services.workpaper_sync.adapters.base import Projection

    bank = build_d17_bank_projection(payload, contract=contract, limits=limits)
    comm = build_d17_commercial_projection(payload, contract=contract, limits=limits)
    values = dict(bank.values)
    values.update(comm.values)
    return Projection(
        contract_id=contract.contract_id, semantic_version=contract.semantic_version,
        document_type=contract.document_type, values=values,
        row_keys={**dict(bank.row_keys), **dict(comm.row_keys)},
    )


def merge_projection_into_d17_store(
    *, projection: Any, base_state: Mapping[str, Any] | None
) -> tuple[dict[str, Any], int, int, set[str]]:
    """把 extract projection 合回 {bankRows, commercialRows} 嵌套结构。"""
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        managed_field_specs,
    )

    base = dict(base_state) if isinstance(base_state, Mapping) else {}
    regions: dict[str, list] = {
        "bankRows": list(base.get("bankRows") or []),
        "commercialRows": list(base.get("commercialRows") or []),
    }
    table_to_region = {
        ROWS_TABLE_KEY_BANK: "bankRows",
        ROWS_TABLE_KEY_COMMERCIAL: "commercialRows",
    }
    # 两区各自的列映射（column_key → json_key）
    field_map = {row[0]: row[4] for row in managed_field_specs(SPEC_D107_BANK)}

    by_id: dict[str, dict[str, dict]] = {"bankRows": {}, "commercialRows": {}}
    order: dict[str, list[str]] = {"bankRows": [], "commercialRows": []}
    for region_name, rows in regions.items():
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            rid = str(row.get(ROW_IDENTITY_KEY) or "").strip()
            if not rid:
                continue
            by_id[region_name][rid] = dict(row)
            order[region_name].append(rid)

    applied = 0
    visited = 0
    touched: set[str] = set()
    bank_prefix = f"{ROWS_TABLE_KEY_BANK}/"
    comm_prefix = f"{ROWS_TABLE_KEY_COMMERCIAL}/"

    for key in projection.stable_keys():
        sk = str(key)
        fv = projection.get(key)
        if fv is None or getattr(fv, "is_protected", False):
            continue
        if sk.startswith(bank_prefix):
            region_name = "bankRows"
        elif sk.startswith(comm_prefix):
            region_name = "commercialRows"
        else:
            continue
        rid = getattr(fv, "row_key", None)
        if not rid:
            continue
        rid = str(rid)
        target = by_id[region_name].get(rid)
        if target is None:
            target = {ROW_IDENTITY_KEY: rid}
            by_id[region_name][rid] = target
            order[region_name].append(rid)
        col_key = sk.rsplit("/", 1)[-1]
        json_key = field_map.get(col_key)
        if not json_key:
            continue
        visited += 1
        new_val = getattr(fv, "value", None)
        if target.get(json_key) != new_val:
            target[json_key] = new_val
            applied += 1
            touched.add(rid)

    merged = dict(base)
    for region_name in ("bankRows", "commercialRows"):
        merged[region_name] = [by_id[region_name][rid] for rid in order[region_name]]
    return merged, applied, visited, touched


def merge_projection_into_d17_store_state(
    *, projection: Any, base_state: Mapping[str, Any] | None
) -> tuple[dict[str, Any], int, int]:
    """3-tuple 门面（oo_to_html 镜像用）。"""
    merged, applied, visited, _ = merge_projection_into_d17_store(
        projection=projection, base_state=base_state
    )
    return merged, applied, visited


def merge_d17_from_projection(
    *, projection: Any, base_state: Mapping[str, Any] | None
) -> tuple[dict[str, Any], int, int]:
    """DedicatedStoreItem 注册的门面（naming convention 同 D4-9 的 merge_d49_from_projection）。"""
    return merge_projection_into_d17_store_state(
        projection=projection, base_state=base_state
    )
