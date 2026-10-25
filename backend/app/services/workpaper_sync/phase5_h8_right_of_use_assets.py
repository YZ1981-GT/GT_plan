"""H8 使用权资产 —— Phase 5 entry 模块（H 循环第四条，58 列全 1:1 的最规整一条）。

spec: `h4-h8-sub-entry-lanes-and-seed-identity-defects`
现算底账：同 spec 的 `evidence/h2-h4-h8-h10-mapping-facts.md` §3

═══ 与前三条的差异 ═══

1. 🔴 **58 有效列全部 1:1 映射、零 `template_only_columns`** —— 全 H 唯一。
   前端 `H8DetailRow` 的 `cost*` / `dep*` / `impair*` 三族与模板三大区块逐列同构。
   闭合自检 = 58 映射 + 0 template-only == 58 有效列（落契约 review）。
2. 🔴 **四级表头 + 四大区块**（原值 D..V / 累计折旧 W..AM / 减值准备 AN..BD /
   审定净值 BE..BF）。H4 是三区块 49 列、H9 22 列单区块、H6 16 列单区块。
3. 🔴 **数据区 20 行**（R12-R31），全 H 最长（H4 16 行、H9/H6 各 5 行）。
4. 🔴 **3 条 `H8T` 子入口**（H4 是 2 条）按 AC 1.6 复用本 entry 的 adapter。
5. 🔴 册 465,476 B，**全 H 最大**；裸 `IF(` 也是全 H 最重（主来源
   `使用权资产 租赁负债初始及后续计量（按月）H8-6`，361 行 × 16 列）⇒ 中性化必挂。

═══ 三处"看着像、其实不同"的坑（已在 sheet 声明里逐条钉住）═══

* **区块内增减去向数不同**：原值块 3 增 3 减，折旧/减值块 2 增 3 减 ——
  照抄原值块会多映一列、整块右移。
* **未审期末的 SUM 端点不同**：`K=SUM(D:G)-SUM(H:J)`（含期初 D）vs
  `AC=SUM(W:Y)-SUM(Z:AB)` —— 区块起始列不同，range 不能平移。
* **BE/BF 是审定净值不是未审净值**（`BE=S-AJ-BA` / `BF=V-AM-BD`）⇒ 映 `netBeginAud`/
  `netEndAud`；前端 `netBeginUnadj`/`netEndUnadj` 模板无列，是 store-only。
  按名字直觉映过去会把审定净值写进未审字段。

═══ 🔴 HD-7：H8 **没有** TB 发布门 ═══

`publishToTb` 在 H8 全链路实测 **0 处**（同 H9）。`H8-adj-tb-amount-{ending,opening}`
两个键是**TB 核对种子**不是发布门 —— 它们供审定表比对试算平衡表用，不写 TB。
sync 路径对 `trial_balance` 的写次数必须为 **0**；本模块不含任何 TB 写入。

═══ 幻影码 `H8R` 是真幻影码 ═══

三条 finder 路径实测全空 ⇒ `phantom_code_resolves_to_own_workbook=False`。
程序表码是 `H8A`（册内 sheet `使用权资产实质性程序表H8A`），不是 `H8R`。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from app.services.workpaper_sync import phase5_h8_02_detail as _h802
from app.services.workpaper_sync import phase5_h_cycle_common as HC
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

PHASE5_WAVE: Final[str] = "phase5_right_of_use_assets_detail"
ENTRY_ID: Final[str] = "xlsx/gt-h8-right-of-use-assets"
ADAPTER_ID: Final[str] = "h8.right_of_use_assets_detail"

WP_CODES: Final[frozenset[str]] = frozenset({"H8R"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "H/H8 使用权资产.xlsx"
#: 2026-10-01 安全净化后实测（419,735 B）：115 个断链外链公式已内化为本册引用。
TEMPLATE_SHA256: Final[str] = (
    "05abaabbc46fe8861e171ea35b580fe7c69659363ab6d85e3be096a1e23747e9"
)

STORE_ITEM_ID: Final[str] = _h802.STORE_ITEM_ID_H802
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
ROW_IDENTITY_STORE_KEY: Final[str] = _h802.ROW_IDENTITY_STORE_KEY_H802

PAYLOAD_COLUMN: Final[str] = "remark"
PAYLOAD_COLUMN_MODE: Final[str] = "dual_write_remark_and_conclusion"

#: 🔴 HD-7：H8 无 TB 发布门（`publishToTb` 全链路 0 处，同 H9）。
TB_PUBLISH_GATE: Final[None] = None

#: 🔴 AC 1.6：3 条子入口复用本 entry 的 adapter，**不新建 adapter / 不单独登记契约**。
#: 逐字取 manifest 的 `parent_duplicate` entry（按 entry_id 现算，**不按目录名推演**）：
#:   `xlsx/h8/impairment/h8-tab-recoverable`       → H8TabRecoverable.vue
#:   `xlsx/h8/measurement/h8-tab-measurement-annual`  → H8TabMeasurementAnnual.vue
#:   `xlsx/h8/measurement/h8-tab-measurement-monthly` → H8TabMeasurementMonthly.vue
#: 🔴 两条 `measurement` 子入口对应册内**同名两张** sheet
#: `使用权资产 租赁负债初始及后续计量（按年/按月）H8-6` —— 那是 HC-5 变体轴，
#: 也是本册裸 `IF(` 的主来源（按月版 361 行 × 16 列）。
#: 🔴 `H8TabImpairment` / `H8TabDepreciation*` **不在**子入口清单里（manifest 无对应
#: parent_duplicate entry）—— 早先按目录名猜成子入口是错的，实测已纠正。
SUB_ENTRY_IDS: Final[tuple[str, ...]] = (
    "xlsx/h8/impairment/h8-tab-recoverable",
    "xlsx/h8/measurement/h8-tab-measurement-annual",
    "xlsx/h8/measurement/h8-tab-measurement-monthly",
)
SUB_ENTRY_HOSTS: Final[tuple[str, ...]] = (
    "h8/impairment/H8TabRecoverable.vue",
    "h8/measurement/H8TabMeasurementAnnual.vue",
    "h8/measurement/H8TabMeasurementMonthly.vue",
)

EntrySelectionError = HC.HEntrySelectionError
StorePayloadError = HC.HStorePayloadError

_EXTRA_REVIEW: Final[dict[str, Any]] = {
    "enum_fields": {},
    "derived_fields": [],
    "store_only_fields": list(_h802.STORE_ONLY_FIELDS_H802),
    # 🔴 **空** —— 58 列全部有 store 字段（全 H 唯一）
    "template_only_columns": [],
    # 🔴 footer R32 之下的按类别 SUMPRODUCT 小计区（分组列 **A**，H4 是 B）
    "unmanaged_regions": [dict(r) for r in _h802.UNMANAGED_REGIONS_H802],
    "derived_total_keys": list(_h802.DERIVED_TOTAL_KEYS_H802),
    # 🔴 同模块但**另一张表**的 11 个键（H8-1 审定表 7 + H8-8 折旧 1 + TB 核对种子 2）
    "sibling_tables_not_managed": list(_h802.SIBLING_TABLE_KEYS_H802),
    # 🔴 与 H9/H6 不同：本键的 12 个消费方**全在 entry 内**（不是跨 entry）。
    #    冻结力度更强 —— 改名要同步改 12 个文件，其中 3 处是审定勾稽与附注推送入口。
    "frozen_intra_entry_ref": {
        _h802.STORE_ITEM_ID_H802: list(_h802.INTRA_ENTRY_CONSUMERS_H802)
    },
    "variant_axis": None,
    "carrier": {
        "write": "host_inline",
        "read": "host_inline_render_config_refetch",
        "tb_publish_gate": TB_PUBLISH_GATE,
    },
    "sub_entry_hosts": list(SUB_ENTRY_HOSTS),
    "effective_columns": _h802.EFFECTIVE_COLUMNS_H802,
    "uuid_column": _h802.UUID_COL_H802,
    "column_coverage_closure": {
        "mapped": len(_h802.FIELD_SPECS_H802),
        "template_only": len(_h802.TEMPLATE_ONLY_COLUMNS_H802),
        "effective_columns": _h802.EFFECTIVE_COLUMNS_H802,
    },
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
    #: `H8R` 三条 finder 路径实测全空（程序表码是 `H8A`）
    phantom_code_resolves_to_own_workbook=False,
    tb_publish_gate=TB_PUBLISH_GATE,
    extra_review=_EXTRA_REVIEW,
)

_HTML_STORE_NOTE: Final[str] = (
    "H8 使用权资产的结构化 Tab 行数据存成 checklist_responses 的 **remark** JSON 数组，"
    "按 stable field + 行身份 `rowId` 拆开。"
    "🔴 模板 **58 有效列全部**映射 store 字段，`template_only_columns` 为**空** —— "
    "全 H 唯一（H4 有 18 条、H9 有 2 条）。闭合自检 58 + 0 == 58。"
    "🔴 前端 19 个字段模板无列（store-only）：租赁合同要素 6 个（在 H8-4/H8-5 表）、"
    "初始计量 4 个（在 H8-6 表）、**未审净值 2 个**（模板 BE/BF 是审定口径）、"
    "其它 3 个、旧命名遗留折旧 4 个。"
    "🔴 三处易抄错已在 sheet 声明里逐条钉住：①原值块 3 增 3 减 vs 折旧/减值块 2 增 3 减；"
    "②未审期末 `K=SUM(D:G)-SUM(H:J)` 含期初 D，而 `AC=SUM(W:Y)-SUM(Z:AB)` 首格即期初，"
    "range 端点不能平移；③审定减少 `AL=Z+AI+AB+AA+AG+AH` 是**乱序但等价**，"
    "逐字保留模板原式不做整理（整理等于改模板）。"
    "🔴 `H8-adj-tb-amount-{ending,opening}` 是 **TB 核对种子**不是发布门 —— "
    "H8 `publishToTb` 全链路 0 处，sync 对 trial_balance 写 0 次。"
)

_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐格实测 H/H8 使用权资产.xlsx 的 `明细表H8-2`"
    "（四级表头 R8/R9/R10/R11 共 51 个合并域 / 数据 R12-R31 共 20 行 / footer R32 `合计` / "
    "有效内容列 58 即 A..BF（与 max_column 相等）/ 数据行公式列 17 个 / "
    "四区块 D8:V8 原值 · W8:AM8 累计折旧 · AN8:BD8 减值准备 · BE8:BF9 审定净值 / "
    "footer 之下 R33-R38 为按 **A 列**类别 SUMPRODUCT 小计区）"
    " + 前端 `useH8Detail.ts` 按值 grep（ROWS_KEY / H8DetailRow 78 字段 / "
    "H8-2-initial-total 派生键 / H8-1 审定表 7 键 + H8-8 折旧 1 键 + TB 核对种子 2 键 "
    "皆属另表）"
    " + 四项闭合自检（58 映射 + 0 template-only == 58 有效列；列序连续 A..BF 无缺口；"
    "17 个公式模板与 R12 逐字一致；58 个 header_text 与模板最下层表头逐字一致）"
    " + 真库现算（`H8-2-rows` = `[]` 2 B ⇒ 主表无行；`H8-1-rows` 3656 B / "
    "`H8-listed-categories` 137 B 属另表）"
)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 受管 sheet 清单（灰度开关）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 本轮只放 H8-2 一张；册内其余 18 个 sheet 的处置：
#   底稿目录 / 使用权资产实质性程序表H8A     → 不接
#   审定表H8-1                              → 归审定表后置族（7 个键）
#   调整分录汇总H8-3                        → FC-6 默认 `single_html`
#   租赁的识别H8-4 / 租赁期的确定H8-5        → 归后续批次
#   使用权资产 租赁负债初始及后续计量（按年/按月）H8-6 → 🔴 **同名两张**（变体轴，HC-5），
#                                             归后续批次；也是本册裸 IF 的主来源
#   租赁变更H8-7                            → 归后续批次
#   折旧测算表（不含减值 / 含减值）H8-8       → 🔴 **同名两张**（变体轴），归后续批次
#   折旧分配分析表H8-9 / 减值测算表H8-10 /
#   可收回金额测试表H8-11                    → 3 条 H8T 子入口相关，复用本 adapter
#   减少检查表H8-12 / 简化处理的租赁检查表H8-13 /
#   关联交易检查表H8-14                      → 归后续批次
#   附注披露信息（上市公司 / 国企）           → 归附注披露族

_INCLUDE_H802: Final[bool] = True


def managed_row_table_specs() -> tuple[Any, ...]:
    specs: list[Any] = []
    if _INCLUDE_H802:
        specs.append(_h802.SPEC_H802)
    return tuple(specs)


def all_store_item_ids() -> tuple[str, ...]:
    items: list[str] = []
    for spec in managed_row_table_specs():
        if spec.store_item_id and spec.store_item_id not in items:
            items.append(spec.store_item_id)
    return tuple(items)


def adjudication_spec() -> Any:
    """H8-1 审定表 —— 归后置批次，本 spec 恒 None。"""
    return None


def all_managed_sheet_names() -> tuple[str, ...]:
    return tuple(s.managed_sheet for s in managed_row_table_specs())


def instrumentation_specs() -> tuple[ExcelInstrumentationSpec, ...]:
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
    """口径见 `phase5_h_cycle_common.assert_phantom_code_does_not_leak`。"""
    del wp_codes
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
            "useH8Detail.ts —— `_persist()` 经宿主 onSave 写 "
            "{ item_id: 'H8-2-rows', remark: JSON.stringify(rows) }"
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
# 5. store 投影 / 合并（**薄转发**框架层）
# ═══════════════════════════════════════════════════════════════════════════


def _spec_of_store_item(store_item_id: str) -> Any:
    for spec in managed_row_table_specs():
        if spec.store_item_id == store_item_id:
            return spec
    raise HC.HEntrySelectionError(
        f"store item {store_item_id!r} 不在 H8 受管清单里；"
        f"已受管：{sorted(all_store_item_ids())}"
    )


def build_store_projection(
    payload: str | bytes | Sequence[Any],
    *,
    contract: SyncContract,
    limits: Any | None = None,
    store_item_id: str | None = None,
) -> Any:
    """HTML store 载荷 → `Projection`。

    🔴 签名形态刚性：`payload` 第一个位置参、`store_item_id` 走关键字。
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
    """matcher 域：幻影码 `H8R` + `document_type="xlsx"`（FC-3 在 H 成立）。"""
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
    """发布链编排：attach H8 adapter（实现委托公共骨架）。"""
    return await HC.attach_h_entry_adapter(
        registry,
        IDENTITY,
        session=session,
        contract_payload_builder=build_contract_payload,
    )


