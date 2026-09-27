"""G1 交易性金融资产 —— Phase 5 entry 模块（`g-cycle-single-region-detail-lanes` 第八条，**最后一条**）。

spec: `g-cycle-single-region-detail-lanes` · Task 14 / C-13

═══ 范式：照 `phase5_g9_other_noncurrent`（**三区共用一个 store 键**）═══

本模块与 G9 几何近同构（都是「三区 + 区标题行 + 逐区小计 + 合计」），差异集中在下面四条。

🔴 **一：区① 独有跨表 `T` 列 ⇒ 三区不得共用 `formula_columns`**（判据 P6 的唯一不等点）。
逐格实测：区① `T12..T16 = ='公允价值测试表G1-6'!H10..H14 - '明细表G1-2'!R12..R16`；
区②③ 的 `T` **整格无公式**（8 格全 `None`）⇒ 区① 13 个公式列、区②③ 12 个。
`T` 在区① 判 `formula`、在区②③ 判 `editable`（判 formula 会让 materialize 在那 8 格抛
`ProtectedRegionWriteError`）。G9 三区公式列完全相同、可共用一份；G1 抄三份共用必漂移。

🔴 **二：payload 列是 `conclusion` 不是 `remark`**（FD-1 的 `conclusion_only` 族，与 G3 同、
与另七条相反）。`row_section_field="acctClass"` 把同一数组的行分到三区
（`trading` / `classified_fvpl` / `designated_fvpl`），照 G9 的 `section` 范式。

🔴 **三：前端列模型本轮按模板改齐 6 处口径 + 合并 M + 新补 AA**（用户拍板「跟模板一致」）。
`P=C+M` 起点改回期初余额成本、`Q=D+N` 同理、`R=P+Q` 不再被市价覆盖、`W=U+V` 不含 AJE/RJE、
`L=J+K` 与 `Y=W+X` 改成**加**（`K`/`X` 存负数）、`addedCost`/`reducedCost` 合并为模板的净额
单列 `periodCostChange`、新增 `confirmationRequested`（模板 `AA` 是否函证）。
完整对照表见 :mod:`app.services.workpaper_sync.phase5_g1_02_detail` 模块头「三」。

🔴 **四：29 个非模板列字段不删、不受管**。tasks.md 按「类 I 去范围」写「删 ~29」，本轮按值
普查真消费方后推翻：**17 个有生产代码消费方**（删了要同时改 5 个兄弟表 composable 的数据源
—— `useG1FairValueTest` / `useG1IncomeCalc` / `useG1Inventory` / `g1CrossHelpers` /
`useG1Adjudication`），**12 个只有自己的 spec 在用**（可删清单登记在
`REMOVABLE_FRONTEND_FIELDS_G102`，本轮不删：受管面已严格 27 列，删它们属前端瘦身）。
⇒ 与 G13「不受管 ≠ 必须删」同一条道理。

BP-5（G1 sheet 兜底标签表 5 条错名）已由 foundation Task 5 修复（slice `status=FIXED`，
守卫 `TestGfP4Bp5G1SheetLabels` 9 passed）；GC-9 已裁决「TB 回写不在本 spec 改造范围」。
整册裸 IF **0 格**（18 sheet 全零）⇒ 中性化对本册是空操作；per-file 照挂（GC-2）。

wp_code 裁决：manifest 幻影码 `G1T`（matcher 域），真码 **G1**（载荷所在）。
FC-9 红线 = 本 provider 对 `trial_balance` 写次数为 0；审定表 G1-1 归后置 spec
`g-cycle-adjudication-sheets-coverage`（GF-H5）。
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from app.services.workpaper_sync.adapters.registry import (
    AdapterRegistration,
    EntryMatcher,
    WorkpaperSyncAdapterRegistry,
)
from app.services.workpaper_sync.contracts import (
    CONTRACT_SCHEMA_VERSION,
    SyncContract,
    contract_path_for,
    load_contract,
    parse_contract,
)
from app.services.workpaper_sync.definitions import canonical_digest
from app.services.workpaper_sync.entry_profile import (
    Capability,
    DescriptorFacts,
    RoomFacts,
    capability_of,
    load_entry_manifest,
    manifest_entries_by_id,
)
from app.services.workpaper_sync.excel_instrumentation import (
    ExcelIdentityCarrierGate,
    ExcelInstrumentationSpec,
    build_instrumentation_payload_for_sheets,
    build_template_payload,
    normalized_structure_hash,
)
from app.services.workpaper_sync.models import SyncDomainError
from app.services.workpaper_sync.sheet_geometry import col_index


class EntrySelectionError(SyncDomainError):
    """G1 entry 的选型必要条件不再成立。"""

    error_code = "sync_phase5_g1_selection_invalid"


class StorePayloadError(SyncDomainError):
    """HTML store 载荷形态不合法。"""

    error_code = "sync_phase5_g1_store_payload_invalid"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量
# ═══════════════════════════════════════════════════════════════════════════

PHASE5_WAVE: Final[str] = "phase5_trading_financial_assets_detail"
ENTRY_ID: Final[str] = "xlsx/gt-g1-trading-financial-assets"
ADAPTER_ID: Final[str] = "g1.trading_financial_assets_detail"

#: 🔴 manifest 冻结的**幻影码**（FC-2）。真码是 `G1`，见模块 docstring。
WP_CODES: Final[frozenset[str]] = frozenset({"G1T"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "G/G1 交易性金融资产.xlsx"
#: 逐字取 slice `authoritative_templates.files`（完整 64 位；实测 157,253 B）
TEMPLATE_SHA256: Final[str] = (
    "eba510b3b7cef68a0e3ea1a16eaa1262468bee11fccbee47a39ff513c33fba73"
)

#: 受管 store item —— 按值取自 `useG1Detail.ts` 的 `ITEM_ID`
STORE_ITEM_ID: Final[str] = "G1-2-rows"
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
ROW_IDENTITY_STORE_KEY: Final[str] = "rowId"

#: 🔴 FD-1：payload 落 `remark`（真库实证 remark 2 B / conclusion 0 B）。
PAYLOAD_COLUMN: Final[str] = "conclusion"
PAYLOAD_COLUMN_MODE: Final[str] = "conclusion_only"

_BACKEND_ROOT: Final[Path] = Path(__file__).resolve().parents[3]


# ═══════════════════════════════════════════════════════════════════════════
# 2. 权威模板
# ═══════════════════════════════════════════════════════════════════════════


def excel_carrier_gate() -> ExcelIdentityCarrierGate:
    return ExcelIdentityCarrierGate.load()


def authoritative_template_path() -> Path:
    return excel_carrier_gate().assert_template_under_authority(TEMPLATE_RELATIVE_PATH)


def read_authoritative_template() -> bytes:
    path = authoritative_template_path()
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != TEMPLATE_SHA256:
        raise EntrySelectionError(
            f"权威模板字节已变: {TEMPLATE_RELATIVE_PATH} 实测 sha256={digest}，"
            f"冻结哨兵={TEMPLATE_SHA256}"
        )
    return data


# ═══════════════════════════════════════════════════════════════════════════
# 3. 选型必要条件（照 G2/G9 同签名：`resolution` 必填、**无关闭开关**）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class TemplateResolutionFacts:
    by_wp_code: Mapping[str, Sequence[Any]]
    parent_code: str
    parent_resolved_path: Any


def assert_no_implicit_template_fallback(
    resolution: TemplateResolutionFacts,
    *,
    wp_codes: frozenset[str],
) -> None:
    """幻影码不得在 finder 里命中真模板（零回退）。"""
    missing = sorted(wp_codes - set(resolution.by_wp_code))
    if missing:
        raise EntrySelectionError(f"缺少 wp_code {missing} 的 finder 实测结果")
    leaked = {
        code: [str(item) for item in hits if item]
        for code, hits in resolution.by_wp_code.items()
        if any(hits)
    }
    if leaked:
        raise EntrySelectionError(
            f"幻影码 {sorted(leaked)} 在 finder 里意外命中真模板 "
            f"—— 零回退判据要求幻影码不得命中：{leaked}"
        )


def assert_entry_selectable(
    *,
    resolution: TemplateResolutionFacts,
    manifest: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    """对**真 manifest** 核四条事实 + 零回退（FC-2：不留关闭开关）。"""
    payload = manifest if manifest is not None else load_entry_manifest()
    entry = manifest_entries_by_id(payload).get(ENTRY_ID)
    if entry is None:
        raise EntrySelectionError(f"冻结的 entry {ENTRY_ID!r} 不在 manifest 里")
    if str(entry.get("document_type") or "") != "xlsx":
        raise EntrySelectionError(f"{ENTRY_ID!r} document_type 非 xlsx")
    if not entry.get("independent_entry"):
        raise EntrySelectionError(
            f"{ENTRY_ID!r} independent_entry={entry.get('independent_entry')!r}"
        )
    profile_id = str((entry.get("scenario_profile") or {}).get("profile_id") or "")
    if profile_id != EXPECTED_PROFILE_ID:
        raise EntrySelectionError(
            f"{ENTRY_ID!r} profile_id={profile_id!r} 与冻结的 {EXPECTED_PROFILE_ID!r} 不符"
        )
    codes = {
        str(c) for c in (entry.get("wp_match") or {}).get("wp_code_patterns") or ()
    }
    if codes != set(WP_CODES):
        raise EntrySelectionError(
            f"{ENTRY_ID!r} wp_code_patterns={sorted(codes)} "
            f"与冻结的 {sorted(WP_CODES)} 不一致"
        )
    assert_no_implicit_template_fallback(resolution, wp_codes=frozenset(codes))
    return entry


# ═══════════════════════════════════════════════════════════════════════════
# 4. 灰度开关与受管 sheet 清单
# ═══════════════════════════════════════════════════════════════════════════
#
# G1 册 **18** 个 sheet 的处置（逐字取自 `wb.sheetnames`，G 循环最多的一册）：
#   明细表G1-2            → 本 spec（🔴 **三区** R12-16 / R19-23 / R26-28，`_INCLUDE_G102`）
#   审定表G1-1            → 后置 spec `g-cycle-adjudication-sheets-coverage`（GF-H5）
#   调整分录汇总G1-3      → 后续 lane
#   结存表G1-4            → 后续 lane
#   收益测算表G1-5        → 后续 lane（消费 G1-2 的 soldQuantity/realizedGain，见非模板列登记）
#   公允价值测试表G1-6    → 后续 lane（🔴 **本 spec 的区① T 列跨表引它的 H10..H14**）
#   第三层次公允价值计量的调节表G1-7 / 业务模式分析G1-8 / 分类的适当性检查表G1-9 /
#   合同现金流量特征分析G1-10 / 有价证券监盘表G1-11 / 有价证券盘点倒轧表G1-12 /
#   检查表G1-13 / 衍生金融工具核查表G1-14  → 后续 lane
#   其余（底稿目录 / 附注披露 ×2 / 程序表G1A（🔴 tab 名尾部带一个空格））→ 不接

#: 明细表G1-2（🔴 三区共用一个 store 键，`row_section_field="acctClass"` 过滤）
_INCLUDE_G102: Final[bool] = True
#: 审定表G1-1（AdjudicationSheetSpec，归后置 spec）
_INCLUDE_G101: Final[bool] = False


def managed_row_table_specs() -> tuple[Any, ...]:
    """本 entry 当前受管的行表型 spec 清单（按灰度开关）。

    🔴 **三条**（区①②③）——与 G9 同范式：同一 store 键 `G1-2-rows` 按 `acctClass` 分区。
    区① 的 `formula_columns` 多一个跨表 `T`，三区**不共用**那份声明（判据 P6 的不等点）。
    """
    specs: list[Any] = []
    if _INCLUDE_G102:
        from app.services.workpaper_sync import phase5_g1_02_detail as _g102

        specs.extend(_g102.ALL_SPECS_G102)
    return tuple(specs)


def all_store_item_ids() -> tuple[str, ...]:
    """本 entry 全部 store item（**单一口径**，出/回两方向都从它取）。"""
    items: list[str] = []
    for spec in managed_row_table_specs():
        if spec.store_item_id and spec.store_item_id not in items:
            items.append(spec.store_item_id)
    return tuple(items)


def adjudication_spec() -> Any:
    """G1-1 审定表 —— 归后置 spec，本 spec 恒 None（GF-H5）。"""
    if not _INCLUDE_G101:
        return None
    raise EntrySelectionError(
        "G1-1 审定表归后置 spec `g-cycle-adjudication-sheets-coverage`（裁决 GF-H5）；"
        "本 spec 不交付其 AdjudicationSheetSpec"
    )


def all_managed_sheet_names() -> tuple[str, ...]:
    """本 entry 全部受管 sheet 的 Excel 名称。"""
    names: list[str] = []
    seen: set[str] = set()
    for s in managed_row_table_specs():
        if s.managed_sheet not in seen:
            names.append(s.managed_sheet)
            seen.add(s.managed_sheet)
    adj = adjudication_spec()
    if adj is not None and adj.managed_sheet not in seen:
        names.append(adj.managed_sheet)
    return tuple(names)


def _managed_last_col_of(spec: Any) -> str:
    if not spec.field_specs:
        raise EntrySelectionError(f"{spec.managed_sheet} 未声明任何受管字段")
    return max((row[1] for row in spec.field_specs), key=col_index)


def _instrumentation_of(spec: Any) -> ExcelInstrumentationSpec:
    return ExcelInstrumentationSpec(
        entry_id=ENTRY_ID,
        template_id=spec.template_id,
        template_relative_path=TEMPLATE_RELATIVE_PATH,
        managed_sheet=spec.managed_sheet,
        first_data_row=spec.first_data_row,
        last_data_row=spec.last_data_row,
        footer_row=spec.footer_row,
        managed_last_col=_managed_last_col_of(spec),
        uuid_col=spec.uuid_col,
        table_name=spec.table_name,
        sheet_key=spec.sheet_key,
    )


def instrumentation_specs() -> tuple[ExcelInstrumentationSpec, ...]:
    """全部 instrumentation 声明（G1 单区 ⇒ **一条**）。"""
    return tuple(_instrumentation_of(s) for s in managed_row_table_specs())


def template_definition_payload() -> dict[str, Any]:
    data = read_authoritative_template()
    specs = managed_row_table_specs()
    if not specs:
        raise EntrySelectionError("G1 当前无受管 sheet")
    return build_template_payload(
        spec=_instrumentation_of(specs[0]),
        template_sha256=TEMPLATE_SHA256,
        structure_hash=normalized_structure_hash(data),
    )


def instrumentation_definition_payload() -> dict[str, Any]:
    return build_instrumentation_payload_for_sheets(
        specs=instrumentation_specs(),
        template_definition_sha256=canonical_digest(template_definition_payload()),
        template_sha256=TEMPLATE_SHA256,
        gate=excel_carrier_gate(),
    )


# ═══════════════════════════════════════════════════════════════════════════
# 5. 契约装配
# ═══════════════════════════════════════════════════════════════════════════

_HTML_STORE_NOTE: Final[str] = (
    "G1-2 的受管行存成 checklist_responses 的 **conclusion** JSON 数组"
    f"（FD-1 的 `conclusion_only` 族 —— 与另七条的 remark 相反）。item_id `{STORE_ITEM_ID}`。"
    "🔴 **三区共用这一个键**：前端把三区的行存在同一个数组里、用 `acctClass` 标记区归属"
    "（trading / classified_fvpl / designated_fvpl）⇒ 引擎声明 `row_section_field=\"acctClass\"` "
    "+ 各段 `row_section_value`（照 G9 的 `section` 范式）；`iter_store_rows` 按它过滤、"
    "`merge_projection_into_store_rows` 给新增行补它，两处成对。"
    "行身份键 **`id`**，生成器 `g1d-${mintRowIdSuffix()}`（Task 7 修 BP-7 时收口到 "
    "`g1g3RowIdentity.ts`，前缀留在消费方内联以便逐字回源）。"
    "🔴 前端另有 **29** 个非模板列字段不受管（17 个有生产消费方、12 个只有 spec 在用）——"
    "逐条消费方见 `phase5_g1_02_detail.FRONTEND_ONLY_FIELD_OWNERS_G102`，可删清单见 "
    "`REMOVABLE_FRONTEND_FIELDS_G102`。"
)

_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐格实测 G/G1 交易性金融资产.xlsx 的 `明细表G1-2`"
    "（两级表头 R9/R10：横向组 **7** 个（C9:E9 期初余额 · F9:G9 期初账项调整 · H9:J9 期初审定数"
    " · M9:O9 本期变动 · P9:R9 期末余额 · S9:T9 账项调整 · U9:W9 期末审定数）+ 纵向合并 **8** 列"
    "（A/B/K/L/X/Y/Z/AA）/ "
    "🔴 **三区**：区标题 R11/R18/R25（不受管）· 数据 R12-16 / R19-23 / R26-28 · "
    "小计 R17/R24/R29 逐列 SUM · 合计 R30 `=SUM(C17,C24,C29)` 枚举三个小计 / "
    "R31 是注1「已到期可收取但尚未收到的利息在'应收利息'反映」⇒ **G1 无期末应收利息列**"
    "（推给 G2 底稿）/ "
    "🔴 有效内容列 **27**（A..AA）**小于 max_column=35**（8 个空尾列）⇒ 三区 uuid 逐区错开取 "
    "AB/AC/AD / 0 个 definedName / 18 sheets / "
    "🔴 整册裸 IF **0 格** ⇒ 中性化对本册是空操作 / "
    "🔴 **区① 独有跨表 T 列**（`='公允价值测试表G1-6'!H10..H14 - '明细表G1-2'!R12..R16` 逐行引"
    "不同源格），区②③ 的 T **8 格全 None** ⇒ 三区 formula_columns 差集恰 {T}，这正是判据 P6 "
    "要断言的「G1 ≠ G9」唯一不等点)"
    " + 前端 `useG1Detail.ts` 按值 grep（DATA_KEY / 行身份键 id / 27 个受管字段与模板列序 "
    "A..AA 逐列对应 / 本轮按模板改齐的 6 处口径 + M 合并 + AA 新补）"
    " + 非模板列字段的**真消费方**普查（先筛出 import useG1Detail/TradingDetailRow 的 10 个"
    "文件再统计 —— 按名字全仓统计毫无意义：remark 命中 11083 次、aje 1886 次，全是别的"
    " composable 的同名字段）"
    " + BP-5 已修（foundation Task 5，slice status=FIXED，守卫 9 passed）"
    " + 模板编制思路：成本与累计公允价值变动**双桶**分列，期初→本期变动→期末三段滚动，"
    "每段各有「未审 / 账项调整 / 审定」三层，末端扣「超过一年到期的部分」得报表数"
)


def _sheets_payload() -> list[dict[str, Any]]:
    """受管 spec → 契约 `sheets[]`（一律走框架层引擎的规范产出）。

    按 `sheet_key` 分组是防御性的（G1 单区 ⇒ 实际只有一组）：将来若在同一张 sheet 上
    加第二个受管区，这里自动合成「一张 sheet + 多条 tables」而不是产出两个同
    `excel_name` 的条目（G9 三区就是这么组合的）。
    """
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        spec_to_contract_sheet_payload,
    )

    sheets: list[dict[str, Any]] = []
    by_sheet_key: dict[str, dict[str, Any]] = {}
    for spec in managed_row_table_specs():
        produced = spec_to_contract_sheet_payload(spec)
        existing = by_sheet_key.get(spec.sheet_key)
        if existing is None:
            by_sheet_key[spec.sheet_key] = produced
            sheets.append(produced)
        else:
            existing["tables"].extend(produced["tables"])
    return sheets


def build_contract_payload() -> dict[str, Any]:
    template_payload = template_definition_payload()
    sheets = _sheets_payload()
    if not sheets:
        raise EntrySelectionError("G1 当前无受管 sheet")

    return {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "contract_id": ADAPTER_ID,
        "semantic_version": "1.0.0",
        "review_status": "reviewed",
        "document_type": "xlsx",
        "template_definition_sha256": canonical_digest(template_payload),
        "instrumentation_definition_sha256": canonical_digest(
            instrumentation_definition_payload()
        ),
        "template": {
            "relative_path": TEMPLATE_RELATIVE_PATH,
            "template_sha256": TEMPLATE_SHA256,
            "normalized_structure_hash": template_payload["normalized_structure_hash"],
        },
        "identity_carriers": [
            "hidden_sheet",
            "defined_name",
            "excel_table",
            "hidden_uuid_column",
        ],
        "sheets": sheets,
        "review": {
            "entry_id": ENTRY_ID,
            "pilot_class": PHASE5_WAVE,
            "authority_root": "backend/wp_templates",
            "html_store": {
                "table": "checklist_responses",
                "item_ids": list(all_store_item_ids()),
                "shape": "json_array_of_row_objects",
                "payload_column": PAYLOAD_COLUMN,
                "payload_column_mode": PAYLOAD_COLUMN_MODE,
                "payload_column_source": (
                    "audit-platform/frontend/src/components/workpaper/composables/"
                    "useG1Detail.ts —— 写入点为 "
                    "debouncedSave(ITEM_ID, { remark: JSON.stringify(list) })"
                ),
                "note": _HTML_STORE_NOTE,
            },
            "reviewed_basis": _REVIEWED_BASIS,
        },
    }


def contract_file_path() -> Path:
    return contract_path_for(ADAPTER_ID)


def load_contract_from_disk() -> SyncContract:
    return load_contract(ADAPTER_ID)


def assert_contract_file_matches_source() -> SyncContract:
    expected = build_contract_payload()
    on_disk = load_contract_from_disk()
    if canonical_digest(on_disk.canonical_payload) != canonical_digest(expected):
        raise EntrySelectionError(
            "磁盘 per-entry contract 与本模块现算 payload 不一致 —— "
            f"disk={canonical_digest(on_disk.canonical_payload)} "
            f"source={canonical_digest(expected)}；"
            "请用 generate_phase5_g1_contract.py --apply 重生成"
        )
    parse_contract(expected, adapter_id=ADAPTER_ID)
    return on_disk


# ═══════════════════════════════════════════════════════════════════════════
# 6. store 投影/合并（**薄转发**框架层，≤3 行 —— 单区，不需伴生模块）
# ═══════════════════════════════════════════════════════════════════════════


def _spec_of_store_item(store_item_id: str) -> Any:
    """store item → 受管 spec。未登记即抛（不静默跳过）。"""
    for spec in managed_row_table_specs():
        if spec.store_item_id == store_item_id:
            return spec
    raise EntrySelectionError(
        f"store item {store_item_id!r} 不在 G1 受管清单里；"
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

    :param store_item_id: 指定按哪个受管区投影；缺省用 :data:`STORE_ITEM_ID`。

    🔴 **签名形态是刚性的**：`payload` 必须是**第一个位置参数**、其余走关键字。零回归门
    `scripts/check/check_sync_provider_golden_digest.py` 按
    `mod.build_store_projection(rows, contract=contract)` 调用 —— 写成
    `(store_item_id, payload, *, contract)` 两位置参的 F1/F2 在该门上直接
    `TypeError`（G2 初版照抄 F1 也踩过）。
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
# 7. manifest capability 检查
# ═══════════════════════════════════════════════════════════════════════════


def manifest_capability_enabled(*, manifest: Mapping[str, Any] | None = None) -> bool:
    try:
        assert_manifest_capability_enabled(manifest=manifest)
    except EntrySelectionError:
        return False
    return True


def assert_manifest_capability_enabled(
    *, manifest: Mapping[str, Any] | None = None
) -> None:
    entry = manifest_entries_by_id(
        manifest if manifest is not None else load_entry_manifest()
    ).get(ENTRY_ID)
    if entry is None:
        raise EntrySelectionError(f"{ENTRY_ID} 不在 manifest 里")
    cap = capability_of(entry)
    if cap is not Capability.bidirectional:
        raise EntrySelectionError(f"{ENTRY_ID} capability={cap!r}，期望 bidirectional")
    # 🔴 R3 安全补丁（D4/F1/G2/G9/G10/G8/G14 同款）：overlay 裁决 bidirectional 后 adapter_id 必须回写
    #    （本行注释里的码是**先例清单**，不是 G1 自己的码）
    aid = str(entry.get("adapter_id") or "")
    if aid and aid != ADAPTER_ID:
        raise EntrySelectionError(
            f"{ENTRY_ID} adapter_id={aid!r} 与本 provider 的 {ADAPTER_ID!r} 不符"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 8. adapter 注册与宿主接线（照 `phase5_g2_interest_receivable`）
# ═══════════════════════════════════════════════════════════════════════════


def build_matcher() -> EntryMatcher:
    """matcher 域：幻影码 `G1I` + `document_type="xlsx"`（`sheet_keys` 留空，见模块头）。"""
    return EntryMatcher(document_type="xlsx", wp_codes=WP_CODES)


def build_registration(
    *,
    adapter: Any,
    bundle: Any,
    descriptor: DescriptorFacts,
    room: RoomFacts,
    contract: SyncContract | None = None,
) -> AdapterRegistration:
    return AdapterRegistration(
        adapter=adapter,
        entry_id=ENTRY_ID,
        matcher=build_matcher(),
        bundle=bundle,
        descriptor=descriptor,
        room=room,
        declared_capability=Capability.bidirectional,
        contract=(contract if contract is not None else load_contract_from_disk()),
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
    registration = build_registration(
        adapter=adapter,
        bundle=bundle,
        descriptor=descriptor,
        room=room,
        contract=contract,
    )
    registry.register(registration)
    return registration


async def resolve_published_frozen_definitions(
    *, session: Any, representation: Any, contract: SyncContract
) -> Any:
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.published_identity_observer import (
        observe_published_frozen_definitions,
    )
    from app.services.workpaper_sync.resolution import CanonicalResolutionService

    observation = await observe_published_frozen_definitions(
        session=session,
        resolution=CanonicalResolutionService(
            session, CanonicalArtifactRepository(_BACKEND_ROOT)
        ),
        representation=representation,
        correlation_id=f"{ADAPTER_ID}@{getattr(representation, 'id', None)}",
    )
    if observation.definitions.contract.canonical_sha256 != contract.canonical_sha256:
        raise EntrySelectionError(
            f"entry {ENTRY_ID}: 观测器读出的契约 digest "
            f"{observation.definitions.contract.canonical_sha256} "
            f"与本模块 source-locked 的 {contract.canonical_sha256} 不一致"
        )
    return observation


async def attach_pilot_adapters(
    registry: WorkpaperSyncAdapterRegistry, *, session: Any
) -> tuple[str, ...]:
    """发布链编排：attach G1 adapter（照 G2/G9/G10/G8/G14 同构）。

    第③环（published representation）缺供给时**返回空元组**而不是伪造通过 ——
    BP-1~BP-3 是平台级欠账，如实登记为 `upstream_gap`。
    """
    if ADAPTER_ID in {reg.adapter_id for reg in registry.registrations()}:
        return ()
    if not manifest_capability_enabled():
        return ()

    import sqlalchemy as sa

    from app.models.workpaper_sync_models import WorkpaperContentRepresentation
    from app.services.workpaper_sync import entry_source_facts as facts
    from app.services.workpaper_sync.adapters.excel import build_excel_adapter
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.projection_target_resolution import (
        resolve_visible_current_representation_id,
    )
    from app.services.workpaper_sync.resolution import CanonicalResolutionService

    representation_id = await resolve_visible_current_representation_id(
        session, entry_id=ENTRY_ID
    )
    if representation_id is None:
        return ()
    representation = (
        await session.execute(
            sa.select(WorkpaperContentRepresentation).where(
                WorkpaperContentRepresentation.id == representation_id
            )
        )
    ).scalar_one_or_none()
    if representation is None or representation.definition_bundle_id is None:
        return ()

    resolution = CanonicalResolutionService(
        session, CanonicalArtifactRepository(_BACKEND_ROOT)
    )
    bundle = await resolution.load_bundle_snapshot(representation.definition_bundle_id)
    contract = assert_contract_file_matches_source()
    entry = manifest_entries_by_id(load_entry_manifest())[ENTRY_ID]
    descriptor = facts.observe_descriptor_facts(entry)
    if descriptor is None:
        raise EntrySelectionError(f"entry {ENTRY_ID} 的宿主实测不可达")
    observation = await resolve_published_frozen_definitions(
        session=session, representation=representation, contract=contract
    )
    register_adapter(
        registry,
        adapter=build_excel_adapter(
            definitions=observation.definitions,
            binding=observation.identity_binding,
            direction="html_to_oo",
        ),
        bundle=bundle,
        descriptor=descriptor,
        room=facts.observe_room_facts(entry),
        contract=contract,
    )
    return (ADAPTER_ID,)


__all__ = [
    "ENTRY_ID",
    "ADAPTER_ID",
    "STORE_ITEM_ID",
    "build_store_projection",
    "merge_projection_into_store_rows",
    "iter_store_rows",
]
