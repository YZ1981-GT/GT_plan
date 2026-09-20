# -*- coding: utf-8 -*-
"""D4 收入「主营业务收入明细表 D4-2」—— Phase 5 第六个 canary（位置数组行形态）。

spec: d4-revenue-matrix-bidirectional · Task 5

═══ 第五种行形态：位置数组（positional array）═══

受管 sheet = `主营业务收入明细表D4-2`（openpyxl 逐格实测 / T01）：单级表头行 11，数据区
12-23，footer 行 24「合计」（纯两字无空格）。18 条契约字段：A=product + B..M=months/0..11
+ N=period_total(formula) + O=audit_adjustment + Q/R prior + V=remark。P/S/T/U 是模板内部
公式列，进 FORMULA_MASK 但不进契约。

HTML store = `checklist_responses` 单条 item `D4-2-rows`（前端 useD4RevenueDetail.ts 的
RevenueDetailRow 整行数组）。`months` 是长度 12 的 list；json_pointer 用
`/rows/{uuid}/months/0` 等数组下标段。读写必须走共享
`app.services.workpaper_sync.json_path`（禁止本模块私有 dict-only 副本）。

wp_code：模块 WP_CODES = manifest 冻结的 `{'D4O'}`（宿主 GtD4OperatingRevenue CamelCase
幻影码，finder 零命中）；裁决码以真载荷落点 `D4` 为准（Task 6 adjudication，非本模块）。
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
    build_instrumentation_payload_for_sheets,
    build_template_payload,
    normalized_structure_hash,
)
from app.services.workpaper_sync.phase5_d4_adjudication_sheet import (
    EXPECTED_MAPPING_DIGEST_D41,
    MANAGED_SHEET_D41,
    ROWS_TABLE_KEY_MAIN as ROWS_TABLE_KEY_D41_MAIN,
    ROWS_TABLE_KEY_OTHER as ROWS_TABLE_KEY_D41_OTHER,
    ROW_IDENTITY_STORE_KEY_D41,
    SHEET_KEY_D41,
    STORE_ITEM_ID_D41,
    TEMPLATE_ID_MAIN as TEMPLATE_ID_D41_MAIN,
    TEMPLATE_ID_OTHER as TEMPLATE_ID_D41_OTHER,
    TABLE_NAME_MAIN as TABLE_NAME_D41_MAIN,
    TABLE_NAME_OTHER as TABLE_NAME_D41_OTHER,
    assert_mapping_digest_d41,
    build_store_projection_d41,
    instrumentation_spec_d41,
    merge_projection_into_d41_rows,
    sheet_payload_d41,
)
from app.services.workpaper_sync.phase5_d4_other_revenue_sheet import (
    EXPECTED_MAPPING_DIGEST_D43,
    MANAGED_SHEET_D43,
    ROWS_TABLE_KEY_D43,
    SHEET_KEY_D43,
    STORE_ITEM_ID_D43,
    TABLE_NAME_D43,
    TEMPLATE_ID_D43,
    assert_mapping_digest_d43,
    instrumentation_spec_d43,
    merge_projection_into_d43_store_rows,
    rows_table_payload_d43,
    split_store_row_d43,
)
from app.services.workpaper_sync.phase5_d4_other_check_sheet import (
    EXPECTED_MAPPING_DIGEST_D435,
    MANAGED_SHEET_D435,
    ROWS_TABLE_KEY_D435,
    ROW_IDENTITY_STORE_KEY_D435,
    SHEET_KEY_D435,
    STORE_ITEM_ID_D435,
    TABLE_NAME_D435,
    TEMPLATE_ID_D435,
    assert_mapping_digest_d435,
    build_d435_store_projection,
    instrumentation_spec_d435,
    merge_projection_into_d435_store_rows,
    rows_table_payload_d435,
    split_store_row_d435,
)
from app.services.workpaper_sync.phase5_d4_policy_check_sheet import (
    EXPECTED_MAPPING_DIGEST_D45,
    MANAGED_SHEET_D45,
    SHEET_KEY_D45,
    STORE_ITEM_ID_D45_GROUPS,
    STORE_ITEM_IDS_D45_FIXED,
    TABLE_NAME_D45,
    TEMPLATE_ID_D45,
    assert_mapping_digest_d45,
    build_d45_fixed_store_projection,
    build_d45_groups_store_projection,
    instrumentation_spec_d45,
    merge_projection_into_d45_fixed_items,
    merge_projection_into_d45_group_rows,
    sheet_payload_d45,
)
from app.services.workpaper_sync.phase5_d4_ipo_related_sheets import (
    EXPECTED_MAPPING_DIGEST_D421,
    EXPECTED_MAPPING_DIGEST_D422,
    EXPECTED_MAPPING_DIGEST_D423,
    EXPECTED_MAPPING_DIGEST_D424,
    ROWS_TABLE_KEY_D421,
    ROWS_TABLE_KEY_D422,
    ROWS_TABLE_KEY_D423,
    ROWS_TABLE_KEY_D424,
    ROW_IDENTITY_STORE_KEY_D421,
    ROW_IDENTITY_STORE_KEY_D422,
    ROW_IDENTITY_STORE_KEY_D423,
    ROW_IDENTITY_STORE_KEY_D424,
    SHEET_KEY_D421,
    SHEET_KEY_D422,
    SHEET_KEY_D423,
    SHEET_KEY_D424,
    STORE_ITEM_ID_D421,
    STORE_ITEM_ID_D422,
    STORE_ITEM_ID_D423,
    STORE_ITEM_ID_D424,
    TABLE_NAME_D421,
    TABLE_NAME_D422,
    TABLE_NAME_D423,
    TABLE_NAME_D424,
    TEMPLATE_ID_D421,
    TEMPLATE_ID_D422,
    TEMPLATE_ID_D423,
    TEMPLATE_ID_D424,
    MANAGED_SHEET_D421,
    MANAGED_SHEET_D422,
    MANAGED_SHEET_D423,
    MANAGED_SHEET_D424,
    assert_all_sibling_mapping_digests,
    build_d421_store_projection,
    build_d422_store_projection,
    build_d423_store_projection,
    build_d424_store_projection,
    instrumentation_spec_d421,
    instrumentation_spec_d422,
    instrumentation_spec_d423,
    instrumentation_spec_d424,
    merge_projection_into_d421_store_rows,
    merge_projection_into_d422_store_rows,
    merge_projection_into_d423_store_rows,
    merge_projection_into_d424_store_rows,
    rows_table_payload_d421,
    rows_table_payload_d422,
    rows_table_payload_d423,
    rows_table_payload_d424,
)
from app.services.workpaper_sync.phase5_d4_29_customer_detail import (
    MANAGED_SHEET as MANAGED_SHEET_D429,
    SHEET_KEY as SHEET_KEY_D429,
    STORE_ITEM_ID as STORE_ITEM_ID_D429,
    build_store_projection as build_d429_store_projection,
    merge_projection_into_store as merge_d429_projection_into_store,
    sheet_payload,
    assert_mapping_digest as assert_mapping_digest_d429,
)
from app.services.workpaper_sync.phase5_d4_customer_structure import (
    EXPECTED_MAPPING_DIGEST_D49,
    MANAGED_SHEET_D49,
    ROWS_TABLE_KEY_CURRENT as ROWS_TABLE_KEY_D49_CURRENT,
    ROWS_TABLE_KEY_PRIOR as ROWS_TABLE_KEY_D49_PRIOR,
    ROW_IDENTITY_STORE_KEY_D49,
    SHEET_KEY_D49,
    STORE_ITEM_ID_D49,
    TABLE_NAME_CURRENT as TABLE_NAME_D49_CURRENT,
    TABLE_NAME_PRIOR as TABLE_NAME_D49_PRIOR,
    TEMPLATE_ID_CURRENT as TEMPLATE_ID_D49_CURRENT,
    TEMPLATE_ID_PRIOR as TEMPLATE_ID_D49_PRIOR,
    assert_mapping_digest_d49,
    build_d49_store_projection,
    instrumentation_spec_d49,
    merge_projection_into_d49_store,
    merge_projection_into_d49_store_state,
    sheet_payload_d49,
)

from app.services.workpaper_sync.phase5_d4_ipo_interview_sheets import (
    codes as INTERVIEW_SHEET_CODES,
    instrumentation_spec as instrumentation_spec_interview,
    sheet_payload as interview_sheet_payload,
    store_item_id as interview_store_item_id,
    build_store_projection as build_interview_store_projection,
    merge_projection_into_store as merge_interview_projection_into_store,
)
from app.services.workpaper_sync.phase5_d4_indicator_sheet import (  # noqa: E402
    STORE_ITEM_ID_D46,
    sheet_payload_d46,
    instrumentation_spec_d46,
    build_store_projection_d46,
    merge_projection_into_d46_rows,
)
from app.services.workpaper_sync.phase5_d4_cutoff_forward_sheet import (  # noqa: E402
    STORE_ITEM_ID_D417,
    sheet_payload_d417,
    instrumentation_spec_d417,
    build_store_projection_d417,
    merge_projection_into_d417_rows,
)
from app.services.workpaper_sync.phase5_d4_cutoff_backward_sheet import (  # noqa: E402
    STORE_ITEM_ID_D418,
    sheet_payload_d418,
    instrumentation_spec_d418,
    build_store_projection_d418,
    merge_projection_into_d418_rows,
)
from app.services.workpaper_sync.phase5_d4_discount_sheet import (  # noqa: E402
    STORE_ITEM_ID_D419,
    sheet_payload_d419,
    instrumentation_spec_d419,
    build_store_projection_d419,
    merge_projection_into_d419_rows,
)
from app.services.workpaper_sync.phase5_d4_ipo_checklist_sheets import (  # noqa: E402
    CHECKLIST_SHEET_CODES,
    SHEET_KEY_BY_CODE,
    STORE_ITEM_ID_BY_CODE,
    assert_all_checklist_mapping_digests,
    build_store_projection as build_ipo_checklist_store_projection,
    instrumentation_spec as instrumentation_spec_ipo_checklist,
    merge_projection_into_rows as merge_ipo_checklist_projection_into_rows,
    sheet_payload as ipo_checklist_sheet_payload,
)
from app.services.workpaper_sync.phase5_d4_inspection_sheets import (  # noqa: E402
    INSPECTION_SHEET_CODES,
    SHEET_KEY_BY_CODE as INSPECTION_SHEET_KEY_BY_CODE,
    STORE_ITEM_ID_BY_CODE as INSPECTION_STORE_ITEM_ID_BY_CODE,
    assert_all_inspection_mapping_digests,
    build_store_projection as build_inspection_store_projection,
    instrumentation_spec as instrumentation_spec_inspection,
    merge_projection_into_rows as merge_inspection_projection_into_rows,
    sheet_payload as inspection_sheet_payload,
)
from app.services.workpaper_sync.json_path import (
    JsonPathMissingSegmentError,
    resolve_json_path,
    set_json_path,
)
from app.services.workpaper_sync.models import (
    AuthorityModel,
    BundleSlot,
    DefinitionKind,
    SyncDomainError,
)


class EntrySelectionError(SyncDomainError):
    """冻结的 canary entry 不再满足选型必要条件（manifest / 模板 / mapping digest 漂移）。"""

    error_code = "sync_phase5_d4_selection_invalid"


class StorePayloadError(SyncDomainError):
    """HTML store 大 JSON 载荷形态不合法（非数组、缺 row identity、重复 identity）。"""

    error_code = "sync_phase5_d4_store_payload_invalid"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量（从真实 manifest / Wave 1 证据）
# ═══════════════════════════════════════════════════════════════════════════

PHASE5_WAVE: Final[str] = "phase5_revenue_detail"
ENTRY_ID: Final[str] = "xlsx/gt-d4-operating-revenue"
ADAPTER_ID: Final[str] = "d4.revenue_detail"
#: 🔴 manifest 冻结的 wp_code_pattern（宿主 GtD4OperatingRevenue CamelCase 抽出的幻影码）。
#: assert_entry_selectable / build_matcher 用它；provisioner 用 adjudication 的 ['D4']（Task 6）。
WP_CODES: Final[frozenset[str]] = frozenset({"D4O"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "D/D4 收入底稿.xlsx"
#: Task 4 净化后权威模板哨兵（sanitize --apply 后实测）。
TEMPLATE_SHA256: Final[str] = (
    "b8fb92d4c22cd5d639e415403a12cb61650639153f136a5330c930b880167b5f"
)
#: D4-30/31/32 IPO 访谈/资金流水受管 sheet 接入（批次A-5，d4-ipo-fraud Task 8，2026-09-20）。
#: 旧「几何未就绪」注释已作废（探针实证）：contract parse 通过 19 sheets、instrumentation_specs=19
#: 与行 table 数对齐、_align_specs_to_sibling_tables 成功（sibling 内核已由 D4-1 dual-region
#: GENERALIZE，单 sheet 单 table 是其子集）。已跑发布链 + rematerialize gen52 无 drift。
_INCLUDE_IPO_INTERVIEW_SHEETS: Final[bool] = True
#: D4-6 重要指标分析表接入（批次B 从零第一张，2026-09-20）。固定 12 行静态指标、
#: 行身份=key、受管列 B/C/E/F/H、formula_mask D/G（差异率内部公式）、注入 UUID 列 I。
#: provider=phase5_d4_indicator_sheet，单 sheet 单 table（interview 范式子集）。
_INCLUDE_D46_INDICATOR_SHEET: Final[bool] = True
#: D4-17 营业收入截止测试（账到单据）接入（批次B 第二张，2026-09-20）。单 sheet 单动态行
#: table，行身份=id、受管列 A-J、formula_mask K（是否跨期派生）、注入 UUID 列 L。
#: provider=phase5_d4_cutoff_forward_sheet。provider + 契约 + 投影/合并 + 前端接桥 + 守卫
#: (test_d4_17_cutoff_contract 6 passed / d4CutoffForwardSyncHostWiring 7 passed) 已完成并单测验证。
#: 2026-09-20：曾因共享 entry 的 D4-9 provider 对真实 list 形态 D4-9-data 抛 StorePayloadError
#: 卡死全 entry rematerialize 而暂关；D4-9 `_parse_store_payload` 已加 legacy list 容差（视为
#: 空载荷、不打挂全 entry）解除阻塞，故重开为 True 并跑发布链。
_INCLUDE_D417_CUTOFF_SHEET: Final[bool] = True
#: D4-18 营业收入截止测试（单据到账）接入（批次B 第三张，2026-09-20）。与 D4-17 同构，列序反转
#: （发货单 A-E / 记账凭证 F-J）。provider=phase5_d4_cutoff_backward_sheet。
_INCLUDE_D418_CUTOFF_SHEET: Final[bool] = True
#: D4-19 销售折扣与折让检查接入（批次B 第四张，2026-09-20）。单 sheet 单动态行，行身份=id、
#: 受管列 A-D+F-N、formula_mask E（折扣比例派生）、注入 UUID 列 P。provider=phase5_d4_discount_sheet。
_INCLUDE_D419_DISCOUNT_SHEET: Final[bool] = True
#: 🔴 D4-1 同 sheet 双区 instrumentation 接线开关（Task 5）。
#: 契约 sheet（sheet_payload_d41）+ store projection + merge 恒接（判据先行 Task 2 判据）；
#: 但 instrumentation_specs 两 spec（主营/其他）暂**不接**，唯一阻塞 = 运行态 sibling binding
#: 对齐仍是「1 spec ↔ 1 sheet」的位置 zip（`_attach_sibling_bindings` /
#: `_sibling_identity_bindings`：`len(sheets) != len(specs)` 且 `zip(specs, sheets)`），
#: 无法把 D4-1 的 2 个 spec 归到同一张 sheet。同 sheet 双区 **XML 注入内核**
#: (`_attach_table_part` 合并 `<tableParts>`) 已由 D4-9 Task 1 落地（gate GREEN），但
#: **binding 对齐**这一段属另一段共享内核工作（主控 §5.3 共享锁，D4-9 owner）。为遵守
#: 「不改动影响 D4-2/3/5/15/16/25~28 任何字节」，本开关默认 False：两 spec 不进
#: instrumentation_specs（否则 specs 数比 row_oriented_sheets 多 1，publish 侧
#: `_sibling_identity_bindings` 抛 ProviderCapabilityError 打挂整个 gt-d4-operating-revenue
#: entry）。唯一解除条件：dual-region binding 对齐（按 managed_sheet 归组 spec）落地 + 守卫。
_INCLUDE_D41_ADJUDICATION_INSTRUMENTATION: Final[bool] = True
#: D4-29 uses an independently compiled, workbook-scope transposed anchor.
_INCLUDE_D429_TRANSPOSED: Final[bool] = True
MANAGED_SHEET: Final[str] = "主营业务收入明细表D4-2"
TEMPLATE_ID: Final[str] = "D42"
SHEET_KEY: Final[str] = f"{TEMPLATE_ID.lower()}-managed"
ROWS_TABLE_KEY: Final[str] = "revenue_detail_rows"

#: 单级表头（openpyxl / T01）。
HEADER_ROW: Final[int] = 11
FIRST_DATA_ROW: Final[int] = 12
LAST_DATA_ROW: Final[int] = 23
FOOTER_ROW: Final[int] = 24

#: 最后一列受管业务列（V 备注）与隐藏 row UUID 列。
MANAGED_LAST_COL: Final[str] = "V"
UUID_COL: Final[str] = "W"

TABLE_NAME: Final[str] = f"GT_{TEMPLATE_ID}_ROWS"
AUTHORITY_MODEL: Final[AuthorityModel] = AuthorityModel.projection_contract
#: 🔴 footer A24「合计」纯两字无空格（codepoints 0x5408 0x8ba1，T01 实测）。
FOOTER_MARKER: Final[str] = "合计"

STORE_ITEM_ID: Final[str] = "D4-2-rows"
STORE_ITEM_IDS: Final[tuple[str, ...]] = (
    STORE_ITEM_ID,
    STORE_ITEM_ID_D43,
    STORE_ITEM_ID_D45_GROUPS,
    STORE_ITEM_ID_D421,
    STORE_ITEM_ID_D422,
    STORE_ITEM_ID_D423,
    STORE_ITEM_ID_D424,
    STORE_ITEM_ID_D41,
    STORE_ITEM_ID_D49,
    *((STORE_ITEM_ID_D429,) if _INCLUDE_D429_TRANSPOSED else ()),
    *STORE_ITEM_ID_BY_CODE.values(),
)
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
ROW_IDENTITY_STORE_KEY: Final[str] = "rowId"

#: Task 1 冻结的 mapping_digest（evidence/T01-column-field-mapping.json）。
EXPECTED_MAPPING_DIGEST: Final[str] = (
    "6d2f340d45ba0a24c95424c1e698be3df105252c160d174a2e4c748ec1554cc8"
)

MONTH_COLUMNS: Final[tuple[str, ...]] = (
    "B",
    "C",
    "D",
    "E",
    "F",
    "G",
    "H",
    "I",
    "J",
    "K",
    "L",
    "M",
)


def _month_field_specs() -> tuple[tuple[str, str, str, str, str, str], ...]:
    """B..M → month_01..month_12，json_path 用数组下标 months/0..months/11。"""
    return tuple(
        (
            f"month_{i + 1:02d}",
            col,
            "editable",
            "amount",
            f"months/{i}",
            f"{i + 1}月",
        )
        for i, col in enumerate(MONTH_COLUMNS)
    )


#: 18 个受管字段：`(column_key, 列标, mode, value_type, store json 路径, 表头文本)`。
#: 🔴 顺序即 Excel 列序。P/S/T/U 不入契约（仅 formula_mask）。
MANAGED_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    ("product", "A", "editable", "text", "product", "项目"),
    *_month_field_specs(),
    ("period_total", "N", "formula", "amount", "periodTotal", "本期未审数合计"),
    ("audit_adjustment", "O", "editable", "amount", "auditAdjustment", "本期审计调整"),
    ("prior_unadjusted", "Q", "editable", "amount", "priorUnadjusted", "上期未审数"),
    ("prior_adjustment", "R", "editable", "amount", "priorAdjustment", "上期审计调整"),
    ("remark", "V", "editable", "text", "remark", "备注"),
)

#: N（契约 formula）+ P/S/T/U（模板内部公式，不进契约）—— 投影不得覆盖。
FORMULA_MASK: Final[tuple[str, ...]] = (
    f"N{FIRST_DATA_ROW}:N{LAST_DATA_ROW}",
    f"P{FIRST_DATA_ROW}:P{LAST_DATA_ROW}",
    f"S{FIRST_DATA_ROW}:S{LAST_DATA_ROW}",
    f"T{FIRST_DATA_ROW}:T{LAST_DATA_ROW}",
    f"U{FIRST_DATA_ROW}:U{LAST_DATA_ROW}",
)


def mapping_digest_payload() -> dict[str, Any]:
    """与 T01 digest_payload 同形 —— 用于 Task 5 校验 mapping_digest 未漂移。"""
    return {
        "contract_fields": [
            {
                "col": col,
                "column_key": column_key,
                "header": header_text,
                "json_path": json_path,
                "mode": mode,
            }
            for column_key, col, mode, _vt, json_path, header_text in MANAGED_FIELD_SPECS
        ],
        "first_data_row": FIRST_DATA_ROW,
        "footer_marker_exact": FOOTER_MARKER,
        "footer_row": FOOTER_ROW,
        "header_row": HEADER_ROW,
        "last_data_row": LAST_DATA_ROW,
        "managed_sheet": MANAGED_SHEET,
        "template_relative_path": TEMPLATE_RELATIVE_PATH,
    }


def compute_mapping_digest() -> str:
    canon = json.dumps(
        mapping_digest_payload(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def assert_mapping_digest() -> str:
    got = compute_mapping_digest()
    if got != EXPECTED_MAPPING_DIGEST:
        raise EntrySelectionError(
            f"D4 mapping_digest 漂移：现算={got} 冻结={EXPECTED_MAPPING_DIGEST} —— "
            "与 evidence/T01-column-field-mapping.json 不一致，Task 5/6/7 阻塞"
        )
    if len(MANAGED_FIELD_SPECS) != 18:
        raise EntrySelectionError(
            f"D4 契约字段数必须为 18，实得 {len(MANAGED_FIELD_SPECS)}"
        )
    try:
        assert_mapping_digest_d43()
        assert_all_sibling_mapping_digests()  # D4-21/22/23/24
    except ValueError as exc:
        raise EntrySelectionError(str(exc)) from exc
    return got


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
    assert_mapping_digest()
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
    """D4-2 主受管 sheet（保持单 sheet 调用面）。"""
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
        transposed_sheets=(sheet_payload(),) if _INCLUDE_D429_TRANSPOSED else (),
    )


def instrumentation_specs() -> tuple:
    """D4-2/3/5 + D4-21/22/23/24 受管 sheet（同 entry / 同 template blob）。"""
    return (
        instrumentation_spec(),
        instrumentation_spec_d43(
            entry_id=ENTRY_ID, template_relative_path=TEMPLATE_RELATIVE_PATH
        ),
        instrumentation_spec_d45(
            entry_id=ENTRY_ID, template_relative_path=TEMPLATE_RELATIVE_PATH
        ),
        instrumentation_spec_d421(
            entry_id=ENTRY_ID, template_relative_path=TEMPLATE_RELATIVE_PATH
        ),
        instrumentation_spec_d422(
            entry_id=ENTRY_ID, template_relative_path=TEMPLATE_RELATIVE_PATH
        ),
        instrumentation_spec_d423(
            entry_id=ENTRY_ID, template_relative_path=TEMPLATE_RELATIVE_PATH
        ),
        instrumentation_spec_d424(
            entry_id=ENTRY_ID, template_relative_path=TEMPLATE_RELATIVE_PATH
        ),
        # D4-35 由并发会话加入契约 sheets（8 张）但漏了这条 spec，导致
        # instrumentation_specs(7) 与契约 sheets(8) 不对齐、多 sheet binding 无法对齐、
        # 全 D4 entry attach fail-closed。补齐这条使二者一致（spec 函数已 import）。
        instrumentation_spec_d435(
            entry_id=ENTRY_ID, template_relative_path=TEMPLATE_RELATIVE_PATH
        ),
        # D4-25/26/27/28 IPO 检查表追加受管 sheet（同 entry / 同 template blob）。
        *(
            instrumentation_spec_ipo_checklist(
                code, entry_id=ENTRY_ID, template_relative_path=TEMPLATE_RELATIVE_PATH
            )
            for code in CHECKLIST_SHEET_CODES
        ),
        # D4-15/16 检查表追加受管 sheet（同 entry / 同 template blob；B1 spec d4-inspection）。
        *(
            instrumentation_spec_inspection(
                code, entry_id=ENTRY_ID, template_relative_path=TEMPLATE_RELATIVE_PATH
            )
            for code in INSPECTION_SHEET_CODES
        ),
        # D4-30/31/32：D4-31 singleton 多字段挤同一物理行，materialize roundtrip 红；
        # 暂不进 instrumentation，待几何重裁后再开（否则挡 D4-5 rematerialize）。
        *(
            instrumentation_spec_interview(
                code, entry_id=ENTRY_ID, template_relative_path=TEMPLATE_RELATIVE_PATH
            )
            for code in INTERVIEW_SHEET_CODES()
            if _INCLUDE_IPO_INTERVIEW_SHEETS
        ),
        *(
            (
                instrumentation_spec_d46(
                    entry_id=ENTRY_ID, template_relative_path=TEMPLATE_RELATIVE_PATH
                ),
            )
            if _INCLUDE_D46_INDICATOR_SHEET
            else ()
        ),
        *(
            (
                instrumentation_spec_d417(
                    entry_id=ENTRY_ID, template_relative_path=TEMPLATE_RELATIVE_PATH
                ),
            )
            if _INCLUDE_D417_CUTOFF_SHEET
            else ()
        ),
        *(
            (
                instrumentation_spec_d418(
                    entry_id=ENTRY_ID, template_relative_path=TEMPLATE_RELATIVE_PATH
                ),
            )
            if _INCLUDE_D418_CUTOFF_SHEET
            else ()
        ),
        *(
            (
                instrumentation_spec_d419(
                    entry_id=ENTRY_ID, template_relative_path=TEMPLATE_RELATIVE_PATH
                ),
            )
            if _INCLUDE_D419_DISCOUNT_SHEET
            else ()
        ),
        # D4-1 营业收入审定表：同 sheet 双区（主营 R8 起 / 其他 R14 起）两 spec，同
        # managed_sheet 不同行段/UUID 列（W/X）。默认不接（见
        # _INCLUDE_D41_ADJUDICATION_INSTRUMENTATION 注释：runtime sibling binding 对齐仍
        # 是 1spec↔1sheet 位置 zip，2 spec 会打挂整个 entry 的 publish）。
        *(
            instrumentation_spec_d41(
                entry_id=ENTRY_ID, template_relative_path=TEMPLATE_RELATIVE_PATH
            )
            if _INCLUDE_D41_ADJUDICATION_INSTRUMENTATION
            else ()
        ),
        # D4-9 重要客户结构分析：同 sheet 双区（本期 R13-22 / 上期 R27-36）两 spec，同
        # managed_sheet 不同行段/UUID 列（W/X）。同 sheet 双区注入内核已由 Task 1 落地，
        # binding 对齐走共享 _align_specs_to_sibling_tables（与 D4-1 同路径）。
        *instrumentation_spec_d49(
            entry_id=ENTRY_ID, template_relative_path=TEMPLATE_RELATIVE_PATH
        ),
    )


def template_definition_payload() -> dict[str, Any]:
    data = read_authoritative_template()
    return build_template_payload(
        spec=instrumentation_spec(),
        template_sha256=TEMPLATE_SHA256,
        structure_hash=normalized_structure_hash(data),
    )


def instrumentation_definition_payload() -> dict[str, Any]:
    """多 sheet instrumentation（D4-2 + D4-3 + D4-5）。"""
    payload = build_instrumentation_payload_for_sheets(
        specs=instrumentation_specs(),
        template_definition_sha256=canonical_digest(template_definition_payload()),
        template_sha256=TEMPLATE_SHA256,
        gate=excel_carrier_gate(),
    )
    payload["transposed_sheets"] = (
        [sheet_payload()] if _INCLUDE_D429_TRANSPOSED else []
    )
    return payload


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
    return f"{ROWS_TABLE_KEY}/{row_identity}/{column_key}"


def _rows_table_payload() -> dict[str, Any]:
    fields: list[dict[str, Any]] = []
    for column_key, column, mode, value_type, json_path, header_text in MANAGED_FIELD_SPECS:
        fields.append(
            {
                "stable_field_key": stable_key_for(column_key),
                "json_pointer": f"/rows/{{row_uuid}}/{json_path}",
                "column_key": column_key,
                "cell": {"column": column, "row_from": "row_identity"},
                "mode": mode,
                "value_type": value_type,
                "source_ref": _src(f"{column}{FIRST_DATA_ROW}"),
                "header_source_ref": _src(f"{column}{HEADER_ROW}"),
                "store_item_id": STORE_ITEM_ID,
                "header_text": header_text,
            }
        )
    return {
        "table_key": ROWS_TABLE_KEY,
        "anchor": f"A{HEADER_ROW}",
        "header_rows": 1,
        "row_identity": {"kind": "field", "json_pointer": f"/rows/*/{ROW_IDENTITY_STORE_KEY}"},
        "delete_policy": "tombstone",
        "footer_anchor": {
            "marker": FOOTER_MARKER,
            "search_column": "A",
            "carries_total_formula": True,
            "note": (
                "footer 行 A24「合计」（纯两字无空格，T01）。声明为真使结构性插行有权按声明"
                "位移量扩张合计公式区间；N 列 =SUM(B:M) 为内部公式须保留。"
            ),
        },
        "formula_mask": list(FORMULA_MASK),
        "fields": fields,
    }


_HTML_STORE_NOTE: Final[str] = (
    "整张主营业务收入明细表存成这一条 item 的 remark（JSON 数组字符串，useD4RevenueDetail 的 "
    "JSON.stringify(rows)）。本契约按 stable field + row rowId 拆开；B~M 十二列走 months 数组"
    "下标（months/0..months/11），禁止把整 JSON 或整 months 当一个字段比较。periodTotal 由"
    "模板内部公式计算（store 可不持久化），projection 不得覆盖 N/P/S/T/U。"
)

_REVIEWED_BASIS: Final[str] = (
    "openpyxl 直读净化后权威模板 D/D4 收入底稿.xlsx（Task 4 sha256 "
    "b8fb92d4c22cd5d639e415403a12cb61650639153f136a5330c930b880167b5f），三受管 sheet："
    "（1）主营业务收入明细表D4-2：单级表头行 11，数据区 12-23，A24「合计」footer；18 契约字段 "
    "（A product + B-M months/0..11 + N formula periodTotal + O auditAdjustment + Q/R prior "
    "+ V remark）；P/S/T/U 仅 formula_mask。mapping_digest="
    f"{EXPECTED_MAPPING_DIGEST}（T01 D4-2）。"
    "（2）其他业务收入明细表D4-3：两级表头 11+12，受管区 13-18（A19「……」BP-21 排除），"
    f"A20「合计」；6 契约字段 item/current*/prior*/remark；D/E/F/I/J/K/L/M mask。"
    f"mapping_digest={EXPECTED_MAPPING_DIGEST_D43}（T01 D4-3）。"
    "（3）营业收入会计政策检查D4-5：分组紧凑表 d45_policy_groups（A–D+Z，footer=信用政策）"
    f"+ fixed B11-B16/信用/说明/结论；mapping_digest={EXPECTED_MAPPING_DIGEST_D45}（T09）。"
    "宿主：D4-2/3 走统一 WorkpaperSyncEditorHost；D4-5 由 D4TabPolicyCheck 自管路径。"
    "wp_code 模块侧 D4O（manifest 幻影码）；裁决落点 D4。"
)

_HTML_STORE_NOTE_D43: Final[str] = (
    "其他业务收入明细存成 checklist_responses item D4-3-rows（JSON 数组，"
    "useD4OtherRevenue StoredOtherRow）。与 D4-2-rows 分 item；按 sheet_key=d43-managed "
    "extract/merge。D/I 重分类不进 store。"
)

_HTML_STORE_NOTE_D45: Final[str] = (
    "D4-5 政策检查：分组 JSON 存 D4-5-policy-groups（PolicyGroup.id=row identity）；"
    "经营模式/信用/说明/结论为独立 item（D4-5-biz-* / credit / note / conclusion）。"
    "sheet_key=d45-managed；宿主独立于 isD4DetailSheet。"
    "Excel 契约仅 groups + 经营模式 B11–B16；信用/说明/结论为 HTML-only"
    "（footer 下 static_row 与插行 fail-closed 冲突，见 phase5_d4_policy_check_sheet）。"
)


def build_contract_payload() -> dict[str, Any]:
    from app.services.workpaper_sync.excel_extract import TABLE_SHEET_ANCHOR

    assert_mapping_digest()
    assert_mapping_digest_d43()
    assert_mapping_digest_d45()
    assert_mapping_digest_d435()
    assert_mapping_digest_d41()
    assert_mapping_digest_d49()
    assert_all_checklist_mapping_digests()
    assert_all_inspection_mapping_digests()
    if _INCLUDE_D429_TRANSPOSED:
        assert_mapping_digest_d429()
    template_payload = template_definition_payload()
    return {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "contract_id": ADAPTER_ID,
        "semantic_version": "1.2.0",
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
            },
            {
                "sheet_key": SHEET_KEY_D43,
                "excel_name": MANAGED_SHEET_D43,
                "locator": {"anchor": TABLE_SHEET_ANCHOR},
                "tables": [rows_table_payload_d43()],
            },
            sheet_payload_d45(),
            {
                "sheet_key": SHEET_KEY_D421,
                "excel_name": MANAGED_SHEET_D421,
                "locator": {"anchor": TABLE_SHEET_ANCHOR},
                "tables": [rows_table_payload_d421()],
            },
            {
                "sheet_key": SHEET_KEY_D422,
                "excel_name": MANAGED_SHEET_D422,
                "locator": {"anchor": TABLE_SHEET_ANCHOR},
                "tables": [rows_table_payload_d422()],
            },
            {
                "sheet_key": SHEET_KEY_D423,
                "excel_name": MANAGED_SHEET_D423,
                "locator": {"anchor": TABLE_SHEET_ANCHOR},
                "tables": [rows_table_payload_d423()],
            },
            {
                "sheet_key": SHEET_KEY_D424,
                "excel_name": MANAGED_SHEET_D424,
                "locator": {"anchor": TABLE_SHEET_ANCHOR},
                "tables": [rows_table_payload_d424()],
            },
            {
                "sheet_key": SHEET_KEY_D435,
                "excel_name": MANAGED_SHEET_D435,
                "locator": {"anchor": TABLE_SHEET_ANCHOR},
                "tables": [rows_table_payload_d435()],
            },
            # D4-1 营业收入审定表：同 sheet 双区（2 张 row table，main/other），
            # provider 返回完整 sheet dict（含 sheet 级 formula_mask + tb_check）。
            sheet_payload_d41(),
            # D4-9 重要客户结构分析：同 sheet 三 table（本期/上期动态行 + totals 静态标量）。
            sheet_payload_d49(),
            *(
                (
                    {
                        "sheet_key": SHEET_KEY_D429,
                        "excel_name": MANAGED_SHEET_D429,
                        "locator": sheet_payload()["locator"],
                        "tables": sheet_payload()["tables"],
                    },
                )
                if _INCLUDE_D429_TRANSPOSED
                else ()
            ),
            *(ipo_checklist_sheet_payload(code) for code in CHECKLIST_SHEET_CODES),
            *(inspection_sheet_payload(code) for code in INSPECTION_SHEET_CODES),
            *(
                interview_sheet_payload(code)
                for code in INTERVIEW_SHEET_CODES()
                if _INCLUDE_IPO_INTERVIEW_SHEETS
            ),
            *([sheet_payload_d46()] if _INCLUDE_D46_INDICATOR_SHEET else []),
            *([sheet_payload_d417()] if _INCLUDE_D417_CUTOFF_SHEET else []),
            *([sheet_payload_d418()] if _INCLUDE_D418_CUTOFF_SHEET else []),
            *([sheet_payload_d419()] if _INCLUDE_D419_DISCOUNT_SHEET else []),
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
                "sibling_stores": [
                    {
                        "item_id": STORE_ITEM_ID_D43,
                        "sheet_key": SHEET_KEY_D43,
                        "table_key": rows_table_payload_d43()["table_key"],
                        "row_identity_key": "rowId",
                        "note": _HTML_STORE_NOTE_D43,
                    },
                    {
                        "item_id": STORE_ITEM_ID_D45_GROUPS,
                        "sheet_key": SHEET_KEY_D45,
                        "table_key": "d45_policy_groups",
                        "row_identity_key": "id",
                        "note": _HTML_STORE_NOTE_D45,
                        "fixed_item_ids": list(STORE_ITEM_IDS_D45_FIXED),
                    },
                    {
                        "item_id": STORE_ITEM_ID_D421,
                        "sheet_key": SHEET_KEY_D421,
                        "table_key": ROWS_TABLE_KEY_D421,
                        "row_identity_key": ROW_IDENTITY_STORE_KEY_D421,
                        "note": (
                            "D4-21 关联方销售/价格分析：动态行 store（12 受管列）；I/K 差异率入 mask；"
                            "O16-24 关联关系图例逐字保留、UUID 用 P。"
                        ),
                    },
                    {
                        "item_id": STORE_ITEM_ID_D422,
                        "sheet_key": SHEET_KEY_D422,
                        "table_key": ROWS_TABLE_KEY_D422,
                        "row_identity_key": ROW_IDENTITY_STORE_KEY_D422,
                        "note": (
                            "D4-22 重要指标分析：固定 12 指标行 + 同业公司 {slot}_{seq} 动态列；"
                            "固定列 A/B/C/H。"
                        ),
                    },
                    {
                        "item_id": STORE_ITEM_ID_D423,
                        "sheet_key": SHEET_KEY_D423,
                        "table_key": ROWS_TABLE_KEY_D423,
                        "row_identity_key": ROW_IDENTITY_STORE_KEY_D423,
                        "note": (
                            "D4-23 收入与开票比较：固定 12 月行（月份天然键）；D/I/J 内部算术入 mask + "
                            "footer24 SUM。"
                        ),
                    },
                    {
                        "item_id": STORE_ITEM_ID_D424,
                        "sheet_key": SHEET_KEY_D424,
                        "table_key": ROWS_TABLE_KEY_D424,
                        "row_identity_key": ROW_IDENTITY_STORE_KEY_D424,
                        "note": (
                            "D4-24 第三方回款：动态行 store（13 列，枚举列 J/K）；"
                            "A24 导航引用 <E1-31>/<D2-7> 走 cross_wp_references。"
                        ),
                    },
                    {
                        "item_id": STORE_ITEM_ID_D435,
                        "sheet_key": SHEET_KEY_D435,
                        "table_key": ROWS_TABLE_KEY_D435,
                        "row_identity_key": ROW_IDENTITY_STORE_KEY_D435,
                        "note": (
                            "D4-35 其他业务收入检查表：受管 rows 均质行（16 列 A-Q，check1..6 = H-M）；"
                            "store 嵌套 {rows,sampling,periodAmount}，sampling(抽样参数区 8-10 行)/periodAmount "
                            "为 HTML-only 非行数据，不进 Excel Table 受管区（15..25），mirror 回读须包回并保留。"
                        ),
                    },
                    # D4-1 营业收入审定表：同 sheet 双区共享单个 store item D4-1-rows，
                    # 按 sectionKey(main-revenue/other-revenue) 分流到两张 row table。
                    {
                        "item_id": STORE_ITEM_ID_D41,
                        "sheet_key": SHEET_KEY_D41,
                        "table_key": ROWS_TABLE_KEY_D41_MAIN,
                        "row_identity_key": ROW_IDENTITY_STORE_KEY_D41,
                        "note": (
                            "D4-1 主营段动态行（section main-revenue，R8 起，UUID 列 W）；单个 store "
                            "D4-1-rows 按 sectionKey 分流两区，label + 6 金额受管；E/I 审定数 + "
                            "小计/合计/差异(12/18/19/21) 入 formula_mask 不回写。"
                        ),
                    },
                    {
                        "item_id": STORE_ITEM_ID_D41,
                        "sheet_key": SHEET_KEY_D41,
                        "table_key": ROWS_TABLE_KEY_D41_OTHER,
                        "row_identity_key": ROW_IDENTITY_STORE_KEY_D41,
                        "note": (
                            "D4-1 其他段动态行（section other-revenue，R14 起，UUID 列 X≠主营）；"
                            "同 store D4-1-rows，两区 rowId 各自唯一不串区（同 D4-9 W/X 思路）。"
                        ),
                    },
                    # D4-9 重要客户结构分析：单个 store D4-9-data（{current,prior}+totals 嵌套），
                    # 同 sheet 三 table（本期/上期动态行 UUID 列 W/X + totals 静态标量）。
                    {
                        "item_id": STORE_ITEM_ID_D49,
                        "sheet_key": SHEET_KEY_D49,
                        "table_key": ROWS_TABLE_KEY_D49_CURRENT,
                        "row_identity_key": ROW_IDENTITY_STORE_KEY_D49,
                        "note": (
                            "D4-9 本期段动态行（customer_current_rows，R13-22，UUID 列 W）；单个 store "
                            "D4-9-data 嵌套 {current,prior} 按 table_key 分流三区，B name/C amount/"
                            "D amountRatio(公式)/E quantity/F quantityRatio(公式)/G priorRank；D/F 占比 "
                            "+ 合计入 formula_mask 不回写；4 总额 C24/E24/C38/E38 为 totals 静态标量。"
                        ),
                    },
                    {
                        "item_id": STORE_ITEM_ID_D49,
                        "sheet_key": SHEET_KEY_D49,
                        "table_key": ROWS_TABLE_KEY_D49_PRIOR,
                        "row_identity_key": ROW_IDENTITY_STORE_KEY_D49,
                        "note": (
                            "D4-9 上期段动态行（customer_prior_rows，R27-36，UUID 列 X≠本期）；"
                            "同 store D4-9-data，两区 rowId 各自唯一不串区。"
                        ),
                    },
                    *(
                        (
                            {
                                "item_id": STORE_ITEM_ID_D429,
                                "sheet_key": SHEET_KEY_D429,
                                "table_key": sheet_payload()["tables"][0]["table_key"],
                                "row_identity_key": "id",
                                "note": "客户按 id 同步，Excel 转置客户列由专用 dispatcher 读写。",
                            },
                        )
                        if _INCLUDE_D429_TRANSPOSED
                        else ()
                    ),
                    *(
                        {
                            "item_id": STORE_ITEM_ID_BY_CODE[code],
                            "sheet_key": SHEET_KEY_BY_CODE[code],
                            "table_key": ipo_checklist_sheet_payload(code)["tables"][0]["table_key"],
                            "row_identity_key": "rowId",
                            "note": f"{code} IPO 检查表动态行 store；json_path 与前端 ipoChecklistSchema 列 key 逐列对齐。",
                        }
                        for code in CHECKLIST_SHEET_CODES
                    ),
                    *(
                        {
                            "item_id": INSPECTION_STORE_ITEM_ID_BY_CODE[code],
                            "sheet_key": INSPECTION_SHEET_KEY_BY_CODE[code],
                            "table_key": inspection_sheet_payload(code)["tables"][0]["table_key"],
                            "row_identity_key": "id",
                            "note": f"{code} 检查表动态行 store；D4-15 三维嵌套 json_path(delivery/invoice/voucher)、D4-16 差异派生入 mask。",
                        }
                        for code in INSPECTION_SHEET_CODES
                    ),
                ],
            },
            "reviewed_basis": _REVIEWED_BASIS,
            "mapping_digest": EXPECTED_MAPPING_DIGEST,
            "mapping_digest_d43": EXPECTED_MAPPING_DIGEST_D43,
            "mapping_digest_d45": EXPECTED_MAPPING_DIGEST_D45,
            "mapping_digest_d435": EXPECTED_MAPPING_DIGEST_D435,
            "mapping_digest_d41": EXPECTED_MAPPING_DIGEST_D41,
            "mapping_digest_d49": EXPECTED_MAPPING_DIGEST_D49,
            "mapping_digest_ipo_checklist": assert_all_checklist_mapping_digests(),
            "mapping_digest_inspection": assert_all_inspection_mapping_digests(),
            **(
                {"mapping_digest_d429": assert_mapping_digest_d429()}
                if _INCLUDE_D429_TRANSPOSED
                else {}
            ),
            "instrumentation_template_ids": [
                TEMPLATE_ID,
                TEMPLATE_ID_D43,
                TEMPLATE_ID_D45,
                TEMPLATE_ID_D421,
                TEMPLATE_ID_D422,
                TEMPLATE_ID_D423,
                TEMPLATE_ID_D424,
                TEMPLATE_ID_D435,
                TEMPLATE_ID_D49_CURRENT,
                TEMPLATE_ID_D49_PRIOR,
                *(
                    (sheet_payload()["template_id"],)
                    if _INCLUDE_D429_TRANSPOSED
                    else ()
                ),
                *[ipo_checklist_sheet_payload(c)["template_id"] for c in CHECKLIST_SHEET_CODES],
                *[inspection_sheet_payload(c)["template_id"] for c in INSPECTION_SHEET_CODES],
            ],
            "instrumentation_tables": [
                TABLE_NAME,
                TABLE_NAME_D43,
                TABLE_NAME_D45,
                TABLE_NAME_D421,
                TABLE_NAME_D422,
                TABLE_NAME_D423,
                TABLE_NAME_D424,
                TABLE_NAME_D435,
                TABLE_NAME_D49_CURRENT,
                TABLE_NAME_D49_PRIOR,
                *(
                    (sheet_payload()["tables"][0]["table_key"],)
                    if _INCLUDE_D429_TRANSPOSED
                    else ()
                ),
                *[ipo_checklist_sheet_payload(c)["tables"][0]["table_key"] for c in CHECKLIST_SHEET_CODES],
                *[inspection_sheet_payload(c)["tables"][0]["table_key"] for c in INSPECTION_SHEET_CODES],
            ],
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
            "backend/scripts/gen/generate_phase5_d4_contract.py --apply` 重生成"
        )
    parse_contract(expected, adapter_id=ADAPTER_ID)
    return on_disk


# ═══════════════════════════════════════════════════════════════════════════
# 6. HTML store 载荷拆分（stable field + row UUID；months 走共享 json_path）
# ═══════════════════════════════════════════════════════════════════════════


def store_row_identity(row: Mapping[str, Any], *, ordinal: int) -> str:
    raw = row.get(ROW_IDENTITY_STORE_KEY)
    if not isinstance(raw, str) or not raw.strip():
        raise StorePayloadError(
            f"{STORE_ITEM_ID} 第 {ordinal} 行缺少稳定行身份 {ROW_IDENTITY_STORE_KEY!r}"
            f"（实得 {raw!r}）—— 不得退回数组下标作身份（Requirement 6.5 / Property 23）"
        )
    return raw.strip()


def iter_store_rows(
    payload: str | bytes | Sequence[Any],
) -> Iterator[tuple[str, Mapping[str, Any]]]:
    if isinstance(payload, (str, bytes, bytearray)):
        text = payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else payload
        try:
            rows: Any = json.loads(text)
        except ValueError as exc:
            raise StorePayloadError(f"{STORE_ITEM_ID} 的 remark 不是合法 JSON: {exc}") from exc
    else:
        rows = payload
    if not isinstance(rows, list):
        raise StorePayloadError(
            f"{STORE_ITEM_ID} 的载荷必须是行对象数组，实得 {type(rows).__name__} —— 必须 fail closed"
        )
    seen: set[str] = set()
    for ordinal, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise StorePayloadError(
                f"{STORE_ITEM_ID} 第 {ordinal} 项不是对象，实得 {type(row).__name__}"
            )
        identity = store_row_identity(row, ordinal=ordinal)
        if identity in seen:
            raise StorePayloadError(
                f"{STORE_ITEM_ID} 出现重复行身份 {identity!r}（第 {ordinal} 项）—— 不得静默合并"
            )
        seen.add(identity)
        yield identity, row


def _resolve_store_path(row: Mapping[str, Any], json_path: str) -> Any:
    """共享 resolve_json_path；标量缺失段 → None（periodTotal 等可不持久化）。

    months/* 缺失不得软化：数组路径必须 fail closed（Requirement 1.4）。
    periodTotal 不在 HTML store 持久化时，用 months 求和作为投影基线，避免 OO 公式
    缓存值（N=SUM(B:M)）与 base=0 形成 protected 冲突挡住整次 apply。
    """
    if json_path == "periodTotal":
        months = row.get("months")
        if isinstance(months, list) and len(months) == 12:
            total = 0.0
            saw_numeric = False
            for cell in months:
                if cell is None or cell == "":
                    continue
                try:
                    total += float(cell)
                    saw_numeric = True
                except (TypeError, ValueError):
                    continue
            if saw_numeric or all(c is None or c == "" or c == 0 for c in months):
                return total
    try:
        return resolve_json_path(row, json_path)
    except JsonPathMissingSegmentError:
        if json_path.startswith("months/"):
            raise
        return None


def split_store_row(
    row: Mapping[str, Any], *, row_identity: str, contract: SyncContract
) -> Iterator[tuple[str, Any, FieldSpec]]:
    for column_key, _column, _mode, _vt, json_path, _label in MANAGED_FIELD_SPECS:
        spec = contract.field_by_stable_key(stable_key_for(column_key))
        yield stable_key_for(column_key, row_identity), _resolve_store_path(row, json_path), spec


def _ensure_months_list(row: dict[str, Any]) -> None:
    """HTML store 行必须带长度 12 的 months list（仅 product 写入时也不得落成 null）。"""
    months = row.get("months")
    if isinstance(months, list) and len(months) == 12:
        return
    if isinstance(months, list):
        padded = list(months) + [None] * 12
        row["months"] = padded[:12]
        return
    row["months"] = [None] * 12


def build_store_projection(
    payload: str | bytes | Sequence[Any],
    *,
    contract: SyncContract,
    limits: Any | None = None,
) -> Any:
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection
    from app.services.workpaper_sync.excel_extract import StreamingProjectionBudget
    from app.services.workpaper_sync.limits import load_limits

    lim = limits or load_limits()
    budget = StreamingProjectionBudget(lim)
    values: dict[str, FieldValue] = {}
    row_keys: list[str] = []
    for identity, row in iter_store_rows(payload):
        budget.add_row(ROWS_TABLE_KEY)
        row_keys.append(identity)
        # 历史/仅写 product 的行可能缺 months；投影前归一成长度 12，避免 store-projection 422
        normalized = dict(row)
        _ensure_months_list(normalized)
        for stable_key, value, spec in split_store_row(
            normalized, row_identity=identity, contract=contract
        ):
            budget.add_field()
            values[stable_key] = FieldValue(
                stable_key=stable_key,
                value=value,
                value_type=spec.value_type,
                mode=spec.mode,
                row_key=identity,
            )
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys={ROWS_TABLE_KEY: tuple(row_keys)},
    )


def merge_projection_into_store_rows(
    *,
    projection: Any,
    base_rows: list[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], int, int, set[str]]:
    """把已 extract 的 projection 合进 D4-2-rows（共享 set_json_path，months 保持 list）。

    只消费 ``revenue_detail_rows/*`` 键；D4-3 的 ``other_revenue_detail_rows/*`` 由
    :func:`merge_projection_into_d43_store_rows` / :func:`merge_projection_into_all_d4_stores` 处理。
    """
    field_to_path = {spec[0]: spec[4] for spec in MANAGED_FIELD_SPECS}
    prefix = f"{ROWS_TABLE_KEY}/"
    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in base_rows:
        rid = str(row.get(ROW_IDENTITY_STORE_KEY) or "").strip()
        if not rid:
            continue
        copied = dict(row)
        _ensure_months_list(copied)
        by_id[rid] = copied
        order.append(rid)

    applied = 0
    visited = 0
    touched_rows: set[str] = set()
    for key in projection.stable_keys():
        sk = str(key)
        if not sk.startswith(prefix):
            continue
        fv = projection.get(key)
        if fv is None or getattr(fv, "is_protected", False):
            continue
        rid = getattr(fv, "row_key", None)
        if not rid:
            continue
        target = by_id.get(str(rid))
        if target is None:
            target = {ROW_IDENTITY_STORE_KEY: str(rid), "product": ""}
            _ensure_months_list(target)
            by_id[str(rid)] = target
            order.append(str(rid))
        field_id = sk.rsplit("/", 1)[-1]
        json_path = field_to_path.get(field_id)
        if not json_path:
            continue
        visited += 1
        new_val = getattr(fv, "value", None)
        if set_json_path(target, json_path, new_val):
            applied += 1
            touched_rows.add(str(rid))
            _ensure_months_list(target)

    return [by_id[rid] for rid in order], applied, visited, touched_rows


def build_d43_store_projection(
    payload: str | bytes | Sequence[Any],
    *,
    contract: SyncContract,
    limits: Any | None = None,
) -> Any:
    """把 D4-3-rows JSON 投影成 other_revenue_detail_rows/* FieldValue。"""
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection
    from app.services.workpaper_sync.excel_extract import StreamingProjectionBudget
    from app.services.workpaper_sync.limits import load_limits

    lim = limits or load_limits()
    budget = StreamingProjectionBudget(lim)
    values: dict[str, FieldValue] = {}
    row_keys: list[str] = []
    for identity, row in iter_store_rows(payload):
        budget.add_row(ROWS_TABLE_KEY_D43)
        row_keys.append(identity)
        for stable_key, value, spec in split_store_row_d43(
            row, row_identity=identity, contract=contract
        ):
            budget.add_field()
            values[stable_key] = FieldValue(
                stable_key=stable_key,
                value=value,
                value_type=spec.value_type,
                mode=spec.mode,
                row_key=identity,
            )
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys={ROWS_TABLE_KEY_D43: tuple(row_keys)},
    )


def build_combined_store_projection(
    payloads: Mapping[str, str | bytes | Sequence[Any]],
    *,
    contract: SyncContract,
    limits: Any | None = None,
) -> Any:
    """合并 D4-2 / D4-3 / D4-5(groups+fixed) store 投影（materialize overlay 用）。"""
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection

    d42_payload = payloads.get(STORE_ITEM_ID, EMPTY_STORE_PAYLOAD)
    d43_payload = payloads.get(STORE_ITEM_ID_D43, EMPTY_STORE_PAYLOAD)
    d45_groups = payloads.get(STORE_ITEM_ID_D45_GROUPS, "[]")
    left = build_store_projection(d42_payload, contract=contract, limits=limits)
    right = build_d43_store_projection(d43_payload, contract=contract, limits=limits)
    groups = build_d45_groups_store_projection(d45_groups, contract=contract)
    fixed_payloads = {
        item_id: (
            payloads.get(item_id)
            if isinstance(payloads.get(item_id), str)
            else None
        )
        for item_id in STORE_ITEM_IDS_D45_FIXED
    }
    # allow bytes
    for item_id in STORE_ITEM_IDS_D45_FIXED:
        raw = payloads.get(item_id)
        if isinstance(raw, (bytes, bytearray)):
            fixed_payloads[item_id] = raw.decode("utf-8")
        elif isinstance(raw, str):
            fixed_payloads[item_id] = raw
    fixed = build_d45_fixed_store_projection(fixed_payloads, contract=contract)
    d429 = (
        build_d429_store_projection(
            payloads.get(STORE_ITEM_ID_D429, []), contract=contract, limits=limits
        )
        if _INCLUDE_D429_TRANSPOSED
        else None
    )

    d421 = build_d421_store_projection(
        payloads.get(STORE_ITEM_ID_D421, EMPTY_STORE_PAYLOAD), contract=contract, limits=limits
    )
    d422 = build_d422_store_projection(
        payloads.get(STORE_ITEM_ID_D422, EMPTY_STORE_PAYLOAD), contract=contract, limits=limits
    )
    d423 = build_d423_store_projection(
        payloads.get(STORE_ITEM_ID_D423, EMPTY_STORE_PAYLOAD), contract=contract, limits=limits
    )
    d424 = build_d424_store_projection(
        payloads.get(STORE_ITEM_ID_D424, EMPTY_STORE_PAYLOAD), contract=contract, limits=limits
    )
    # D4-35 dict store（{rows,sampling,periodAmount}）：只投影 rows；空/缺失时安全返回空投影。
    d435 = build_d435_store_projection(
        payloads.get(STORE_ITEM_ID_D435, {}), contract=contract, limits=limits
    )
    # D4-1 营业收入审定表：单个 store D4-1-rows 按 sectionKey 分流两区（main/other）。
    d41 = build_store_projection_d41(
        payloads.get(STORE_ITEM_ID_D41, EMPTY_STORE_PAYLOAD), contract=contract, limits=limits
    )
    # D4-9 重要客户结构分析：单个 store D4-9-data（{current,prior}+totals）三 table 合并投影。
    d49 = build_d49_store_projection(
        payloads.get(STORE_ITEM_ID_D49, "{}"), contract=contract, limits=limits
    )
    interview_projs = [
        build_interview_store_projection(
            code,
            payloads.get(interview_store_item_id(code), {} if code == "D4-31" else []),
            contract=contract,
            limits=limits,
        )
        for code in INTERVIEW_SHEET_CODES()
        if _INCLUDE_IPO_INTERVIEW_SHEETS
    ]
    d46_projs = (
        [build_store_projection_d46(payloads.get(STORE_ITEM_ID_D46, []), contract=contract, limits=limits)]
        if _INCLUDE_D46_INDICATOR_SHEET
        else []
    )
    d417_projs = (
        [build_store_projection_d417(payloads.get(STORE_ITEM_ID_D417, []), contract=contract, limits=limits)]
        if _INCLUDE_D417_CUTOFF_SHEET
        else []
    )
    d418_projs = (
        [build_store_projection_d418(payloads.get(STORE_ITEM_ID_D418, []), contract=contract, limits=limits)]
        if _INCLUDE_D418_CUTOFF_SHEET
        else []
    )
    d419_projs = (
        [build_store_projection_d419(payloads.get(STORE_ITEM_ID_D419, []), contract=contract, limits=limits)]
        if _INCLUDE_D419_DISCOUNT_SHEET
        else []
    )
    # D4-25/26/27/28 IPO 检查表追加受管 sheet（空载荷时安全返回空投影）。
    inspection_projs = [
        build_inspection_store_projection(
            code,
            payloads.get(INSPECTION_STORE_ITEM_ID_BY_CODE[code], EMPTY_STORE_PAYLOAD),
            contract=contract,
            limits=limits,
        )
        for code in INSPECTION_SHEET_CODES
    ]
    ipo_checklist_projs = [
        build_ipo_checklist_store_projection(
            code,
            payloads.get(STORE_ITEM_ID_BY_CODE[code], EMPTY_STORE_PAYLOAD),
            contract=contract,
            limits=limits,
        )
        for code in CHECKLIST_SHEET_CODES
    ]
    values: dict[str, FieldValue] = dict(left.values)
    values.update(right.values)
    values.update(groups.values)
    values.update(fixed.values)
    for proj in (d421, d422, d423, d424, d435, d41, d49, *ipo_checklist_projs, *inspection_projs, *interview_projs, *d46_projs, *d417_projs, *d418_projs, *d419_projs):
        values.update(proj.values)
    if d429 is not None:
        values.update(d429.values)
    row_keys = {
        **dict(left.row_keys),
        **dict(right.row_keys),
        **dict(groups.row_keys),
        **dict(d421.row_keys),
        **dict(d422.row_keys),
        **dict(d423.row_keys),
        **dict(d424.row_keys),
        **dict(d435.row_keys),
        **dict(d41.row_keys),
        **dict(d49.row_keys),
        **(dict(d429.row_keys) if d429 is not None else {}),
        **{k: v for p in interview_projs for k, v in dict(p.row_keys).items()},
        **{k: v for p in ipo_checklist_projs for k, v in dict(p.row_keys).items()},
        **{k: v for p in inspection_projs for k, v in dict(p.row_keys).items()},
        **{k: v for p in d46_projs for k, v in dict(p.row_keys).items()},
        **{k: v for p in d417_projs for k, v in dict(p.row_keys).items()},
        **{k: v for p in d418_projs for k, v in dict(p.row_keys).items()},
        **{k: v for p in d419_projs for k, v in dict(p.row_keys).items()},
    }
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys=row_keys,
    )


def merge_projection_into_all_d4_stores(
    *,
    projection: Any,
    base_by_item: Mapping[str, list[Mapping[str, Any]]],
) -> dict[str, tuple[list[dict[str, Any]], int, int, set[str]]]:
    """对 D4-2 / D4-3 / D4-5-policy-groups 分别 merge（fixed items 另见 merge_d45_fixed）。"""
    d42_base = list(base_by_item.get(STORE_ITEM_ID) or ())
    d43_base = list(base_by_item.get(STORE_ITEM_ID_D43) or ())
    d45_base = list(base_by_item.get(STORE_ITEM_ID_D45_GROUPS) or ())
    d421_base = list(base_by_item.get(STORE_ITEM_ID_D421) or ())
    d422_base = list(base_by_item.get(STORE_ITEM_ID_D422) or ())
    d423_base = list(base_by_item.get(STORE_ITEM_ID_D423) or ())
    d424_base = list(base_by_item.get(STORE_ITEM_ID_D424) or ())
    d41_base = list(base_by_item.get(STORE_ITEM_ID_D41) or ())
    interview_results = {
        interview_store_item_id(code): merge_interview_projection_into_store(
            code,
            projection=projection,
            base_payload=base_by_item.get(interview_store_item_id(code), {} if code == "D4-31" else []),
        )
        for code in INTERVIEW_SHEET_CODES()
        if _INCLUDE_IPO_INTERVIEW_SHEETS
    }
    d46_results = (
        {
            STORE_ITEM_ID_D46: merge_projection_into_d46_rows(
                projection=projection,
                base_payload=base_by_item.get(STORE_ITEM_ID_D46, []),
            )
        }
        if _INCLUDE_D46_INDICATOR_SHEET
        else {}
    )
    d417_results = (
        {
            STORE_ITEM_ID_D417: merge_projection_into_d417_rows(
                projection=projection,
                base_payload=base_by_item.get(STORE_ITEM_ID_D417, []),
            )
        }
        if _INCLUDE_D417_CUTOFF_SHEET
        else {}
    )
    d418_results = (
        {
            STORE_ITEM_ID_D418: merge_projection_into_d418_rows(
                projection=projection,
                base_payload=base_by_item.get(STORE_ITEM_ID_D418, []),
            )
        }
        if _INCLUDE_D418_CUTOFF_SHEET
        else {}
    )
    d419_results = (
        {
            STORE_ITEM_ID_D419: merge_projection_into_d419_rows(
                projection=projection,
                base_payload=base_by_item.get(STORE_ITEM_ID_D419, []),
            )
        }
        if _INCLUDE_D419_DISCOUNT_SHEET
        else {}
    )
    return {
        STORE_ITEM_ID: merge_projection_into_store_rows(
            projection=projection, base_rows=d42_base
        ),
        STORE_ITEM_ID_D43: merge_projection_into_d43_store_rows(
            projection=projection, base_rows=d43_base
        ),
        STORE_ITEM_ID_D45_GROUPS: merge_projection_into_d45_group_rows(
            projection=projection, base_rows=d45_base
        ),
        STORE_ITEM_ID_D421: merge_projection_into_d421_store_rows(
            projection=projection, base_rows=d421_base
        ),
        STORE_ITEM_ID_D422: merge_projection_into_d422_store_rows(
            projection=projection, base_rows=d422_base
        ),
        STORE_ITEM_ID_D423: merge_projection_into_d423_store_rows(
            projection=projection, base_rows=d423_base
        ),
        STORE_ITEM_ID_D424: merge_projection_into_d424_store_rows(
            projection=projection, base_rows=d424_base
        ),
        # D4-1 营业收入审定表：两区投影按 table_key 分流合回单个 store D4-1-rows，
        # 按 sectionKey(main/other) 归属，两区 rowId 不串（merge_projection_into_d41_rows）。
        STORE_ITEM_ID_D41: merge_projection_into_d41_rows(
            projection=projection, base_rows=d41_base
        ),
        # D4-9 是嵌套 dict store（非行数组），不走本 rows 汇总；由 oo_to_html 专用 dict 块
        # 经 merge_d49_from_projection 单独处理（同 D4-35 STORE_ITEM_ID_D435_DICT 模式）。
        **(
            {
                STORE_ITEM_ID_D429: merge_d429_projection_into_store(
                    projection=projection,
                    base_payload=base_by_item.get(STORE_ITEM_ID_D429),
                )
            }
            if _INCLUDE_D429_TRANSPOSED
            else {}
        ),

        **interview_results,
        **d46_results,
        **d417_results,
        **d418_results,
        **d419_results,
        **{
            STORE_ITEM_ID_BY_CODE[code]: merge_ipo_checklist_projection_into_rows(
                code,
                projection=projection,
                base_rows=list(base_by_item.get(STORE_ITEM_ID_BY_CODE[code]) or ()),
            )
            for code in CHECKLIST_SHEET_CODES
        },
        **{
            INSPECTION_STORE_ITEM_ID_BY_CODE[code]: merge_inspection_projection_into_rows(
                code,
                projection=projection,
                base_rows=list(base_by_item.get(INSPECTION_STORE_ITEM_ID_BY_CODE[code]) or ()),
            )
            for code in INSPECTION_SHEET_CODES
        },
    }


def merge_d45_fixed_from_projection(
    *,
    projection: Any,
    base_by_item: Mapping[str, str | None],
) -> dict[str, str]:
    """D4-5 固定 item（remark 纯文本）← projection。"""
    return merge_projection_into_d45_fixed_items(
        projection=projection, base_by_item=base_by_item
    )


#: D4-35 store item（dict 形态 {rows, sampling, periodAmount}，非行数组，不进 STORE_ITEM_IDS）。
STORE_ITEM_ID_D435_DICT: Final[str] = STORE_ITEM_ID_D435

#: D4-9 store item（dict 形态 {current,prior}+totals，嵌套非行数组）。**在** STORE_ITEM_IDS 里
#: （combined projection / 单 item flush 需要），但 oo_to_html 镜像走专用 dict 块（不进 rows 循环）。
STORE_ITEM_ID_D49_DICT: Final[str] = STORE_ITEM_ID_D49


def merge_d49_from_projection(
    *,
    projection: Any,
    base_state: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], int, int]:
    """D4-9 dict store ← projection：三 table 分流回 {current,prior}+totals 嵌套结构。

    返回 (merged_dict, applied, visited)。委托 sibling provider 的 merge。
    """
    return merge_projection_into_d49_store_state(
        projection=projection, base_state=base_state
    )


def merge_d435_from_projection(
    *,
    projection: Any,
    base_state: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], int, int]:
    """D4-35 dict store ← projection：只 merge rows，保留 sampling/periodAmount（HTML-only 非行数据）。

    返回 (merged_dict, applied, visited)。merged_dict 恒为 {rows, sampling, periodAmount} 完整形态。
    """
    base = dict(base_state) if isinstance(base_state, Mapping) else {}
    base_rows = base.get("rows")
    if not isinstance(base_rows, list):
        base_rows = []
    merged_rows, applied, visited, _touched = merge_projection_into_d435_store_rows(
        projection=projection, base_rows=base_rows
    )
    return (
        {
            "rows": merged_rows,
            "sampling": base.get("sampling", {}),        # 保留：抽样设计不被 OO 回读冲掉
            "periodAmount": base.get("periodAmount", ""),  # 保留
        },
        applied,
        visited,
    )


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
    sibling_bindings = _attach_sibling_bindings(
        primary=observation.identity_binding,
        contract=contract,
        dynamic_bindings=observation.identity_binding.dynamic_column_columns,
    )
    register_adapter(
        registry,
        adapter=build_excel_adapter(
            definitions=observation.definitions,
            binding=observation.identity_binding,
            sibling_bindings=sibling_bindings,
            direction="html_to_oo",
        ),
        bundle=bundle,
        descriptor=descriptor,
        room=facts.observe_room_facts(entry),
        contract=contract,
    )
    return (ADAPTER_ID,)


def _attach_sibling_bindings(
    *,
    primary: Any,
    contract: Any,
    dynamic_bindings: Mapping[str, Any],
) -> tuple[Any, ...]:
    """Attach 时补 sibling binding（与 publish 的 `_sibling_identity_bindings` 同规则）。

    🔴 对齐规则与 publish 路径共享同一内核 `_align_specs_to_sibling_tables`：按
    managed sheet 归组、同 sheet 双区靠 UUID 列一一配对、计数守卫数行 table 不数
    sheet。两路径必须使用同一规则，否则 publish 与 attach 的 sibling binding 会漂移。
    """
    from app.services.excel_structure_fingerprint import GT_SYNC_SHEET_NAME
    from app.services.workpaper_sync.excel_extract import ExcelIdentityBinding
    from app.services.workpaper_sync.projection_first_publication import (
        _align_specs_to_sibling_tables,
    )

    # attach 路径以本模块为 provider（暴露 instrumentation_specs）。
    import app.services.workpaper_sync.phase5_d4_revenue_detail as _provider

    pairs = _align_specs_to_sibling_tables(
        provider=_provider, contract=contract, primary=primary
    )
    siblings: list[Any] = []
    for spec, dynamic in pairs:
        binding = ExcelIdentityBinding(
            table_name=str(spec.table_name),
            uuid_column=str(spec.uuid_col),
            table_key=str(dynamic.table_key),
            metadata_sheet=GT_SYNC_SHEET_NAME,
            defined_name_prefix=str(
                getattr(spec, "defined_name_prefix", None) or "GT_"
            ),
            tombstoned_row_keys=(),
            dynamic_column_columns={
                str(table_key): dict(mapping)
                for table_key, mapping in (dynamic_bindings or {}).items()
                if isinstance(mapping, Mapping)
            },
        )
        siblings.append(binding)
    return tuple(siblings)


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
