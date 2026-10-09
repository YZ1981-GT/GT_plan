# -*- coding: utf-8 -*-
"""D5 应收款项融资「明细表 D5-2」—— Phase 5 第五个 canary（harness 无关的独立 entry 双向路径）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Phase 5 (G5-1)

═══ 最简 canary：两级表头但**无账龄组**（FVOCI，17 列 A-Q）═══

受管 sheet = `应收款项融资明细表D5-2`（openpyxl 逐格实测）：两级表头（行 10 组标题 + 行 11 子
标题），17 列 A-Q。组标题：期初数 C:G / 本期变动 H:I / 期末数 J:P（A/B/Q 为 10-11 纵向合并
的单列）。数据区行 12-16，footer 行 17「合计」（**纯两字无空格，同 D3**，非 D7 三空格）。
四个公式列逐行：F=C+E+D（期初审定）、J=C+H-I（期末余额）、L=J+K（期末未审）、O=J+N+M（期末审定）。

🔴 与 D3/D6/D7 关键差异：**无账龄组**，每个 group 下的子列都是不同语义字段（非账龄 4 段），
故本模块无 AGING_GROUPS，只用 SCALAR_FIELD_SPECS 的 group_cell（第 6 列）标注它属于哪个组。

HTML store = `checklist_responses` 单条 item `D5-2-rows`（前端 useD5Detail.ts 的 DetailRow
整行数组 JSON.stringify）。D5-2-rows 全库 0 行（明细表从未录入，同 H1/D3/D6 空表单），空首版。
🔴 useD5Detail.DetailRow 有 19 字段，但 postRealized(R)/eclStage(S) 是**store-only**（模板无
对应列），故本模块只映射 A-Q 的 17 个字段。

wp_code 裁决 = adjudication 的 `['D5']`（载荷落点）；模块 WP_CODES = manifest 冻结的
`{'D5R'}`（宿主 GtD5ReceivablesFinancing CamelCase 幻影码，finder 零命中）。
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



# 🔴 Task 16/17 声明化：Error 类由共享编排工厂提供，兼容别名在文件底部 _orch 块之后。


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量
# ═══════════════════════════════════════════════════════════════════════════

PHASE5_WAVE: Final[str] = "phase5_receivables_financing"
ENTRY_ID: Final[str] = "xlsx/gt-d5-receivables-financing"
ADAPTER_ID: Final[str] = "d5.receivables_financing_detail"
WP_CODES: Final[frozenset[str]] = frozenset({"D5R"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "D/D5 应收款项融资.xlsx"
TEMPLATE_SHA256: Final[str] = (
    "92c5f7f2d2d54340c29bef6094b24a9360edcfa730fcfd406aeb071d4d138ac4"
)
MANAGED_SHEET: Final[str] = "应收款项融资明细表D5-2"
TEMPLATE_ID: Final[str] = "D52"
SHEET_KEY: Final[str] = f"{TEMPLATE_ID.lower()}-managed"
ROWS_TABLE_KEY: Final[str] = "receivables_financing_detail_rows"

#: 两级表头：组标题在行 10，子标题在行 11。
HEADER_GROUP_ROW: Final[int] = 10
HEADER_LEAF_ROW: Final[int] = 11

#: 数据区与 footer（openpyxl 逐格实测：数据 12-16，合计 17）。
FIRST_DATA_ROW: Final[int] = 12
LAST_DATA_ROW: Final[int] = 16
FOOTER_ROW: Final[int] = 17

MANAGED_LAST_COL: Final[str] = "Q"
UUID_COL: Final[str] = "R"

TABLE_NAME: Final[str] = f"GT_{TEMPLATE_ID}_ROWS"
AUTHORITY_MODEL: Final[AuthorityModel] = AuthorityModel.projection_contract
#: 🔴 footer A17「合计」（纯两字无空格，同 D3，非 D7 三空格）。
FOOTER_MARKER: Final[str] = "合计"

STORE_ITEM_ID: Final[str] = "D5-2-rows"
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
ROW_IDENTITY_STORE_KEY: Final[str] = "rowId"

#: 17 个受管字段：`(column_key, 列标, mode, value_type, store json 键, 行 11 子标题, 组标题单元格|"")`。
#: 🔴 顺序即 Excel 列序。store 键 = 前端 useD5Detail.DetailRow 的 camelCase 键。
#: F/J/L/O 四列在模板里逐行有真公式（F=C+E+D / J=C+H-I / L=J+K / O=J+N+M）⇒ formula。
#: 第 6 列 = 组标题单元格（C-G 属期初数 C10 / H-I 属本期变动 H10 / J-P 属期末数 J10；A/B/Q 空）。
#: 🔴 D5 无账龄组，group 下每个子列是不同语义字段（非 4 段账龄），故不展开账龄。
#: 🔴 useD5Detail 的 postRealized(R)/eclStage(S) 是 store-only（模板无列），不列入。
MANAGED_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("category", "A", "editable", "enum", "category", "类别", ""),
    ("item_name", "B", "editable", "text", "itemName", "明细项目", ""),
    ("prior_unadjusted", "C", "editable", "amount", "priorUnadjusted", "未审数", "C10"),
    ("prior_aje", "D", "editable", "amount", "priorAje", "账项调整", "C10"),
    ("prior_rje", "E", "editable", "amount", "priorRje", "重分类调整", "C10"),
    ("prior_audited", "F", "formula", "amount", "priorAudited", "审定数", "C10"),
    ("oci_impairment", "G", "editable", "amount", "ociImpairment", "其他综合收益-应收款项融资减值准备余额", "C10"),
    ("period_increase", "H", "editable", "amount", "periodIncrease", "本期增加", "H10"),
    ("period_decrease", "I", "editable", "amount", "periodDecrease", "本期减少", "H10"),
    ("end_balance", "J", "formula", "amount", "endBalance", "期末余额", "J10"),
    ("entity_reclass", "K", "editable", "amount", "entityReclass", "被审计单位重分类调整", "J10"),
    ("end_unadjusted", "L", "formula", "amount", "endUnadjusted", "期末未审余额", "J10"),
    ("end_aje", "M", "editable", "amount", "endAje", "账项调整", "J10"),
    ("end_rje", "N", "editable", "amount", "endRje", "重分类调整", "J10"),
    ("end_audited", "O", "formula", "amount", "endAudited", "审定数", "J10"),
    ("end_oci_impairment", "P", "editable", "amount", "endOciImpairment", "其他综合收益-应收款项融资减值准备余额", "J10"),
    ("remark", "Q", "editable", "text", "remark", "备注", ""),
)


#: 🔴 Task 17 声明化：D5 原自带的 `_col_index` 函数体已删（Task 5 当时未覆盖 D5，本次一并
#: 收敛）。它唯一的调用方是本文件已删除的 `_aging_field_specs` 等引擎函数，收敛后本文件
#: 不再需要该别名（D5 无账龄组，`managed_field_specs()` 内部用框架层 `col_index`）。

# ═══════════════════════════════════════════════════════════════════════════
# Task 17 声明化（spec: d1-sync-row-table-engine-and-d1-coverage）：SPEC_D52 是本 entry
# 唯一权威声明。🔴 D5 原本就是内联 7 元组的来源家（design 裁决 3 的零改动对照）+ 无账龄组
# （引擎「无分组」路径基准样本，`aging_layout=None`）—— 若它的 digest 变了说明引擎理解错了。
# ═══════════════════════════════════════════════════════════════════════════

from app.services.workpaper_sync.phase5_row_table_sheet import (  # noqa: E402
    RowTableSheetSpec,
    StoreKind,
)
from app.services.workpaper_sync.phase5_row_table_sheet import (  # noqa: E402
    managed_field_specs as _engine_managed_field_specs,
)

SPEC_D52: Final[RowTableSheetSpec] = RowTableSheetSpec(
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
    field_specs=MANAGED_FIELD_SPECS,  # 已是 7 元组，零改动对照，直接引用
    formula_columns=("F", "J", "L", "O"),
    aging_layout=None,  # D5 无账龄组：引擎「无分组」路径基准样本
    footer_marker=FOOTER_MARKER,
    error_label="D5-2 明细表",
    #: 🔴 D5 首列 `category` 是枚举（非空字符串占位符合法但语义上不是"名称"），幽灵行防护
    #: 改用第 1 位 `item_name`（原实现即 `MANAGED_FIELD_SPECS[1]`，与 D6 同款例外）。
    ghost_row_anchor_index=1,
)

#: 四个公式列的只读区域（F/J/L/O）。
#: 🔴 本值现由框架层 `SPEC_D52.formula_mask` property 现算，provider 不再手写字面量。
FORMULA_MASK: Final[tuple[str, ...]] = SPEC_D52.formula_mask


# ═══════════════════════════════════════════════════════════════════════════
# 2. 权威模板
# ═══════════════════════════════════════════════════════════════════════════

_BACKEND_ROOT: Final[Path] = Path(__file__).resolve().parents[3]


# ═══════════════════════════════════════════════════════════════════════════
# 3. 选型必要条件
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
    """薄转发框架层同名函数（Task 17 声明化，逐字节等价）。"""
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        stable_key_for as _engine_stable_key_for,
    )

    return _engine_stable_key_for(SPEC_D52, column_key, row_identity)


def _rows_table_payload() -> dict[str, Any]:
    fields: list[dict[str, Any]] = []
    for column_key, column, mode, value_type, json_path, leaf_text, group_cell in MANAGED_FIELD_SPECS:
        # 有组标题的列表头指向行 11（子标题）；无组的（A/B/Q）指向行 10。
        header_row = HEADER_LEAF_ROW if group_cell else HEADER_GROUP_ROW
        spec: dict[str, Any] = {
            "stable_field_key": stable_key_for(column_key),
            "json_pointer": f"/rows/{{row_uuid}}/{json_path}",
            "column_key": column_key,
            "cell": {"column": column, "row_from": "row_identity"},
            "mode": mode,
            "value_type": value_type,
            "source_ref": _src(f"{column}{FIRST_DATA_ROW}"),
            "header_source_ref": _src(f"{column}{header_row}"),
            "store_item_id": STORE_ITEM_ID,
            "header_text": leaf_text,
        }
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
            "note": "footer 行 A17「合计」（纯两字无空格，同 D3）。声明为真使结构性插行按声明位移量扩张。",
        },
        "formula_mask": list(FORMULA_MASK),
        "fields": fields,
    }


_HTML_STORE_NOTE: Final[str] = (
    "整张应收款项融资明细表存成这一条 item 的 remark（JSON 数组字符串，useD5Detail 的 "
    "JSON.stringify(rows)）。本契约按 stable field + row rowId 拆开。🔴 无账龄组，两级表头的组"
    "（期初数/本期变动/期末数）下每个子列是不同语义字段。postRealized/eclStage 是 store-only 不入。"
)

_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐 sheet 直读净化后权威模板 D/D5 应收款项融资.xlsx（外链净化后 sha256 92c5f7f2），"
    "只取受管 sheet 应收款项融资明细表D5-2：两级表头 行 10（组标题 期初数 C:G / 本期变动 H:I / "
    "期末数 J:P）/ 行 11（子标题），17 列 A-Q，数据区 12-16，F/J/L/O 四列逐行公式 =C+E+D / "
    "=C+H-I / =J+K / =J+N+M，A17「合计」footer（纯两字）；FVOCI 无账龄组；字段键与前端 "
    "useD5Detail.DetailRow 逐字段锁死（postRealized/eclStage store-only 不入）。wp_code=D5"
    "（载荷落点：D5-2-rows 全库 0 行同 H1/D3/D6 空表单，D5 wp 未删除有 file_path；非 D5R 幻影码）"
)


def _d567_expansion_sheets() -> list[dict[str, Any]]:
    """D5 扩容面 sheets（D5-4 行表 + 审定表D5），灰度开关由 expansion 模块控制。

    spec: d567-sync-coverage-via-row-table-engine · Task 6/7
    """
    from app.services.workpaper_sync import phase5_d5_expansion as _exp
    from app.services.workpaper_sync.phase5_d567_expansion_contract import (
        build_adjudication_sheet, build_expansion_sheets,
    )

    sheets = build_expansion_sheets(_exp.managed_row_table_specs())
    if getattr(_exp, "_INCLUDE_D501_ADJUDICATION", False):
        from app.services.workpaper_sync.phase5_d5_01_adjudication import SPEC_D501
        sheets.extend(build_adjudication_sheet(SPEC_D501, key_prefix="d5_adj"))
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
# 6. HTML store 载荷拆分（stable field + row UUID，流式；D5 无 nested）
# ═══════════════════════════════════════════════════════════════════════════


#: 🔴 Task 17 声明化：`store_row_identity` / `iter_store_rows` / `_resolve_json_path` /
#: `split_store_row` 四个内部 helper 已收敛进框架层 `phase5_row_table_sheet`。
#: `build_store_projection` 保留同名薄转发。


def build_store_projection(
    payload: str | bytes | Sequence[Any],
    *,
    contract: SyncContract,
    limits: Any | None = None,
) -> Any:
    """薄转发框架层 `build_store_projection(SPEC_D52, ...)`（逐字节等价）。

    🔴 **必须转译引擎异常**（2026-09-26 修 Task 17 遗留回归）：引擎抛
    `RowTableStorePayloadError(Exception)`（非 domain 错误），若直接冒泡会被
    `wp_sync_router` 当未知异常 ⇒ **opaque 500**；而收敛前本函数抛
    `StorePayloadError(SyncDomainError)` 带 `error_code` ⇒ 映射 **4xx**。
    畸形 store 载荷是**用户侧数据问题**（OCR/导入/手改可写出非数组），必须是 4xx。
    框架层 docstring 原文已要求「provider 侧薄转发时按需转译」，Task 17 漏做了这一步。
    golden digest 门禁只覆盖成功路径的三段产物，抓不到失败路径的错误分类漂移 ⇒
    另立判据 `test_store_payload_error_stays_domain_error.py`。
    """
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        RowTableStorePayloadError,
        build_store_projection as _engine_build_store_projection,
    )

    try:
        return _engine_build_store_projection(
            SPEC_D52, payload, contract=contract, limits=limits
        )
    except RowTableStorePayloadError as exc:
        raise StorePayloadError(str(exc)) from exc


def merge_projection_into_store_rows(
    *,
    projection: Any,
    base_rows: list[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], int, int, set[str]]:
    """薄转发框架层 `merge_projection_into_store_rows(SPEC_D52, ...)`（逐字节等价）。

    🔴 幽灵行防护锚点取 `SPEC_D52.ghost_row_anchor_index=1`（`item_name`，不是 `[0]` 的
    `category`）—— D5 首列是枚举类别不是自由文本名称，用它做门槛判不准"用户到底填了没"；
    这条差异化已通过框架层 `ghost_row_anchor_index` 参数表达（与 D6 同款例外）。
    `_set_json_path` 已收敛进框架层 `set_json_path`。
    """
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        merge_projection_into_store_rows as _engine_merge,
    )

    return _engine_merge(SPEC_D52, projection=projection, base_rows=base_rows)


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
    error_code_prefix="sync_phase5_d5",
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
