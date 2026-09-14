# -*- coding: utf-8 -*-
"""D3 预收账款「预收账款明细表 D3-2」—— Phase 5 第三个 canary（harness 无关的独立 entry 双向路径）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Phase 5 (G5-1)

═══ 与 D7 canary 同范式（两级表头 + 账龄组），列语义按 D3-2 权威模板逐格实测 ═══

受管 sheet = `预收账款明细表D3-2`（openpyxl 逐格实测）：两级表头（行 10 组标题 + 行 11 账龄
子标题），27 列 A-AA，含两个账龄组（期初审定账龄 I-L / 审定账龄 U-X，各 4 段 THREE_YEAR =
1年以内/1-2/2-3/3年以上，与 D7 同段）。数据区行 12-23，footer 行 24「合计」（**纯「合计」两字，
无空格**，与 D7 的「合   计」不同 —— 别照搬 D7 的 FOOTER_MARKER）。四个公式列逐行：
H=E+F+G（期初审定）、O=E+N-M（期末余额，贷方科目 贷增借减）、Q=O+P（期末未审）、T=Q+R+S（期末审定）。

HTML store = `checklist_responses` 单条 item `D3-det-rows`（前端 useD3Detail.ts 的 DetailRow
整行数组 JSON.stringify）。账龄是 nested keyed（`agingPrior.{seg}` / `agingAudited.{seg}`，
段来自 useAgingConfig D3 默认 THREE_YEAR 的 4 段），json_pointer 用 `/rows/{uuid}/agingPrior/within1`。

wp_code 裁决 = adjudication 文件里的 `['D3']`（载荷落点）；模块 WP_CODES = manifest 冻结的
`{'D3P'}`（宿主 CamelCase 幻影码，finder 零命中）—— 与 D7（模块 D7C / 裁决 D7）同理：
manifest wp_code_patterns 与 assert_entry_selectable / build_matcher 用 WP_CODES，provisioner
JOIN wp_index 用 adjudication.wp_codes。D3-det-rows 真库 0 行（从未录入明细，同 H1-8-rows），
但 sibling D3-vc-current-rows 载荷落 wp_code=D3（1 行 3601B）已证 D3 store 落点 = D3。
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


class EntrySelectionError(SyncDomainError):
    """冻结的 canary entry 不再满足选型必要条件（manifest / 模板真源漂移即打红）。"""

    error_code = "sync_phase5_d3_selection_invalid"


class StorePayloadError(SyncDomainError):
    """HTML store 大 JSON 载荷形态不合法（非数组、缺 row identity、重复 identity）。"""

    error_code = "sync_phase5_d3_store_payload_invalid"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量（从真实 manifest / 真库实测）
# ═══════════════════════════════════════════════════════════════════════════

PHASE5_WAVE: Final[str] = "phase5_prepaid_receipts"
ENTRY_ID: Final[str] = "xlsx/gt-d3-prepaid-accounts"
ADAPTER_ID: Final[str] = "d3.prepaid_receipts_detail"
#: 🔴 manifest 冻结的 wp_code_pattern（宿主 GtD3PrepaidAccounts CamelCase 抽出的幻影码，
#: finder 零命中）。assert_entry_selectable / build_matcher 用它；provisioner 用 adjudication 的 ['D3']。
WP_CODES: Final[frozenset[str]] = frozenset({"D3P"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "D/D3 预收账款.xlsx"
TEMPLATE_SHA256: Final[str] = (
    "699a9be0e7da639f3e5cd3a2d3bfdf38f7e777b330f9ec6959f5cc390fb6c2d2"
)
MANAGED_SHEET: Final[str] = "预收账款明细表D3-2"
TEMPLATE_ID: Final[str] = "D32"
SHEET_KEY: Final[str] = f"{TEMPLATE_ID.lower()}-managed"
ROWS_TABLE_KEY: Final[str] = "prepaid_receipts_detail_rows"

#: 两级表头：组标题在行 10，账龄子标题在行 11（openpyxl 逐格实测）。
HEADER_GROUP_ROW: Final[int] = 10
HEADER_LEAF_ROW: Final[int] = 11

#: 数据区与 footer（openpyxl 逐格实测：数据 12-23，合计 24）。
FIRST_DATA_ROW: Final[int] = 12
LAST_DATA_ROW: Final[int] = 23
FOOTER_ROW: Final[int] = 24

#: 最后一列受管业务列（AA 备注）与隐藏 row UUID 列。
MANAGED_LAST_COL: Final[str] = "AA"
UUID_COL: Final[str] = "AB"

TABLE_NAME: Final[str] = f"GT_{TEMPLATE_ID}_ROWS"
AUTHORITY_MODEL: Final[AuthorityModel] = AuthorityModel.projection_contract
#: 🔴 footer 单元格 A24 的精确文本 = 「合计」两字（codepoints 0x5408 0x8ba1，无空格，
#: openpyxl 逐格实测）。**不要**照搬 D7 的「合   计」（那是 D7-2 A23 的 3 空格特例）。
FOOTER_MARKER: Final[str] = "合计"

STORE_ITEM_ID: Final[str] = "D3-det-rows"
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
ROW_IDENTITY_STORE_KEY: Final[str] = "rowId"

#: D3 默认账龄 = THREE_YEAR 的 4 段（与前端 useAgingConfig DEFAULT_SUBJECT_PRESETS['D3'] 一致，
#: 与 D7 同段）。`(段 key, 行 11 子标题文本)`。子标题用模板实测的全角字符（２／～）。
AGING_SEGMENTS: Final[tuple[tuple[str, str], ...]] = (
    ("within1", "1年以下"),
    ("y1to2", "1～2年"),
    ("y2to3", "２～3年"),
    ("over3", "3年以上"),
)

#: 两个账龄组：`(json 前缀, 组标题单元格, 四列列标)`。I-L 期初 / U-X 期末审定。
AGING_GROUPS: Final[tuple[tuple[str, str, tuple[str, ...]], ...]] = (
    ("agingPrior", f"I{HEADER_GROUP_ROW}", ("I", "J", "K", "L")),
    ("agingAudited", f"U{HEADER_GROUP_ROW}", ("U", "V", "W", "X")),
)


#: 19 个标量列（非账龄）：`(column_key, 列标, mode, value_type, store json 键, 行 10 表头文本)`。
#: 🔴 顺序即 Excel 列序。store json 键 = 前端 useD3Detail.DetailRow 的 camelCase 键。
#: H/O/Q/T 四列在模板里逐行有真公式（H=E+F+G / O=E+N-M / Q=O+P / T=Q+R+S）⇒ formula。
#: 🔴 D3 列语义与 D7 不同：借方 M / 贷方 N（D7 是 N/O）；款项性质 C / 关联方类型 D（D7 是 D/E）。
SCALAR_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    ("customer_name", "A", "editable", "text", "customerName", "对方单位名称"),
    ("company_code", "B", "editable", "text", "companyCode", "公司代码"),
    ("nature", "C", "editable", "enum", "nature", "款项性质"),
    ("relation_type", "D", "editable", "enum", "relationType", "关联方类型"),
    ("prior_unadjusted", "E", "editable", "amount", "priorUnadjusted", "期初未审余额"),
    ("prior_adjustment", "F", "editable", "amount", "priorAdjustment", "期初账项调整"),
    ("prior_reclass", "G", "editable", "amount", "priorReclass", "期初重分类调整"),
    ("prior_audited", "H", "formula", "amount", "priorAudited", "期初审定余额"),
    ("debit", "M", "editable", "amount", "debit", "借方发生"),
    ("credit", "N", "editable", "amount", "credit", "贷方发生"),
    ("end_balance", "O", "formula", "amount", "endBalance", "期末余额"),
    ("entity_reclass", "P", "editable", "amount", "entityReclass", "被审计单位重分类调整"),
    ("end_unadjusted", "Q", "formula", "amount", "endUnadjusted", "期末未审余额"),
    ("end_aje", "R", "editable", "amount", "endAje", "期末账项调整"),
    ("end_rje", "S", "editable", "amount", "endRje", "期末重分类调整"),
    ("end_audited", "T", "formula", "amount", "endAudited", "期末审定数"),
    ("is_confirmed", "Y", "editable", "text", "isConfirmed", "是否发函"),
    ("post_period_settlement", "Z", "editable", "amount", "postPeriodSettlement", "期后结转"),
    ("remark", "AA", "editable", "text", "remark", "备注"),
)


def _snake(camel: str) -> str:
    out: list[str] = []
    for ch in camel:
        if ch.isupper():
            out.append("_")
            out.append(ch.lower())
        else:
            out.append(ch)
    return "".join(out)


def _col_index(letters: str) -> int:
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch) - 64)
    return idx


def _aging_field_specs() -> tuple[tuple[str, str, str, str, str, str], ...]:
    """两个账龄组展开成 8 条 spec（形态同 SCALAR_FIELD_SPECS，json 键为 nested 路径）。"""
    out: list[tuple[str, str, str, str, str, str]] = []
    for json_prefix, _group_cell, columns in AGING_GROUPS:
        if len(columns) != len(AGING_SEGMENTS):
            raise EntrySelectionError(
                f"账龄组 {json_prefix} 声明了 {len(columns)} 列，段清单有 "
                f"{len(AGING_SEGMENTS)} 段 —— 列与段必须一一对应"
            )
        prefix_key = _snake(json_prefix)
        for column, (seg_key, leaf_label) in zip(columns, AGING_SEGMENTS):
            out.append(
                (
                    f"{prefix_key}_{seg_key.lower()}",
                    column,
                    "editable",
                    "amount",
                    f"{json_prefix}/{seg_key}",
                    leaf_label,
                )
            )
    return tuple(out)


#: 27 个受管字段 = 19 标量 + 8 账龄，按 Excel 列序（A→AA）排列。
MANAGED_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str], ...]] = tuple(
    sorted(SCALAR_FIELD_SPECS + _aging_field_specs(), key=lambda row: _col_index(row[1]))
)

#: column_key → 账龄组标题单元格（只有账龄列有）。
GROUP_HEADER_CELLS: Final[Mapping[str, str]] = {
    f"{_snake(json_prefix)}_{seg_key.lower()}": group_cell
    for json_prefix, group_cell, _cols in AGING_GROUPS
    for seg_key, _leaf in AGING_SEGMENTS
}

#: 四个公式列的只读区域（H/O/Q/T）。
FORMULA_MASK: Final[tuple[str, ...]] = (
    f"H{FIRST_DATA_ROW}:H{LAST_DATA_ROW}",
    f"O{FIRST_DATA_ROW}:O{LAST_DATA_ROW}",
    f"Q{FIRST_DATA_ROW}:Q{LAST_DATA_ROW}",
    f"T{FIRST_DATA_ROW}:T{LAST_DATA_ROW}",
)


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
    return f"{ROWS_TABLE_KEY}/{row_identity}/{column_key}"


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
                "footer 行 A24「合计」（纯两字无空格）。声明为真使结构性插行有权按声明位移量"
                "扩张该区间（同 D7，但 D3 marker 无空格）"
            ),
        },
        "formula_mask": list(FORMULA_MASK),
        "fields": fields,
    }


_HTML_STORE_NOTE: Final[str] = (
    "整张预收账款明细表存成这一条 item 的 remark（JSON 数组字符串，useD3Detail 的 "
    "JSON.stringify(rows)）。本契约按 stable field + row rowId 拆开，禁止把整 JSON 当一个"
    "字段比较（对齐 D2 AC 6.9 / 6.12）。账龄为 nested keyed（agingPrior/agingAudited，段来自 "
    "useAgingConfig D3 默认 THREE_YEAR 的 4 段），json_pointer 用 /rows/{uuid}/agingPrior/within1"
)

_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐 sheet 直读净化后权威模板 D/D3 预收账款.xlsx（外链净化后 sha256 699a9be0），"
    "只取受管 sheet 预收账款明细表D3-2：两级表头 行 10（组标题）/ 行 11（账龄子标题 "
    "1年以下/1～2/２～3/3年以上），27 列 A-AA，数据区 12-23，H/O/Q/T 四列逐行公式 "
    "=E+F+G / =E+N-M（贷方科目）/ =O+P / =Q+R+S，A24「合计」footer（纯两字无空格）；"
    "19 标量列 + 两个账龄组各 4 段（I-L 期初 / U-X 期末审定）；字段键与前端 useD3Detail.DetailRow "
    "逐字段锁死。wp_code=D3（载荷落点：sibling D3-vc-current-rows 落 D3；D3-det-rows 全库 0 行"
    "但 D3 wp 未删除有 file_path，同 H1 空表单情形；非 D3P 幻影码 / 非 D3-2 名义码）"
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
            "backend/scripts/gen/generate_phase5_d3_contract.py --apply` 重生成"
        )
    parse_contract(expected, adapter_id=ADAPTER_ID)
    return on_disk


# ═══════════════════════════════════════════════════════════════════════════
# 6. HTML store 载荷拆分（stable field + row UUID，流式，账龄 nested）
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


def _resolve_json_path(row: Mapping[str, Any], json_path: str) -> Any:
    """按 `agingPrior/within1` 这类路径取值；缺失返回 None（不猜、不造）。"""
    cursor: Any = row
    for segment in json_path.split("/"):
        if not isinstance(cursor, Mapping):
            return None
        cursor = cursor.get(segment)
    return cursor


def split_store_row(
    row: Mapping[str, Any], *, row_identity: str, contract: SyncContract
) -> Iterator[tuple[str, Any, FieldSpec]]:
    for column_key, _column, _mode, _vt, json_path, _label in MANAGED_FIELD_SPECS:
        spec = contract.field_by_stable_key(stable_key_for(column_key))
        yield stable_key_for(column_key, row_identity), _resolve_json_path(row, json_path), spec


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
        for stable_key, value, spec in split_store_row(
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
        row_keys={ROWS_TABLE_KEY: tuple(row_keys)},
    )


def _set_json_path(row: dict[str, Any], json_path: str, value: Any) -> bool:
    """按 `agingPrior/within1` 写值，逐级建 dict；返回是否真的改了值。"""
    parts = json_path.split("/")
    cursor: dict[str, Any] = row
    for seg in parts[:-1]:
        nxt = cursor.get(seg)
        if not isinstance(nxt, dict):
            nxt = {}
            cursor[seg] = nxt
        cursor = nxt
    leaf = parts[-1]
    if cursor.get(leaf) != value:
        cursor[leaf] = value
        return True
    return False


def merge_projection_into_store_rows(
    *,
    projection: Any,
    base_rows: list[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], int, int, set[str]]:
    """把已 extract 的 projection 合进 D3-det-rows HTML store 行（不读盘）。

    🔴 field_id（snake column_key）→ store json 路径（含 nested 账龄 agingPrior/within1）
    的映射由 MANAGED_FIELD_SPECS 的第 0/4 列给出，两侧不可能各写一份而脱钩。
    """
    field_to_path = {spec[0]: spec[4] for spec in MANAGED_FIELD_SPECS}
    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in base_rows:
        rid = str(row.get(ROW_IDENTITY_STORE_KEY) or "").strip()
        if not rid:
            continue
        by_id[rid] = dict(row)
        order.append(rid)

    applied = 0
    visited = 0
    touched_rows: set[str] = set()
    for key in projection.stable_keys():
        fv = projection.get(key)
        if fv is None or getattr(fv, "is_protected", False):
            continue
        rid = getattr(fv, "row_key", None)
        if not rid:
            continue
        target = by_id.get(str(rid))
        if target is None:
            target = {ROW_IDENTITY_STORE_KEY: str(rid)}
            by_id[str(rid)] = target
            order.append(str(rid))
        field_id = str(key).rsplit("/", 1)[-1]
        json_path = field_to_path.get(field_id)
        if not json_path:
            continue
        visited += 1
        new_val = getattr(fv, "value", None)
        if _set_json_path(target, json_path, new_val):
            applied += 1
            touched_rows.add(str(rid))

    return [by_id[rid] for rid in order], applied, visited, touched_rows


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
