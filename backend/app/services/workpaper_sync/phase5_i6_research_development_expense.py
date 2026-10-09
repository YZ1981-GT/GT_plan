# -*- coding: utf-8 -*-
"""I6 研发费用 —— Phase 5 entry 模块（I 循环 canary，从零建）。

spec: `i-cycle-sync-foundation-and-first-canary` · Task 20 / 22

═══ 范式裁决：`phase5_*` + 复用 H 循环公共骨架 ═══

I 循环**无 pilot**（四个 pilot 是 B60/D2/H1/G7，逐文件读 `review.entry_id` 无一条属 I），
所以没有「照哪个 pilot 抄」的问题。本模块按 D/E/F/G/H 已验通的 `phase5_*` 声明式范式，
七段公共流程直接复用 `phase5_h_cycle_common`（实测**零 H 硬编码**，类名带 H 只是历史命名）。

🔴 唯一**必须**复用 pilot 产物的是 `oo_crash_neutralization_fn`（IC-9）——
那是范式无关的 per-file 缓解件，声明在 `store_item_registry.STORE_MERGE_REGISTRY`。

═══ IC-9：I6 册裸 IF **45 格** ⇒ 必挂中性化 ═══

按生产函数 `g7_oo_crash_if_neutralize._BARE_IF_CALL` 的真实正则逐格现算
（口径 = `findall`，同格内嵌套 `IF(IF(…))` 算 2 次）= **45**（全 I 最少；最重的 I1 是 321）。
中性化是 **per-file**（整册就地改写 substrate 副本）⇒ 即使受管表本身只有 10 个 IF 也必须挂。
🔴 **不得**以「裸 IF 少」推断某册不需要；整册统一挂也不行（I1 的 321 与 I6 的 45 差 7 倍）。

═══ 🔴 GC-9 在 I 反向：I6 **有** TB 发布门 ⇒ canary 直接覆盖发布链 ═══

I 循环 **6/6 全有发布门**（与 H 的 H8/H9 完全无门相反）。
I6 的门实测在 `composables/useI6Adjudication.ts`（`publishToTb` ×3）
+ `i6/core/I6TabAdjudication.vue`（×2）⇒ 发布链**不外移首例**。

发布只走 `POST /api/workpapers/{wpId}/audit-determination/publish-to-tb` + 必经二次确认；
🔴 **禁**在 `watch` / `onMounted` / debounce 回调内发布（复用平台既有 2 道 CI 守卫）。
sync 路径对 `trial_balance` 的写次数必须为 **0** —— 本模块不含任何 TB 写入。

═══ IC-2 载体族：`host_inline` 写 + `render_config_refetch` 读 ═══

I 循环载体**二分**（不是 H 的四族）：5 条 `host_inline`（含 I6）+ 1 条 `formdata_composable`（只有 I5）。
I6 宿主 `GtI6ResearchDevelopmentExpense.vue` 自己 `import http from '@/utils/http'` 并 PUT；
读路径先看 `props.htmlData.allResponses`，无则 `GET /render-config?force_component_type=…`。

🔴 **6 宿主 `checklist-responses` 的 GET 命中数 == 0** —— 这个 0 是判据的一部分不是省略。
照 H 的「载体里必须有 checklist GET」会对 I 全部 6 条假红。

═══ 🔴 BP-5②：`useI6FormData.ts` 是双零消费死代码，禁接 ═══

它 448 行、含完整 checklist GET/PUT + trial-balance/writeback 管道，但
**import 生产消费 0 / import 测试消费 0**（按 import 路径字面量三形态现算，禁符号名 grep）。
接到它上面会让宿主行为一点不变、而守卫因「文件确实被改了」全绿 = **假绿第①源**。
契约 `forbidden_carriers` 显式禁接。

═══ IC-4：读认两键、写只写主键 ═══

`useI6Detail.ts` 同时有 `STORAGE_KEY = 'I6-2-detail-rows'`（主键）与
`LEGACY_STORAGE_KEY = 'I6-2-rows'`（读兼容）。契约声明 legacy alias 是为了
「读兼容不能悄悄消失」—— 删了它历史数据读不出。

🔴 **主键被 5 个跨 entry 消费方读**，其中 `h1DepAllocCounterpartPull.ts` 属 **H1 pilot**
（adapter 已注册、golden 已锁）⇒ 键名冻结，任何改动完成后回归 H1 契约 golden digest，
且**不得修改 H1 的契约 / adapter / golden**。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Final, Mapping

from app.services.workpaper_sync import phase5_h_cycle_common as HC
from app.services.workpaper_sync import phase5_i6_02_detail as _i602
from app.services.workpaper_sync.adapters.registry import (
    AdapterRegistration,
    EntryMatcher,
    WorkpaperSyncAdapterRegistry,
)
from app.services.workpaper_sync.contracts import SyncContract
from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec

# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量
# ═══════════════════════════════════════════════════════════════════════════

PHASE5_WAVE: Final[str] = "phase5_research_development_expense_detail"
ENTRY_ID: Final[str] = "xlsx/gt-i6-research-development-expense"
ADAPTER_ID: Final[str] = "i6.research_development_expense_detail"

#: 🔴 manifest 冻结的**幻影码**（FC-2）。`I6R` 三条 finder 路径实测全为空。
WP_CODES: Final[frozenset[str]] = frozenset({"I6R"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "I/I6 研发费用.xlsx"
#: 逐字现算（完整 64 位；87,268 B —— 全 I 最小册）
TEMPLATE_SHA256: Final[str] = (
    "924a1e8348a897c268dcef7231c6c3d0db2f8382446a729d051e825ea71748eb"
)

#: canary store item（`明细表I6-2`）
STORE_ITEM_ID: Final[str] = _i602.STORE_ITEM_ID_I602
EMPTY_STORE_PAYLOAD: Final[str] = _i602.EMPTY_PAYLOAD_I602
ROW_IDENTITY_STORE_KEY: Final[str] = _i602.ROW_IDENTITY_STORE_KEY_I602

#: 🔴 I 循环真库 7 行实测 payload 全落 `remark`、`conclusion` 全 NULL。
PAYLOAD_COLUMN: Final[str] = "remark"
PAYLOAD_COLUMN_MODE: Final[str] = "remark_only"

#: 🔴 GC-9 在 I 反向：I6 **有** TB 发布门。
TB_PUBLISH_GATE: Final[str] = (
    "composables/useI6Adjudication.ts + i6/core/I6TabAdjudication.vue"
)

# 向后兼容别名：既有通用判据按 `EntrySelectionError` / `StorePayloadError` 取 provider 异常。
EntrySelectionError = HC.HEntrySelectionError
StorePayloadError = HC.HStorePayloadError


#: 契约 `review` 段的 I6 专属声明。
_EXTRA_REVIEW: Final[dict[str, Any]] = {
    # 🔴 IC-4：读认两键、写只写主键（删 legacy alias 会让历史数据读不出）
    "legacy_alias_item_id": _i602.LEGACY_STORE_ITEM_ID_I602,
    # 🔴 IC-7③：真库那 2 行原本既无 id 也无 rowId，已一次性 backfill（Task 19）
    "identity_backfill_required": True,
    "identity_backfill_done": "i6-detail-bf01-zhptyd / i6-detail-bf02-xplcsy",
    # 🔴 IC-17：键名冻结（5 消费方中 4 个不属 I6，含已注册 adapter 的 H1 pilot）
    "frozen_key": True,
    "frozen_cross_ref": {
        _i602.STORE_ITEM_ID_I602: [
            "expenseWpI1AmortPull.ts",
            "h1DepAllocCounterpartPull.ts",
            "h8DepAllocCounterpartPull.ts",
            "i1AmortAllocCounterpartPull.ts",
            "useI2Analysis.ts",
        ]
    },
    # 🔴 BP-5②：双零消费死代码，禁接（假绿第①源）
    "forbidden_carriers": ["composables/useI6FormData.ts"],
    # HTML 有字段、模板无列 ⇒ 不映射任何格
    "store_only_fields": list(_i602.STORE_ONLY_FIELDS_I602),
    # 模板有列、HTML 无字段 ⇒ 只进 formula_mask 不进 field_specs（D4-2 同源口径）
    "template_only_columns": [
        {"column": col, "header_text": text}
        for col, text in _i602.TEMPLATE_ONLY_FORMULA_COLUMNS_I602
    ],
    # 🔴 单元格锁标志实测事实（保护未启用 ⇒ locked 惰性，不得据它判 mode）
    "template_cell_lock_facts": dict(_i602.TEMPLATE_CELL_LOCK_FACTS_I602),
    # 🔴 IC-13：双 footer 事实声明（引擎锚点只取 R19，R20 是 R19 的派生）
    "footer_rows": list(_i602.FOOTER_ROWS_FACT_I602),
    "footer_kinds": {str(k): v for k, v in _i602.FOOTER_KINDS_FACT_I602.items()},
    "footer_labels": {str(k): v for k, v in _i602.FOOTER_LABELS_FACT_I602.items()},
    # 🔴 IC-13 登记不修的两处模板小缺陷
    "known_template_quirks": list(_i602.KNOWN_TEMPLATE_QUIRKS_I602),
    # IC-8①：月度矩阵同源引用（H10-2 / F5-2 / D4-2）
    "monthly_matrix": {
        "columns": [chr(ord("B") + i) for i in range(12)],
        "annual_total_column": "N",
        "json_path_form": "months/0..months/11",
        "rule_ref": "D4-2 已验通范式；json_path 是唯一数组段真源",
    },
    # 🔴 IC-8②：中英双字段名（中文键是历史/导入路径形态，英文是当前真库形态）
    "field_name_aliases": {"类别": "category", "本期审定": "auditedAmount"},
    # IC-5 / CD-4 = BP-8①：分类枚举后 4 条无真源（不阻塞 canary —— 分类只作字段值不是行身份）
    "classification": {
        "impl_constant": "I6_DETAIL_DEFAULT_CATEGORIES",
        "source_ref": "明细表I6-2!A9:A12",
        "verdict": "PREFIX_MATCH_WITH_UNSOURCED_TAIL",
        "status": "defect_registered_not_fixed",
        "note": (
            "源只有 4 条（人工费/材料费/制造费用分摊/无形资产摊销，A13:A18 六格实测全空）；"
            "impl 后 4 条（设计费/装备调试费/委外研发费/其他）无真源。"
            "分类只作 category 字段值、不是行身份 ⇒ 不阻塞 canary。"
        ),
    },
    # HC-5 / IC-11：I6 主表无变体轴（同尾码双 sheet 在 I 循环 0 组）
    "variant_axis": None,
    # IC-2 实测载体族（守卫按族标签分派，不按文件名推断）
    "carrier": {
        "write": "host_inline",
        "write_client": "http",
        "read": "host_inline_render_config_refetch",
        "force_component_type": "i6-research-development-expense",
        "tb_publish_gate": TB_PUBLISH_GATE,
        "mounts": 2,
        # 🔴 这个 0 是判据的一部分：照 H 的「载体里必须有 checklist GET」会对 I 全 6 条假红
        "host_checklist_get_hits": 0,
    },
    # IC-10 / HC-13：UUID 列 = 有效内容列 + 1（不得放 max_column+1）
    "effective_columns": _i602.EFFECTIVE_COLUMNS_I602,
    "max_column": _i602.MAX_COLUMN_I602,
    "uuid_column": _i602.UUID_COL_I602,
    # IC-18：现算 3 个，禁写死阈值
    "derived_total_keys": [
        "I6-1-audited-total",
        "I6-adj-audited-total",
        "I6-adj-expected-total",
    ],
    # IC-10：definedName 基线不增长口径（本册 0；I4=476 / I5=334 才是非零基线）
    "defined_name_baseline": 0,
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
    # 🔴 `I6R` 是真幻影码（三条 finder 路径实测全空）
    phantom_code_resolves_to_own_workbook=False,
    tb_publish_gate=TB_PUBLISH_GATE,
    extra_review=_EXTRA_REVIEW,
)

_HTML_STORE_NOTE: Final[str] = (
    "I6 研发费用的结构化 Tab 行数据存成 checklist_responses 的 **remark** JSON 数组。"
    "本契约按 stable field + 行身份 `id`（🔴 不是 `rowId`）拆开。"
    "🔴 22 个受管字段里 12 个是月度列，json_key 走**数组下标** `months/0`..`months/11`"
    "（同 D4-2；读写必须走 `app.services.workpaper_sync.json_path`，禁私有 dict-only 副本）。"
    "🔴 4 个公式列（N/Q/R/W）在前端 `I6DetailStoredRow` 里**无对应字段** —— 前端 load 时"
    "按同一套公式重算，`formula_mask` 保证 OO 侧不被 HTML 的 None 覆盖；它们只进 "
    "`formula_columns` 不进 `field_specs`。反之 `expenseNature` 是 store 有字段、模板无列 "
    "⇒ `store_only_fields`（前端行类型注释把它标为「X列」有误，X 列实测是 `个别报表下的重分类`）。"
)

_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐格实测 I/I6 研发费用.xlsx 的 `明细表I6-2`"
    "（**单级**表头 R8 / 数据 R9-18 共 10 行 / footer R19 合计（B..Y 各 =SUM(x9:x18)）+ "
    "🔴 R20「各月比例」第二派生行（B..N 各 =IF($N$19=0,0,x19/$N$19)）/ "
    "公式列 N·Q·R·W（R 的分母是 footer 绝对引用 $Q$19）/ 有效内容列 26 即 A..Z / "
    "max_column 65（有效与 max 差 39 列全空 ⇒ UUID 放 AA 不放 66）/ 84 公式 / merged 2 / "
    "裸 IF 45（findall 口径，全 I 最少）/ 0 个 definedName / 无 Excel Table / "
    "册内 hidden sheet GT_Custom / ws.protection.sheet=False ⇒ 数据行 locked 全惰性）"
    " + 前端 `useI6Detail.ts` 按值 grep（STORAGE_KEY='I6-2-detail-rows' + "
    "LEGACY_STORAGE_KEY='I6-2-rows' / 身份字段 `id` / removeRow(id: string) / "
    "I6DetailStoredRow 的 13 个落库字段含 months 数组 / 中英双字段名 r.类别||r.category 与 "
    "r.本期审定??r.auditedAmount）"
    " + 真库现算（checklist_responses.item_id='I6-2-detail-rows' 的 remark 194 B / 2 行；"
    "🔴 原载荷既无 id 也无 rowId，已在 Task 19 一次性 backfill 为 "
    "i6-detail-bf01-zhptyd / i6-detail-bf02-xplcsy）"
)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 受管 sheet 清单（灰度开关）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 canary 只放 I6-2 一张；册内其余 10 个 sheet 的处置：
#   底稿目录 / 研发费用实质性程序 I6A          → 不接
#   审定表I6-1                                → 归后置（审定表族）
#   调整分录汇总I6-3                          → FC-6 默认 `single_html`（Tab 是 hub）
#   其他针对性检查表I6-4                      → 归后续批次
#   截止性测试（账到单据）I6-5 / （单据到账）I6-6 → 归后续批次
#   附注披露（上市公司 / 国有企业）            → 归附注披露族
#   GT_Custom（hidden）                       → 🔴 **不纳管**

#: canary：明细表I6-2
_INCLUDE_I602: Final[bool] = True


def managed_row_table_specs() -> tuple[Any, ...]:
    """本 entry 当前受管的行表型 spec 清单（按灰度开关）。"""
    specs: list[Any] = []
    if _INCLUDE_I602:
        specs.append(_i602.SPEC_I602)
    return tuple(specs)


def all_store_item_ids() -> tuple[str, ...]:
    """本 entry 全部 store item（**单一口径**，出/回两方向都从它取）。"""
    items: list[str] = []
    for spec in managed_row_table_specs():
        if spec.store_item_id and spec.store_item_id not in items:
            items.append(spec.store_item_id)
    return tuple(items)


def adjudication_spec() -> Any:
    """I6-1 审定表 —— 归后置批次，本 spec 恒 None。"""
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
# 3. 选型必要条件
# ═══════════════════════════════════════════════════════════════════════════

TemplateResolutionFacts = HC.TemplateResolutionFacts


def assert_no_implicit_template_fallback(
    resolution: HC.TemplateResolutionFacts, *, wp_codes: frozenset[str] | None = None
) -> None:
    """保留本名以与 D/E/F/G/H 十二家的判据措辞一致；实现委托公共骨架。"""
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
            "audit-platform/frontend/src/components/workpaper/composables/useI6Detail.ts"
            " —— `_persist()` 经宿主 onSave 写 "
            "{ item_id: 'I6-2-detail-rows', remark: JSON.stringify(storedRows) }"
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
# 5. manifest capability
# ═══════════════════════════════════════════════════════════════════════════


def manifest_capability_enabled(*, manifest: Mapping[str, Any] | None = None) -> bool:
    return HC.manifest_capability_enabled(IDENTITY, manifest=manifest)


def assert_manifest_capability_enabled(
    *, manifest: Mapping[str, Any] | None = None
) -> None:
    HC.assert_manifest_capability_enabled(IDENTITY, manifest=manifest)


# ═══════════════════════════════════════════════════════════════════════════
# 6. adapter 注册
# ═══════════════════════════════════════════════════════════════════════════


def build_matcher() -> EntryMatcher:
    return HC.build_matcher(IDENTITY)


def build_registration(
    *, manifest: Mapping[str, Any] | None = None
) -> AdapterRegistration:
    return HC.build_registration(IDENTITY, manifest=manifest)


def register_adapter(
    registry: WorkpaperSyncAdapterRegistry,
    *,
    manifest: Mapping[str, Any] | None = None,
) -> AdapterRegistration:
    return HC.register_adapter(IDENTITY, registry, manifest=manifest)


async def attach_pilot_adapters(
    registry: WorkpaperSyncAdapterRegistry, *, session: Any
) -> tuple[str, ...]:
    """发布链编排：attach 本 entry 的 adapter（照 H 循环 9 条同构，实现委托公共骨架）。

    🔴 符号名必须是 `attach_pilot_adapters` —— `adapters/registry.py` 的 `_attach_of()`
    按这个**固定名字**从白名单模块里取（不是按 `register_adapter`），
    `test_registrar_delegates_to_each_entry_own_attach` 逐 provider 核它存在。

    🔴 第③环（published representation）缺供给时公共骨架**返回空元组**而不是伪造通过 ——
    BP-1~BP-3 是平台级欠账，如实登记为 `upstream_gap`。
    """
    return await HC.attach_h_entry_adapter(
        registry,
        IDENTITY,
        session=session,
        contract_payload_builder=build_contract_payload,
    )


async def resolve_published_frozen_definitions(
    *, session: Any, representation: Any, contract: SyncContract
) -> Any:
    """读已发布的冻结身份（照 H 循环 9 条同构，实现委托公共骨架）。

    🔴 **薄委托**：函数体只有一条 `return await HC.<同名>(...)`。
    `test_task75_published_identity_observer` 的 `implementing_node()` 据此把四条判据
    转移到骨架那层执行（真 await 共享观测器 / 真做 contract digest 比对 / raise 在条件
    分支里 / 不返回 None）。这里**多写一条语句**就会被判为「provider 自有实现」，
    转而按严格判据核本函数 —— 那是故意的：借薄委托外壳偷塞逻辑必须打红。

    🔴 **不得**在本函数里抄 loader 九步（`ExcelEntryDefinitionLoader` /
    `assert_no_structure_drift` / `parse_identity_inventory` / `structure_fingerprint`）
    —— 抄一遍就是第二真源，任一侧被短路都不改变行为。
    """
    return await HC.resolve_published_frozen_definitions(
        IDENTITY, session=session, representation=representation, contract=contract
    )


# ═══════════════════════════════════════════════════════════════════════════
# ── 五环发布面（委托 HC，2026-10-01）
#
# 🔴 硬前置：`projection_provisioning.load_projection_supply()` 只认
#    `publish_pilot_definitions` + `PILOT_WP_CODES`；`projection_first_publication`
#    另要 `instrumentation_spec()`（单数 = 主表）与 `build_store_projection`。
#    实现全在 `phase5_h_cycle_common`，这里只写薄委托（与 J1 / L1 同形，不复制逻辑）。
# ═══════════════════════════════════════════════════════════════════════════


def instrumentation_spec() -> ExcelInstrumentationSpec:
    return HC.primary_instrumentation_spec(IDENTITY, managed_row_table_specs())


def build_store_projection(
    payload: Any,
    *,
    contract: SyncContract,
    limits: Any | None = None,
    store_item_id: str | None = None,
) -> Any:
    """🔴 `payload` 必须是首位位置参数（golden digest 门按此调用）。"""
    return HC.build_store_projection_for(
        IDENTITY,
        managed_row_table_specs(),
        payload,
        contract=contract,
        limits=limits,
        store_item_id=store_item_id,
    )


def merge_projection_into_store_rows(
    *, projection: Any, base_rows: list, store_item_id: str | None = None
) -> Any:
    return HC.merge_projection_into_store_rows_for(
        IDENTITY,
        managed_row_table_specs(),
        projection=projection,
        base_rows=base_rows,
        store_item_id=store_item_id,
    )


def iter_store_rows(payload: Any, *, store_item_id: str | None = None) -> Any:
    return HC.iter_store_rows_for(
        IDENTITY, managed_row_table_specs(), payload, store_item_id=store_item_id
    )


async def publish_definitions(publisher: Any) -> HC.HEntryDefinitions:
    return await HC.publish_h_entry_definitions(
        IDENTITY,
        managed_row_table_specs(),
        publisher=publisher,
        contract_payload_builder=build_contract_payload,
    )


publish_pilot_definitions = publish_definitions

#: 首版发布 binding 装配读的两个 provider 常量（与 J1 / L1 同名）。🔴 必须有：
#: `ExcelInstrumentationSpec` 的字段名是 `uuid_col`，而 `projection_first_publication`
#: 按 `spec.uuid_column or provider.UUID_COL` 取 ⇒ 缺这个常量时 UUID 列解析为 None，
#: 首版发布炸在 `excel_entry_identity_inventory_invalid`（I6 实测）。
#: 多受管表（I5）时 `ROWS_TABLE_KEY` 指向主表，其余由 sibling binding 覆盖。
UUID_COL: Final[str] = instrumentation_spec().uuid_col
ROWS_TABLE_KEY: Final[str] = managed_row_table_specs()[0].table_key
PILOT_WP_CODES = WP_CODES
