# -*- coding: utf-8 -*-
"""J3 股份支付 —— Phase 5 entry 模块（J 循环第三条 entry）。

J3-1 股份支付情况表（明细表）作为 canary。

═══ 几何（openpyxl 逐格实测 `股份支付情况表J3-1`）═══

max_row=43 / max_column=18 / merged=8 / protection=False / 公式 7（全部引用底稿目录） /
definedName 502（断链 479，跨循环复制残留，**不删**）

🔴 **零业务公式** —— 全部 7 个公式都是 `=底稿目录!A*` 引用（R3-R4 表头栏），数据区无公式。
🔴 **无审定表**（J3 无独立科目，费用走 K8/K9，权益走 M4）。
🔴 **无 TB 发布门**。

═══ 明细表列映射（对齐前端 `PlanRow`，R20 表头）═══

| col | header_R20 | json_key | mode |
|-----|------------|----------|------|
| A | 股份支付项目名称 | name | editable |
| B | 类型 | category | editable |
| C | 授予日 | grantDate | editable |
| D | 批准部门 | approver | editable |
| E | 行权日 | exerciseDate | editable |
| F | 权益工具数量 | quantity | editable |
| G | 等待期 | vestingPeriod | editable |
| H | 公允价值确定方法和数据来源 | fairValueMethod | editable |
| I | 协议变更/取消情况 | modification | editable |
| J | 资产负债表日估计更新情况 | bsDateUpdate | editable |
| K | 剩余等待期限 | remainingPeriod | editable |
| L | 协议索引号 | agreementRef | editable |
| M | 股份支付计算表索引号 | calcRef | editable |
| N | 结论 | conclusion | editable |

数据区 R21-R27（7 行），无 footer。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from app.services.workpaper_sync import phase5_h_cycle_common as HC
from app.services.workpaper_sync.adapters.registry import (
    AdapterRegistration,
    EntryMatcher,
    WorkpaperSyncAdapterRegistry,
)
from app.services.workpaper_sync.contracts import SyncContract
from app.services.workpaper_sync.entry_profile import DescriptorFacts, RoomFacts
from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec
from app.services.workpaper_sync.models import AuthorityModel, BundleSlot, DefinitionKind
from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

# ═══════════════════════════════════════════════════════════════════════════
# 1. Entry 常量
# ═══════════════════════════════════════════════════════════════════════════

PHASE5_WAVE: Final[str] = "phase5_j3_share_based_payment"
ENTRY_ID: Final[str] = "xlsx/j3/gt-j3-share-based-payment"
ADAPTER_ID: Final[str] = "j3.share_based_payment_detail"

WP_CODES: Final[frozenset[str]] = frozenset({"J3"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "J/J3 股份支付.xlsx"
TEMPLATE_SHA256: Final[str] = (
    "d2e9d7eb236b6476ccdc6edde1fadbd7119476bb2769bd95c9c9cc1699621bb4"
)

# ═══════════════════════════════════════════════════════════════════════════
# 2. Sheet spec（股份支付情况表 J3-1 明细区 R21-R27）
# ═══════════════════════════════════════════════════════════════════════════

MANAGED_SHEET: Final[str] = "股份支付情况表J3-1"
SHEET_KEY: Final[str] = "j31-plans-managed"
ROWS_TABLE_KEY: Final[str] = "share_based_payment_plans"
TEMPLATE_ID: Final[str] = "J31P"
UUID_COL: Final[str] = "S"  # max_column(18) + 1 = S(19)

HEADER_ROW: Final[int] = 20
FIRST_DATA_ROW: Final[int] = 21
LAST_DATA_ROW: Final[int] = 27
#: 🔴 无 footer 合计行。R28 是 `三、审计说明：` 不是 footer。
#: 引擎 dataclass 必填 footer_row ⇒ 给 28 占位 + footer_carries_total_formula=False。
FOOTER_ROW: Final[int] = 28
FOOTER_MARKER: Final[str] = ""

STORE_ITEM_ID: Final[str] = "J3-1-plans"
#: 🔴 真库行身份字段是 `id`（纯序号 `1, 2, ...`）不是 `key`。
ROW_IDENTITY_KEY: Final[str] = "id"
EMPTY_PAYLOAD: Final[str] = "[]"

PAYLOAD_COLUMN: Final[str] = "remark"
PAYLOAD_COLUMN_MODE: Final[str] = "remark_only"

#: 15 个受管字段（全 editable，零公式列）。json_key 按真库实际键名。
FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("name", "A", "editable", "text", "name", "股份支付项目名称", ""),
    ("type", "B", "editable", "text", "type", "类型", ""),
    ("grant_date", "C", "editable", "text", "grantDate", "授予日", ""),
    ("approval_dept", "D", "editable", "text", "approvalDept", "批准部门", ""),
    ("exercise_date", "E", "editable", "text", "exerciseDate", "行权日", ""),
    ("instrument_qty", "F", "editable", "text", "instrumentQty", "权益工具数量", ""),
    ("vesting_period", "G", "editable", "text", "vestingPeriod", "等待期", ""),
    ("fv_method", "H", "editable", "text", "fvMethod", "公允价值确定方法和数据来源", ""),
    ("agreement_change", "I", "editable", "text", "agreementChange", "协议变更/取消情况", ""),
    ("bs_update", "J", "editable", "text", "bsUpdate", "资产负债表日估计更新情况", ""),
    ("remaining_period", "K", "editable", "text", "remainingPeriod", "剩余等待期限", ""),
    ("agreement_index", "L", "editable", "text", "agreementIndex", "协议索引号", ""),
    ("calc_table_index", "M", "editable", "text", "calcTableIndex", "股份支付计算表索引号", ""),
    ("conclusion", "N", "editable", "text", "conclusion", "结论", ""),
)

#: 🔴 零公式列。
FORMULA_COLUMNS: Final[tuple[str, ...]] = ()
FORMULA_TEMPLATES: Final[dict[str, str]] = {}

SPEC_J31_PLANS: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET,
    sheet_key=SHEET_KEY,
    table_key=ROWS_TABLE_KEY,
    template_id=TEMPLATE_ID,
    table_name=f"GT_{TEMPLATE_ID}_ROWS",
    uuid_col=UUID_COL,
    first_data_row=FIRST_DATA_ROW,
    last_data_row=LAST_DATA_ROW,
    footer_row=FOOTER_ROW,
    header_row=HEADER_ROW,
    store_item_id=STORE_ITEM_ID,
    empty_payload=EMPTY_PAYLOAD,
    row_identity_key=ROW_IDENTITY_KEY,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS,
    formula_columns=FORMULA_COLUMNS,
    formula_templates=FORMULA_TEMPLATES,
    footer_marker=FOOTER_MARKER,
    footer_carries_total_formula=False,
    error_label="J3-1 股份支付情况表（明细区）",
)

# ═══════════════════════════════════════════════════════════════════════════
# 3. Identity
# ═══════════════════════════════════════════════════════════════════════════

EntrySelectionError = HC.HEntrySelectionError
StorePayloadError = HC.HStorePayloadError

IDENTITY: Final[HC.HEntryIdentity] = HC.HEntryIdentity(
    entry_id=ENTRY_ID,
    adapter_id=ADAPTER_ID,
    phase5_wave=PHASE5_WAVE,
    wp_codes=WP_CODES,
    template_relative_path=TEMPLATE_RELATIVE_PATH,
    template_sha256=TEMPLATE_SHA256,
    primary_store_item_id=STORE_ITEM_ID,
    expected_profile_id=EXPECTED_PROFILE_ID,
    phantom_code_resolves_to_own_workbook=False,
    tb_publish_gate=None,
)

_HTML_STORE_NOTE: Final[str] = (
    "J3 股份支付情况表 J3-1 明细行数据存成 checklist_responses.remark JSON 数组"
    "（item_id J3-1-plans）。14 列全文本 editable，零公式。"
    "行身份用 `key`（前端 PlanRow.key），不是 UUID。"
    "真库 J3-1-plans 251 B。"
)

_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐格实测 J/J3 股份支付.xlsx 的 `股份支付情况表J3-1`"
    "（max_row=43 / max_column=18 / merged=8 / protection=False / "
    "公式 7 全部引用底稿目录（零业务公式） / definedName 502（断链 479，跨循环复制残留，不删） / "
    "单级表头 R20（14 列：项目名称/类型/授予日/批准部门/行权日/数量/等待期/公允价值方法/"
    "协议变更/资产负债表日估计/剩余等待期/协议索引/计算表索引/结论） / "
    "数据区 R21-R27（7 行） / 无 footer 合计行（R28 是「三、审计说明：」） / "
    "全文本 editable 零公式 / UUID 放 S 列 / "
    "真库 J3-1-plans 251 B）"
)


# ═══════════════════════════════════════════════════════════════════════════
# 4. Facade 函数（照 J1/J2 同构）
# ═══════════════════════════════════════════════════════════════════════════

def managed_row_table_specs() -> tuple[RowTableSheetSpec, ...]:
    return (SPEC_J31_PLANS,)


def all_store_item_ids() -> tuple[str, ...]:
    return (STORE_ITEM_ID,)


def all_managed_sheet_names() -> tuple[str, ...]:
    return (MANAGED_SHEET,)


def instrumentation_specs() -> tuple[ExcelInstrumentationSpec, ...]:
    return HC.instrumentation_specs_for(IDENTITY, managed_row_table_specs())


def instrumentation_spec() -> ExcelInstrumentationSpec:
    specs = instrumentation_specs()
    if len(specs) != 1:
        raise HC.HEntrySelectionError(f"J3 受管 spec 应恰 1 条，实际 {len(specs)}")
    return specs[0]


def template_definition_payload() -> dict[str, Any]:
    return HC.template_definition_payload(IDENTITY, managed_row_table_specs())


def instrumentation_definition_payload() -> dict[str, Any]:
    return HC.instrumentation_definition_payload(IDENTITY, managed_row_table_specs())


def excel_carrier_gate():
    return HC.excel_carrier_gate()


def authoritative_template_path() -> Path:
    return HC.authoritative_template_path(IDENTITY)


def read_authoritative_template() -> bytes:
    return HC.read_authoritative_template(IDENTITY)


TemplateResolutionFacts = HC.TemplateResolutionFacts


def assert_no_implicit_template_fallback(
    resolution: HC.TemplateResolutionFacts, *, wp_codes: frozenset[str] | None = None
) -> None:
    del wp_codes
    HC.assert_phantom_code_does_not_leak(IDENTITY, resolution)


def assert_entry_selectable(
    *,
    resolution: HC.TemplateResolutionFacts,
    manifest: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    return HC.assert_entry_selectable(IDENTITY, resolution=resolution, manifest=manifest)


def build_contract_payload() -> dict[str, Any]:
    return HC.build_contract_payload(
        IDENTITY,
        managed_row_table_specs(),
        html_store_note=_HTML_STORE_NOTE,
        reviewed_basis=_REVIEWED_BASIS,
        payload_column=PAYLOAD_COLUMN,
        payload_column_mode=PAYLOAD_COLUMN_MODE,
        payload_column_source=(
            "audit-platform/frontend/src/components/workpaper/j3/core/J3TabDetail.vue — "
            "item_id J3-1-plans，checklist_responses.remark JSON 数组"
        ),
    )


def contract_file_path() -> Path:
    from app.services.workpaper_sync.contracts import contract_path_for
    return contract_path_for(ADAPTER_ID)


def load_contract_from_disk() -> SyncContract:
    from app.services.workpaper_sync.contracts import load_contract
    return load_contract(ADAPTER_ID)


def assert_contract_file_matches_source() -> SyncContract:
    return HC.assert_contract_file_matches_source(IDENTITY, build_contract_payload())


def _spec_of_store_item(store_item_id: str) -> RowTableSheetSpec:
    for spec in managed_row_table_specs():
        if spec.store_item_id == store_item_id:
            return spec
    raise HC.HEntrySelectionError(
        f"store item {store_item_id!r} 不在 J3 受管清单里；"
        f"已受管：{sorted(all_store_item_ids())}"
    )


def _coerce_id_to_str(payload: str | bytes | Sequence[Any]) -> str:
    """🔴 J3 的行身份 `id` 是 number（`mintJRowId` 铸造的时间戳级整数），但引擎的
    `store_row_identity` 要求 str。投影前统一把 `id` 转成字符串。
    不改真库数据（前端写 number 是 J 循环的刻意设计，见 jRowIdentity.ts 文件头注释）。
    """
    import json as _json
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8")
    if isinstance(payload, str):
        rows = _json.loads(payload)
    else:
        rows = list(payload)
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict) and "id" in row:
                row["id"] = str(row["id"])
    return _json.dumps(rows, ensure_ascii=False)


def build_store_projection(
    payload: str | bytes | Sequence[Any],
    *,
    contract: SyncContract,
    limits: Any | None = None,
    store_item_id: str | None = None,
) -> Any:
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        build_store_projection as _engine,
    )
    spec = _spec_of_store_item(store_item_id or STORE_ITEM_ID)
    return _engine(spec, _coerce_id_to_str(payload), contract=contract, limits=limits)


def merge_projection_into_store_rows(
    *,
    projection: Any,
    base_rows: list[Mapping[str, Any]],
    store_item_id: str | None = None,
) -> tuple[list[dict[str, Any]], int, int, set[str]]:
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        merge_projection_into_store_rows as _engine_merge,
    )
    spec = _spec_of_store_item(store_item_id or STORE_ITEM_ID)
    return _engine_merge(spec, projection=projection, base_rows=base_rows)


def iter_store_rows(payload: Any, *, store_item_id: str | None = None):
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        iter_store_rows as _engine_iter,
    )
    spec = _spec_of_store_item(store_item_id or STORE_ITEM_ID)
    return _engine_iter(spec, _coerce_id_to_str(payload))


def manifest_capability_enabled(*, manifest: Mapping[str, Any] | None = None) -> bool:
    return HC.manifest_capability_enabled(IDENTITY, manifest=manifest)


def assert_manifest_capability_enabled(
    *, manifest: Mapping[str, Any] | None = None,
) -> None:
    HC.assert_manifest_capability_enabled(IDENTITY, manifest=manifest)


def build_matcher() -> EntryMatcher:
    return HC.build_matcher(IDENTITY)


def build_registration(
    *,
    adapter: Any,
    bundle: Any,
    descriptor: DescriptorFacts,
    room: RoomFacts,
    contract: SyncContract | None = None,
) -> AdapterRegistration:
    return HC.build_registration(
        IDENTITY,
        adapter=adapter, bundle=bundle, descriptor=descriptor, room=room, contract=contract,
    )


def register_adapter(
    registry: WorkpaperSyncAdapterRegistry,
    *,
    adapter: Any,
    bundle: Any,
    descriptor: DescriptorFacts,
    room: RoomFacts,
    contract: SyncContract | None = None,
) -> AdapterRegistration:
    return HC.register_adapter(
        registry, IDENTITY,
        adapter=adapter, bundle=bundle, descriptor=descriptor, room=room, contract=contract,
    )


async def attach_pilot_adapters(
    registry: WorkpaperSyncAdapterRegistry, *, session: Any
) -> tuple[str, ...]:
    return await HC.attach_h_entry_adapter(
        registry, IDENTITY,
        session=session, contract_payload_builder=build_contract_payload,
    )


def authority_model_payload() -> dict[str, Any]:
    return HC.authority_model_payload(IDENTITY, managed_row_table_specs())


@dataclass(frozen=True, slots=True)
class Phase5Definitions:
    template: Any
    instrumentation: Any
    authority: Any

    def as_dict(self) -> dict[str, Any]:
        return {"template": self.template, "instrumentation": self.instrumentation, "authority": self.authority}


async def publish_definitions(publisher: Any) -> Phase5Definitions:
    return await HC.publish_definitions_for(
        IDENTITY, managed_row_table_specs(), publisher=publisher,
    )


async def resolve_published_frozen_definitions(
    session: Any, *, representation: Any = None, contract: SyncContract | None = None,
) -> Any:
    return await HC.resolve_published_frozen_definitions(
        IDENTITY, session=session, representation=representation, contract=contract,
    )


PILOT_WP_CODES: Final[frozenset[str]] = WP_CODES


async def publish_pilot_definitions(publisher: Any) -> Phase5Definitions:
    return await publish_definitions(publisher)
