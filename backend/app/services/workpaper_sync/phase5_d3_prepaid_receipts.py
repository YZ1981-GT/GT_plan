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
from app.services.workpaper_sync.sheet_geometry import col_index, snake



# 🔴 Task 16 声明化：两个 Error 类由共享编排工厂提供（error_code 参数化）。
#    原定义位置在此，但 _orch 在文件底部 ⇒ 别名导出也在底部（见 _orch 块之后）。
#    需要在 _orch 定义前引用 EntrySelectionError 的代码（如 read_authoritative_template）
#    现在不直接引用它了（工厂内部自带），只有外部调用方需要模块级名字。


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


#: 几何纯函数收敛进框架层 sheet_geometry（Task 5，逐字节等价）；保留原名薄别名。
_snake = snake
_col_index = col_index


#: column_key → 账龄组标题单元格（只有账龄列有）。
#: 🔴 保留独立 mapping 供既有调用方（如有）；权威来源已内联进 `SPEC_D32.field_specs` 第 7 位
#: （design 裁决 3：group_header_cell 统一为内联第 7 位）。
GROUP_HEADER_CELLS: Final[Mapping[str, str]] = {
    f"{_snake(json_prefix)}_{seg_key.lower()}": group_cell
    for json_prefix, group_cell, _cols in AGING_GROUPS
    for seg_key, _leaf in AGING_SEGMENTS
}

# ═══════════════════════════════════════════════════════════════════════════
# Task 16 声明化（spec: d1-sync-row-table-engine-and-d1-coverage）：SPEC_D32 是本 entry
# 唯一权威声明，MANAGED_FIELD_SPECS / FORMULA_MASK 两个既有常量名从它派生（与 D7 同批，
# 两者同为 nested 账龄，作引擎该路径的对照）。
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

#: nested 账龄两组，翻成框架层 `AgingGroupSpec`。
_AGING_GROUP_SPECS_D32: Final[tuple[AgingGroupSpec, ...]] = tuple(
    AgingGroupSpec(
        json_prefix=json_prefix,
        group_header_cell=group_cell,
        segments=tuple(
            (seg_key, column) for column, (seg_key, _leaf) in zip(columns, AGING_SEGMENTS)
        ),
        leaf_labels=tuple(leaf for _seg, leaf in AGING_SEGMENTS),
    )
    for json_prefix, group_cell, columns in AGING_GROUPS
)

SPEC_D32: Final[RowTableSheetSpec] = RowTableSheetSpec(
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
    formula_columns=("H", "O", "Q", "T"),
    aging_layout=AgingLayout.nested,
    aging_groups=_AGING_GROUP_SPECS_D32,
    footer_marker=FOOTER_MARKER,
    error_label="D3-2 明细表",
)

#: 27 个受管字段 = 19 标量 + 8 账龄，按 Excel 列序（A→AA）排列。
#: 🔴 本值现由框架层 `managed_field_specs(SPEC_D32)` 现算；`_aging_field_specs()` 函数体
#: 已删（改用框架层 `expand_aging_fields`）。
MANAGED_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str], ...]] = tuple(
    row[:6] for row in _engine_managed_field_specs(SPEC_D32)
)

#: 四个公式列的只读区域（H/O/Q/T）。
#: 🔴 本值现由框架层 `SPEC_D32.formula_mask` property 现算，provider 不再手写字面量。
FORMULA_MASK: Final[tuple[str, ...]] = SPEC_D32.formula_mask


# ═══════════════════════════════════════════════════════════════════════════
# 2. 权威模板
# ═══════════════════════════════════════════════════════════════════════════

_BACKEND_ROOT: Final[Path] = Path(__file__).resolve().parents[3]


# ═══════════════════════════════════════════════════════════════════════════
# 3. 选型必要条件（真实 manifest / 真实 resolver，不经封闭枚举）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class TemplateResolutionFacts:
    by_wp_code: Mapping[str, Sequence[Any]]
    parent_code: str
    parent_resolved_path: Any


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

    return _engine_stable_key_for(SPEC_D32, column_key, row_identity)


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


def _expansion_sheets_payload() -> list[dict[str, Any]]:
    """扩容面（D3-6 / D3-4 双区 / D3-5 / D3-7 双区）的契约 `sheets[]` 条目。

    spec: d3-sync-coverage-via-row-table-engine · Task 6/8/9/10/11/12（接线重建）

    🔴 **本函数一度丢失**：Task 6~12 的 evidence 明确记录过它的存在与两次演进
    （Task 6 新建 `_expansion_sheet_row_table_payload()` + 本函数、`sheets` 里 splice
    `*_expansion_sheets_payload()`，entry 模块 869→942 行；Task 8 把它重构为**按
    `sheet_key` 分组**以支持 D3-4 双区，942→965 行），但那份工作树从未 `git add` ⇒
    入库版本的 `build_contract_payload()` 里既没有这两个私有函数、也没有 splice，
    磁盘契约停在「只有 D3-2 一张」。

    后果是一个**两把锁都看不见**的缺口：
      * `assert_contract_file_matches_source()` 比「磁盘 vs 源 payload」—— 两边漏的是
        同样 4 张 ⇒ 逐字节相等 ⇒ 报绿；
      * `assert_specs_align_with_contract_sheets()` 能看见，但它没有生产调用方，
        只在本 lane 的 `test_d3_expansion.py` 里被调用 ⇒ 那 3 条红从 commit
        `57c78b53c` 起就一直在 HEAD 上（CI `backend-tests` 全量带 `-x`）。

    🔴 重建时**不再写 D3 私有实现**，改调 d567 lane 后来抽出的共享实现
    `phase5_d567_expansion_contract.build_expansion_sheets()` —— 它的按 `sheet_key`
    分组逻辑与 Task 8 重构后的 D3 版逐字同构（双区两个 spec 共享同一 `sheet_key`
    必须归入同一 `sheets[]` 条目的 `tables[]`，否则契约解析器报「sheet_key 重复」
    fail-closed）。共享实现原先硬编码 `carries_total_formula: True`，本次同步改成读
    `spec.footer_carries_total_formula` —— 全仓唯一取 False 的正是 D3-4 段②贷方。
    """
    from app.services.workpaper_sync import phase5_d3_expansion as _exp
    from app.services.workpaper_sync.phase5_d567_expansion_contract import (
        build_expansion_sheets,
    )

    return build_expansion_sheets(_exp.managed_row_table_specs())


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
            },
            *_expansion_sheets_payload(),
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


