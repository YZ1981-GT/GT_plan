"""H6 固定资产清理 —— Phase 5 entry 模块（H 循环第二条，**发布链首例**）。

spec: `h2-h6-h10-pilot-cross-reference-lanes`

═══ 与 canary H9 的三处实质差异（照抄 H9 会静默出错的地方）═══

1. 🔴 **`H6A` 不是幻影码** —— 它同时是**真实程序表码**，`find_template_file('H6A')`
   解析到 H6 自己的册（`固定资产清理实质性程序表H6A` 是册内 sheet）。
   ⇒ `phantom_code_resolves_to_own_workbook=True`。照 G2 的「幻影码不得命中任何模板」
   写会让本 provider 注册时**直接抛**；正确不变量是「不得命中**别的 entry** 的册子」，
   实现见 `phase5_h_cycle_common.assert_phantom_code_does_not_leak`。
2. 🔴 **审定期末公式是资产口径** `L = I+J-K`（H9 是负债口径 `L = I-J+K`）。
   见 `phase5_h6_02_detail.FORMULA_TEMPLATES_H602` 的说明。
3. 🔴 **有 TB 发布门** —— H6 的审定数经 `H6TabAdjudication → useH6Adjudication.publishToTb`
   走显式发布门（POST 科目 1606，中文二次确认）。H8/H9 两条完全没有门。
   ⇒ 本 entry 是 H 循环**发布链首例**，`tb_publish_gate` 是**真值**不是 None。

   🔴 但 sync 路径本身对 `trial_balance` 的写次数仍必须为 **0**：发布门是**用户显式动作**
   （审定表 Tab 的按钮 + 二次确认），不是回写副作用。本模块不含任何 TB 写入 ——
   把 sync 的 materialize/merge 接到 TB 上会绕过二次确认，违反
   `tb-writeback-explicit-publish-gate` 的铁律。

═══ 范式：`phase5_*` 不照 H1 的 `pilot_*` ═══

同 canary 的裁决（H1 的 `pilot_h1_grouped_dynamic` 形态早于行表引擎，照它写出的代码无法
复用引擎）。七段公共流程仍走 `phase5_h_cycle_common`。
唯一必须复用 pilot 产物的是 `oo_crash_neutralization_fn`（HC-12）。

═══ HC-12：H6 册裸 IF **12 格（全 H 最低）⇒ 仍必挂中性化** ═══

中性化是 **per-file**（整册就地改写 substrate 副本）⇒ 受管表自身干净也必须挂。
🔴 BP-4（真 OO 9.4 场景集）未交付前**不得**以「裸 IF 最少」推断本册不需要。

═══ HD-1/HD-2 载体族：写 host_inline · 读 snapshot 透传 ═══

写路径 `host_inline`（宿主 `GtH6AssetDisposalClearing.vue` 自己 `import http`，
`checklist_put` 实测 **2 处**：#L242 与 #L270）；
读路径 `render_config_snapshot_passthrough`（`props.htmlData.responses_snapshot`，
宿主自身不 GET `/checklist-responses`）。
payload 列是 `dual_write_remark_and_conclusion`（slice 逐字）—— 与 H9 的 `remark_only` 不同。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from app.services.workpaper_sync import phase5_h_cycle_common as HC
from app.services.workpaper_sync import phase5_h6_02_detail as _h602
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

PHASE5_WAVE: Final[str] = "phase5_asset_disposal_clearing_detail"
ENTRY_ID: Final[str] = "xlsx/gt-h6-asset-disposal-clearing"
ADAPTER_ID: Final[str] = "h6.asset_disposal_clearing_detail"

#: 🔴 slice 的 `wp_code_pattern` 是 `H6A`，**但它不是幻影码** —— 见模块 docstring 第 1 条。
WP_CODES: Final[frozenset[str]] = frozenset({"H6A"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "H/H6 固定资产清理.xlsx"
#: 逐字取 openpyxl 现算（48,865 B）
TEMPLATE_SHA256: Final[str] = (
    "c7d0d78a798ce9c3c47aab64ea02ffc93919a9b02474d8801d115c614656e8a8"
)

#: 受管 store item（`明细表H6-2`）
STORE_ITEM_ID: Final[str] = _h602.STORE_ITEM_ID_H602
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
ROW_IDENTITY_STORE_KEY: Final[str] = _h602.ROW_IDENTITY_STORE_KEY_H602

#: 🔴 H6 是 `dual_write_remark_and_conclusion`（slice 逐字），不是 H9 的 `remark_only`。
#: 行数组仍落 `remark`；`conclusion` 由宿主另一处写点使用 ⇒ merge 只动 `remark`。
PAYLOAD_COLUMN: Final[str] = "remark"
PAYLOAD_COLUMN_MODE: Final[str] = "dual_write_remark_and_conclusion"

#: 🔴 HD-7：H6 **有** TB 发布门（H 循环首例）。声明它让 roundtrip 判据知道本 entry
#: 覆盖发布链；同时钉住「发布走用户显式动作，不是 sync 副作用」。
TB_PUBLISH_GATE: Final[str] = (
    "H6TabAdjudication → useH6Adjudication.publishToTb "
    "（POST /api/workpapers/{wpId}/audit-determination/publish-to-tb，科目 1606，"
    "中文二次确认；sync 路径对 trial_balance 写 0 次）"
)

# 向后兼容别名：既有通用判据按 `EntrySelectionError` / `StorePayloadError` 取 provider 异常。
EntrySelectionError = HC.HEntrySelectionError
StorePayloadError = HC.HStorePayloadError


#: 契约 `review` 段的 H6 专属声明。
_EXTRA_REVIEW: Final[dict[str, Any]] = {
    # 🔴 HC-11：中文枚举域（`status` 是 store-only，登记它让回写侧不当自由文本覆盖）
    "enum_fields": {k: list(v) for k, v in _h602.CHINESE_ENUM_FIELDS_H602.items()},
    # 🔴 派生字段：`endAdjustment` 模板无列、由 F/G/H 算出 ⇒ OO 侧不可编辑
    "derived_fields": list(_h602.DERIVED_STORE_ONLY_FIELDS_H602),
    # HTML 有字段、模板无列 ⇒ 不映射任何格（含 4 对跨 entry 读别名）
    "store_only_fields": list(_h602.STORE_ONLY_FIELDS_H602),
    # 🔴 本表为空：16 个模板列全部有 store 字段（与 H9 的 U/V 两列不同）
    "template_only_columns": [
        {"column": col, "header_text": text}
        for col, text in _h602.TEMPLATE_ONLY_COLUMNS_H602
    ],
    # 🔴 公式列里 json_key **不落库**的两个 ⇒ 回写比对必须排除，否则把「本来就没有」
    #    误报成「回写丢字段」。H6 是**部分落库**（E/I/L 落、J/K 不落），
    #    不同于 H9 的「公式列一律不落库」—— 不得按 H9 的口径推演。
    "non_persisted_formula_keys": list(_h602.NON_PERSISTED_FORMULA_KEYS_H602),
    # 🔴 HC-6 派生合计副本 6 键：与主表同批写出，不参与 roundtrip 比对
    "derived_total_keys": list(_h602.DERIVED_TOTAL_KEYS_H602),
    # 🔴 HC-8 键名冻结依据：`H6-2-rows` 的跨 entry 消费方
    "frozen_cross_ref": {
        _h602.STORE_ITEM_ID_H602: list(_h602.CROSS_ENTRY_CONSUMERS_H602)
    },
    # HC-5：H6 主表无变体轴（实测单张）
    "variant_axis": None,
    # HD-1 / HD-2 实测载体族（守卫按族标签分派，不按文件名推断）
    "carrier": {
        "write": "host_inline",
        "read": "render_config_snapshot_passthrough",
        "tb_publish_gate": TB_PUBLISH_GATE,
    },
    # HC-13：UUID 列 = 有效内容列 + 1
    "effective_columns": _h602.EFFECTIVE_COLUMNS_H602,
    "uuid_column": _h602.UUID_COL_H602,
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
    # 🔴 `H6A` 同时是真实程序表码 ⇒ 解析到**自己**的册（不是泄漏）
    phantom_code_resolves_to_own_workbook=True,
    tb_publish_gate=TB_PUBLISH_GATE,
    extra_review=_EXTRA_REVIEW,
)

_HTML_STORE_NOTE: Final[str] = (
    "H6 固定资产清理的结构化 Tab 行数据存成 checklist_responses 的 **remark** JSON 数组。"
    "本契约按 stable field + 行身份 `rowId` 拆开。"
    "🔴 16 个模板列全部有 store 字段（`template_only_columns` 为空）；"
    "反向有 20 个 HTML 字段模板无列（store-only，含 accDepreciation / tax / netGainLoss / "
    "h1Reference / h10Reference 五个兼容别名与派生列 endAdjustment）。"
    "🔴 公式列 E/I/J/K/L 中 **J / K 的 json_key 不落库**（前端 load 时 "
    "`applyH62BalanceFormulas` 重算），E/I/L 落库 —— **部分落库**，"
    "不同于 H9 的「公式列一律不落库」。`formula_mask` 保证 OO 侧不被 HTML 的 None 覆盖。"
)

_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐格实测 H/H6 固定资产清理.xlsx 的 `明细表H6-2`"
    "（两级表头 R9/R10 / 数据 R11-15 共 5 行 / footer R16 A16='　合计'（前导全角空格 U+3000）"
    "且 B16..L16 各 =SUM(x11:x15) / 公式列 E·I·J·K·L / 有效内容列 16 即 A..P / "
    "max_column=25 是空列尾巴 / 表头合并 A9:A10·F9:F10·M9:M10·N9:N10·O9:O10·P9:P10 纵向 + "
    "B9:E9·G9:H9·I9:L9 横向 / 册内 8 sheets 且**无** GT_Custom）"
    " + 前端 `useH6Detail.ts` 按值 grep（ROWS_KEY=#L119 / _persist()=#L531-570 的落库字段 / "
    "applyH62BalanceFormulas 的 E·I·J·K·L 重算 / 6 个 H6-2-subtotal-* 同批写出 / "
    "status 三值中文枚举 / rowId 生成式为时间戳+随机属 HC-7 族 A）"
    " + 真库现算（checklist_responses.item_id='H6-2-rows' **无行** ⇒ roundtrip 真实证需造数据，"
    "这正是 canary 选 H9 而非 H6 的原因，如实登记不粉饰）"
)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 受管 sheet 清单（灰度开关）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 本轮只放 H6-2 一张；册内其余 7 个 sheet 的处置：
#   底稿目录 / 固定资产清理实质性程序表H6A   → 不接
#   审定表H6-1                              → 归审定表后置族（同 G 的 GF-H5 裁决）
#                                             🔴 它是 TB 发布门所在，但发布门是**用户动作**，
#                                             不需要把该 sheet 纳入 sync 受管面
#   调整分录汇总H6-3                        → FC-6 默认 `single_html`（Tab 是 hub）
#   检查表H6-4                              → 归后续批次（useH6Check 26 字段，另一形态）
#   附注披露信息（上市公司 / 国有企业）      → 归附注披露族

_INCLUDE_H602: Final[bool] = True


def managed_row_table_specs() -> tuple[Any, ...]:
    """本 entry 当前受管的行表型 spec 清单（按灰度开关）。"""
    specs: list[Any] = []
    if _INCLUDE_H602:
        specs.append(_h602.SPEC_H602)
    return tuple(specs)


def all_store_item_ids() -> tuple[str, ...]:
    """本 entry 全部 store item（**单一口径**，出/回两方向都从它取）。"""
    items: list[str] = []
    for spec in managed_row_table_specs():
        if spec.store_item_id and spec.store_item_id not in items:
            items.append(spec.store_item_id)
    return tuple(items)


def adjudication_spec() -> Any:
    """H6-1 审定表 —— 归后置批次，本 spec 恒 None。"""
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
    """🔴 口径见 `phase5_h_cycle_common.assert_phantom_code_does_not_leak`。

    H6 的 `H6A` 解析到**自己**的册（`phantom_code_resolves_to_own_workbook=True`），
    不变量是「不得命中**别的 entry** 的册子」—— 照 G2 的「不得命中任何模板」会在此直接抛。
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
            "useH6Detail.ts —— `_persist()` 经宿主 onSave 写 "
            "{ item_id: 'H6-2-rows', remark: JSON.stringify(rows) }"
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
        f"store item {store_item_id!r} 不在 H6 受管清单里；"
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
    `mod.build_store_projection(rows, contract=contract)` 调用 —— 写成两位置参会 TypeError。
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
    """matcher 域：`H6A` + `document_type="xlsx"`（FC-3 在 H 成立 ⇒ 无需 sheet_keys）。"""
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
    """发布链编排：attach H6 adapter（实现委托公共骨架）。"""
    return await HC.attach_h_entry_adapter(
        registry,
        IDENTITY,
        session=session,
        contract_payload_builder=build_contract_payload,
    )
