# -*- coding: utf-8 -*-
"""D7 合同负债「明细表 D7-2」—— Phase 5 第二个 canary（harness 无关的独立 entry 双向路径）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Phase 5 (G5-1)

═══ 与 D1 canary 同范式，但明细带两级表头 + 账龄组（更接近 D2）═══

D1（`phase5_d1_notes_receivable`）是单级表头 15 列；D7-2 是**两级表头**（行 8 组标题 + 行 9
账龄子标题），27 列 A-AA，含两个账龄组（期初审定账龄 J-M / 期末审定账龄 V-Y，各 4 段
`THREE_YEAR` = 1年以内/1-2/2-3/3年以上）。故本模块 `header_rows=2`、账龄字段带
`group_source_ref`，形态介于 D1 与 D2 之间。

受管 sheet = `明细表D7-2`（openpyxl 逐格实测）：单级列 A-I/N-U/Z-AA（行 8 与行 9 纵向合并），
账龄组 J8:M8（期初）/ V8:Y8（期末）子标题在行 9。数据区行 10-22，footer 行 23「合计」。
四个公式列逐行：I=F+G+H（期初审定）、P=F-N+O（期末未审，贷方科目 贷增借减）、
R=P+Q（期末未审余额）、U=R+S+T（期末审定）。

HTML store = `checklist_responses` 单条 item `D7-2-rows`（前端 useD7Detail.ts 的 DetailRow
整行数组 JSON.stringify）。账龄是 nested keyed（`agingPrior.{seg}` / `agingAudited.{seg}`，
段来自 useAgingConfig D7 默认 THREE_YEAR 的 4 段），json_pointer 用 `/rows/{uuid}/agingPrior/within1`。

wp_code 裁决 = `['D7']`（**不是 D7C/D7-2**）：查真库确认 store item `D7-2-rows` 载荷全部落
wp_code=D7（project 0ec33ac9 / wp 6f23dcce / 669B），D7C 是 manifest 从宿主 CamelCase 抽出的
幻影码（finder 零命中），D7-2 名字最像却无载荷 —— 载荷落点才是判据。
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



# 🔴 Task 16/17 声明化：Error 类由共享编排工厂提供，兼容别名在文件底部 _orch 块之后。


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量（从真实 manifest / 真库实测）
# ═══════════════════════════════════════════════════════════════════════════

PHASE5_WAVE: Final[str] = "phase5_contract_liabilities"
ENTRY_ID: Final[str] = "xlsx/gt-d7-contract-liabilities"
ADAPTER_ID: Final[str] = "d7.contract_liabilities_detail"
WP_CODES: Final[frozenset[str]] = frozenset({"D7C"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "D/D7 合同负债.xlsx"
TEMPLATE_SHA256: Final[str] = (
    "0facd3fe2297dbf72804d513d54ca08c55d6a26a41bf1d5c59fc3d7ea1c76a9a"
)
MANAGED_SHEET: Final[str] = "明细表D7-2"
TEMPLATE_ID: Final[str] = "D72"
SHEET_KEY: Final[str] = f"{TEMPLATE_ID.lower()}-managed"
ROWS_TABLE_KEY: Final[str] = "contract_liabilities_detail_rows"

#: 两级表头：组标题在行 8，账龄子标题在行 9。
HEADER_GROUP_ROW: Final[int] = 8
HEADER_LEAF_ROW: Final[int] = 9

#: 数据区与 footer（openpyxl 逐格实测）。
FIRST_DATA_ROW: Final[int] = 10
LAST_DATA_ROW: Final[int] = 22
FOOTER_ROW: Final[int] = 23

#: 最后一列受管业务列（AA 期后结转）与隐藏 row UUID 列。
MANAGED_LAST_COL: Final[str] = "AA"
UUID_COL: Final[str] = "AB"

TABLE_NAME: Final[str] = f"GT_{TEMPLATE_ID}_ROWS"
AUTHORITY_MODEL: Final[AuthorityModel] = AuthorityModel.projection_contract
#: 🔴 footer 单元格 A23 的**精确**文本是「合」+3 个半角空格+「计」（openpyxl 逐格实测
#: `\u5408\u0020\u0020\u0020\u8ba1`），不是「合计」。footer anchor 匹配是精确 cell 文本
#: 比对（_find_marker_row 走 shared strings，不做空格规整），marker 写「合计」会 FooterAnchorDriftError。
FOOTER_MARKER: Final[str] = "合   计"

STORE_ITEM_ID: Final[str] = "D7-2-rows"
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
ROW_IDENTITY_STORE_KEY: Final[str] = "rowId"

#: D7 默认账龄 = THREE_YEAR 的 4 段（与前端 useAgingConfig.DEFAULT_SUBJECT_PRESETS['D7'] 一致）。
#: `(段 key, 行 9 子标题文本)`。
AGING_SEGMENTS: Final[tuple[tuple[str, str], ...]] = (
    ("within1", "1年以内"),
    ("y1to2", "1-2年"),
    ("y2to3", "2-3年"),
    ("over3", "3年以上"),
)

#: 两个账龄组：`(json 前缀, 组标题单元格, 四列列标)`。
AGING_GROUPS: Final[tuple[tuple[str, str, tuple[str, ...]], ...]] = (
    ("agingPrior", f"J{HEADER_GROUP_ROW}", ("J", "K", "L", "M")),
    ("agingAudited", f"V{HEADER_GROUP_ROW}", ("V", "W", "X", "Y")),
)


#: 19 个标量列（非账龄）：`(column_key, 列标, mode, value_type, store json 键, 行 8 表头文本)`。
#: 🔴 顺序即 Excel 列序。store json 键 = 前端 useD7Detail.DetailRow 的 camelCase 键。
#: I/P/R/U 四列在模板里逐行有真公式（I=F+G+H / P=F-N+O / R=P+Q / U=R+S+T）⇒ formula。
SCALAR_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    ("contract_name", "A", "editable", "text", "contractName", "合同名称/项目名称"),
    ("company_name", "B", "editable", "text", "companyName", "单位名称"),
    ("company_code", "C", "editable", "text", "companyCode", "公司代码"),
    ("related_party_type", "D", "editable", "enum", "relatedPartyType", "关联关系"),
    ("nature_type", "E", "editable", "enum", "natureType", "类型"),
    ("prior_unadjusted", "F", "editable", "amount", "priorUnadjusted", "期初未审数"),
    ("prior_aje", "G", "editable", "amount", "priorAje", "账项调整"),
    ("prior_rje", "H", "editable", "amount", "priorRje", "重分类调整"),
    ("prior_audited", "I", "formula", "amount", "priorAudited", "期初审定数"),
    ("debit_amount", "N", "editable", "amount", "debitAmount", "借方发生"),
    ("credit_amount", "O", "editable", "amount", "creditAmount", "贷方发生"),
    ("end_balance", "P", "formula", "amount", "endBalance", "期末未审数"),
    ("entity_reclass", "Q", "editable", "amount", "entityReclass", "被审计单位重分类调整"),
    ("end_unadjusted", "R", "formula", "amount", "endUnadjusted", "期末未审余额"),
    ("end_aje", "S", "editable", "amount", "endAje", "账项调整"),
    ("end_rje", "T", "editable", "amount", "endRje", "重分类调整"),
    ("end_audited", "U", "formula", "amount", "endAudited", "期末审定数"),
    ("is_confirmed", "Z", "editable", "text", "isConfirmed", "是否发函"),
    ("post_transfer", "AA", "editable", "amount", "postTransfer", "期后结转"),
)


#: 几何纯函数收敛进框架层 sheet_geometry（Task 5，逐字节等价）；保留原名薄别名。
_snake = snake
_col_index = col_index


#: column_key → 账龄组标题单元格（只有账龄列有）。
#: 🔴 保留独立 mapping 供既有调用方（如有）；权威来源已内联进 `SPEC_D72.field_specs` 第 7 位
#: （design 裁决 3：group_header_cell 统一为内联第 7 位）。
GROUP_HEADER_CELLS: Final[Mapping[str, str]] = {
    f"{_snake(json_prefix)}_{seg_key.lower()}": group_cell
    for json_prefix, group_cell, _cols in AGING_GROUPS
    for seg_key, _leaf in AGING_SEGMENTS
}

# ═══════════════════════════════════════════════════════════════════════════
# Task 16 声明化（spec: d1-sync-row-table-engine-and-d1-coverage）：SPEC_D72 是本 entry
# 唯一权威声明，MANAGED_FIELD_SPECS / FORMULA_MASK 两个既有常量名从它派生（保留名字与值
# 不变，供既有调用方与零回归门核对；不删除是因为 `pilot_` 别名同款裁决 —— 改名收益低于
# 全仓 grep 调用方的风险）。
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

#: nested 账龄两组，翻成框架层 `AgingGroupSpec`（`segments` 二元 `(seg_key, column)` +
#: 独立 `leaf_labels`，与 D7 原 `AGING_SEGMENTS` 的 `(seg_key, leaf_label)` 一一对应）。
_AGING_GROUP_SPECS_D72: Final[tuple[AgingGroupSpec, ...]] = tuple(
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

SPEC_D72: Final[RowTableSheetSpec] = RowTableSheetSpec(
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
    formula_columns=("I", "P", "R", "U"),
    aging_layout=AgingLayout.nested,
    aging_groups=_AGING_GROUP_SPECS_D72,
    footer_marker=FOOTER_MARKER,
    error_label="D7-2 明细表",
)

#: 27 个受管字段 = 19 标量 + 8 账龄，按 Excel 列序（A→AA）排列。
#: 🔴 本值现由框架层 `managed_field_specs(SPEC_D72)` 现算（去掉引擎输出第 7 位
#: group_header_cell，还原成本 entry 原 6 元组形态）；`_aging_field_specs()` 函数体
#: 已删（改用框架层 `expand_aging_fields`，逐字节等价见 Property 3 判据）。
MANAGED_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str], ...]] = tuple(
    row[:6] for row in _engine_managed_field_specs(SPEC_D72)
)

#: 四个公式列的只读区域。
#: 🔴 本值现由框架层 `SPEC_D72.formula_mask` property 现算（Requirement 1.2），
#: provider 不再手写字面量。
FORMULA_MASK: Final[tuple[str, ...]] = SPEC_D72.formula_mask


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
    """薄转发框架层同名函数（Task 16 声明化，逐字节等价：两者都是
    `f"{table_key}/{row_identity}/{column_key}"`）。"""
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        stable_key_for as _engine_stable_key_for,
    )

    return _engine_stable_key_for(SPEC_D72, column_key, row_identity)


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
                "footer 行 A23 承载合计公式（I23..AA23 = SUM(x10:x22)，openpyxl 逐格实测）。"
                "声明为真使结构性插行有权按声明位移量扩张该区间"
            ),
        },
        "formula_mask": list(FORMULA_MASK),
        "fields": fields,
    }


_HTML_STORE_NOTE: Final[str] = (
    "整张合同负债明细表存成这一条 item 的 remark（JSON 数组字符串，useD7Detail 的 "
    "JSON.stringify(rows)）。本契约按 stable field + row rowId 拆开，禁止把整 JSON 当一个"
    "字段比较（对齐 D2 AC 6.9 / 6.12）。账龄为 nested keyed（agingPrior/agingAudited，段来自 "
    "useAgingConfig D7 默认 THREE_YEAR 的 4 段），json_pointer 用 /rows/{uuid}/agingPrior/within1"
)

_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐 sheet 直读权威模板 D/D7 合同负债.xlsx，只取受管 sheet 明细表D7-2：两级表头 "
    "行 8（组标题）/ 行 9（账龄子标题 1年以内/1-2/2-3/3年以上），27 列 A-AA，数据区 10-22，"
    "I/P/R/U 四列逐行公式 =F+G+H / =F-N+O（贷方科目）/ =P+Q / =R+S+T，A23 合计 footer；"
    "19 标量列 + 两个账龄组各 4 段（J-M 期初 / V-Y 期末）；字段键与前端 useD7Detail.DetailRow "
    "逐字段锁死。wp_code=D7（载荷落点，非 D7C 幻影码 / 非 D7-2 名义码）"
)


def _d567_expansion_sheets() -> list[dict[str, Any]]:
    """D7 扩容面 sheets（D7-5/D7-6 单区 + D7-4/D7-7 双区 + 审定表D7-1）。

    spec: d567-sync-coverage-via-row-table-engine · Task 12/16/19
    """
    from app.services.workpaper_sync import phase5_d7_expansion as _exp
    from app.services.workpaper_sync.phase5_d567_expansion_contract import (
        build_adjudication_sheet, build_expansion_sheets,
    )

    sheets = build_expansion_sheets(_exp.managed_row_table_specs())
    if getattr(_exp, "_INCLUDE_D701_ADJUDICATION", False):
        from app.services.workpaper_sync.phase5_d7_01_adjudication import SPEC_D701
        sheets.extend(build_adjudication_sheet(SPEC_D701, key_prefix="d7_adj"))
    return sheets


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
            *_d567_expansion_sheets(),
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
#: `split_store_row` / `build_store_projection` 五个函数已收敛进框架层
#: `phase5_row_table_sheet`（逐字节等价，Task 1 的 golden digest 门钉住零回归）。
#: 本模块保留 `build_store_projection` 同名薄转发（既有调用方零改动），其余四个内部
#: helper 不再需要独立名字（框架层内部消费，provider 不再各自复制）。


def build_store_projection(
    payload: str | bytes | Sequence[Any],
    *,
    contract: SyncContract,
    limits: Any | None = None,
) -> Any:
    """薄转发框架层 `build_store_projection(SPEC_D72, ...)`（逐字节等价）。

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
            SPEC_D72, payload, contract=contract, limits=limits
        )
    except RowTableStorePayloadError as exc:
        raise StorePayloadError(str(exc)) from exc


def merge_projection_into_store_rows(
    *,
    projection: Any,
    base_rows: list[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], int, int, set[str]]:
    """薄转发框架层 `merge_projection_into_store_rows(SPEC_D72, ...)`（逐字节等价，含幽灵行防护）。

    🔴 Task 16 声明化：`_set_json_path` 已收敛进框架层 `set_json_path`（provider 不再复制）。
    """
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        merge_projection_into_store_rows as _engine_merge,
    )

    return _engine_merge(SPEC_D72, projection=projection, base_rows=base_rows)


# ═══════════════════════════════════════════════════════════════════════════
# 共享发布编排（Task 16/17 声明化）
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
    error_code_prefix="sync_phase5_d7",
    build_contract_payload_fn=build_contract_payload,
))

# ── 导出工厂产出的名字 ──
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

# ── 别名 ──
publish_pilot_definitions = publish_definitions
attach_pilot_adapters = attach_adapters
PILOT_WP_CODES = WP_CODES

# ── Error 类兼容别名 ──
EntrySelectionError = _orch.EntrySelectionError
StorePayloadError = _orch.StorePayloadError
