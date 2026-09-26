# -*- coding: utf-8 -*-
"""D6 合同资产「明细表 D6-2」—— Phase 5 第四个 canary（harness 无关的独立 entry 双向路径）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Phase 5 (G5-1)

═══ 与 D3/D7 同范式（两级表头 + 账龄组），但账龄字段是 FLAT top-level 键（非 nested）═══

受管 sheet = `明细表D6-2`（openpyxl 逐格实测）：两级表头（行 12 组标题 + 行 13 账龄子标题），
32 列 A-AF，含两个账龄组（期初审定账龄 K-N / 期末审定账龄 U-X，各 4 段固定 1年以下/1-2/2-3/
3年以上）。数据区行 14-25，footer 行 26「合   计」（**3 半角空格，同 D7**，非 D3 纯两字）。
三个公式列逐行：J=G+H+I（期初审定）、Q=G+O-P（期末未审，借方科目 借增贷减，**用 G 期初未审
不是 J 期初审定**）、T=Q+R+S（期末审定）。

🔴 与 D3/D7 关键差异：**账龄是 useD6Detail.DetailRow 的 FLAT top-level 键**（agePrior1y /
agePrior1to2y / agePrior2to3y / agePrior3yAbove / ageEnd1y / ... ），不是 nested
`agingPrior/{seg}`。故 json_path 就是键本身、无 `/` 分层；但 K:N / U:X 在 Excel 里是 merged
4-col 组，仍带 group_source_ref。

HTML store = `checklist_responses` 单条 item `D6-2-rows`（前端 useD6Detail.ts 的 DetailRow
整行数组 JSON.stringify）。D6-2-rows 全库 0 行（明细表从未录入，同 H1/D3 空表单），首版空发布。

wp_code 裁决 = adjudication 文件的 `['D6']`（载荷落点）；模块 WP_CODES = manifest 冻结的
`{'D6C'}`（宿主 GtD6ContractAssets CamelCase 幻影码，finder 零命中）—— 同 D7/D3 双码分工。
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Iterator, Mapping, Sequence

from app.services.workpaper_sync.adapters.registry import (
    AdapterRegistration,
    EntryMatcher,
    WorkpaperSyncAdapterRegistry,
)
from app.services.workpaper_sync.contracts import (
    CONTRACT_SCHEMA_VERSION,
    FieldSpec,
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
    InstrumentationError,
    build_instrumentation_payload,
    build_template_payload,
    normalized_structure_hash,
)
from app.services.workpaper_sync.models import (
    AuthorityModel,
    BundleSlot,
    DefinitionKind,
    SyncDomainError,
)
from app.services.workpaper_sync.sheet_geometry import col_index, snake


class EntrySelectionError(SyncDomainError):
    """冻结的 canary entry 不再满足选型必要条件（manifest / 模板真源漂移即打红）。"""

    error_code = "sync_phase5_d6_selection_invalid"


class StorePayloadError(SyncDomainError):
    """HTML store 大 JSON 载荷形态不合法（非数组、缺 row identity、重复 identity）。"""

    error_code = "sync_phase5_d6_store_payload_invalid"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量（从真实 manifest / 真库实测）
# ═══════════════════════════════════════════════════════════════════════════

PHASE5_WAVE: Final[str] = "phase5_contract_assets"
ENTRY_ID: Final[str] = "xlsx/gt-d6-contract-assets"
ADAPTER_ID: Final[str] = "d6.contract_assets_detail"
#: manifest 冻结的 wp_code_pattern（宿主 GtD6ContractAssets CamelCase 幻影码，finder 零命中）。
WP_CODES: Final[frozenset[str]] = frozenset({"D6C"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "D/D6 合同资产.xlsx"
TEMPLATE_SHA256: Final[str] = (
    "88125e42d79d72813c5d460be2d925adb623d85f881a177dcb4eb7c9ec1e218c"
)
MANAGED_SHEET: Final[str] = "明细表D6-2"
TEMPLATE_ID: Final[str] = "D62"
SHEET_KEY: Final[str] = f"{TEMPLATE_ID.lower()}-managed"
ROWS_TABLE_KEY: Final[str] = "contract_assets_detail_rows"

#: 两级表头：组标题在行 12，账龄子标题在行 13（openpyxl 逐格实测）。
HEADER_GROUP_ROW: Final[int] = 12
HEADER_LEAF_ROW: Final[int] = 13

#: 数据区与 footer（openpyxl 逐格实测：数据 14-25，合计 26）。
FIRST_DATA_ROW: Final[int] = 14
LAST_DATA_ROW: Final[int] = 25
FOOTER_ROW: Final[int] = 26

#: 最后一列受管业务列（AD 期后结转金额）与隐藏 row UUID 列（AF 空档之后）。
MANAGED_LAST_COL: Final[str] = "AD"
UUID_COL: Final[str] = "AG"

TABLE_NAME: Final[str] = f"GT_{TEMPLATE_ID}_ROWS"
AUTHORITY_MODEL: Final[AuthorityModel] = AuthorityModel.projection_contract
#: 🔴 footer 单元格 A26 精确文本 = 「合」+3 半角空格+「计」（同 D7，非 D3 纯两字）。
FOOTER_MARKER: Final[str] = "合   计"

STORE_ITEM_ID: Final[str] = "D6-2-rows"
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
ROW_IDENTITY_STORE_KEY: Final[str] = "rowId"

#: 两个账龄组：`(组标题单元格, [(flat store 键, 列标, 行 13 子标题)...])`。
#: 🔴 D6 账龄键是 FLAT（agePrior1y 而非 agingPrior/within1），故 json_path=键本身。
AGING_GROUPS: Final[tuple[tuple[str, tuple[tuple[str, str, str], ...]], ...]] = (
    (
        f"K{HEADER_GROUP_ROW}",
        (
            ("agePrior1y", "K", "1年以下"),
            ("agePrior1to2y", "L", "1～2年"),
            ("agePrior2to3y", "M", "２～3年"),
            ("agePrior3yAbove", "N", "3年以上"),
        ),
    ),
    (
        f"U{HEADER_GROUP_ROW}",
        (
            ("ageEnd1y", "U", "1年以下"),
            ("ageEnd1to2y", "V", "1～2年"),
            ("ageEnd2to3y", "W", "２～3年"),
            ("ageEnd3yAbove", "X", "3年以上"),
        ),
    ),
)


#: 22 个标量列（非账龄）：`(column_key, 列标, mode, value_type, store json 键, 行 12 表头文本)`。
#: 🔴 顺序即 Excel 列序。store json 键 = 前端 useD6Detail.DetailRow 的 camelCase 键。
#: J/Q/T 三列在模板里逐行有真公式（J=G+H+I / Q=G+O-P / T=Q+R+S）⇒ formula。
SCALAR_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    ("seq_no", "A", "editable", "integer", "seqNo", "序号"),
    ("contract_name", "B", "editable", "text", "contractName", "合同名称/项目名称"),
    ("contract_type", "C", "editable", "enum", "contractType", "类型"),
    ("customer_name", "D", "editable", "text", "customerName", "客户名称"),
    ("company_code", "E", "editable", "text", "companyCode", "公司代码"),
    ("related_party_type", "F", "editable", "enum", "relatedPartyType", "关联关系"),
    ("prior_unadjusted", "G", "editable", "amount", "priorUnadjusted", "期初未审数"),
    ("prior_aje", "H", "editable", "amount", "priorAje", "期初账项调整"),
    ("prior_rje", "I", "editable", "amount", "priorRje", "期初重分类调整"),
    ("prior_audited", "J", "formula", "amount", "priorAudited", "期初审定余额"),
    ("debit_amount", "O", "editable", "amount", "debitAmount", "借方发生"),
    ("credit_amount", "P", "editable", "amount", "creditAmount", "贷方发生"),
    ("end_unadjusted", "Q", "formula", "amount", "endUnadjusted", "期末未审余额"),
    ("end_aje", "R", "editable", "amount", "endAje", "账项调整"),
    ("end_rje", "S", "editable", "amount", "endRje", "重分类调整"),
    ("end_audited", "T", "formula", "amount", "endAudited", "期末审定余额"),
    ("receivable_within_1y", "Y", "editable", "amount", "receivableWithin1y", "1年以内收款权"),
    ("receivable_above_1y", "Z", "editable", "amount", "receivableAbove1y", "1年以上收款权"),
    ("is_in_construction_period", "AA", "editable", "text", "isInConstructionPeriod", "是否在建设期或质保期内"),
    ("credit_risk_group", "AB", "editable", "text", "creditRiskGroup", "信用风险组合方式"),
    ("is_confirmed", "AC", "editable", "text", "isConfirmed", "是否函证"),
    ("post_period_settlement", "AD", "editable", "amount", "postPeriodSettlement", "期后结转金额"),
)


#: 几何纯函数收敛进框架层 sheet_geometry（Task 5，逐字节等价）；保留原名薄别名。
_snake = snake
_col_index = col_index


#: column_key → 账龄组标题单元格（只有账龄列有）。
#: 🔴 保留独立 mapping 供既有调用方（如有）；权威来源已内联进 `SPEC_D62.field_specs` 第 7 位。
GROUP_HEADER_CELLS: Final[Mapping[str, str]] = {
    _snake(flat_key): group_cell
    for group_cell, cols in AGING_GROUPS
    for flat_key, _col, _leaf in cols
}

# ═══════════════════════════════════════════════════════════════════════════
# Task 16 声明化（spec: d1-sync-row-table-engine-and-d1-coverage）：SPEC_D62 是本 entry
# 唯一权威声明。🔴 D6 是引擎 flat 账龄路径的**唯一样本**（D3/D7 是 nested），与它们同批做
# 正是为了让两条路径在同一轮对照验证。
# ═══════════════════════════════════════════════════════════════════════════

from app.services.workpaper_sync.phase5_row_table_sheet import (  # noqa: E402
    AgingGroupSpec,
    AgingLayout,
    RowTableSheetSpec,
    StoreKind,
)
from app.services.workpaper_sync.phase5_row_table_sheet import (  # noqa: E402
    managed_field_specs as _engine_managed_field_specs,
)

#: SCALAR_FIELD_SPECS 是 6 元组（无 group_header_cell 独立位），补空第 7 位内联（裁决 3）。
_SCALAR_FIELD_SPECS_7TUPLE: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = tuple(
    (*row, "") for row in SCALAR_FIELD_SPECS
)

#: flat 账龄两组，翻成框架层 `AgingGroupSpec`（`segments` 三元 `(flat_key, column, leaf_label)`，
#: 与 D6 原 `AGING_GROUPS` 的 `cols` 逐字一致；`json_prefix` flat 时不使用，留空）。
_AGING_GROUP_SPECS_D62: Final[tuple[AgingGroupSpec, ...]] = tuple(
    AgingGroupSpec(json_prefix="", group_header_cell=group_cell, segments=cols)
    for group_cell, cols in AGING_GROUPS
)

SPEC_D62: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET,
    sheet_key=SHEET_KEY,
    table_key=ROWS_TABLE_KEY,
    template_id=TEMPLATE_ID,
    table_name=TABLE_NAME,
    uuid_col=UUID_COL,
    first_data_row=FIRST_DATA_ROW,
    last_data_row=LAST_DATA_ROW,
    footer_row=FOOTER_ROW,
    header_group_row=HEADER_GROUP_ROW,
    header_leaf_row=HEADER_LEAF_ROW,
    store_item_id=STORE_ITEM_ID,
    empty_payload=EMPTY_STORE_PAYLOAD,
    row_identity_key=ROW_IDENTITY_STORE_KEY,
    store_kind=StoreKind.rows,
    field_specs=_SCALAR_FIELD_SPECS_7TUPLE,
    formula_columns=("J", "Q", "T"),
    aging_layout=AgingLayout.flat,
    aging_groups=_AGING_GROUP_SPECS_D62,
    footer_marker=FOOTER_MARKER,
    error_label="D6-2 明细表",
    #: 🔴 D6 首列 `seq_no` 是整数序号，`0` 是合法真值不是"空"信号，幽灵行防护改用
    #: 第 1 位 `contract_name`（原实现即 `MANAGED_FIELD_SPECS[1]`，见框架层
    #: `RowTableSheetSpec.ghost_row_anchor_index` 文档）。
    ghost_row_anchor_index=1,
)

#: 30 个受管字段 = 22 标量 + 8 账龄，按 Excel 列序（A→AD）排列。
#: 🔴 本值现由框架层 `managed_field_specs(SPEC_D62)` 现算；`_aging_field_specs()` 函数体
#: 已删（改用框架层 `expand_aging_fields` 的 flat 分支）。
MANAGED_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str], ...]] = tuple(
    row[:6] for row in _engine_managed_field_specs(SPEC_D62)
)

#: 三个公式列的只读区域（J/Q/T）。
#: 🔴 本值现由框架层 `SPEC_D62.formula_mask` property 现算，provider 不再手写字面量。
FORMULA_MASK: Final[tuple[str, ...]] = SPEC_D62.formula_mask


# ═══════════════════════════════════════════════════════════════════════════
# 2. 权威模板
# ═══════════════════════════════════════════════════════════════════════════

_BACKEND_ROOT: Final[Path] = Path(__file__).resolve().parents[3]


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
            f"冻结哨兵={TEMPLATE_SHA256} —— `backend/wp_templates/` 运行时只读（Requirement 9.9）"
        )
    return data


# ═══════════════════════════════════════════════════════════════════════════
# 3. 选型必要条件（真实 manifest / 真实 resolver，不经封闭枚举）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class TemplateResolutionFacts:
    by_wp_code: Mapping[str, Sequence[Any]]
    parent_code: str
    parent_resolved_path: Any


def assert_no_implicit_template_fallback(
    resolution: TemplateResolutionFacts, *, wp_codes: frozenset[str]
) -> None:
    missing = sorted(wp_codes - set(resolution.by_wp_code))
    if missing:
        raise EntrySelectionError(
            f"缺少 wp_code {missing} 的 finder 实测结果 —— 零回退判据不得对未观测的码放行"
        )
    leaked = {
        code: [str(item) for item in hits if item]
        for code, hits in resolution.by_wp_code.items()
        if any(hits)
    }
    if leaked:
        raise EntrySelectionError(
            f"wp_code {sorted(leaked)} 在 `wp_template_finder` 上解析到了 {leaked} —— "
            "本 canary 的零回退判据要求它们全部解析不到任何文件"
        )
    resolved = resolution.parent_resolved_path
    if resolved is None or Path(str(resolved)).resolve() != authoritative_template_path().resolve():
        raise EntrySelectionError(
            f"父码 {resolution.parent_code!r} 的 canonical resolver 落在 {resolved} —— "
            f"与冻结的权威模板 {TEMPLATE_RELATIVE_PATH!r} 不是同一份文件"
        )


def assert_entry_selectable(
    *,
    resolution: TemplateResolutionFacts,
    manifest: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    payload = manifest if manifest is not None else load_entry_manifest()
    entries = manifest_entries_by_id(payload)
    entry = entries.get(ENTRY_ID)
    if entry is None:
        raise EntrySelectionError(
            f"冻结的 canary entry {ENTRY_ID!r} 不在 source-backed manifest 里 —— 宿主挂载点已变"
        )
    if str(entry.get("document_type") or "") != "xlsx":
        raise EntrySelectionError(f"{ENTRY_ID!r} document_type 非 xlsx")
    if not entry.get("independent_entry"):
        raise EntrySelectionError(
            f"{ENTRY_ID!r} independent_entry={entry.get('independent_entry')!r} —— 重复入口不得注册"
        )
    profile_id = str((entry.get("scenario_profile") or {}).get("profile_id") or "")
    if profile_id != EXPECTED_PROFILE_ID:
        raise EntrySelectionError(
            f"{ENTRY_ID!r} profile_id={profile_id!r} 与冻结的 {EXPECTED_PROFILE_ID!r} 不符"
        )
    codes = {str(c) for c in (entry.get("wp_match") or {}).get("wp_code_patterns") or ()}
    if codes != set(WP_CODES):
        raise EntrySelectionError(
            f"{ENTRY_ID!r} wp_code_patterns={sorted(codes)} 与冻结的 {sorted(WP_CODES)} 不一致"
        )
    assert_no_implicit_template_fallback(resolution, wp_codes=frozenset(codes))
    return entry


# ═══════════════════════════════════════════════════════════════════════════
# 4. instrumentation spec 与 definition payloads
# ═══════════════════════════════════════════════════════════════════════════


def instrumentation_spec() -> ExcelInstrumentationSpec:
    return ExcelInstrumentationSpec(
        entry_id=ENTRY_ID,
        template_id=TEMPLATE_ID,
        template_relative_path=TEMPLATE_RELATIVE_PATH,
        managed_sheet=MANAGED_SHEET,
        first_data_row=FIRST_DATA_ROW,
        last_data_row=LAST_DATA_ROW,
        footer_row=FOOTER_ROW,
        managed_last_col=MANAGED_LAST_COL,
        uuid_col=UUID_COL,
        table_name=TABLE_NAME,
    )


def template_definition_payload() -> dict[str, Any]:
    data = read_authoritative_template()
    return build_template_payload(
        spec=instrumentation_spec(),
        template_sha256=TEMPLATE_SHA256,
        structure_hash=normalized_structure_hash(data),
    )


def instrumentation_definition_payload() -> dict[str, Any]:
    return build_instrumentation_payload(
        spec=instrumentation_spec(),
        template_definition_sha256=canonical_digest(template_definition_payload()),
        template_sha256=TEMPLATE_SHA256,
        gate=excel_carrier_gate(),
    )


def authority_model_payload() -> dict[str, Any]:
    return {
        "schema_version": "authority-model-definition:v1",
        "authority_model": AUTHORITY_MODEL.value,
        "content_authority": "structured_projection",
        "merge_model": "stable_field_three_way",
        "required_slots": [
            BundleSlot.template.value,
            BundleSlot.instrumentation.value,
            BundleSlot.contract.value,
        ],
        "entry_id": ENTRY_ID,
        "pilot_class": PHASE5_WAVE,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 5. per-entry contract（与磁盘契约双向锁死）
# ═══════════════════════════════════════════════════════════════════════════


def _src(cell: str) -> str:
    return f"源xlsx!{MANAGED_SHEET}!{cell}"


def stable_key_for(column_key: str, row_identity: str = "{row_uuid}") -> str:
    """薄转发框架层同名函数（Task 16 声明化，逐字节等价）。"""
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        stable_key_for as _engine_stable_key_for,
    )

    return _engine_stable_key_for(SPEC_D62, column_key, row_identity)


def _rows_table_payload() -> dict[str, Any]:
    fields: list[dict[str, Any]] = []
    for column_key, column, mode, value_type, json_path, header_text in MANAGED_FIELD_SPECS:
        spec: dict[str, Any] = {
            "stable_field_key": stable_key_for(column_key),
            "json_pointer": f"/rows/{{row_uuid}}/{json_path}",
            "column_key": column_key,
            "cell": {"column": column, "row_from": "row_identity"},
            "mode": mode,
            "value_type": value_type,
            "source_ref": _src(f"{column}{FIRST_DATA_ROW}"),
            "header_source_ref": _src(
                f"{column}{HEADER_LEAF_ROW if column_key in GROUP_HEADER_CELLS else HEADER_GROUP_ROW}"
            ),
            "store_item_id": STORE_ITEM_ID,
            "header_text": header_text,
        }
        group_cell = GROUP_HEADER_CELLS.get(column_key)
        if group_cell:
            spec["group_source_ref"] = _src(group_cell)
        fields.append(spec)
    return {
        "table_key": ROWS_TABLE_KEY,
        "anchor": f"A{HEADER_GROUP_ROW}",
        "header_rows": 2,
        "row_identity": {"kind": "field", "json_pointer": f"/rows/*/{ROW_IDENTITY_STORE_KEY}"},
        "delete_policy": "tombstone",
        "footer_anchor": {
            "marker": FOOTER_MARKER,
            "search_column": "A",
            "carries_total_formula": True,
            "note": (
                "footer 行 A26「合   计」（3 半角空格，同 D7）。声明为真使结构性插行有权按声明"
                "位移量扩张该区间"
            ),
        },
        "formula_mask": list(FORMULA_MASK),
        "fields": fields,
    }


_HTML_STORE_NOTE: Final[str] = (
    "整张合同资产明细表存成这一条 item 的 remark（JSON 数组字符串，useD6Detail 的 "
    "JSON.stringify(rows)）。本契约按 stable field + row rowId 拆开。🔴 账龄是 FLAT top-level "
    "键（agePrior1y / ageEnd1y ...），json_pointer 无 nested 分层（与 D3/D7 的 nested "
    "agingPrior/within1 不同）。"
)

_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐 sheet 直读净化后权威模板 D/D6 合同资产.xlsx（外链净化后 sha256 88125e42），"
    "只取受管 sheet 明细表D6-2：两级表头 行 12（组标题）/ 行 13（账龄子标题 1年以下/1～2/２～3/"
    "3年以上），32 列 A-AF，数据区 14-25，J/Q/T 三列逐行公式 =G+H+I / =G+O-P（借方科目）/ "
    "=Q+R+S，A26「合   计」footer（3 半角空格）；20 标量列 + 两个账龄组各 4 段（K-N 期初 / U-X "
    "期末，FLAT 键 agePrior*/ageEnd*）；字段键与前端 useD6Detail.DetailRow 逐字段锁死。wp_code=D6"
    "（载荷落点：D6-2-rows 全库 0 行同 H1/D3 空表单，D6 wp 未删除有 file_path；非 D6C 幻影码）"
)


def build_contract_payload() -> dict[str, Any]:
    from app.services.workpaper_sync.excel_extract import TABLE_SHEET_ANCHOR

    template_payload = template_definition_payload()
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
        "sheets": [
            {
                "sheet_key": SHEET_KEY,
                "excel_name": MANAGED_SHEET,
                "locator": {"anchor": TABLE_SHEET_ANCHOR},
                "tables": [_rows_table_payload()],
            }
        ],
        "review": {
            "entry_id": ENTRY_ID,
            "pilot_class": PHASE5_WAVE,
            "authority_root": "backend/wp_templates",
            "html_store": {
                "table": "checklist_responses",
                "item_id": STORE_ITEM_ID,
                "row_identity_key": ROW_IDENTITY_STORE_KEY,
                "shape": "json_array_of_row_objects",
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
            f"disk={canonical_digest(on_disk.canonical_payload)} source={canonical_digest(expected)}；"
            "请用 `& d:/GT_plan/.venv/Scripts/python.exe "
            "backend/scripts/gen/generate_phase5_d6_contract.py --apply` 重生成"
        )
    parse_contract(expected, adapter_id=ADAPTER_ID)
    return on_disk


# ═══════════════════════════════════════════════════════════════════════════
# 6. HTML store 载荷拆分（stable field + row UUID，流式；D6 账龄 FLAT）
# ═══════════════════════════════════════════════════════════════════════════


#: 🔴 Task 16 声明化：`store_row_identity` / `iter_store_rows` / `_resolve_json_path` /
#: `split_store_row` 四个内部 helper 已收敛进框架层 `phase5_row_table_sheet`。
#: `build_store_projection` 保留同名薄转发。


def build_store_projection(
    payload: str | bytes | Sequence[Any],
    *,
    contract: SyncContract,
    limits: Any | None = None,
) -> Any:
    """薄转发框架层 `build_store_projection(SPEC_D62, ...)`（逐字节等价）。

    🔴 **必须转译引擎异常**（2026-09-26 修 Task 16 遗留回归）：引擎抛
    `RowTableStorePayloadError(Exception)` 非 domain 错误 ⇒ 直接冒泡是 **opaque 500**；
    收敛前本函数抛带 `error_code` 的 `StorePayloadError(SyncDomainError)` ⇒ **4xx**。
    畸形 store 载荷属用户侧数据问题，必须 4xx。判据见
    `test_store_payload_error_stays_domain_error.py`。
    """
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        RowTableStorePayloadError,
        build_store_projection as _engine_build_store_projection,
    )

    try:
        return _engine_build_store_projection(
            SPEC_D62, payload, contract=contract, limits=limits
        )
    except RowTableStorePayloadError as exc:
        raise StorePayloadError(str(exc)) from exc


def merge_projection_into_store_rows(
    *,
    projection: Any,
    base_rows: list[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], int, int, set[str]]:
    """薄转发框架层 `merge_projection_into_store_rows(SPEC_D62, ...)`（逐字节等价）。

    🔴 幽灵行防护锚点取 `SPEC_D62.ghost_row_anchor_index=1`（`contract_name`，不是
    `[0]` 的 `seq_no`）—— D6 首列是整数序号，`0` 是合法真值不是"空"信号；这条差异化
    已通过框架层 `ghost_row_anchor_index` 参数表达（Task 16 复盘补：不是所有七家都
    用第 0 位锚点，D5/D6 是例外，二者原实现均用 `[1]`）。`_set_json_path` 已收敛进
    框架层 `set_json_path`。
    """
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        merge_projection_into_store_rows as _engine_merge,
    )

    return _engine_merge(SPEC_D62, projection=projection, base_rows=base_rows)


# ═══════════════════════════════════════════════════════════════════════════
# 7. 发布
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Phase5Definitions:
    authority_model_definition_id: uuid.UUID
    authority_model_definition_sha256: str
    template_definition_id: uuid.UUID
    template_definition_sha256: str
    instrumentation_definition_id: uuid.UUID
    instrumentation_definition_sha256: str
    contract_definition_id: uuid.UUID
    contract_definition_sha256: str
    bundle_id: uuid.UUID
    bundle_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "entry_id": ENTRY_ID,
            "adapter_id": ADAPTER_ID,
            "authority_model": AUTHORITY_MODEL.value,
            "authority_model_definition_id": str(self.authority_model_definition_id),
            "authority_model_definition_sha256": self.authority_model_definition_sha256,
            "template_definition_id": str(self.template_definition_id),
            "template_definition_sha256": self.template_definition_sha256,
            "instrumentation_definition_id": str(self.instrumentation_definition_id),
            "instrumentation_definition_sha256": self.instrumentation_definition_sha256,
            "contract_definition_id": str(self.contract_definition_id),
            "contract_definition_sha256": self.contract_definition_sha256,
            "definition_bundle_id": str(self.bundle_id),
            "definition_bundle_sha256": self.bundle_sha256,
        }


async def publish_definitions(publisher: Any) -> Phase5Definitions:
    contract = assert_contract_file_matches_source()
    authority = await publisher.publish_definition(
        kind=DefinitionKind.authority_model,
        payload=authority_model_payload(),
        logical_id=f"{ADAPTER_ID}.authority-model",
        semantic_version="1.0.0",
    )
    template_payload = template_definition_payload()
    template = await publisher.publish_definition(
        kind=DefinitionKind.template,
        payload=template_payload,
        logical_id=f"{ADAPTER_ID}.template",
        semantic_version="1.0.0",
        blob_bytes=read_authoritative_template(),
        structure_hash=template_payload["normalized_structure_hash"],
    )
    instrumentation = await publisher.publish_definition(
        kind=DefinitionKind.instrumentation,
        payload=instrumentation_definition_payload(),
        logical_id=f"{ADAPTER_ID}.instrumentation",
        semantic_version="1.0.0",
    )
    contract_definition = await publisher.publish_definition(
        kind=DefinitionKind.contract,
        payload=dict(contract.canonical_payload),
        logical_id=ADAPTER_ID,
        semantic_version=contract.semantic_version,
    )
    if template.sha256 != contract.template_definition_sha256:
        raise EntrySelectionError(
            f"已发布 template digest {template.sha256} 与契约声明 "
            f"{contract.template_definition_sha256} 不一致 —— 单向引用断裂"
        )
    if instrumentation.sha256 != contract.instrumentation_definition_sha256:
        raise EntrySelectionError(
            f"已发布 instrumentation digest {instrumentation.sha256} 与契约声明 "
            f"{contract.instrumentation_definition_sha256} 不一致 —— 单向引用断裂"
        )
    bundle = await publisher.publish_bundle(
        authority_model_definition_id=authority.definition_id,
        authority_model=AUTHORITY_MODEL,
        authority_model_definition_sha256=authority.sha256,
        slots={
            BundleSlot.template: {
                "type": "definition",
                "ref": f"definition:{template.definition_id}",
                "digest": template.sha256,
            },
            BundleSlot.instrumentation: {
                "type": "definition",
                "ref": f"definition:{instrumentation.definition_id}",
                "digest": instrumentation.sha256,
            },
            BundleSlot.contract: {
                "type": "definition",
                "ref": f"definition:{contract_definition.definition_id}",
                "digest": contract_definition.sha256,
            },
        },
    )
    return Phase5Definitions(
        authority_model_definition_id=authority.definition_id,
        authority_model_definition_sha256=authority.sha256,
        template_definition_id=template.definition_id,
        template_definition_sha256=template.sha256,
        instrumentation_definition_id=instrumentation.definition_id,
        instrumentation_definition_sha256=instrumentation.sha256,
        contract_definition_id=contract_definition.definition_id,
        contract_definition_sha256=contract_definition.sha256,
        bundle_id=bundle.bundle_id,
        bundle_sha256=bundle.canonical_sha256,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 8. adapter 注册与宿主接线
# ═══════════════════════════════════════════════════════════════════════════


def build_matcher() -> EntryMatcher:
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
        contract=contract if contract is not None else load_contract_from_disk(),
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
        adapter=adapter, bundle=bundle, descriptor=descriptor, room=room, contract=contract
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
            f"{observation.definitions.contract.canonical_sha256} 与本模块 source-locked 的 "
            f"{contract.canonical_sha256} 不一致 —— 冻结身份与生产契约脱钩"
        )
    return observation


async def attach_adapters(
    registry: WorkpaperSyncAdapterRegistry, *, session: Any
) -> tuple[str, ...]:
    if ADAPTER_ID in {reg.adapter_id for reg in registry.registrations()}:
        return ()
    if not manifest_capability_enabled():
        return ()

    import sqlalchemy as sa

    from app.models.workpaper_sync_models import WorkpaperContentRepresentation
    from app.services.workpaper_sync.projection_target_resolution import (
        resolve_visible_current_representation_id,
    )
    from app.services.workpaper_sync import entry_source_facts as facts
    from app.services.workpaper_sync.adapters.excel import build_excel_adapter
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.resolution import CanonicalResolutionService

    representation_id = await resolve_visible_current_representation_id(session, entry_id=ENTRY_ID)
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

    resolution = CanonicalResolutionService(session, CanonicalArtifactRepository(_BACKEND_ROOT))
    bundle = await resolution.load_bundle_snapshot(representation.definition_bundle_id)
    contract = assert_contract_file_matches_source()
    entry = manifest_entries_by_id(load_entry_manifest())[ENTRY_ID]
    descriptor = facts.observe_descriptor_facts(entry)
    if descriptor is None:
        raise EntrySelectionError(
            f"entry {ENTRY_ID} 的宿主实测不可达（产不出 descriptor 事实）—— 不可达入口不得注册 adapter"
        )
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


def manifest_capability_enabled(*, manifest: Mapping[str, Any] | None = None) -> bool:
    try:
        assert_manifest_capability_enabled(manifest=manifest)
    except EntrySelectionError:
        return False
    return True


def assert_manifest_capability_enabled(*, manifest: Mapping[str, Any] | None = None) -> None:
    entry = manifest_entries_by_id(
        manifest if manifest is not None else load_entry_manifest()
    )[ENTRY_ID]
    capability = capability_of(entry)
    if capability is not Capability.bidirectional:
        raise EntrySelectionError(
            f"entry {ENTRY_ID} 的 manifest capability={capability.value} —— "
            "注册 bidirectional adapter 前必须先由 reviewed overlay 裁决为 bidirectional 并重生成 manifest"
        )
    if str(entry.get("adapter_id") or "") != ADAPTER_ID:
        raise EntrySelectionError(
            f"entry {ENTRY_ID} 的 manifest adapter_id={entry.get('adapter_id')!r} 与本 canary 的 {ADAPTER_ID!r} 不符"
        )


def _unused_instrumentation_error_guard() -> type[InstrumentationError]:
    return InstrumentationError


# ═══════════════════════════════════════════════════════════════════════════
# 9. provisioning / attach 白名单接口别名
# ═══════════════════════════════════════════════════════════════════════════

publish_pilot_definitions = publish_definitions
attach_pilot_adapters = attach_adapters
PILOT_WP_CODES = WP_CODES
