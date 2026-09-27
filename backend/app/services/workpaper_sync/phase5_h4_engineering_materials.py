"""H4 工程物资 —— Phase 5 entry 模块（H 循环第三条，首个四级表头 + 三区块宽表）。

spec: `h4-h8-sub-entry-lanes-and-seed-identity-defects`
现算底账：`.kiro/specs/h4-h8-sub-entry-lanes-and-seed-identity-defects/evidence/
h2-h4-h8-h10-mapping-facts.md`

═══ 与 H9 / H6 的差异（照抄会静默出错）═══

1. 🔴 **四级表头**（R8/R9/R10/R11）。H9/H6 都是两级。这是 `contracts.MAX_HEADER_ROWS`
   从 3 扩到 4 之后的首个真实消费者 —— 若 schema 回退到 3，本 entry 直接无法表达。
2. 🔴 **49 有效列、三区块**（原值 E..AH / 减值准备 AI..AS / 期末净值 AT..AU）。
   H9 是 22 列单区块、H6 是 16 列单区块。
3. 🔴 **18 个 template-only 列**（模板有列、HTML 无字段），主体是调整/审定块的
   **数量列与单价列** —— 前端在那些位置只有金额标量。
   映射覆盖自检：31 映射 + 18 template-only = **49 = 有效列数**，恰好闭合。
4. 🔴 **footer 之后还有不受管区域 R29-R34**（按类别 SUMPRODUCT 小计）。
   H9/H6 的 footer 之下无内容。见 `phase5_h4_02_detail.UNMANAGED_REGIONS_H402`。
5. 载体是 `formdata_composable`（H9/H6 都是 `host_inline`）⇒ flush 钩子取
   composable 的导出而不是宿主内联函数。
6. 🔴 **2 条 `H4T` 子入口**（`H4TabImpairment` / `H4TabRecoverable`）按 AC 1.6
   复用本 entry 的 adapter —— 不新建 adapter，也不给子入口单独登记契约。

═══ HC-12：H4 册裸 `IF(` ⇒ 必挂中性化 ═══

中性化是 **per-file**（整册就地改写 substrate 副本），点同册任一 sheet 的在线编辑都会
触发整册加载 ⇒ 受管表自身干净也必须挂。函数与 G7/G2/H9/H6 **共用一个**，不新造。

═══ 幻影码 `H4E` 是真幻影码 ═══

与 `H6A` / `H10A`（同时是真实程序表码）不同，`H4E` 三条 finder 路径实测全空
⇒ `phantom_code_resolves_to_own_workbook=False`。
程序表码是 `H4A`（册内 sheet `工程物资实质性程序表H4A`），不是 `H4E`。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from app.services.workpaper_sync import phase5_h4_02_detail as _h402
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

PHASE5_WAVE: Final[str] = "phase5_engineering_materials_detail"
ENTRY_ID: Final[str] = "xlsx/gt-h4-engineering-materials"
ADAPTER_ID: Final[str] = "h4.engineering_materials_detail"

WP_CODES: Final[frozenset[str]] = frozenset({"H4E"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "H/H4 工程物资.xlsx"
#: 逐字取 openpyxl 现算（112,937 B）
TEMPLATE_SHA256: Final[str] = (
    "c2c3ee61b33f4a7ca2603359810207bfb14f189c464135e0ede3e0a738c658cc"
)

STORE_ITEM_ID: Final[str] = _h402.STORE_ITEM_ID_H402
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
ROW_IDENTITY_STORE_KEY: Final[str] = _h402.ROW_IDENTITY_STORE_KEY_H402

PAYLOAD_COLUMN: Final[str] = "remark"
PAYLOAD_COLUMN_MODE: Final[str] = "dual_write_remark_and_conclusion"

#: 🔴 HD-7：H4 无 TB 发布门（`publishToTb` 在 H4 链路 0 处；发布链首例是 H6）。
TB_PUBLISH_GATE: Final[None] = None

#: 🔴 AC 1.6：2 条子入口复用本 entry 的 adapter，**不新建 adapter / 不单独登记契约**。
SUB_ENTRY_HOSTS: Final[tuple[str, ...]] = (
    "h4/impairment/H4TabImpairment.vue",
    "h4/impairment/H4TabRecoverable.vue",
)

EntrySelectionError = HC.HEntrySelectionError
StorePayloadError = HC.HStorePayloadError

_EXTRA_REVIEW: Final[dict[str, Any]] = {
    # 本表无中文枚举字段（`aging` / `quality` 是自由文本；模板 AW 的括号内容是提示不是值域）
    "enum_fields": {},
    "derived_fields": [],
    "store_only_fields": list(_h402.STORE_ONLY_FIELDS_H402),
    # 🔴 18 条：调整/审定块的数量列与单价列 + 序号 + 减值调整三列 + 减值审定三列
    "template_only_columns": [
        {"column": col, "header_text": text}
        for col, text in _h402.TEMPLATE_ONLY_COLUMNS_H402
    ],
    # 🔴 footer 之下的按类别 SUMPRODUCT 小计区 —— 不受管、不比对、不覆盖
    "unmanaged_regions": [dict(r) for r in _h402.UNMANAGED_REGIONS_H402],
    "derived_total_keys": list(_h402.DERIVED_TOTAL_KEYS_H402),
    # 🔴 `H4-3-rows` 是**另一张表**（调整分录汇总 H4-3），不是本表的合计副本，
    #    也不在本轮受管面 —— 登记它是为了让后续批次不把它误当派生键跳过。
    "sibling_tables_not_managed": ["H4-3-rows"],
    "variant_axis": None,
    "carrier": {
        "write": "formdata_composable",
        "read": "formdata_composable",
        "tb_publish_gate": TB_PUBLISH_GATE,
    },
    "sub_entry_hosts": list(SUB_ENTRY_HOSTS),
    "effective_columns": _h402.EFFECTIVE_COLUMNS_H402,
    "uuid_column": _h402.UUID_COL_H402,
    # 🔴 覆盖闭合自检（判据可复算）：映射列 + template-only 列 == 有效列数
    "column_coverage_closure": {
        "mapped": len(_h402.FIELD_SPECS_H402),
        "template_only": len(_h402.TEMPLATE_ONLY_COLUMNS_H402),
        "effective_columns": _h402.EFFECTIVE_COLUMNS_H402,
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
    #: `H4E` 三条 finder 路径实测全空（程序表码是 `H4A`，不是 `H4E`）
    phantom_code_resolves_to_own_workbook=False,
    tb_publish_gate=TB_PUBLISH_GATE,
    extra_review=_EXTRA_REVIEW,
)

_HTML_STORE_NOTE: Final[str] = (
    "H4 工程物资的结构化 Tab 行数据存成 checklist_responses 的 **remark** JSON 数组，"
    "按 stable field + 行身份 `rowId` 拆开。"
    "🔴 模板 49 有效列中 **31 列**映射 store 字段、**18 列** template-only —— "
    "两数相加恰等于 49（覆盖闭合，见 review.column_coverage_closure）。"
    "18 条 template-only 的主体是**调整/审定块的数量列与单价列**："
    "前端在那些位置只有金额标量（`useH4Detail.ts#L63` 注释『调整（金额口径 AJE）』+ "
    "`#L140 auditedBegin = calcAuditedAmount(beginAmount, ajeBegin, 0)` 以金额为基）。"
    "🔴 把 `ajeBegin` 映到数量列 Q 会把金额写进数量格，且单价公式 `=金额/数量` "
    "立刻算出荒谬单价 —— 该映射由代码定死，不是命名推测。"
    "🔴 `ajeImpair` 是 store-only：前端把减值调整压成一个字段，模板却是 "
    "AM 期初调整 + AN 账项增加 + AO 账项减少三列且 AS 走 `=AP+AQ-AR`，一对三无法确定分摊。"
    "🔴 footer R28 之下的 R29-R34 是按类别 SUMPRODUCT 小计区，**不受管**。"
)

_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐格实测 H/H4 工程物资.xlsx 的 `明细表H4-2`"
    "（四级表头 R8/R9/R10/R11 / 数据 R12-R27 共 16 行 / footer R28 `合计` / "
    "有效内容列 49 即 A..AW（max_column=67 是空列尾巴）/ 数据行公式列 25 个 / "
    "三区块 E8:AH8 原值 · AI8:AS8 减值准备 · AT8:AU9 期末净值 / "
    "尾列 AV 库龄 · AW 品质状况 / footer 之下 R29-R34 为按类别 SUMPRODUCT 小计区）"
    " + 前端 `useH4Detail.ts` 按值 grep（ROWS_KEY / H4DetailRow 43 字段 / "
    "L63 注释确立金额口径 / L140-151 六个 calcAuditedAmount·calcNetBookValue 算式 / "
    "四个 H4-2-*-total 派生键 / H4-3-rows 属另一张表）"
    " + 覆盖闭合自检（31 映射 + 18 template-only == 49 有效列，无重复无交叠）"
)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 受管 sheet 清单（灰度开关）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 本轮只放 H4-2 一张；册内其余 11 个 sheet 的处置：
#   底稿目录 / 工程物资实质性程序表H4A      → 不接
#   审定表H4-1                              → 归审定表后置族
#   调整分录汇总H4-3                        → FC-6 默认 `single_html`（Tab 是 hub）
#   增加检查表H4-4 / 减少检查表H4-5 / 盘点检查表H4-6 → 归后续批次
#   减值测算表H4-7 / 可收回金额测试表H4-8   → 两条 H4T 子入口的 sheet，复用本 adapter
#   关联交易检查表H4-9                      → 归后续批次
#   附注披露信息（上市公司 / 国有企业）      → 归附注披露族

_INCLUDE_H402: Final[bool] = True


def managed_row_table_specs() -> tuple[Any, ...]:
    specs: list[Any] = []
    if _INCLUDE_H402:
        specs.append(_h402.SPEC_H402)
    return tuple(specs)


def all_store_item_ids() -> tuple[str, ...]:
    items: list[str] = []
    for spec in managed_row_table_specs():
        if spec.store_item_id and spec.store_item_id not in items:
            items.append(spec.store_item_id)
    return tuple(items)


def adjudication_spec() -> Any:
    """H4-1 审定表 —— 归后置批次，本 spec 恒 None。"""
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
            "useH4Detail.ts —— `_persist()` 经 onSave 写 "
            "{ item_id: 'H4-2-rows', remark: JSON.stringify(rows) }"
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
        f"store item {store_item_id!r} 不在 H4 受管清单里；"
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

    🔴 签名形态刚性：`payload` 第一个位置参、`store_item_id` 走关键字
    （零回归门按 `mod.build_store_projection(rows, contract=contract)` 调用）。
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
    """matcher 域：幻影码 `H4E` + `document_type="xlsx"`（FC-3 在 H 成立）。"""
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
    """发布链编排：attach H4 adapter（实现委托公共骨架）。"""
    return await HC.attach_h_entry_adapter(
        registry,
        IDENTITY,
        session=session,
        contract_payload_builder=build_contract_payload,
    )
