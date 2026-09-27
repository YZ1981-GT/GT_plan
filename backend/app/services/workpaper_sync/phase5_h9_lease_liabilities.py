# -*- coding: utf-8 -*-
"""H9 租赁负债 —— Phase 5 entry 模块（H 循环 canary，从零建）。

spec: `h-cycle-sync-foundation-and-first-canary` · Task 20

═══ 范式裁决：用 `phase5_*` 不照 H1 的 `pilot_*` ═══

H1 是 H 循环**唯一**已注册 adapter 的 entry，但它走 `pilot_h1_grouped_dynamic.py`
（`PILOT_ADAPTER_ID`）—— 那是 Tasks 40~43 四个先导之一，形态早于行表引擎。
照它会写出无法复用引擎的单例代码。本模块按 D/E/F/G 已验通 11 家的 `phase5_*` 声明式范式，
并把七段公共流程收进 `phase5_h_cycle_common`（H 要接 9 条，再抄 9 份就是 9 个漂移面）。

🔴 唯一**必须**复用 pilot 产物的是 `oo_crash_neutralization_fn`（HC-12）——
那是范式无关的 per-file 缓解件，声明在 `store_item_registry.STORE_MERGE_REGISTRY`。

═══ HC-12：H9 册裸 IF **24 格** ⇒ 必挂中性化 ═══

按生产函数 `g7_oo_crash_if_neutralize._BARE_IF_CALL` 的真实正则逐格现算 = **24**
（全 H 次少，仅多于 H6 的 12；最重的 H8 是数量级之外）。
中性化是 **per-file**（整册就地改写 substrate 副本）⇒ 即使受管表本身干净也必须挂。
🔴 BP-4（真 OO 9.4 场景集）未交付前**不得**以「裸 IF 数少」推断某册不需要。

═══ 🔴 HD-7：H9 **没有** TB 发布门 —— 本 canary 不覆盖发布链 ═══

`publishToTb` 在 H9 全链路实测 **0 处**（H8 同）。契约 `review.tb_publish_gate = None`
是**声明**而不是遗漏：roundtrip 判据据此知道「不覆盖发布链」。
发布链首例归 `h2-h6-h10-pilot-cross-reference-lanes`（该 lane 三条都有门）。

sync 路径对 `trial_balance` 的写次数必须为 **0** —— 本模块不含任何 TB 写入。

═══ HD-2 第三族读路径（canary 顺带把最复杂的先打通）═══

H9 的读路径是 `GET /render-config?force_component_type=…` 再合并
`sheets[].html_data.responses_snapshot`（宿主 `force_component_type` 命中 1 处、
`responses_snapshot` 命中 2 处），**不是** checklist GET。
写路径是 `host_inline`（宿主自己 `import http from '@/utils/http'`，`checklist_put`=1）。

═══ 🔴 幻影码 `H9L` 是真幻影码（7 条之一）═══

`find_template_file('H9L')` / `find_template_file_any('H9L')` / `find_all_template_files('H9L')`
实测全为空 ⇒ `phantom_code_resolves_to_own_workbook=False`。
（对比：`H6A` / `H10A` **同时**是真实程序表码，那两条 provider 必须显式声明 `True`，
详见 `phase5_h_cycle_common.assert_phantom_code_does_not_leak` 的口径说明。）
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from app.services.workpaper_sync import phase5_h_cycle_common as HC
from app.services.workpaper_sync import phase5_h9_02_detail as _h902
from app.services.workpaper_sync.adapters.registry import (
    AdapterRegistration,
    EntryMatcher,
    WorkpaperSyncAdapterRegistry,
)
from app.services.workpaper_sync.contracts import SyncContract, contract_path_for
from app.services.workpaper_sync.entry_profile import DescriptorFacts, RoomFacts
from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec

# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量
# ═══════════════════════════════════════════════════════════════════════════

PHASE5_WAVE: Final[str] = "phase5_lease_liability_detail"
ENTRY_ID: Final[str] = "xlsx/gt-h9-lease-liabilities"
ADAPTER_ID: Final[str] = "h9.lease_liability_detail"

#: 🔴 manifest 冻结的**幻影码**（FC-2）。`H9L` 三条 finder 路径实测全为空。
WP_CODES: Final[frozenset[str]] = frozenset({"H9L"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "H/H9 租赁负债.xlsx"
#: 逐字取 slice `authoritative_templates`（完整 64 位；67,693 B）
TEMPLATE_SHA256: Final[str] = (
    "7b1afdb49f190854160548349a24a07a65ac39f2014fbe8c1014b86c92c598a4"
)

#: canary store item（`租赁负债明细表H9-2`）
STORE_ITEM_ID: Final[str] = _h902.STORE_ITEM_ID_H902
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
ROW_IDENTITY_STORE_KEY: Final[str] = _h902.ROW_IDENTITY_STORE_KEY_H902

#: 🔴 H 循环 9 条实测 payload 全落 `remark`。
PAYLOAD_COLUMN: Final[str] = "remark"
PAYLOAD_COLUMN_MODE: Final[str] = "remark_only"

#: 🔴 HD-7 缺口：H9 无 TB 发布门（`publishToTb` 全链路 0 处）。
TB_PUBLISH_GATE: Final[None] = None

# 向后兼容别名：既有通用判据按 `EntrySelectionError` / `StorePayloadError` 取 provider 异常。
EntrySelectionError = HC.HEntrySelectionError
StorePayloadError = HC.HStorePayloadError


#: 契约 `review` 段的 H9 专属声明（HC-11 中文枚举 / derived / store-only / 模板 only）。
_EXTRA_REVIEW: Final[dict[str, Any]] = {
    # 🔴 HC-11：中文枚举域，**不得**声明为 boolean（回写会把 "否" 写成 false，前端下拉失配）
    "enum_fields": {k: list(v) for k, v in _h902.CHINESE_ENUM_FIELDS_H902.items()},
    # 🔴 HC-11：跨 entry 派生标记，OO 侧不可编辑（H8 终止租赁流程回传，改了会被覆盖）
    "derived_fields": list(_h902.DERIVED_STORE_ONLY_FIELDS_H902),
    # HTML 有字段、模板无列 ⇒ 不映射任何格（merge 只动受管列，这些字段原样保留）
    "store_only_fields": list(_h902.STORE_ONLY_FIELDS_H902),
    # 模板有列、HTML 无字段 ⇒ 不进 field_specs（Requirement 6.1 禁止无来源自造字段）
    "template_only_columns": [
        {"column": col, "header_text": text}
        for col, text in _h902.TEMPLATE_ONLY_COLUMNS_H902
    ],
    # 🔴 单元格锁标志实测事实（sheet 级保护未启用 ⇒ locked 惰性，不得据它判 mode）
    "template_cell_lock_facts": {
        key: (list(value) if isinstance(value, tuple) else value)
        for key, value in _h902.TEMPLATE_CELL_LOCK_FACTS_H902.items()
    },
    # 🔴 HC-8：该键被 H8 侧跨 entry 消费 ⇒ 键名冻结
    "frozen_cross_ref": {
        _h902.STORE_ITEM_ID_H902: [
            "useH8CrossSheet.ts",
            "useH8DisposalCheck.ts",
        ]
    },
    # HC-5：H9 主表无变体轴（实测单张）
    "variant_axis": None,
    # HD-1 / HD-2 实测载体族（守卫按族标签分派，不按文件名推断）
    "carrier": {
        "write": "host_inline",
        "read": "render_config_force_component_type",
        "tb_publish_gate": TB_PUBLISH_GATE,
    },
    # HC-13：UUID 列 = 有效内容列 + 1
    "effective_columns": _h902.EFFECTIVE_COLUMNS_H902,
    "uuid_column": _h902.UUID_COL_H902,
}

IDENTITY: Final[HC.HEntryIdentity] = HC.HEntryIdentity(
    entry_id=ENTRY_ID,
    adapter_id=ADAPTER_ID,
    phase5_wave=PHASE5_WAVE,
    wp_codes=WP_CODES,
    template_relative_path=TEMPLATE_RELATIVE_PATH,
    template_sha256=TEMPLATE_SHA256,
    primary_store_item_id=STORE_ITEM_ID,
    expected_profile_id=EXPECTED_PROFILE_ID,
    # 🔴 `H9L` 是真幻影码（三条 finder 路径实测全空）
    phantom_code_resolves_to_own_workbook=False,
    tb_publish_gate=TB_PUBLISH_GATE,
    extra_review=_EXTRA_REVIEW,
)

_HTML_STORE_NOTE: Final[str] = (
    "H9 租赁负债的结构化 Tab 行数据存成 checklist_responses 的 **remark** JSON 数组。"
    "本契约按 stable field + 行身份 `rowId` 拆开。"
    "🔴 22 个落库字段里只有 20 个映射模板列：`U 期后付款` / `V 备注` 模板有列但 HTML 无字段；"
    "`contractNo` / `assetDesc` / `ibrRate` / `leaseTerm` / `isTerminated` / "
    "`terminationDate` / `terminatedFromH8` 七个 HTML 有字段但模板无列（store-only）。"
    "🔴 6 个公式列（E/I/J/K/L/N）的 json_key **不落库** —— 前端 load 时按同一套公式重算，"
    "`formula_mask` 保证 OO 侧不被 HTML 的 None 覆盖。"
)

_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐格实测 H/H9 租赁负债.xlsx 的 `租赁负债明细表H9-2`"
    "（两级表头 R7/R8 / 数据 R9-13 共 5 行 / footer R14 合计（B..R 与 U 各 =SUM(x9:x13)）/ "
    "公式列 E·I·J·K·L·N / 有效内容列 22 即 A..V / max_column 22 / 0 个 definedName / "
    "无 Excel Table / 册内 hidden sheet GT_Custom / 数据行 locked=E·I·J·K·L·M·N 七列）"
    " + 前端 `useH9Detail.ts` 按值 grep（ROWS_KEY / _persist() 的 22 个落库字段 / "
    "_normalizeRow() 的六个公式重算 / 三个中文枚举缺省值 '否' / "
    "markTerminatedFromH8 写 terminatedFromH8）"
    " + 真库现算（checklist_responses.item_id='H9-2-rows' 的 remark 819 B / 2 行，"
    "行身份 row-liab-H91-FILL-1784691549786 与 row-mrvjayxr-u0mc 均属 HC-7 族 A）"
)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 受管 sheet 清单（灰度开关）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 canary 只放 H9-2 一张；册内其余 8 个 sheet 的处置：
#   底稿目录 / 租赁负债实质性程序表H9A       → 不接
#   审定表H9-1                              → 归后置（审定表族，同 G 的 GF-H5 裁决）
#   调整分录汇总H9-3                        → FC-6 默认 `single_html`（Tab 是 hub）
#   摊销表H9-4 / 财务费用测算H9-6 / 关联方检查H9-5 → 归后续批次
#   附注披露信息（上市公司 / 国有企业）      → 归附注披露族
#   GT_Custom（hidden）                     → 🔴 **不纳管**（HC-14 断言其存在且不纳管）

#: canary：租赁负债明细表H9-2
_INCLUDE_H902: Final[bool] = True


def managed_row_table_specs() -> tuple[Any, ...]:
    """本 entry 当前受管的行表型 spec 清单（按灰度开关）。"""
    specs: list[Any] = []
    if _INCLUDE_H902:
        specs.append(_h902.SPEC_H902)
    return tuple(specs)


def all_store_item_ids() -> tuple[str, ...]:
    """本 entry 全部 store item（**单一口径**，出/回两方向都从它取）。"""
    items: list[str] = []
    for spec in managed_row_table_specs():
        if spec.store_item_id and spec.store_item_id not in items:
            items.append(spec.store_item_id)
    return tuple(items)


def adjudication_spec() -> Any:
    """H9-1 审定表 —— 归后置批次，本 spec 恒 None。"""
    return None


def all_managed_sheet_names() -> tuple[str, ...]:
    return tuple(s.managed_sheet for s in managed_row_table_specs())


def instrumentation_specs() -> tuple[ExcelInstrumentationSpec, ...]:
    """本 entry 的全部 instrumentation 声明（**复数** —— 注册路径读的是这个）。"""
    return HC.instrumentation_specs_for(IDENTITY, managed_row_table_specs())


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


# ═══════════════════════════════════════════════════════════════════════════
# 3. 选型必要条件（照 D3/G2 同签名：`resolution` 必填、**无关闭开关**）
# ═══════════════════════════════════════════════════════════════════════════

TemplateResolutionFacts = HC.TemplateResolutionFacts


def assert_no_implicit_template_fallback(
    resolution: HC.TemplateResolutionFacts, *, wp_codes: frozenset[str] | None = None
) -> None:
    """🔴 口径见 `phase5_h_cycle_common.assert_phantom_code_does_not_leak`。

    保留本名以便与 D/E/F/G 十一家的判据措辞一致；实现委托公共骨架。
    """
    del wp_codes  # 身份已冻结在 IDENTITY 里，不接受调用方覆盖
    HC.assert_phantom_code_does_not_leak(IDENTITY, resolution)


def assert_entry_selectable(
    *,
    resolution: HC.TemplateResolutionFacts,
    manifest: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    return HC.assert_entry_selectable(IDENTITY, resolution=resolution, manifest=manifest)


# ═══════════════════════════════════════════════════════════════════════════
# 4. 契约装配
# ═══════════════════════════════════════════════════════════════════════════


def build_contract_payload() -> dict[str, Any]:
    return HC.build_contract_payload(
        IDENTITY,
        managed_row_table_specs(),
        html_store_note=_HTML_STORE_NOTE,
        reviewed_basis=_REVIEWED_BASIS,
        payload_column=PAYLOAD_COLUMN,
        payload_column_mode=PAYLOAD_COLUMN_MODE,
        payload_column_source=(
            "audit-platform/frontend/src/components/workpaper/composables/"
            "useH9Detail.ts —— `_persist()` 经宿主 onSave 写 "
            "{ item_id: 'H9-2-rows', remark: JSON.stringify(rows) }"
        ),
    )


def contract_file_path() -> Path:
    return contract_path_for(ADAPTER_ID)


def load_contract_from_disk() -> SyncContract:
    from app.services.workpaper_sync.contracts import load_contract

    return load_contract(ADAPTER_ID)


def assert_contract_file_matches_source() -> SyncContract:
    return HC.assert_contract_file_matches_source(IDENTITY, build_contract_payload())


# ═══════════════════════════════════════════════════════════════════════════
# 5. store 投影 / 合并（**薄转发**框架层，≤3 行）
# ═══════════════════════════════════════════════════════════════════════════


def _spec_of_store_item(store_item_id: str) -> Any:
    """store item → 受管 spec。未登记即抛（不静默跳过）。"""
    for spec in managed_row_table_specs():
        if spec.store_item_id == store_item_id:
            return spec
    raise HC.HEntrySelectionError(
        f"store item {store_item_id!r} 不在 H9 受管清单里；"
        f"已受管：{sorted(all_store_item_ids())}"
    )


def build_store_projection(
    payload: str | bytes | Sequence[Any],
    *,
    contract: SyncContract,
    limits: Any | None = None,
    store_item_id: str | None = None,
) -> Any:
    """HTML store 载荷 → `Projection`（薄转发框架层引擎）。

    🔴 **签名形态是刚性的**：`payload` 必须是**第一个位置参数**、`store_item_id` 走关键字。
    零回归门 `scripts/check/check_sync_provider_golden_digest.py` 按
    `mod.build_store_projection(rows, contract=contract)` 调用 —— 实测写成
    `(store_item_id, payload, *, contract)` 两位置参的 F1 / F2 在该门上直接
    `TypeError: missing 1 required positional argument: 'payload'`。
    """
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
    """流式 `(row_identity, row)`（薄转发框架层引擎）。"""
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        iter_store_rows as _engine_iter,
    )

    spec = _spec_of_store_item(store_item_id or STORE_ITEM_ID)
    return _engine_iter(spec, payload)


# ═══════════════════════════════════════════════════════════════════════════
# 6. manifest capability / adapter 注册 / attach
# ═══════════════════════════════════════════════════════════════════════════


def manifest_capability_enabled(*, manifest: Mapping[str, Any] | None = None) -> bool:
    return HC.manifest_capability_enabled(IDENTITY, manifest=manifest)


def assert_manifest_capability_enabled(
    *, manifest: Mapping[str, Any] | None = None
) -> None:
    HC.assert_manifest_capability_enabled(IDENTITY, manifest=manifest)


def build_matcher() -> EntryMatcher:
    """matcher 域：幻影码 `H9L` + `document_type="xlsx"`（FC-3 在 H 成立 ⇒ 无需 sheet_keys）。"""
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


async def resolve_published_frozen_definitions(
    *, session: Any, representation: Any, contract: SyncContract
) -> Any:
    return await HC.resolve_published_frozen_definitions(
        IDENTITY, session=session, representation=representation, contract=contract
    )


async def attach_pilot_adapters(
    registry: WorkpaperSyncAdapterRegistry, *, session: Any
) -> tuple[str, ...]:
    """发布链编排：attach H9 adapter（照 D3/G2 同构，实现委托公共骨架）。"""
    return await HC.attach_h_entry_adapter(
        registry,
        IDENTITY,
        session=session,
        contract_payload_builder=build_contract_payload,
    )
