# -*- coding: utf-8 -*-
"""D4-1「营业收入审定表」—— 同 sheet 双区动态行受管 sheet（adapter `d4.revenue_detail`）。

spec: d4-1-adjudication-bidirectional-writeback-and-formula-io · Task 4
Requirements 1.1 / 2.3 / 1.2 · Property 5（双区几何与 fail-closed）

═══ DEC0：同 sheet 双区动态行（参照 D4-9 多 table 结构）═══

受管 sheet = ``营业收入审定表D4-1``（openpyxl 直读权威模板，Task 1 冻结几何
``evidence/d41-geometry.json`` mapping_digest=
``94e813e067d7160e3e1f51b83922025d7f0fd293cffe7ddd6ac490e7477b2bff``）：

* 主营段（``adjudication_main_rows`` / section ``main-revenue``）：表头 R7，数据 R8-11，
  小计 R12，隐藏 UUID 列 **W**。
* 其他段（``adjudication_other_rows`` / section ``other-revenue``）：表头 R13，数据 R14-17，
  小计 R18，隐藏 UUID 列 **X**（≠ 主营，避免同 sheet 双区身份串区）。
* footer：合计 R19 / TB 核对 R20 / 差异 R21。

两区受管列均为 A/B/C/D/F/G/H（label + 6 金额），store_key 与前端 useD4Adjudication
六金额字段逐项对齐：label / currentUnadjusted / currentAje / currentRje /
priorUnadjusted / priorAje / priorRje。E/I 审定数（=SUM）与小计/合计/差异行（12/18/19/21）
的 B–I 落 :data:`FORMULA_MASK`，普通值投影不覆盖；受管数据行 B/C/D/F/G/H 绝不入 mask。

HTML store = ``checklist_responses`` 单条 item ``D4-1-rows``（前端动态行数组，
每行带 ``rowKey/label/accountCode/sectionKey/source`` + 六金额）；按 ``sectionKey``
分流两区（main-revenue → 主营 table，other-revenue → 其他 table）。

🔴 前置阻塞（DEC1）：同 sheet 双区注入依赖 ``excel_instrumentation._attach_table_part``
合并 ``<tableParts>``（D4-9 design §2.1.1 路径 A）。本模块 provider 独立可导入/可校验；
真正双向注入的 e2e 待该内核修复落地（Task 3 BLOCKED 记录）。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final, Iterator, Mapping, Sequence

# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量（从 Task 1 冻结几何 evidence/d41-geometry.json）
# ═══════════════════════════════════════════════════════════════════════════

#: 与 phase5_d4_revenue_detail 共享的模板身份（同 workbook）。
TEMPLATE_RELATIVE_PATH: Final[str] = "D/D4 收入底稿.xlsx"
TEMPLATE_SHA256: Final[str] = (
    "b8fb92d4c22cd5d639e415403a12cb61650639153f136a5330c930b880167b5f"
)

MANAGED_SHEET_D41: Final[str] = "营业收入审定表D4-1"
TEMPLATE_ID_D41: Final[str] = "D41"
SHEET_KEY_D41: Final[str] = "d41-managed"
STORE_ITEM_ID_D41: Final[str] = "D4-1-rows"
#: 🔴 行身份键必须与前端 `dynamicAdjudicationRows.serializeRows` 落库的键一致。
#: 前端持久化 `D4-1-rows` = `[{rowId, label, source, accountCode}]`（`rowId` 是身份，
#: 内存态 `AdjudicationRow.rowKey` 只是 UI 字段、不落库）。此前误写 `rowKey` →
#: 任何 D4-1-rows 有真载荷的底稿一进「在线编辑」即 store-projection 500（fail-closed
#: 抛「缺稳定行身份 rowKey」），把整个 gt-d4-operating-revenue entry 打挂。改回 `rowId`。
ROW_IDENTITY_STORE_KEY_D41: Final[str] = "rowId"

#: 两级表头（R5 项目/本期/上期；R6 未审/账项/重分类/审定）。
HEADER_ROWS_D41: Final[tuple[int, int]] = (5, 6)

# ── 主营段（section main-revenue） ──────────────────────────────────────────
ROWS_TABLE_KEY_MAIN: Final[str] = "adjudication_main_rows"
SECTION_KEY_MAIN: Final[str] = "main-revenue"
TITLE_ROW_MAIN: Final[int] = 7
FIRST_DATA_ROW_MAIN: Final[int] = 8
LAST_DATA_ROW_MAIN: Final[int] = 11
SUBTOTAL_ROW_MAIN: Final[int] = 12
UUID_COL_MAIN: Final[str] = "W"
TABLE_NAME_MAIN: Final[str] = f"GT_{TEMPLATE_ID_D41}_MAIN_ROWS"
TEMPLATE_ID_MAIN: Final[str] = f"{TEMPLATE_ID_D41}MAIN"

# ── 其他段（section other-revenue） ─────────────────────────────────────────
ROWS_TABLE_KEY_OTHER: Final[str] = "adjudication_other_rows"
SECTION_KEY_OTHER: Final[str] = "other-revenue"
TITLE_ROW_OTHER: Final[int] = 13
FIRST_DATA_ROW_OTHER: Final[int] = 14
LAST_DATA_ROW_OTHER: Final[int] = 17
SUBTOTAL_ROW_OTHER: Final[int] = 18
UUID_COL_OTHER: Final[str] = "X"
TABLE_NAME_OTHER: Final[str] = f"GT_{TEMPLATE_ID_D41}_OTHER_ROWS"
TEMPLATE_ID_OTHER: Final[str] = f"{TEMPLATE_ID_D41}OTHER"

# ── footer（合计 / TB 核对 / 差异） ─────────────────────────────────────────
TOTAL_ROW_D41: Final[int] = 19
TB_ROW_D41: Final[int] = 20
DIFF_ROW_D41: Final[int] = 21
FOOTER_MARKER_D41: Final[str] = "合计"

#: 受管业务最后一列（H 上期重分类）；UUID 列在其右侧。
MANAGED_LAST_COL_D41: Final[str] = "H"

#: TB 核对标量（R20 只读回显，不入受管）。
TB_CHECK_KEYS_D41: Final[tuple[str, ...]] = ("D4-1-adj-tb-6001", "D4-1-adj-tb-6051")

#: Task 1 冻结的 mapping_digest（evidence/d41-geometry.json）。
EXPECTED_MAPPING_DIGEST_D41: Final[str] = (
    "94e813e067d7160e3e1f51b83922025d7f0fd293cffe7ddd6ac490e7477b2bff"
)

# ═══════════════════════════════════════════════════════════════════════════
# 2. 受管字段（label + 6 金额，两区同构）与 formula_mask
# ═══════════════════════════════════════════════════════════════════════════

#: 7 个受管字段：`(column_key, 列标, mode, value_type, store_key, 表头文本)`。
#: 顺序即 Excel 列序；E/I 审定数为 =SUM 内部公式（不进契约，进 formula_mask）。
MANAGED_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    ("label", "A", "editable", "text", "label", "项目"),
    ("current_unadjusted", "B", "editable", "amount", "currentUnadjusted", "本期未审数"),
    ("current_aje", "C", "editable", "amount", "currentAje", "本期账项调整"),
    ("current_rje", "D", "editable", "amount", "currentRje", "本期重分类调整"),
    ("prior_unadjusted", "F", "editable", "amount", "priorUnadjusted", "上期未审数"),
    ("prior_aje", "G", "editable", "amount", "priorAje", "上期账项调整"),
    ("prior_rje", "H", "editable", "amount", "priorRje", "上期重分类调整"),
)

#: 受管列（label + 6 金额）。E/I 审定数与小计/合计/差异行不在此列表。
MANAGED_COLUMNS: Final[tuple[str, ...]] = tuple(spec[1] for spec in MANAGED_FIELD_SPECS)

#: 派生审定数列（E 本期审定 / I 上期审定，=SUM 内部公式）。
_AUDITED_COLUMNS: Final[tuple[str, ...]] = ("E", "I")
#: 小计/合计/差异行（B–I 全为 Excel 内部公式）。
_FORMULA_ROWS: Final[tuple[int, ...]] = (
    SUBTOTAL_ROW_MAIN,   # 12
    SUBTOTAL_ROW_OTHER,  # 18
    TOTAL_ROW_D41,       # 19
    DIFF_ROW_D41,        # 21
)
_FOOTER_FORMULA_COLUMNS: Final[tuple[str, ...]] = (
    "B", "C", "D", "E", "F", "G", "H", "I",
)


def _formula_mask_cells() -> tuple[str, ...]:
    """逐格 formula_mask：E/I 数据行 + 小计/合计/差异行(12/18/19/21) 的 B–I。

    顺序与 evidence/d41-geometry.json `formula_mask.cells` 冻结一致：
    先主营数据行 E/I，再其他数据行 E/I，最后 12/18/19/21 行 B–I。
    """
    cells: list[str] = []
    for row in range(FIRST_DATA_ROW_MAIN, LAST_DATA_ROW_MAIN + 1):  # 8..11
        for col in _AUDITED_COLUMNS:
            cells.append(f"{col}{row}")
    for row in range(FIRST_DATA_ROW_OTHER, LAST_DATA_ROW_OTHER + 1):  # 14..17
        for col in _AUDITED_COLUMNS:
            cells.append(f"{col}{row}")
    for row in _FORMULA_ROWS:  # 12,18,19,21
        for col in _FOOTER_FORMULA_COLUMNS:  # B..I
            cells.append(f"{col}{row}")
    return tuple(cells)


#: 逐格 formula_mask（48 格）—— 与 evidence/d41-geometry.json 冻结一致。
FORMULA_MASK: Final[tuple[str, ...]] = _formula_mask_cells()

# ═══════════════════════════════════════════════════════════════════════════
# 3. mapping_digest（与 Task 1 冻结 evidence/d41-geometry.json 的 digest_payload 同形）
# ═══════════════════════════════════════════════════════════════════════════


def mapping_digest_payload() -> dict[str, Any]:
    """与 evidence/d41-geometry.json `digest_payload` 逐字段同形 —— 锁死映射未漂移。

    🔴 键顺序/取值必须与 Task 1 冻结载荷一致，否则 canonical sha256 漂移。
    """
    return {
        "managed_sheet": MANAGED_SHEET_D41,
        "template_relative_path": f"backend/wp_templates/{TEMPLATE_RELATIVE_PATH}",
        "template_sha256": TEMPLATE_SHA256,
        "header_rows": list(HEADER_ROWS_D41),
        "regions": [
            {
                "table_key": ROWS_TABLE_KEY_MAIN,
                "section_key": SECTION_KEY_MAIN,
                "title_row": TITLE_ROW_MAIN,
                "first_data_row": FIRST_DATA_ROW_MAIN,
                "last_data_row": LAST_DATA_ROW_MAIN,
                "subtotal_row": SUBTOTAL_ROW_MAIN,
                "uuid_col": UUID_COL_MAIN,
            },
            {
                "table_key": ROWS_TABLE_KEY_OTHER,
                "section_key": SECTION_KEY_OTHER,
                "title_row": TITLE_ROW_OTHER,
                "first_data_row": FIRST_DATA_ROW_OTHER,
                "last_data_row": LAST_DATA_ROW_OTHER,
                "subtotal_row": SUBTOTAL_ROW_OTHER,
                "uuid_col": UUID_COL_OTHER,
            },
        ],
        "total_row": TOTAL_ROW_D41,
        "tb_row": TB_ROW_D41,
        "diff_row": DIFF_ROW_D41,
        "contract_fields": [
            {"col": col, "store_key": store_key, "value_type": value_type}
            for _ck, col, _mode, value_type, store_key, _hdr in MANAGED_FIELD_SPECS
        ],
        "formula_mask": list(FORMULA_MASK),
        "tb_check_keys": list(TB_CHECK_KEYS_D41),
    }


def compute_mapping_digest() -> str:
    canon = json.dumps(
        mapping_digest_payload(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


#: 兼容主模块命名习惯（其他 sibling provider 用 `mapping_digest`/`assert_mapping_digest`）。
mapping_digest = compute_mapping_digest


def assert_mapping_digest_d41() -> str:
    got = compute_mapping_digest()
    if got != EXPECTED_MAPPING_DIGEST_D41:
        raise ValueError(
            f"D4-1 mapping_digest 漂移：现算={got} 冻结={EXPECTED_MAPPING_DIGEST_D41} —— "
            "与 evidence/d41-geometry.json 不一致"
        )
    if len(MANAGED_FIELD_SPECS) != 7:
        raise ValueError(
            f"D4-1 契约字段数必须为 7（label + 6 金额），实得 {len(MANAGED_FIELD_SPECS)}"
        )
    if len(FORMULA_MASK) != 48:
        raise ValueError(
            f"D4-1 formula_mask 必须为 48 格，实得 {len(FORMULA_MASK)}"
        )
    if UUID_COL_MAIN == UUID_COL_OTHER:
        raise ValueError(
            f"D4-1 两区 UUID 列必须不同（主营={UUID_COL_MAIN} 其他={UUID_COL_OTHER}）"
        )
    return got

# ═══════════════════════════════════════════════════════════════════════════
# 4. 契约 sheet payload（同 sheet 双区：2 张 row table）
# ═══════════════════════════════════════════════════════════════════════════


def _stable_key_for(table_key: str, column_key: str, row_identity: str = "{row_uuid}") -> str:
    return f"{table_key}/{row_identity}/{column_key}"


def stable_key_for_main(column_key: str, row_identity: str = "{row_uuid}") -> str:
    return _stable_key_for(ROWS_TABLE_KEY_MAIN, column_key, row_identity)


def stable_key_for_other(column_key: str, row_identity: str = "{row_uuid}") -> str:
    return _stable_key_for(ROWS_TABLE_KEY_OTHER, column_key, row_identity)


def _region_formula_mask(first_row: int, last_row: int, subtotal_row: int) -> list[str]:
    """某区受管数据行 E/I（审定数）+ 本区小计行 B–I 的逐格 mask。"""
    cells: list[str] = []
    for row in range(first_row, last_row + 1):
        for col in _AUDITED_COLUMNS:
            cells.append(f"{col}{row}")
    for col in _FOOTER_FORMULA_COLUMNS:
        cells.append(f"{col}{subtotal_row}")
    return cells


#: 合计/差异行（12/18 归各区小计，19/21 归 sheet 级）—— 供 sheet 级 formula_mask 兜底。
_SHEET_LEVEL_FORMULA_ROWS: Final[tuple[int, ...]] = (TOTAL_ROW_D41, DIFF_ROW_D41)


def _sheet_level_formula_mask() -> list[str]:
    cells: list[str] = []
    for row in _SHEET_LEVEL_FORMULA_ROWS:  # 19, 21
        for col in _FOOTER_FORMULA_COLUMNS:  # B..I
            cells.append(f"{col}{row}")
    return cells


def _rows_table_payload(
    *,
    table_key: str,
    section_key: str,
    title_row: int,
    first_data_row: int,
    last_data_row: int,
    subtotal_row: int,
    uuid_col: str,
    excel_name: str = MANAGED_SHEET_D41,
) -> dict[str, Any]:
    """单区契约 ``sheets[].tables[]`` 条目（header_rows=2，动态增删行）。"""

    def _src(cell: str) -> str:
        return f"源xlsx!{excel_name}!{cell}"

    fields: list[dict[str, Any]] = []
    for column_key, column, mode, value_type, store_key, header_text in MANAGED_FIELD_SPECS:
        fields.append(
            {
                "stable_field_key": _stable_key_for(table_key, column_key),
                "json_pointer": f"/rows/{{row_uuid}}/{store_key}",
                "column_key": column_key,
                "cell": {"column": column, "row_from": "row_identity"},
                "mode": mode,
                "value_type": value_type,
                "source_ref": _src(f"{column}{first_data_row}"),
                "header_source_ref": _src(f"{column}{HEADER_ROWS_D41[1]}"),
                "store_item_id": STORE_ITEM_ID_D41,
                "store_key": store_key,
                "header_text": header_text,
                "section_key": section_key,
            }
        )
    return {
        "table_key": table_key,
        "section_key": section_key,
        "anchor": f"A{title_row}",
        "header_rows": 2,
        "row_identity": {
            "kind": "field",
            "json_pointer": f"/rows/*/{ROW_IDENTITY_STORE_KEY_D41}",
        },
        "delete_policy": "tombstone",
        "uuid_col": uuid_col,
        "footer_anchor": {
            "marker": "小计",
            "search_column": "A",
            "carries_total_formula": True,
            "note": (
                f"{section_key} 段小计行 R{subtotal_row}「小计」（B–I 为 =SUM 内部公式）；"
                f"数据区 {first_data_row}..{last_data_row}，隐藏 UUID 列 {uuid_col}。"
                "E/I 审定数(=SUM(B:D)/=SUM(F:H)) 与小计 B–I 入 formula_mask，普通值投影不覆盖。"
            ),
        },
        "formula_mask": _region_formula_mask(first_data_row, last_data_row, subtotal_row),
        "fields": fields,
    }


def rows_table_payload_main(*, excel_name: str = MANAGED_SHEET_D41) -> dict[str, Any]:
    return _rows_table_payload(
        table_key=ROWS_TABLE_KEY_MAIN,
        section_key=SECTION_KEY_MAIN,
        title_row=TITLE_ROW_MAIN,
        first_data_row=FIRST_DATA_ROW_MAIN,
        last_data_row=LAST_DATA_ROW_MAIN,
        subtotal_row=SUBTOTAL_ROW_MAIN,
        uuid_col=UUID_COL_MAIN,
        excel_name=excel_name,
    )


def rows_table_payload_other(*, excel_name: str = MANAGED_SHEET_D41) -> dict[str, Any]:
    return _rows_table_payload(
        table_key=ROWS_TABLE_KEY_OTHER,
        section_key=SECTION_KEY_OTHER,
        title_row=TITLE_ROW_OTHER,
        first_data_row=FIRST_DATA_ROW_OTHER,
        last_data_row=LAST_DATA_ROW_OTHER,
        subtotal_row=SUBTOTAL_ROW_OTHER,
        uuid_col=UUID_COL_OTHER,
        excel_name=excel_name,
    )


def sheet_payload_d41() -> dict[str, Any]:
    """D4-1 契约 sheet：单 sheet 双区（2 张 row table）+ sheet 级 formula_mask。"""
    from app.services.workpaper_sync.excel_extract import TABLE_SHEET_ANCHOR

    return {
        "sheet_key": SHEET_KEY_D41,
        "excel_name": MANAGED_SHEET_D41,
        "locator": {"anchor": TABLE_SHEET_ANCHOR},
        "formula_mask": _sheet_level_formula_mask(),
        "tables": [rows_table_payload_main(), rows_table_payload_other()],
        "tb_check": {
            "keys": list(TB_CHECK_KEYS_D41),
            "tb_row": TB_ROW_D41,
            "note": "R20 试算平衡表数只读回显，不入受管；仅标量走 Tier A 公式。",
        },
    }

# ═══════════════════════════════════════════════════════════════════════════
# 5. instrumentation spec（同 managed_sheet 两 spec，不同行段/UUID 列）
# ═══════════════════════════════════════════════════════════════════════════


def instrumentation_spec_main(*, entry_id: str, template_relative_path: str):
    """主营段（数据 R8-11，UUID 列 W，footer=小计 R12）。"""
    from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec

    return ExcelInstrumentationSpec(
        entry_id=entry_id,
        template_id=TEMPLATE_ID_MAIN,
        template_relative_path=template_relative_path,
        managed_sheet=MANAGED_SHEET_D41,
        first_data_row=FIRST_DATA_ROW_MAIN,
        last_data_row=LAST_DATA_ROW_MAIN,
        footer_row=SUBTOTAL_ROW_MAIN,
        managed_last_col=MANAGED_LAST_COL_D41,
        uuid_col=UUID_COL_MAIN,
        table_name=TABLE_NAME_MAIN,
        sheet_key=SHEET_KEY_D41,
    )


def instrumentation_spec_other(*, entry_id: str, template_relative_path: str):
    """其他段（数据 R14-17，UUID 列 X，footer=小计 R18）。"""
    from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec

    return ExcelInstrumentationSpec(
        entry_id=entry_id,
        template_id=TEMPLATE_ID_OTHER,
        template_relative_path=template_relative_path,
        managed_sheet=MANAGED_SHEET_D41,
        first_data_row=FIRST_DATA_ROW_OTHER,
        last_data_row=LAST_DATA_ROW_OTHER,
        footer_row=SUBTOTAL_ROW_OTHER,
        managed_last_col=MANAGED_LAST_COL_D41,
        uuid_col=UUID_COL_OTHER,
        table_name=TABLE_NAME_OTHER,
        sheet_key=SHEET_KEY_D41,
    )


def instrumentation_spec_d41(*, entry_id: str, template_relative_path: str) -> tuple:
    """D4-1 两区 instrumentation spec（同 managed_sheet，不同行段/UUID 列）。

    🔴 同 sheet 双区注入依赖 `_attach_table_part` 合并 `<tableParts>`（DEC1 前置）。
    """
    return (
        instrumentation_spec_main(
            entry_id=entry_id, template_relative_path=template_relative_path
        ),
        instrumentation_spec_other(
            entry_id=entry_id, template_relative_path=template_relative_path
        ),
    )

# ═══════════════════════════════════════════════════════════════════════════
# 6. HTML store 载荷拆分（按 sectionKey 分流两区）
# ═══════════════════════════════════════════════════════════════════════════

SECTION_KEY_FIELD: Final[str] = "sectionKey"
#: sectionKey → (table_key, stable_key builder)。缺省/未知 → 主营段。
_SECTION_TO_TABLE: Final[dict[str, str]] = {
    SECTION_KEY_MAIN: ROWS_TABLE_KEY_MAIN,
    SECTION_KEY_OTHER: ROWS_TABLE_KEY_OTHER,
}
#: store_key → column_key（6 金额 + label）。
_STORE_KEY_TO_COLUMN_KEY: Final[dict[str, str]] = {
    store_key: column_key
    for column_key, _col, _mode, _vt, store_key, _hdr in MANAGED_FIELD_SPECS
}


#: 科目码 → 段（与前端 `d4AccountScope.isMainRevenueCode/isOtherRevenueCode` 同规则：
#: 6051 前缀 = 其他业务收入段，6001 前缀（及缺省）= 主营段）。前端 `serializeRows`
#: **不落库 sectionKey**（只落 rowId/label/source/accountCode），故 section 归属必须能从
#: accountCode 兜底推导，否则真实底稿两区行会全塌进主营（串区，违反 Property 3）。
def _table_key_for_row(row: Mapping[str, Any]) -> str:
    section_key = str(row.get(SECTION_KEY_FIELD) or "").strip()
    if section_key in _SECTION_TO_TABLE:
        return _SECTION_TO_TABLE[section_key]
    account_code = str(row.get("accountCode") or "").strip()
    if account_code.startswith("6051"):
        return ROWS_TABLE_KEY_OTHER
    return ROWS_TABLE_KEY_MAIN


def _table_key_for_section(section_key: Any) -> str:
    return _SECTION_TO_TABLE.get(str(section_key or "").strip(), ROWS_TABLE_KEY_MAIN)


def _iter_store_rows(
    payload: str | bytes | Sequence[Any],
) -> Iterator[tuple[str, Mapping[str, Any]]]:
    """解析 D4-1-rows JSON 数组 → (rowKey, row)；缺/重身份 fail closed。"""
    if isinstance(payload, (str, bytes, bytearray)):
        text = (
            payload.decode("utf-8")
            if isinstance(payload, (bytes, bytearray))
            else payload
        )
        try:
            rows: Any = json.loads(text or "[]")
        except ValueError as exc:
            raise ValueError(f"{STORE_ITEM_ID_D41} 的载荷不是合法 JSON: {exc}") from exc
    else:
        rows = payload
    if isinstance(rows, Mapping):
        rows = rows.get("rows", [])
    if not isinstance(rows, list):
        raise ValueError(
            f"{STORE_ITEM_ID_D41} 载荷必须是行对象数组，实得 {type(rows).__name__} —— 必须 fail closed"
        )
    seen: set[str] = set()
    for ordinal, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(
                f"{STORE_ITEM_ID_D41} 第 {ordinal} 项不是对象，实得 {type(row).__name__}"
            )
        rid = str(row.get(ROW_IDENTITY_STORE_KEY_D41) or "").strip()
        if not rid:
            raise ValueError(
                f"{STORE_ITEM_ID_D41} 第 {ordinal} 行缺稳定行身份 "
                f"{ROW_IDENTITY_STORE_KEY_D41!r} —— 不得退回数组下标作身份"
            )
        if rid in seen:
            raise ValueError(
                f"{STORE_ITEM_ID_D41} 出现重复行身份 {rid!r}（第 {ordinal} 项）—— 不得静默合并"
            )
        seen.add(rid)
        yield rid, row


def build_store_projection_d41(
    payload: str | bytes | Sequence[Any],
    *,
    contract: Any,
    limits: Any | None = None,
) -> Any:
    """把 D4-1-rows 按 sectionKey 分流投影成两区 FieldValue（main→主营 / other→其他）。"""
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection
    from app.services.workpaper_sync.excel_extract import StreamingProjectionBudget
    from app.services.workpaper_sync.limits import load_limits

    lim = limits or load_limits()
    budget = StreamingProjectionBudget(lim)
    values: dict[str, FieldValue] = {}
    row_keys_main: list[str] = []
    row_keys_other: list[str] = []
    for rid, row in _iter_store_rows(payload):
        table_key = _table_key_for_row(row)
        if table_key == ROWS_TABLE_KEY_MAIN:
            budget.add_row(ROWS_TABLE_KEY_MAIN)
            row_keys_main.append(rid)
        else:
            budget.add_row(ROWS_TABLE_KEY_OTHER)
            row_keys_other.append(rid)
        for column_key, _col, _mode, _vt, store_key, _hdr in MANAGED_FIELD_SPECS:
            spec = contract.field_by_stable_key(
                _stable_key_for(table_key, column_key)
            )
            stable_key = _stable_key_for(table_key, column_key, rid)
            budget.add_field()
            values[stable_key] = FieldValue(
                stable_key=stable_key,
                value=row.get(store_key),
                value_type=spec.value_type,
                mode=spec.mode,
                row_key=rid,
            )
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys={
            ROWS_TABLE_KEY_MAIN: tuple(row_keys_main),
            ROWS_TABLE_KEY_OTHER: tuple(row_keys_other),
        },
    )

def merge_projection_into_d41_rows(
    *,
    projection: Any,
    base_rows: list[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], int, int, set[str]]:
    """把两区 extract projection 合回 D4-1-rows；按 table_key 回填 sectionKey，两区不串。

    返回 (merged_rows, applied, visited, touched_rows)。受管字段仅 label + 6 金额；
    formula_mask 覆盖的 E/I/小计/合计/差异不在投影里（is_protected 或不产键），故不回写。
    """
    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in base_rows:
        rid = str(row.get(ROW_IDENTITY_STORE_KEY_D41) or "").strip()
        if not rid:
            continue
        by_id[rid] = dict(row)
        order.append(rid)

    table_to_section = {
        ROWS_TABLE_KEY_MAIN: SECTION_KEY_MAIN,
        ROWS_TABLE_KEY_OTHER: SECTION_KEY_OTHER,
    }
    prefixes = {
        ROWS_TABLE_KEY_MAIN: f"{ROWS_TABLE_KEY_MAIN}/",
        ROWS_TABLE_KEY_OTHER: f"{ROWS_TABLE_KEY_OTHER}/",
    }

    applied = 0
    visited = 0
    touched_rows: set[str] = set()
    for key in projection.stable_keys():
        sk = str(key)
        table_key = None
        for tk, prefix in prefixes.items():
            if sk.startswith(prefix):
                table_key = tk
                break
        if table_key is None:
            continue
        fv = projection.get(key)
        if fv is None or getattr(fv, "is_protected", False):
            continue
        rid = getattr(fv, "row_key", None)
        if not rid:
            continue
        rid = str(rid)
        target = by_id.get(rid)
        if target is None:
            target = {
                ROW_IDENTITY_STORE_KEY_D41: rid,
                "label": "",
                SECTION_KEY_FIELD: table_to_section[table_key],
            }
            by_id[rid] = target
            order.append(rid)
        # 回填/校准 sectionKey（extract 权威区归属，两区不串）。
        target[SECTION_KEY_FIELD] = table_to_section[table_key]
        column_key = sk.rsplit("/", 1)[-1]
        # column_key 即 MANAGED_FIELD_SPECS 的 column_key；映射到 store_key。
        store_key = _column_key_to_store_key(column_key)
        if store_key is None:
            continue
        visited += 1
        new_val = getattr(fv, "value", None)
        if target.get(store_key) != new_val:
            target[store_key] = new_val
            applied += 1
            touched_rows.add(rid)

    return [by_id[rid] for rid in order], applied, visited, touched_rows


_COLUMN_KEY_TO_STORE_KEY: Final[dict[str, str]] = {
    column_key: store_key
    for column_key, _col, _mode, _vt, store_key, _hdr in MANAGED_FIELD_SPECS
}


def _column_key_to_store_key(column_key: str) -> str | None:
    return _COLUMN_KEY_TO_STORE_KEY.get(column_key)
