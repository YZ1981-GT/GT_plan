# -*- coding: utf-8 -*-
"""J2 设定受益计划 —— Phase 5 entry 模块（J 循环第二条 entry）。

spec: J2/J3 双向回写实施 · 阶段 1

═══ 几何（openpyxl 逐格实测 `明细表J2-2`）═══

max_row=90 / max_column=14 / merged=30 / protection=False / 公式 221 /
definedName 0 / 无 Excel Table

🔴 **多分区结构**（6 业务区 + 审计说明/结论）：
  A 主表 R11-R18：设定受益/辞退福利/减一年内/合计（增减四栏 14 列）
  B 未折现到期分析 R19-R27（增减四栏 14 列）
  C 设定受益计划情况 R29-R47（CAS9 六要素，另一种列结构）
  D 计划资产 R48-R61（增减四栏 14 列）
  E 精算假设 R62-R69（4 列）
  F 敏感性分析 R70-R78（5 列）

本 canary **仅接分区 A**（R13-R17 数据行，R11-R12 两级表头，R18 合计）。

═══ 分区 A 列映射（对齐前端 `AdjRow`）═══

| col | header_R11 | header_R12 | json_key | mode |
|-----|------------|------------|----------|------|
| A | 序号 | | seq | readonly |
| B | 项目名称 | | label | readonly |
| C | 未审数 | 期初数 | beginUnadj | editable |
| D | | 本期增加 | incUnadj | editable |
| E | | 本期减少 | decUnadj | editable |
| F | | 期末数 | endUnadj | formula: =C+D-E |
| G | 期初调整 | 账项调整 | openAdjust | editable |
| H | 账项调整 | 本期增加 | incAdjust | editable |
| I | | 本期减少 | decAdjust | editable |
| J | 审定数 | 期初数 | beginAud | formula: =C+G |
| K | | 本期增加 | incAud | formula: =D+H |
| L | | 本期减少 | decAud | formula: =E+I |
| M | | 期末数 | endAud | formula: =J+K-L |
| N | 备注 | | remark | editable |

数据行 R13-R17（含 R13 agg）：
  R13: 一 | 设定受益计划 (agg = R14+R15)
  R14:   | 其中：1、离职后福利 (leaf)
  R15:   |      2、其他长期职工福利 (leaf)
  R16: 二 | 辞退福利 (leaf)
  R17:   | 减：一年内支付的辞退福利 (leaf)
  R18: 合计 (footer = R13+R16-R17)

🔴 行身份用 `key`（前端 `AdjRow.key`），不是 UUID。
🔴 前端用 `remark` 列保存载荷（与 J1 同源 `PAYLOAD_COLUMN: remark`）。
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

PHASE5_WAVE: Final[str] = "phase5_j2_defined_benefit_main"
ENTRY_ID: Final[str] = "xlsx/j2/gt-j2-defined-benefit-plan"
ADAPTER_ID: Final[str] = "j2.defined_benefit_detail"

WP_CODES: Final[frozenset[str]] = frozenset({"J2"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "J/J2 长期应付职工薪酬-设定受益计划净资产.xlsx"
TEMPLATE_SHA256: Final[str] = (
    "10c0518352105d5efd5256a6245b78123b57f4c9af9673ceeee97f63125541e8"
)

# ═══════════════════════════════════════════════════════════════════════════
# 2. Sheet spec（分区 A 主表 R11-R18）
# ═══════════════════════════════════════════════════════════════════════════

MANAGED_SHEET: Final[str] = "明细表J2-2"
SHEET_KEY: Final[str] = "j22-main-managed"
ROWS_TABLE_KEY: Final[str] = "defined_benefit_main_rows"
TEMPLATE_ID: Final[str] = "J22M"
UUID_COL: Final[str] = "O"  # max_column(14) + 1

HEADER_GROUP_ROW: Final[int] = 11
HEADER_LEAF_ROW: Final[int] = 12
FIRST_DATA_ROW: Final[int] = 13
LAST_DATA_ROW: Final[int] = 17
FOOTER_ROW: Final[int] = 18
FOOTER_MARKER: Final[str] = "合计"

STORE_ITEM_ID: Final[str] = "J2-2-main"
ROW_IDENTITY_KEY: Final[str] = "key"
EMPTY_PAYLOAD: Final[str] = "[]"

PAYLOAD_COLUMN: Final[str] = "remark"
PAYLOAD_COLUMN_MODE: Final[str] = "remark_only"

#: 9 个受管字段（A/B 为模板预置标签但 mode=editable，跳过 F/J/K/L/M 五个公式列）。
FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("seq", "A", "editable", "text", "seq", "序号", ""),
    ("label", "B", "editable", "text", "label", "项目名称", ""),
    ("begin_unadj", "C", "editable", "amount", "beginUnadj", "期初数", "C11"),
    ("inc_unadj", "D", "editable", "amount", "incUnadj", "本期增加", "C11"),
    ("dec_unadj", "E", "editable", "amount", "decUnadj", "本期减少", "C11"),
    ("open_adjust", "G", "editable", "amount", "openAdjust", "账项调整", "G11"),
    ("inc_adjust", "H", "editable", "amount", "incAdjust", "本期增加", "H11"),
    ("dec_adjust", "I", "editable", "amount", "decAdjust", "本期减少", "H11"),
    ("remark", "N", "editable", "text", "remark", "备注", ""),
)

FORMULA_COLUMNS: Final[tuple[str, ...]] = ("F", "J", "K", "L", "M")
FORMULA_TEMPLATES: Final[dict[str, str]] = {
    "F": "=C{r}+D{r}-E{r}",
    "J": "=C{r}+G{r}",
    "K": "=D{r}+H{r}",
    "L": "=E{r}+I{r}",
    "M": "=J{r}+K{r}-L{r}",
}

SPEC_J22_MAIN: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET,
    sheet_key=SHEET_KEY,
    table_key=ROWS_TABLE_KEY,
    template_id=TEMPLATE_ID,
    table_name=f"GT_{TEMPLATE_ID}_ROWS",
    uuid_col=UUID_COL,
    first_data_row=FIRST_DATA_ROW,
    last_data_row=LAST_DATA_ROW,
    footer_row=FOOTER_ROW,
    header_group_row=HEADER_GROUP_ROW,
    header_leaf_row=HEADER_LEAF_ROW,
    store_item_id=STORE_ITEM_ID,
    empty_payload=EMPTY_PAYLOAD,
    row_identity_key=ROW_IDENTITY_KEY,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS,
    formula_columns=FORMULA_COLUMNS,
    formula_templates=FORMULA_TEMPLATES,
    footer_marker=FOOTER_MARKER,
    footer_carries_total_formula=True,
    error_label="J2-2 明细表（主表：设定受益/辞退福利区）",
)

# ═══════════════════════════════════════════════════════════════════════════
# 3. Identity（对齐 J1 的 HC.HEntryIdentity 模式）
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
    tb_publish_gate=None,  # J2 无 TB 发布门（明细表不回写试算表）
)

_HTML_STORE_NOTE: Final[str] = (
    "J2 设定受益计划的主明细表数据存成 checklist_responses.remark JSON 数组"
    "（item_id J2-2-main）。增减四栏结构（14 列）与 J1 同构。"
    "🔴 行身份用 `key`（稳定业务键），不是 UUID。"
    "分区 A：R13-R17（5 行含 agg），R18 合计 footer。"
)

_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐格实测 J/J2 长期应付职工薪酬-设定受益计划净资产.xlsx 的 `明细表J2-2`"
    "（多分区结构 6 业务区 / max_row=90 / max_column=14 / merged=30 / protection=False / "
    "公式 221 / definedName 0 / 无 Excel Table / "
    "分区 A 主表 R11-R18 两级表头 R11/R12 + 数据 R13-R17 + footer R18 合计 / "
    "5 个公式列 F=C+D-E J=C+G K=D+H L=E+I M=J+K-L / "
    "R13 是 agg 行 C13=C14+C15 等 / R18 是 footer 行 C18=C13+C16-C17 等 / "
    "9 个受管字段 + 5 个公式列 = 14 列(A~N) / UUID 放 O 列 / "
    "真库 J2-2-main 1101 B 有载荷）"
)


# ═══════════════════════════════════════════════════════════════════════════
# 4. Facade 函数（照 J1 同构，委托 HC 骨架）
# ═══════════════════════════════════════════════════════════════════════════

def managed_row_table_specs() -> tuple[RowTableSheetSpec, ...]:
    return (SPEC_J22_MAIN,)


def all_store_item_ids() -> tuple[str, ...]:
    return (STORE_ITEM_ID,)


def all_managed_sheet_names() -> tuple[str, ...]:
    return (MANAGED_SHEET,)


def instrumentation_specs() -> tuple[ExcelInstrumentationSpec, ...]:
    return HC.instrumentation_specs_for(IDENTITY, managed_row_table_specs())


def instrumentation_spec() -> ExcelInstrumentationSpec:
    specs = instrumentation_specs()
    if len(specs) != 1:
        raise HC.HEntrySelectionError(f"J2 受管 spec 应恰 1 条，实际 {len(specs)}")
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
            "audit-platform/frontend/src/components/workpaper/j2/J2TabDetail.vue — "
            "item_id J2-2-main，checklist_responses.remark JSON 数组"
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


# ═══════════════════════════════════════════════════════════════════════════
# store 投影 / 合并（薄转发框架层引擎，照 J1 同构）
# ═══════════════════════════════════════════════════════════════════════════


def _spec_of_store_item(store_item_id: str) -> RowTableSheetSpec:
    for spec in managed_row_table_specs():
        if spec.store_item_id == store_item_id:
            return spec
    raise HC.HEntrySelectionError(
        f"store item {store_item_id!r} 不在 J2 受管清单里；"
        f"已受管：{sorted(all_store_item_ids())}"
    )


def build_store_projection(
    payload: str | bytes | Sequence[Any],
    *,
    contract: SyncContract,
    limits: Any | None = None,
    store_item_id: str | None = None,
) -> Any:
    """HTML store 载荷 → Projection。payload 必须是首位位置参数（golden digest 门按此调用）。"""
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        build_store_projection as _engine,
    )

    spec = _spec_of_store_item(store_item_id or STORE_ITEM_ID)
    return _engine(spec, payload, contract=contract, limits=limits)


def merge_projection_into_store_rows(
    *,
    projection: Any,
    base_rows: list[Mapping[str, Any]],
    store_item_id: str | None = None,
) -> tuple[list[dict[str, Any]], int, int, set[str]]:
    """projection → HTML store 行（薄转发框架层引擎，含幽灵行防护）。"""
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        merge_projection_into_store_rows as _engine_merge,
    )

    spec = _spec_of_store_item(store_item_id or STORE_ITEM_ID)
    return _engine_merge(spec, projection=projection, base_rows=base_rows)


def iter_store_rows(payload: Any, *, store_item_id: str | None = None):
    """流式 (row_identity, row)（薄转发框架层引擎）。"""
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        iter_store_rows as _engine_iter,
    )

    spec = _spec_of_store_item(store_item_id or STORE_ITEM_ID)
    return _engine_iter(spec, payload)


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
        adapter=adapter,
        bundle=bundle,
        descriptor=descriptor,
        room=room,
        contract=contract,
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
        registry,
        IDENTITY,
        adapter=adapter,
        bundle=bundle,
        descriptor=descriptor,
        room=room,
        contract=contract,
    )


async def attach_pilot_adapters(
    registry: WorkpaperSyncAdapterRegistry, *, session: Any
) -> tuple[str, ...]:
    """发布链编排：attach 本 entry 的 adapter。"""
    return await HC.attach_h_entry_adapter(
        registry,
        IDENTITY,
        session=session,
        contract_payload_builder=build_contract_payload,
    )


def authority_model_payload() -> dict[str, Any]:
    return HC.authority_model_payload(IDENTITY, managed_row_table_specs())


@dataclass(frozen=True, slots=True)
class Phase5Definitions:
    template: Any
    instrumentation: Any
    authority: Any

    def as_dict(self) -> dict[str, Any]:
        return {
            "template": self.template,
            "instrumentation": self.instrumentation,
            "authority": self.authority,
        }


async def publish_definitions(publisher: Any) -> Phase5Definitions:
    return await HC.publish_definitions_for(
        IDENTITY,
        managed_row_table_specs(),
        publisher=publisher,
    )


async def resolve_published_frozen_definitions(
    session: Any,
    *,
    representation: Any = None,
    contract: SyncContract | None = None,
) -> Any:
    return await HC.resolve_published_frozen_definitions(
        IDENTITY, session=session, representation=representation, contract=contract,
    )


#: 🔴 provisioning 链必须的两个 sentinel。
PILOT_WP_CODES: Final[frozenset[str]] = WP_CODES


async def publish_pilot_definitions(publisher: Any) -> Phase5Definitions:
    """provisioning 链调此名（不是 `publish_definitions`）。"""
    return await publish_definitions(publisher)
