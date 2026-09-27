"""H2 在建工程 —— Phase 5 entry 模块（H 循环第五条，**首条带声明缺口**）。

spec: `h2-h6-h10-pilot-cross-reference-lanes`
现算底账：`.kiro/specs/h4-h8-sub-entry-lanes-and-seed-identity-defects/evidence/
h2-h4-h8-h10-mapping-facts.md` §7

═══ 与前四条最大的不同：它有**声明出来的覆盖缺口** ═══

H9/H6/H4/H8 的每个模板列要么有 store 字段、要么明确无对端。H2 有两处两侧**语义打架**：

| 缺口 | 列 | 性质 | 处置 |
|---|---|---|---|
| H2-GAP-1 | `L 增加` | 模板可输入 vs HTML 派生（权威方向相反） | L 判 template-only，5 分项 store-only |
| H2-GAP-2 | `O 其他减少` | 1 格对 2 字段（`decrease + transferOut`） | O→decrease 主映射，transferOut legacy_folded |

两处都**不硬凑映射** —— 硬凑会造成静默错数（前者把 OO 的输入吞掉、后者漏掉
`transferOut` 那部分金额）。宁可留**可见缺口**，不要**不可见错数**。
两处各带停下报告点，需审计域裁决的部分不由接线方拍板，详见
`phase5_h2_02_detail.DECLARED_COVERAGE_GAPS_H202`。

覆盖闭合仍成立：**34 映射 + 16 template-only == 50 有效列**，并集连续 A..AX 无缺口。

═══ 三处不能照抄前四条的地方 ═══

1. 🔴 **footer 之下无 `其中：` SUMPRODUCT 小计区**（R22 直接是「三、审计说明：」）。
   H4/H8 都有 ⇒ 照抄会把「审计说明」误登记成小计区，守卫再去比对一个不存在的
   SUMPRODUCT。本 entry `unmanaged_regions` 显式为**空元组**。
2. 🔴 **footer R21 不是一律 SUM**：`AA21='=K21+T21'` / `AC21='=M21+V21'` /
   `AG21='=Z21+AB21-AD21-AE21'` / `AH21='=AA21+AC21-AF21'` 是**行内派生**。
   按「footer 全是 `=SUM(列)`」写判据会在这四格上假红。
3. 🔴 **两对净值**（期初 `AT9:AU10` + 期末 `AV9:AW10`），H8 只有一对 ⇒ 列位形态不同。

═══ 数据区最短（8 行）═══

R13-R20。H8 20 行 / H4 16 行 / H9·H6 各 5 行 —— 受管区行数写死成别条的值会让 merge
越界写进 footer。

═══ HC-12 / 幻影码 ═══

册 162,616 B / **21 sheets（全 H 最多）** ⇒ 中性化必挂（per-file，与 G7/G2/H9/H6/H4/H8
共用同一函数，不新造）。幻影码 `H2C` 三条 finder 路径实测全空 ⇒
`phantom_code_resolves_to_own_workbook=False`（程序表码是 `H2A`，不是 `H2C`）。

HD-7：H2 **无** TB 发布门（`publishToTb` 在 H2 链路 0 处）。sync 对 `trial_balance` 写 0 次。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from app.services.workpaper_sync import phase5_h2_02_detail as _h202
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

PHASE5_WAVE: Final[str] = "phase5_construction_in_progress_detail"
ENTRY_ID: Final[str] = "xlsx/gt-h2-construction-in-progress"
ADAPTER_ID: Final[str] = "h2.construction_in_progress_detail"

WP_CODES: Final[frozenset[str]] = frozenset({"H2C"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "H/H2 在建工程.xlsx"
#: 逐字取 openpyxl 现算（162,616 B）
TEMPLATE_SHA256: Final[str] = (
    "de9426a33e8d51e9351c8dd2393fe8502433d2cf810f30318f254a474ec480fe"
)

STORE_ITEM_ID: Final[str] = _h202.STORE_ITEM_ID_H202
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
ROW_IDENTITY_STORE_KEY: Final[str] = _h202.ROW_IDENTITY_STORE_KEY_H202

PAYLOAD_COLUMN: Final[str] = "remark"
PAYLOAD_COLUMN_MODE: Final[str] = "dual_write_remark_and_conclusion"

#: 🔴 HD-7：H2 无 TB 发布门（`publishToTb` 在 H2 链路 0 处）。
TB_PUBLISH_GATE: Final[None] = None

EntrySelectionError = HC.HEntrySelectionError
StorePayloadError = HC.HStorePayloadError

_EXTRA_REVIEW: Final[dict[str, Any]] = {
    "enum_fields": {},
    "derived_fields": [],
    "store_only_fields": list(_h202.STORE_ONLY_FIELDS_H202),
    "template_only_columns": [
        {"column": col, "header_text": text}
        for col, text in _h202.TEMPLATE_ONLY_COLUMNS_H202
    ],
    # 🔴 显式空元组：H2 的 footer 之下是「三、审计说明」不是小计区（H4/H8 都有）。
    #    声明空而不省略，免得复用 H4/H8 判据的人以为「忘写了」。
    "unmanaged_regions": [],
    # 🔴 本 entry 的核心差异：两处声明出来的覆盖缺口（含停下报告点）
    "declared_coverage_gaps": [dict(g) for g in _h202.DECLARED_COVERAGE_GAPS_H202],
    "legacy_folded_fields": {
        k: dict(v) for k, v in _h202.LEGACY_FOLDED_FIELDS_H202.items()
    },
    "derived_total_keys": [],
    "sibling_tables_not_managed": list(_h202.SIBLING_TABLE_KEYS_H202),
    "variant_axis": None,
    "carrier": {
        "write": "host_inline",
        "read": "render_config_snapshot_passthrough",
        "tb_publish_gate": TB_PUBLISH_GATE,
    },
    # 🔴 footer 非一律 SUM 的四格（判据不得按「footer 全是 =SUM(列)」写，否则假红）
    "footer_non_sum_cells": {
        "AA21": "=K21+T21",
        "AC21": "=M21+V21",
        "AG21": "=Z21+AB21-AD21-AE21",
        "AH21": "=AA21+AC21-AF21",
    },
    "effective_columns": _h202.EFFECTIVE_COLUMNS_H202,
    "uuid_column": _h202.UUID_COL_H202,
    "column_coverage_closure": {
        "mapped": len(_h202.FIELD_SPECS_H202),
        "template_only": len(_h202.TEMPLATE_ONLY_COLUMNS_H202),
        "effective_columns": _h202.EFFECTIVE_COLUMNS_H202,
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
    #: `H2C` 三条 finder 路径实测全空（程序表码是 `H2A`）
    phantom_code_resolves_to_own_workbook=False,
    tb_publish_gate=TB_PUBLISH_GATE,
    extra_review=_EXTRA_REVIEW,
)

_HTML_STORE_NOTE: Final[str] = (
    "H2 在建工程的结构化 Tab 行数据存成 checklist_responses 的 **remark** JSON 数组，"
    "按 stable field + 行身份 `rowId` 拆开。"
    "🔴 模板 50 有效列中 **34 列**映射 store 字段、**16 列** template-only，"
    "两数相加恰等于 50（覆盖闭合，并集连续 A..AX 无缺口）。"
    "🔴 **本 entry 有两处声明出来的覆盖缺口**（前四条都没有）："
    "① `L 增加` —— 模板无公式是可输入格，HTML 的 `increaseTotal` 由 5 个分项在 "
    "`_recalcFormulas` 派生且不落库 ⇒ 两侧权威方向相反，OO 改 L 回写无处可落、"
    "HTML load 又会用分项覆盖 ⇒ L 判 template-only、5 分项判 store-only，本格不双向；"
    "② `O 其他减少` —— `useH2Detail.ts#L254 _otherDecrease = decrease + transferOut` "
    "是 1 格对 2 字段 ⇒ O 映 `decrease`（主字段），`transferOut` 判 store-only + "
    "legacy_folded，非零时两侧差额恰等于它。两处各带停下报告点（见 review."
    "declared_coverage_gaps），需审计域裁决的部分不由接线方拍板。"
    "🔴 footer R21 **不是一律 SUM**：AA21/AC21/AG21/AH21 四格是行内派生"
    "（见 review.footer_non_sum_cells）—— 判据按「footer 全是 =SUM(列)」写会假红。"
    "🔴 H2 **无** footer 之下的小计区（R22 直接是审计说明），与 H4/H8 相反。"
)

_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐格实测 H/H2 在建工程.xlsx 的 `明细表H2-2`"
    "（四级表头 R9/R10/R11/R12 共 46 个合并域 / 数据 R13-R20 共 **8 行，全 H 最短** / "
    "footer R21 `合计`（AA·AC·AG·AH 四格为行内派生不是列 SUM）/ "
    "有效内容列 50 即 A..AX / 数据行公式列 21 个（映射侧 10 个进 FORMULA_TEMPLATES）/ "
    "分区 A..I 属性列 · 原值 J9:AH9（每组带「其中：」子列，H2 独有）· "
    "减值准备 AI9:AS9 · **两对**净值 AT9:AU10 期初 + AV9:AW10 期末 · AX 是否抵押 / "
    "册 21 sheets 全 H 最多 / footer 之下**无** SUMPRODUCT 小计区）"
    " + 前端 `useH2Detail.ts` 按值 grep（ROWS_KEY / H2DetailRow 78 字段 / "
    "_persist() 56 键 / #L254 `_otherDecrease = decrease + transferOut` 定死缺口② / "
    "#L351 `_recalcFormulas` 的 increaseTotal 由 5 分项派生定死缺口①）"
    " + 六项自检（34+16==50 闭合 / 并集连续无缺口 / 无列重复无交叠 / "
    "10 个公式模板与 R13 逐字一致 / 34 个 header_text 与模板最下层表头逐字一致 / "
    "两条缺口登记与实际映射一致）"
    " + 真库现算（`H2-2-rows` **无行** ⇒ 缺口② 的 `transferOut` 是否真出现过无法实证，"
    "已登记为停下报告点）"
)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 受管 sheet 清单（灰度开关）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 本轮只放 H2-2 一张；册内其余 20 个 sheet（全 H 最多）的处置：
#   底稿目录 / 在建工程实质性程序表H2A       → 不接
#   审定表H2-1                              → 归审定表后置族
#   调整分录汇总H2-3                        → FC-6 默认 `single_html`
#   分析表H2-4 / 转固时点检查表H2-5 /
#   在建工程审核记录H2-6 / 工程造价比较表H2-7 /
#   增加检查表H2-8 / 减少检查表H2-9         → 归后续批次
#   利息资本化测算表（无/有专门借款）H2-10 / H2-11 → 🔴 **变体轴**（HC-5），归后续批次
#   监盘计划H2-12 / 盘点检查表H2-13 / 监盘小结H2-14 → 归后续批次
#   减值测算表H2-15 / 可收回金额测试表H2-16 → 归后续批次
#   关联交易检查表H2-17                     → 归后续批次
#   附注披露信息（上市公司 / 国有企业）      → 归附注披露族

_INCLUDE_H202: Final[bool] = True


def managed_row_table_specs() -> tuple[Any, ...]:
    specs: list[Any] = []
    if _INCLUDE_H202:
        specs.append(_h202.SPEC_H202)
    return tuple(specs)


def all_store_item_ids() -> tuple[str, ...]:
    items: list[str] = []
    for spec in managed_row_table_specs():
        if spec.store_item_id and spec.store_item_id not in items:
            items.append(spec.store_item_id)
    return tuple(items)


def adjudication_spec() -> Any:
    """H2-1 审定表 —— 归后置批次，本 spec 恒 None。"""
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
            "useH2Detail.ts —— `_persist()` 经宿主 onSave 写 "
            "{ item_id: 'H2-2-rows', remark: JSON.stringify(rows) }"
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
        f"store item {store_item_id!r} 不在 H2 受管清单里；"
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
    """matcher 域：幻影码 `H2C` + `document_type="xlsx"`（FC-3 在 H 成立）。"""
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
    """发布链编排：attach H2 adapter（实现委托公共骨架）。"""
    return await HC.attach_h_entry_adapter(
        registry,
        IDENTITY,
        session=session,
        contract_payload_builder=build_contract_payload,
    )