# ═══════════════════════════════════════════════════════════════════════════
# 6. HTML store 载荷拆分（stable field + row UUID，流式，账龄 nested）
# ═══════════════════════════════════════════════════════════════════════════


#: 🔴 Task 16 声明化：`store_row_identity` / `iter_store_rows` / `_resolve_json_path` /
#: `split_store_row` 四个内部 helper 已收敛进框架层 `phase5_row_table_sheet`（逐字节等价），
#: 本模块不再需要独立名字。`build_store_projection` 保留同名薄转发（既有调用方零改动）。


def build_store_projection(
    payload: str | bytes | Sequence[Any],
    *,
    contract: SyncContract,
    limits: Any | None = None,
) -> Any:
    """薄转发框架层 `build_store_projection(SPEC_D32, ...)`（逐字节等价）。"""
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        build_store_projection as _engine_build_store_projection,
    )

    return _engine_build_store_projection(SPEC_D32, payload, contract=contract, limits=limits)


def merge_projection_into_store_rows(
    *,
    projection: Any,
    base_rows: list[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], int, int, set[str]]:
    """薄转发框架层 `merge_projection_into_store_rows(SPEC_D32, ...)`（逐字节等价，含幽灵行防护）。

    🔴 Task 16 声明化：`_set_json_path` 已收敛进框架层 `set_json_path`（provider 不再复制）。
    """
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        merge_projection_into_store_rows as _engine_merge,
    )

    return _engine_merge(SPEC_D32, projection=projection, base_rows=base_rows)


# ═══════════════════════════════════════════════════════════════════════════
# 7. 共享发布编排（Task 16 声明化：D3/D5/D6/D7 逐字只换常量的 22 个函数提成单一实现）
# ═══════════════════════════════════════════════════════════════════════════

from app.services.workpaper_sync.phase5_entry_orchestration import (  # noqa: E402
    Phase5EntryConfig,
    build_orchestration,
)

_orch = build_orchestration(Phase5EntryConfig(
    phase5_wave=PHASE5_WAVE,
    entry_id=ENTRY_ID,
    adapter_id=ADAPTER_ID,
    wp_codes=WP_CODES,
    expected_profile_id=EXPECTED_PROFILE_ID,
    template_relative_path=TEMPLATE_RELATIVE_PATH,
    template_sha256=TEMPLATE_SHA256,
    managed_sheet=MANAGED_SHEET,
    template_id=TEMPLATE_ID,
    sheet_key=SHEET_KEY,
    rows_table_key=ROWS_TABLE_KEY,
    first_data_row=FIRST_DATA_ROW,
    last_data_row=LAST_DATA_ROW,
    footer_row=FOOTER_ROW,
    managed_last_col=MANAGED_LAST_COL,
    uuid_col=UUID_COL,
    table_name=TABLE_NAME,
    authority_model=AUTHORITY_MODEL,
    footer_marker=FOOTER_MARKER,
    store_item_id=STORE_ITEM_ID,
    error_code_prefix="sync_phase5_d3",
    build_contract_payload_fn=build_contract_payload,
))

# ── 导出工厂产出的名字（registry 白名单 / 判据 / provisioner 按名读取）──
Phase5Definitions = _orch.Phase5Definitions
TemplateResolutionFacts = _orch.TemplateResolutionFacts
excel_carrier_gate = _orch.excel_carrier_gate
authoritative_template_path = _orch.authoritative_template_path
read_authoritative_template = _orch.read_authoritative_template
assert_no_implicit_template_fallback = _orch.assert_no_implicit_template_fallback
assert_entry_selectable = _orch.assert_entry_selectable
instrumentation_spec = _orch.instrumentation_spec
template_definition_payload = _orch.template_definition_payload
instrumentation_definition_payload = _orch.instrumentation_definition_payload
authority_model_payload = _orch.authority_model_payload
contract_file_path = _orch.contract_file_path
load_contract_from_disk = _orch.load_contract_from_disk
assert_contract_file_matches_source = _orch.assert_contract_file_matches_source
publish_definitions = _orch.publish_definitions
build_matcher = _orch.build_matcher
build_registration = _orch.build_registration
register_adapter = _orch.register_adapter
resolve_published_frozen_definitions = _orch.resolve_published_frozen_definitions
attach_adapters = _orch.attach_adapters
manifest_capability_enabled = _orch.manifest_capability_enabled
assert_manifest_capability_enabled = _orch.assert_manifest_capability_enabled

# ── 别名（provisioning / attach 白名单读的统一名）──
publish_pilot_definitions = publish_definitions
attach_pilot_adapters = attach_adapters
PILOT_WP_CODES = WP_CODES

# ── Error 类兼容别名（判据 / 外部 import 按模块名取它们时不断裂）──
EntrySelectionError = _orch.EntrySelectionError
StorePayloadError = _orch.StorePayloadError
