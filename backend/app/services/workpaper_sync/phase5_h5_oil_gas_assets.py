"""H5 油气资产 —— Phase 5 entry 模块（H 循环第七条，**映射率最低的一条**）。

spec: `h3-h5-h7-variant-axis-and-dynamic-column-paradigm`

═══ 🔴 先说清楚它交了什么、没交什么 ═══

单张受管 sheet `明细表H5-2`：**10 映射 / 54 有效列（19%）**。
对照 H8 58/58（100%）· H2 34/50（68%）· H3 成本 17/45（38%）。

映射的 10 格全部落在两个「未审数」段的**手敲格**上（类别 / 名称 / 原值期初·增·减 /
增减方式 / 原值期末 / 折耗期初 / 本期计提）—— 那正是两侧口径一致的全部面。
剩下 44 列判 template-only，三条缺口逐条登记在
`phase5_h5_02_detail.DECLARED_COVERAGE_GAPS_H502`，各带停下报告点：

* **H5-GAP-1**：前端 `H5DetailRow` 只 17 字段，**没有任何减值字段**（模板减值整块 15 列）、
  **没有任何审定字段**（模板三块的期初调整/账项调整/审定数共 24 列）。H5 的审定数在
  `useH5Adjudication`（H5-1 审定表，三个独立键），那是**另一张表**不是本 sheet 的列。
* **H5-GAP-2**：`accDepletionReversal`（转回）对应 `T 处置` 还是 `U 其他减少` 属审计口径；
  连带 `V 折耗期末数` 也不能映（Excel 会按自己的 Q..U 重算，把丢掉 reversal 的值灌回来）。
* **H5-GAP-3**：`netValue` 的减值项是**字面 0**，模板 `AW = I-V-AK` 含减值 ⇒ 有减值必错。

🔴 **不硬凑**的理由与 H2-GAP-1 / H3 八条同族：宁可留**可见缺口**，不要**不可见错数**。
OO 侧那 44 列照旧可编辑、Excel 照旧自己算，只是不回写 HTML。

═══ 四处不能照抄前六条的地方 ═══

1. 🔴 **store item 键是拼接出来的**：`useH5Detail.ts` 用 `${ITEM_PREFIX}-rows`
   （`ITEM_PREFIX='H5-2'`）⇒ 按值 grep 字面量 `'H5-2-rows'` **零命中**（HC-4）。
   这是 slice 冻结快照与实测不符的 5 处之一，判据必须解析拼接。
2. 🔴 **没有派生合计键**：H5 的小计是 `computed`（`subtotalRow`），`_persist()` 只写
   `rows.value` ⇒ `DERIVED_TOTAL_KEYS_H502` 是**空元组**。H4 有 4 个、H3 有 3 个 ——
   照抄会让判据去找一批不存在的键。
3. 🔴 **footer 之下小计区的行标签是字面量**（探明矿区权益 / 未探明矿区权益 / 井及相关设施
   / … / …），**不是** `=底稿目录!A9..A13` 引用。H3/H4/H7 都是引用 ⇒ 照抄假红。
4. 🔴 **有效列 54 = 全 H 最宽**，数据区 R13-R32 共 20 行。行数写死成别条的值会让 merge
   越界写进 footer。

═══ HD-7：H5 **有** TB 发布门（H 循环第三例）═══

`useH5Adjudication.ts#L273` 起的 `publishToTb` → POST
`/api/workpapers/{wpId}/audit-determination/publish-to-tb`，中文二次确认。
🔴 它挂在 **H5-1 审定表**上（不是本 sheet），且 `useH5FormData.ts#L229` 另有一处
说明「TB 回写走显式发布门」。sync 路径对 `trial_balance` 写 **0** 次 ——
发布门是用户显式动作，不是回写副作用。

═══ HC-12 / 幻影码 ═══

册 195,306 B / 24 sheets ⇒ 中性化必挂（per-file，与 G7/G2/H9/H6/H4/H8/H2/H3 共用
同一函数，不新造）。幻影码 `H5O` 三条 finder 路径实测全空 ⇒
`phantom_code_resolves_to_own_workbook=False`（程序表码是 `H5A`，不是 `H5O`）。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from app.services.workpaper_sync import phase5_h5_02_detail as _h502
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

PHASE5_WAVE: Final[str] = "phase5_oil_gas_assets_detail"
ENTRY_ID: Final[str] = "xlsx/gt-h5-oil-gas-assets"
ADAPTER_ID: Final[str] = "h5.oil_gas_assets_detail"

WP_CODES: Final[frozenset[str]] = frozenset({"H5O"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "H/H5 油气资产.xlsx"
#: 2026-10-01 安全净化后实测（169,576 B）：Equation.3 OLE 已转静态预览。
TEMPLATE_SHA256: Final[str] = (
    "4fc5ec55eba9418d5651398da617fa666f0b0719799cf1e802f52c55a62e5612"
)

STORE_ITEM_ID: Final[str] = _h502.STORE_ITEM_ID_H502
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
ROW_IDENTITY_STORE_KEY: Final[str] = _h502.ROW_IDENTITY_STORE_KEY_H502

PAYLOAD_COLUMN: Final[str] = "remark"
PAYLOAD_COLUMN_MODE: Final[str] = "dual_write_remark_and_conclusion"

#: 🔴 HD-7：H5 **有** TB 发布门（H 循环第三例，H6 首例 / H3 第二例）。
TB_PUBLISH_GATE: Final[str] = (
    "H5TabAdjudication → useH5Adjudication.publishToTb#L273 "
    "（POST /api/workpapers/{wpId}/audit-determination/publish-to-tb，中文二次确认）。"
    "🔴 挂在 **H5-1 审定表**上，不是本 sheet；sync 路径对 trial_balance 写 0 次。"
)

EntrySelectionError = HC.HEntrySelectionError
StorePayloadError = HC.HStorePayloadError

_EXTRA_REVIEW: Final[dict[str, Any]] = {
    "enum_fields": {},
    "derived_fields": [],
    "store_only_fields": list(_h502.STORE_ONLY_FIELDS_H502),
    "template_only_columns": [
        {"column": col, "header_text": text}
        for col, text in _h502.TEMPLATE_ONLY_COLUMNS_H502
    ],
    "unmanaged_regions": [dict(r) for r in _h502.UNMANAGED_REGIONS_H502],
    "declared_coverage_gaps": [dict(g) for g in _h502.DECLARED_COVERAGE_GAPS_H502],
    "resolved_coverage_gaps": [],
    "legacy_folded_fields": {},
    # 🔴 显式空元组：H5 的小计是 computed 不落库（H4 有 4 个、H3 有 3 个 ⇒ 不照抄）
    "derived_total_keys": list(_h502.DERIVED_TOTAL_KEYS_H502),
    "sibling_tables_not_managed": [
        "H5-1-cost-rows",
        "H5-1-depletion-rows",
        "H5-1-impairment-rows",
        "H5-3-entries",
        "H5-7-rows",
    ],
    "variant_axis": None,
    "carrier": {
        "write": "formdata_composable",
        "read": "formdata_composable",
        "tb_publish_gate": TB_PUBLISH_GATE,
    },
    "footer_non_sum_cells": {},
    "effective_columns": _h502.EFFECTIVE_COLUMNS_H502,
    "uuid_column": _h502.UUID_COL_H502,
    "column_coverage_closure": {
        "mapped": len(_h502.FIELD_SPECS_H502),
        "template_only": len(_h502.TEMPLATE_ONLY_COLUMNS_H502),
        "effective_columns": _h502.EFFECTIVE_COLUMNS_H502,
    },
    "store_item_key_is_concatenated": {
        "key": _h502.STORE_ITEM_ID_H502,
        "source": (
            "audit-platform/frontend/src/components/workpaper/composables/"
            "useH5Detail.ts —— `${ITEM_PREFIX}-rows`（ITEM_PREFIX='H5-2'）"
        ),
        "note": (
            "🔴 按值 grep 字面量 'H5-2-rows' **零命中**（HC-4 拼接解析）。"
            "判据必须解析 `${…}` 拼接，否则会把本 entry 判成「键不存在」。"
        ),
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
    #: `H5O` 三条 finder 路径实测全空（程序表码是 `H5A`）
    phantom_code_resolves_to_own_workbook=False,
    tb_publish_gate=TB_PUBLISH_GATE,
    extra_review=_EXTRA_REVIEW,
)

_HTML_STORE_NOTE: Final[str] = (
    "H5 油气资产的结构化行数据存成 checklist_responses 的 **remark** JSON 数组，"
    "按 stable field + 行身份 `rowId` 拆开。"
    "🔴 **store item 键是拼接出来的**：`useH5Detail.ts` 用 `${ITEM_PREFIX}-rows`"
    "（ITEM_PREFIX='H5-2'）⇒ 按值 grep 字面量 'H5-2-rows' **零命中**（HC-4 拼接解析）。"
    "🔴 **映射率 10/54（19%）是全 H 最低档，低不是漏做**：前端 `H5DetailRow` 只有 17 个"
    "字段，而模板有 54 个有效列（全 H 最宽）。三大成因：①前端**没有任何减值字段**"
    "（模板减值准备整块 AF..AT 共 15 列）；②前端**没有任何审定字段**（模板三个区块的"
    "期初调整 / 账项调整 / 审定数共 24 列 —— H5 的审定数在 useH5Adjudication 的 H5-1 "
    "审定表，键是 H5-1-cost-rows / H5-1-depletion-rows / H5-1-impairment-rows 三个，"
    "那是**另一张表**不是本 sheet 的列）；③三处**算术不等**不可映。"
    "映射的 10 格全部落在两个「未审数」段的手敲格上（A 类别 / C 名称 / D 原值期初 / "
    "E 增加金额 / F 增加方式 / G 减少金额 / H 减少方式 / I 原值期末 / Q 折耗期初 / "
    "R 本期计提）—— 那正是两侧口径一致的全部面。"
    "🔴 **`I` 是本 sheet 唯一可映的公式列**：模板 `=SUM(D:E)-G` 与前端 "
    "`calcAssetEndBalance(begin, increase, decrease) = begin+inc-dec` **逐项相等**。"
    "而 `V 折耗期末数` 不能映 —— 模板 `=SUM(Q:S)-SUM(T:U)`，Excel 会按自己的 Q..U 重算"
    "（S/T/U 皆空 ⇒ V=Q+R），回写时把**丢掉 reversal** 的值灌进 accDepletionEnd（静默错数）；"
    "`AW 期末净值` 也不能映 —— 模板 `=I-V-AK` 含**减值期末**，而前端 "
    "`calcNetValue(cost, depletion, **0**)` 的减值项是字面 0，两者只在减值恒为 0 时相等。"
    "🔴 三条缺口逐条登记（见 review.declared_coverage_gaps），各带停下报告点："
    "H5-GAP-1（无减值 + 无审定，31 列）· H5-GAP-2（转回对应 T 处置还是 U 其他减少属审计口径，"
    "连带 V 不可映）· H5-GAP-3（netValue 的减值项写死 0，连带 AU/AV/AW/AX 不可映）。"
    "🔴 **没有派生合计键**：H5 的小计是 computed（subtotalRow），`_persist()` 只写 "
    "rows.value ⇒ derived_total_keys 是**空元组**（H4 有 4 个、H3 有 3 个，照抄会让判据"
    "去找一批不存在的键）。"
    "🔴 **footer 之下小计区的行标签是字面量**（探明矿区权益 / 未探明矿区权益 / 井及相关设施 "
    "/ … / …），**不是** `=底稿目录!A9..A13` 引用 —— H3/H4/H7 都是引用，照抄假红。"
)

_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐格实测 H/H5 油气资产.xlsx（195,306 B / 24 sheets）的 `明细表H5-2`"
    "（**四级**表头 R9/R10/R11/R12 共 71 个合并域 / 数据 R13-R32 共 20 行 / "
    "footer R33 `合计` **全列 SUM 无行内派生** / **有效内容列 54 即 A..BB，全 H 最宽** / "
    "数据行公式列 19 个（映射侧仅 `I` 一个进 FORMULA_TEMPLATES）/ "
    "三区块四段：原值 D9(未审 D-I 含增减方式两列 / 期初调整 J / 账项调整 K-L / 审定 M-P)· "
    "累计折耗 Q9(未审 Q-V，本期增减各再分两小列 本期计提·其他增加 / 处置·其他减少 / "
    "期初调整 W / 账项调整 X-AA / 审定 AB-AE)· 减值准备 AF9(与折耗块逐列同构 AF-AT)· "
    "净值四列 AU/AV/AW/AX（=D-Q-AF / =M-AB-AQ / =I-V-AK / =P-AE-AT）· "
    "尾部四布尔列 AY 是否提足折耗 / AZ 是否闲置 / BA 是否有权属证明 / BB 是否抵押受限 / "
    "footer 之下 R34-R39 `其中：`+五行 SUMPRODUCT 按类别小计，**行标签是字面量**不是"
    "底稿目录引用)"
    " + 前端按值 grep（useH5Detail.ts `${ITEM_PREFIX}-rows` 拼接键 / H5DetailRow **17 字段** / "
    "SEGMENT_CONFIGS 三段 basic·cost·depletion / _recalcRow 三条算式 / "
    "useH5FormulaEngine.calcAssetEndBalance(begin,debit,credit)=begin+debit-credit / "
    "calcContraEndBalance(begin,debit,credit)=begin+credit-debit（调用实参顺序是 "
    "begin, reversal, provision ⇒ 等于 begin+prov-rev）/ "
    "calcNetValue(cost,accDepletion,impairment) 第三实参是**字面 0** / "
    "subtotalRow 是 computed 不进 _persist)"
    " + 三条 finder 路径实测幻影码 `H5O` 全空（程序表码是 `H5A`）"
    " + 发布门现算（useH5Adjudication.ts#L273 publishToTb，挂在 H5-1 审定表上）"
    " + 覆盖闭合自检（10+44==54，并集连续 A..BB 无缺口、无列重复无交叠）"
)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 受管 sheet 清单（灰度开关）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 本轮只放 H5-2 一张；册内其余 23 个 sheet 的处置：
#   底稿目录 / 油气资产实质性程序表H5A          → 不接
#   审定表H5-1                                  → 归审定表后置族（带 TB 发布门）
#   调整分录汇总H5-3                            → FC-6 默认 `single_html`
#   闲置检查表H5-4                              → 归后续批次（AZ 是否闲置 的真数据源）
#   会计政策会计估计检查表H5-5 / 分析表H5-6      → 归后续批次
#   增加检查表H5-7 / 减少检查表H5-8              → 归后续批次
#   监盘计划H5-9 / 盘点检查表H5-10 / 监盘小结H5-11 → 归后续批次
#   折耗测算表（不含减值 / 含减值）H5-12          → 🔴 **变体轴**（HC-5），归后续批次
#   折耗分配分析表H5-13                          → 归后续批次
#   减值测算表H5-14 / 可收回金额测试表H5-15      → 归后续批次（减值整块的真数据源）
#   权属检查表H5-16                              → 归后续批次（BA 是否有权属证明 的真源）
#   关联交易检查表H5-17                          → 归后续批次
#   经营租出油气资产检查表H5-18 /
#   融资租出油气资产检查表H5-19                  → 归后续批次
#   附注披露信息（上市公司 / 国有企业）           → 归附注披露族

_INCLUDE_H502: Final[bool] = True


def managed_row_table_specs() -> tuple[Any, ...]:
    specs: list[Any] = []
    if _INCLUDE_H502:
        specs.append(_h502.SPEC_H502)
    return tuple(specs)


def all_store_item_ids() -> tuple[str, ...]:
    items: list[str] = []
    for spec in managed_row_table_specs():
        if spec.store_item_id and spec.store_item_id not in items:
            items.append(spec.store_item_id)
    return tuple(items)


def adjudication_spec() -> Any:
    """H5-1 审定表（带 TB 发布门）—— 归后置批次，本 spec 恒 None。"""
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
            "useH5Detail.ts —— `_persist()` 经宿主 onSave 写 "
            "{ item_id: `${ITEM_PREFIX}-rows`, remark: JSON.stringify(rows) }"
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
        f"store item {store_item_id!r} 不在 H5 受管清单里；"
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
    """matcher 域：幻影码 `H5O` + `document_type="xlsx"`（FC-3 在 H 成立）。"""
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
    """发布链编排：attach H5 adapter（实现委托公共骨架）。"""
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