# ═══════════════════════════════════════════════════════════════════════════
# provisioning 白名单接口（approved bundle 发布侧）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 这两个名字是**硬前置**，不是装饰：
# `fix_task76_provision_projection_definitions.py` 经
# `projection_provisioning.load_projection_supply()` **只认** `publish_pilot_definitions`
# 与 `PILOT_WP_CODES`，缺任一即抛 `ProviderModuleNotAllowedError: provider 是空壳`，
# 且该脚本连 `--check`（只读）都 fail closed 在第一个缺口上 ⇒ 缺这两行，本 entry 永远
# 拿不到 approved bundle，`register_from_manifest()` 也就永远注册不上。
#
# 实现在 `phase5_h_cycle_common.publish_definitions_for`（九条共用一份，逐行对照
# `phase5_entry_orchestration.publish_definitions`）。`specs` 必须与
# `build_contract_payload` 同源 —— 两者都用 `managed_row_table_specs()`。


async def publish_pilot_definitions(publisher: Any) -> HC.HDefinitions:
    """发布本 entry 的四段 definition + approved bundle。"""
    return await HC.publish_definitions_for(
        IDENTITY,
        managed_row_table_specs(),
        publisher=publisher,
        contract_payload_builder=build_contract_payload,
    )


PILOT_WP_CODES = WP_CODES
