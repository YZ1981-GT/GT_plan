# -*- coding: utf-8 -*-
"""D4-9「重要客户结构分析」—— gt-d4-operating-revenue 的 sibling sheet（adapter `d4.revenue_detail`）。

spec: d4-9-customer-structure-bidirectional-writeback · Task 3/4/5/7

═══ 架构裁决（路 B）═══

D4-9 与 D4-1/2/3/5/15/16/21~29/35 同架构：**不建独立 entry**，作为
``xlsx/gt-d4-operating-revenue`` 的 sibling sheet 并入 ``phase5_d4_revenue_detail``
（overlay 规则：``d4/**`` 下 mount 归父 entry，不独立计数；D4-1 先例）。本模块只提供
sibling provider 接口（契约 sheet payload / instrumentation spec / store 投影合并），由
父模块在 ``build_contract_payload`` / ``instrumentation_specs`` / ``build_combined_store_projection``
里编排。sheet_key=``d49-managed``，共享 adapter ``d4.revenue_detail``。

═══ 结构：单 sheet 三 table ═══

受管 sheet = ``重要客户结构分析D4-9``（openpyxl 直读权威模板 ``D/D4 收入底稿.xlsx``，
sha256=``b8fb92d4c22cd5d639e415403a12cb61650639153f136a5330c930b880167b5f``）：

* **本期段**（``customer_current_rows``）：表头 R12，数据 R13-22（10 行），合计 R23，
  本期销售总额 R24（C24 金额 / E24 数量）；隐藏 UUID 列 **W**。
* **上期段**（``customer_prior_rows``）：表头 R26，数据 R27-36（10 行），合计 R37，
  上期销售总额 R38（C38 金额 / E38 数量）；隐藏 UUID 列 **X**（≠ 本期）。
* **表级标量**（``customer_totals``）：4 个固定单元格 C24/E24/C38/E38，无 row_identity /
  无 delete_policy，字段 row_scoped=False 用 ``cell.row_from = 静态行号``。

列：A 序号（模板自增，不入契约）/ B 客户名称 / C 销售金额 / D 销售金额占比(公式) /
E 销售数量 / F 销售数量占比(公式) / G 上期排名。

占比公式（本期）D13=IF(C13=0,0,C13/$C$24)，F13=IF(E13=0,0,E13/$E$24)；合计行
C23=SUM(C13:C22)、E23=SUM(E13:E22)。上期同构引用 $C$38/$E$38，合计引 C27:C36。
D/F 占比列 + 合计行入 formula_mask，普通值投影不覆盖。

HTML store = ``checklist_responses`` 单条 item ``D4-9-data``（前端
D4TabCustomerStructure.vue），remark 存嵌套结构 ``{current:{rows,totalAmount,
totalQuantity}, prior:{...}}``；投影按三 table 分流。

Requirements: 1.1/1.4 · 2.1~2.6 · 3.1/3.3/3.4 · 4.1/4.2
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final, Iterator, Mapping, Sequence

from app.services.workpaper_sync.contracts import FieldSpec, SyncContract


class StorePayloadError(ValueError):
    """HTML store 载荷形态不合法（非对象、缺 row identity、重复 identity）。"""


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量（openpyxl 实测 + requirements.md 冻结事实）
# ═══════════════════════════════════════════════════════════════════════════

#: 与父模块共享的模板身份（同 workbook）。
TEMPLATE_RELATIVE_PATH: Final[str] = "D/D4 收入底稿.xlsx"
TEMPLATE_SHA256: Final[str] = (
    "b8fb92d4c22cd5d639e415403a12cb61650639153f136a5330c930b880167b5f"
)

MANAGED_SHEET_D49: Final[str] = "重要客户结构分析D4-9"
TEMPLATE_ID_D49: Final[str] = "D49"
SHEET_KEY_D49: Final[str] = "d49-managed"
STORE_ITEM_ID_D49: Final[str] = "D4-9-data"
ROW_IDENTITY_STORE_KEY_D49: Final[str] = "rowId"

#: 单级表头。
HEADER_ROW_CURRENT: Final[int] = 12
HEADER_ROW_PRIOR: Final[int] = 26

# ── 本期段（customer_current_rows） ────────────────────────────────────────
ROWS_TABLE_KEY_CURRENT: Final[str] = "customer_current_rows"
FIRST_DATA_ROW_CURRENT: Final[int] = 13
LAST_DATA_ROW_CURRENT: Final[int] = 22
FOOTER_ROW_CURRENT: Final[int] = 23
TOTAL_ROW_CURRENT: Final[int] = 24
UUID_COL_CURRENT: Final[str] = "W"
TABLE_NAME_CURRENT: Final[str] = f"GT_{TEMPLATE_ID_D49}C_ROWS"
TEMPLATE_ID_CURRENT: Final[str] = f"{TEMPLATE_ID_D49}C"

# ── 上期段（customer_prior_rows） ──────────────────────────────────────────
ROWS_TABLE_KEY_PRIOR: Final[str] = "customer_prior_rows"
FIRST_DATA_ROW_PRIOR: Final[int] = 27
LAST_DATA_ROW_PRIOR: Final[int] = 36
FOOTER_ROW_PRIOR: Final[int] = 37
TOTAL_ROW_PRIOR: Final[int] = 38
UUID_COL_PRIOR: Final[str] = "X"
TABLE_NAME_PRIOR: Final[str] = f"GT_{TEMPLATE_ID_D49}P_ROWS"
TEMPLATE_ID_PRIOR: Final[str] = f"{TEMPLATE_ID_D49}P"

# ── 表级标量（customer_totals） ────────────────────────────────────────────
TOTALS_TABLE_KEY: Final[str] = "customer_totals"

#: 受管业务最后一列（G 上期排名）；UUID 列在其右侧。
MANAGED_LAST_COL_D49: Final[str] = "G"
FOOTER_MARKER_D49: Final[str] = "合计"

#: Task 3 冻结的 mapping_digest（openpyxl 实测几何，compute_mapping_digest 现算）。
EXPECTED_MAPPING_DIGEST_D49: Final[str] = (
    "3a803643bc64a945c1867d4a0a5324f5347ec4a78723bded8bb3a6740f0b04d1"
)

# ═══════════════════════════════════════════════════════════════════════════
# 2. 受管字段（本期/上期动态行同构 6 列；totals 4 静态标量）
# ═══════════════════════════════════════════════════════════════════════════

#: 动态行 6 个受管字段：`(column_key, 列标, mode, value_type, store_key, 表头文本)`。
#: A 序号（模板自增）不入契约；D/F 占比为 formula（进 formula_mask）。
MANAGED_ROW_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    ("customer_name", "B", "editable", "text", "name", "客户名称"),
    ("sales_amount", "C", "editable", "amount", "amount", "销售金额"),
    ("amount_ratio", "D", "formula", "ratio", "amountRatio", "销售金额占比"),
    ("sales_quantity", "E", "editable", "amount", "quantity", "销售数量"),
    ("quantity_ratio", "F", "formula", "ratio", "quantityRatio", "销售数量占比"),
    ("prior_rank", "G", "editable", "text", "priorRank", "上期排名"),
)

#: totals 4 个表级标量：`(column_key, 列标, 静态行号, value_type, json_pointer, 表头文本)`。
MANAGED_TOTALS_FIELD_SPECS: Final[
    tuple[tuple[str, str, int, str, str, str], ...]
] = (
    ("current_total_amount", "C", TOTAL_ROW_CURRENT, "amount", "/current/totalAmount", "本期销售总额"),
    ("current_total_quantity", "E", TOTAL_ROW_CURRENT, "amount", "/current/totalQuantity", "本期销售总量"),
    ("prior_total_amount", "C", TOTAL_ROW_PRIOR, "amount", "/prior/totalAmount", "上期销售总额"),
    ("prior_total_quantity", "E", TOTAL_ROW_PRIOR, "amount", "/prior/totalQuantity", "上期销售总量"),
)


def _region_formula_mask(first_row: int, last_row: int, footer_row: int) -> list[str]:
    """某区 D/F 占比列（数据行 + 合计行）逐区间 mask。"""
    return [
        f"D{first_row}:D{last_row}",
        f"F{first_row}:F{last_row}",
        f"C{footer_row}:F{footer_row}",
    ]


FORMULA_MASK_CURRENT: Final[tuple[str, ...]] = tuple(
    _region_formula_mask(FIRST_DATA_ROW_CURRENT, LAST_DATA_ROW_CURRENT, FOOTER_ROW_CURRENT)
)
FORMULA_MASK_PRIOR: Final[tuple[str, ...]] = tuple(
    _region_formula_mask(FIRST_DATA_ROW_PRIOR, LAST_DATA_ROW_PRIOR, FOOTER_ROW_PRIOR)
)

# ═══════════════════════════════════════════════════════════════════════════
# 3. mapping_digest（冻结列↔单元格映射；字段数校验 current 6 + prior 6 + totals 4）
# ═══════════════════════════════════════════════════════════════════════════


def mapping_digest_payload() -> dict[str, Any]:
    """冻结映射的 canonical 载荷 —— 锁死列↔单元格映射未漂移。"""
    return {
        "managed_sheet": MANAGED_SHEET_D49,
        "template_relative_path": f"backend/wp_templates/{TEMPLATE_RELATIVE_PATH}",
        "template_sha256": TEMPLATE_SHA256,
        "regions": [
            {
                "table_key": ROWS_TABLE_KEY_CURRENT,
                "header_row": HEADER_ROW_CURRENT,
                "first_data_row": FIRST_DATA_ROW_CURRENT,
                "last_data_row": LAST_DATA_ROW_CURRENT,
                "footer_row": FOOTER_ROW_CURRENT,
                "total_row": TOTAL_ROW_CURRENT,
                "uuid_col": UUID_COL_CURRENT,
            },
            {
                "table_key": ROWS_TABLE_KEY_PRIOR,
                "header_row": HEADER_ROW_PRIOR,
                "first_data_row": FIRST_DATA_ROW_PRIOR,
                "last_data_row": LAST_DATA_ROW_PRIOR,
                "footer_row": FOOTER_ROW_PRIOR,
                "total_row": TOTAL_ROW_PRIOR,
                "uuid_col": UUID_COL_PRIOR,
            },
        ],
        "row_fields": [
            {"col": col, "column_key": ck, "store_key": store_key, "value_type": vt, "mode": mode}
            for ck, col, mode, vt, store_key, _hdr in MANAGED_ROW_FIELD_SPECS
        ],
        "totals_fields": [
            {"col": col, "column_key": ck, "static_row": row, "json_pointer": ptr, "value_type": vt}
            for ck, col, row, vt, ptr, _hdr in MANAGED_TOTALS_FIELD_SPECS
        ],
        "footer_marker_exact": FOOTER_MARKER_D49,
        "formula_mask_current": list(FORMULA_MASK_CURRENT),
        "formula_mask_prior": list(FORMULA_MASK_PRIOR),
    }


def compute_mapping_digest() -> str:
    canon = json.dumps(
        mapping_digest_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


mapping_digest = compute_mapping_digest


def assert_mapping_digest_d49() -> str:
    got = compute_mapping_digest()
    if got != EXPECTED_MAPPING_DIGEST_D49:
        raise ValueError(
            f"D4-9 mapping_digest 漂移：现算={got} 冻结={EXPECTED_MAPPING_DIGEST_D49} —— "
            "与 openpyxl 实测几何不一致"
        )
    if len(MANAGED_ROW_FIELD_SPECS) != 6:
        raise ValueError(f"D4-9 动态行契约字段数必须为 6，实得 {len(MANAGED_ROW_FIELD_SPECS)}")
    if len(MANAGED_TOTALS_FIELD_SPECS) != 4:
        raise ValueError(f"D4-9 totals 契约字段数必须为 4，实得 {len(MANAGED_TOTALS_FIELD_SPECS)}")
    if UUID_COL_CURRENT == UUID_COL_PRIOR:
        raise ValueError(
            f"D4-9 两区 UUID 列必须不同（本期={UUID_COL_CURRENT} 上期={UUID_COL_PRIOR}）"
        )
    return got

# ═══════════════════════════════════════════════════════════════════════════
# 4. 契约 sheet payload（单 sheet 三 table：current / prior 动态行 + totals 静态标量）
# ═══════════════════════════════════════════════════════════════════════════


def _stable_key_for(table_key: str, column_key: str, row_identity: str = "{row_uuid}") -> str:
    return f"{table_key}/{row_identity}/{column_key}"


def stable_key_for_current(column_key: str, row_identity: str = "{row_uuid}") -> str:
    return _stable_key_for(ROWS_TABLE_KEY_CURRENT, column_key, row_identity)


def stable_key_for_prior(column_key: str, row_identity: str = "{row_uuid}") -> str:
    return _stable_key_for(ROWS_TABLE_KEY_PRIOR, column_key, row_identity)


def stable_key_for_total(column_key: str) -> str:
    return f"{TOTALS_TABLE_KEY}/{column_key}"


def _rows_table_payload(
    *,
    table_key: str,
    header_row: int,
    first_data_row: int,
    last_data_row: int,
    footer_row: int,
    uuid_col: str,
    formula_mask: tuple[str, ...],
    excel_name: str,
) -> dict[str, Any]:
    """单区动态行契约 table（header_rows=1，动态增删行）。"""

    def _src(cell: str) -> str:
        return f"源xlsx!{excel_name}!{cell}"

    fields: list[dict[str, Any]] = []
    for column_key, column, mode, value_type, store_key, header_text in MANAGED_ROW_FIELD_SPECS:
        fields.append(
            {
                "stable_field_key": _stable_key_for(table_key, column_key),
                "json_pointer": f"/rows/{{row_uuid}}/{store_key}",
                "column_key": column_key,
                "cell": {"column": column, "row_from": "row_identity"},
                "mode": mode,
                "value_type": value_type,
                "source_ref": _src(f"{column}{first_data_row}"),
                "header_source_ref": _src(f"{column}{header_row}"),
                "store_item_id": STORE_ITEM_ID_D49,
                "store_key": store_key,
                "header_text": header_text,
            }
        )
    return {
        "table_key": table_key,
        "anchor": f"A{header_row}",
        "header_rows": 1,
        "row_identity": {
            "kind": "field",
            "json_pointer": f"/rows/*/{ROW_IDENTITY_STORE_KEY_D49}",
        },
        "delete_policy": "tombstone",
        "uuid_col": uuid_col,
        "footer_anchor": {
            "marker": FOOTER_MARKER_D49,
            "search_column": "A",
            "carries_total_formula": True,
            "note": (
                f"合计行 R{footer_row}「合计」（C/E =SUM、D/F =IF 占比内部公式）；"
                f"数据区 {first_data_row}..{last_data_row}，隐藏 UUID 列 {uuid_col}。"
                "D/F 占比列 + 合计行入 formula_mask，普通值投影不覆盖。"
            ),
        },
        "formula_mask": list(formula_mask),
        "fields": fields,
    }


def rows_table_payload_current(*, excel_name: str = MANAGED_SHEET_D49) -> dict[str, Any]:
    return _rows_table_payload(
        table_key=ROWS_TABLE_KEY_CURRENT,
        header_row=HEADER_ROW_CURRENT,
        first_data_row=FIRST_DATA_ROW_CURRENT,
        last_data_row=LAST_DATA_ROW_CURRENT,
        footer_row=FOOTER_ROW_CURRENT,
        uuid_col=UUID_COL_CURRENT,
        formula_mask=FORMULA_MASK_CURRENT,
        excel_name=excel_name,
    )


def rows_table_payload_prior(*, excel_name: str = MANAGED_SHEET_D49) -> dict[str, Any]:
    return _rows_table_payload(
        table_key=ROWS_TABLE_KEY_PRIOR,
        header_row=HEADER_ROW_PRIOR,
        first_data_row=FIRST_DATA_ROW_PRIOR,
        last_data_row=LAST_DATA_ROW_PRIOR,
        footer_row=FOOTER_ROW_PRIOR,
        uuid_col=UUID_COL_PRIOR,
        formula_mask=FORMULA_MASK_PRIOR,
        excel_name=excel_name,
    )


def totals_table_payload(*, excel_name: str = MANAGED_SHEET_D49) -> dict[str, Any]:
    """表级标量 table：4 个静态字段（C24/E24/C38/E38），无 row_identity / 无 delete_policy。"""

    def _src(cell: str) -> str:
        return f"源xlsx!{excel_name}!{cell}"

    fields: list[dict[str, Any]] = []
    for column_key, column, static_row, value_type, json_pointer, header_text in MANAGED_TOTALS_FIELD_SPECS:
        fields.append(
            {
                "stable_field_key": stable_key_for_total(column_key),
                "json_pointer": json_pointer,
                "column_key": column_key,
                "cell": {"column": column, "row_from": static_row},
                "mode": "editable",
                "value_type": value_type,
                "source_ref": _src(f"{column}{static_row}"),
                "store_item_id": STORE_ITEM_ID_D49,
                "header_text": header_text,
            }
        )
    return {
        "table_key": TOTALS_TABLE_KEY,
        "anchor": f"A{TOTAL_ROW_CURRENT}",
        "header_rows": 1,
        "fields": fields,
    }


def sheet_payload_d49() -> dict[str, Any]:
    """D4-9 契约 sheet：单 sheet 三 table（current / prior 动态行 + totals 静态标量）。"""
    from app.services.workpaper_sync.excel_extract import TABLE_SHEET_ANCHOR

    return {
        "sheet_key": SHEET_KEY_D49,
        "excel_name": MANAGED_SHEET_D49,
        "locator": {"anchor": TABLE_SHEET_ANCHOR},
        "tables": [
            rows_table_payload_current(),
            rows_table_payload_prior(),
            totals_table_payload(),
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════
# 5. instrumentation spec（同 managed_sheet 两 spec，不同行段/UUID 列；totals 无 spec）
# ═══════════════════════════════════════════════════════════════════════════


def instrumentation_spec_current(*, entry_id: str, template_relative_path: str):
    """本期段（数据 R13-22，UUID 列 W，footer=合计 R23）。"""
    from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec

    return ExcelInstrumentationSpec(
        entry_id=entry_id,
        template_id=TEMPLATE_ID_CURRENT,
        template_relative_path=template_relative_path,
        managed_sheet=MANAGED_SHEET_D49,
        first_data_row=FIRST_DATA_ROW_CURRENT,
        last_data_row=LAST_DATA_ROW_CURRENT,
        footer_row=FOOTER_ROW_CURRENT,
        managed_last_col=MANAGED_LAST_COL_D49,
        uuid_col=UUID_COL_CURRENT,
        table_name=TABLE_NAME_CURRENT,
        sheet_key=SHEET_KEY_D49,
    )


def instrumentation_spec_prior(*, entry_id: str, template_relative_path: str):
    """上期段（数据 R27-36，UUID 列 X，footer=合计 R37）。"""
    from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec

    return ExcelInstrumentationSpec(
        entry_id=entry_id,
        template_id=TEMPLATE_ID_PRIOR,
        template_relative_path=template_relative_path,
        managed_sheet=MANAGED_SHEET_D49,
        first_data_row=FIRST_DATA_ROW_PRIOR,
        last_data_row=LAST_DATA_ROW_PRIOR,
        footer_row=FOOTER_ROW_PRIOR,
        managed_last_col=MANAGED_LAST_COL_D49,
        uuid_col=UUID_COL_PRIOR,
        table_name=TABLE_NAME_PRIOR,
        sheet_key=SHEET_KEY_D49,
    )


def instrumentation_spec_d49(*, entry_id: str, template_relative_path: str) -> tuple:
    """D4-9 两区 instrumentation spec（同 managed_sheet，不同行段/UUID 列 W/X）。

    🔴 同 sheet 双区注入依赖 `_attach_table_part` 合并 `<tableParts>`（Task 1 已落地）。
    totals 无 instrumented table（静态 cell 走固定坐标，不需 row identity 载体）。
    """
    return (
        instrumentation_spec_current(
            entry_id=entry_id, template_relative_path=template_relative_path
        ),
        instrumentation_spec_prior(
            entry_id=entry_id, template_relative_path=template_relative_path
        ),
    )

# ═══════════════════════════════════════════════════════════════════════════
# 6. HTML store 载荷投影/合并/身份（三 table 分流；fail-closed）
# ═══════════════════════════════════════════════════════════════════════════

_COLUMN_KEY_TO_STORE_KEY: Final[dict[str, str]] = {
    column_key: store_key
    for column_key, _col, _mode, _vt, store_key, _hdr in MANAGED_ROW_FIELD_SPECS
}
#: totals column_key → (区名, store 叶字段)。
_TOTALS_STORE_LEAF: Final[dict[str, tuple[str, str]]] = {
    "current_total_amount": ("current", "totalAmount"),
    "current_total_quantity": ("current", "totalQuantity"),
    "prior_total_amount": ("prior", "totalAmount"),
    "prior_total_quantity": ("prior", "totalQuantity"),
}


def _parse_store_payload(payload: str | bytes | Mapping[str, Any]) -> Mapping[str, Any]:
    """解析 D4-9-data remark → dict；非法 JSON / 非对象 fail closed。"""
    if isinstance(payload, Mapping):
        return payload
    if isinstance(payload, (bytes, bytearray)):
        text = payload.decode("utf-8")
    elif isinstance(payload, str):
        text = payload
    else:
        raise StorePayloadError(
            f"{STORE_ITEM_ID_D49} 载荷类型非法 {type(payload).__name__} —— 必须 fail closed"
        )
    try:
        data = json.loads(text or "{}")
    except ValueError as exc:
        raise StorePayloadError(f"{STORE_ITEM_ID_D49} 的 remark 不是合法 JSON: {exc}") from exc
    if isinstance(data, Mapping):
        return data
    # 🔴 legacy 容差（2026-09-20）：真实项目（如首汽租车）存在**旧形态** D4-9-data —
    # bare list（早于 {current, prior} 双区模型写入）。此形态**没有** current/prior 分区、
    # 也没有当前的 rowId 身份方案。若在此 fail-closed 抛 StorePayloadError，会连累整个共享
    # entry `gt-d4-operating-revenue` 的 materialize/rematerialize 事务回滚（把 D4-1/2/3/6/
    # 15/16/25~32 等 20+ 张一起打挂，重演 D4-15/16 事故）。合并到共享 entry 的设计下，单张
    # sheet 的 legacy 载荷不得成为全 entry 的发布阻断。
    # 处理：bare list（或其它非对象）视为**空 legacy 载荷** → 返回空 {current, prior}
    #   （D4-9 该 sheet 投影为空、materialize 干净，不写 orphan 行）。用户下次在前端编辑
    #   D4-9 时，`persistData()` 会以正确的 {current, prior} dict 覆盖，自然迁移。
    # 注意：这**不**削弱对「dict 但内部 region/rows 畸形」的 fail-closed —— 那仍由
    #   _iter_region_rows / _build_region_projection_values 严格校验。只放行「整体不是 dict」
    #   这一种明确的 legacy 兼容路径。
    if isinstance(data, list):
        return {}
    raise StorePayloadError(
        f"{STORE_ITEM_ID_D49} 载荷必须是对象 {{current, prior}} 或 legacy 数组，实得 {type(data).__name__}"
    )


def _iter_region_rows(
    region: Any, *, region_name: str
) -> Iterator[tuple[str, Mapping[str, Any]]]:
    """解析某区 rows 数组 → (rowId, row)；缺/重身份 fail closed（区内 seen 独立）。"""
    if region is None:
        return
    if not isinstance(region, Mapping):
        raise StorePayloadError(
            f"{STORE_ITEM_ID_D49}.{region_name} 必须是对象，实得 {type(region).__name__}"
        )
    rows = region.get("rows")
    if rows is None:
        return
    if not isinstance(rows, list):
        raise StorePayloadError(
            f"{STORE_ITEM_ID_D49}.{region_name}.rows 必须是行对象数组，实得 {type(rows).__name__}"
            " —— 必须 fail closed"
        )
    seen: set[str] = set()
    for ordinal, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise StorePayloadError(
                f"{STORE_ITEM_ID_D49}.{region_name}.rows 第 {ordinal} 项不是对象，"
                f"实得 {type(row).__name__}"
            )
        rid = row.get(ROW_IDENTITY_STORE_KEY_D49)
        if not isinstance(rid, str) or not rid.strip():
            raise StorePayloadError(
                f"{STORE_ITEM_ID_D49}.{region_name}.rows 第 {ordinal} 行缺稳定行身份 "
                f"{ROW_IDENTITY_STORE_KEY_D49!r}（实得 {rid!r}）—— 不得退回数组下标作身份"
            )
        rid = rid.strip()
        if rid in seen:
            raise StorePayloadError(
                f"{STORE_ITEM_ID_D49}.{region_name}.rows 出现重复行身份 {rid!r}（第 {ordinal} 项）"
                " —— 不得静默合并"
            )
        seen.add(rid)
        yield rid, row


def iter_store_rows(
    payload: str | bytes | Mapping[str, Any],
) -> Iterator[tuple[str, str, Mapping[str, Any]]]:
    """遍历 current + prior 两区 → (table_key, rowId, row)。两区 seen 独立，区内唯一。"""
    data = _parse_store_payload(payload)
    for rid, row in _iter_region_rows(data.get("current"), region_name="current"):
        yield ROWS_TABLE_KEY_CURRENT, rid, row
    for rid, row in _iter_region_rows(data.get("prior"), region_name="prior"):
        yield ROWS_TABLE_KEY_PRIOR, rid, row


def _build_region_projection_values(
    data: Mapping[str, Any],
    *,
    region_name: str,
    table_key: str,
    contract: SyncContract,
    budget: Any,
) -> tuple[dict[str, Any], list[str]]:
    from app.services.workpaper_sync.adapters.base import FieldValue

    values: dict[str, FieldValue] = {}
    row_keys: list[str] = []
    for rid, row in _iter_region_rows(data.get(region_name), region_name=region_name):
        budget.add_row(table_key)
        row_keys.append(rid)
        for column_key, _col, _mode, _vt, store_key, _hdr in MANAGED_ROW_FIELD_SPECS:
            spec = contract.field_by_stable_key(_stable_key_for(table_key, column_key))
            stable_key = _stable_key_for(table_key, column_key, rid)
            budget.add_field()
            values[stable_key] = FieldValue(
                stable_key=stable_key,
                value=row.get(store_key),
                value_type=spec.value_type,
                mode=spec.mode,
                row_key=rid,
            )
    return values, row_keys


def build_d49_current_projection(
    payload: str | bytes | Mapping[str, Any],
    *,
    contract: SyncContract,
    limits: Any | None = None,
) -> Any:
    """本期段（customer_current_rows）投影。"""
    from app.services.workpaper_sync.adapters.base import Projection
    from app.services.workpaper_sync.excel_extract import StreamingProjectionBudget
    from app.services.workpaper_sync.limits import load_limits

    lim = limits or load_limits()
    budget = StreamingProjectionBudget(lim)
    data = _parse_store_payload(payload)
    values, row_keys = _build_region_projection_values(
        data, region_name="current", table_key=ROWS_TABLE_KEY_CURRENT,
        contract=contract, budget=budget,
    )
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys={ROWS_TABLE_KEY_CURRENT: tuple(row_keys)},
    )


def build_d49_prior_projection(
    payload: str | bytes | Mapping[str, Any],
    *,
    contract: SyncContract,
    limits: Any | None = None,
) -> Any:
    """上期段（customer_prior_rows）投影。"""
    from app.services.workpaper_sync.adapters.base import Projection
    from app.services.workpaper_sync.excel_extract import StreamingProjectionBudget
    from app.services.workpaper_sync.limits import load_limits

    lim = limits or load_limits()
    budget = StreamingProjectionBudget(lim)
    data = _parse_store_payload(payload)
    values, row_keys = _build_region_projection_values(
        data, region_name="prior", table_key=ROWS_TABLE_KEY_PRIOR,
        contract=contract, budget=budget,
    )
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys={ROWS_TABLE_KEY_PRIOR: tuple(row_keys)},
    )


def build_d49_totals_projection(
    payload: str | bytes | Mapping[str, Any],
    *,
    contract: SyncContract,
    limits: Any | None = None,
) -> Any:
    """表级标量（customer_totals）投影：4 个静态字段 row_key=None。"""
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection

    data = _parse_store_payload(payload)
    values: dict[str, FieldValue] = {}
    for column_key, _col, _static_row, _vt, _ptr, _hdr in MANAGED_TOTALS_FIELD_SPECS:
        spec = contract.field_by_stable_key(stable_key_for_total(column_key))
        region_name, leaf = _TOTALS_STORE_LEAF[column_key]
        region = data.get(region_name)
        value: Any = None
        if isinstance(region, Mapping):
            value = region.get(leaf)
        # amount 型 totals：缺失(None，含 legacy 空载荷 / 缺 region)归一为 0，与 materialize
        # 后空金额单元格反读值(0)一致 —— 否则 提交 None → 反读 0 触发 RoundtripEquivalenceError
        # (Property 65)。前端 _normalize 也是 setdefault(totalAmount/Quantity, 0)，口径一致。
        if value is None and spec.value_type == "amount":
            value = 0
        values[stable_key_for_total(column_key)] = FieldValue(
            stable_key=stable_key_for_total(column_key),
            value=value,
            value_type=spec.value_type,
            mode=spec.mode,
            row_key=None,
        )
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys={TOTALS_TABLE_KEY: ()},
    )


def build_d49_store_projection(
    payload: str | bytes | Mapping[str, Any],
    *,
    contract: SyncContract,
    limits: Any | None = None,
) -> Any:
    """D4-9 单 store item 的**完整**投影（current + prior + totals 合并）。"""
    from app.services.workpaper_sync.adapters.base import Projection

    cur = build_d49_current_projection(payload, contract=contract, limits=limits)
    pri = build_d49_prior_projection(payload, contract=contract, limits=limits)
    tot = build_d49_totals_projection(payload, contract=contract, limits=limits)
    values = dict(cur.values)
    values.update(pri.values)
    values.update(tot.values)
    row_keys = {**dict(cur.row_keys), **dict(pri.row_keys), **dict(tot.row_keys)}
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys=row_keys,
    )


def merge_projection_into_d49_store(
    *,
    projection: Any,
    base_state: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], int, int, set[str]]:
    """把 extract projection 合回 D4-9-data 的 {current,prior}+totals 嵌套结构。

    按 table_key 前缀分流：customer_current_rows/* → current.rows，
    customer_prior_rows/* → prior.rows，customer_totals/* → 静态标量。
    两区 rowId 各自唯一不串区（Requirement 3.4 / 4.2）。formula_mask 覆盖的 D/F 占比
    与合计不在投影里（is_protected 或不产键），故不回写（Requirement 4.1）。

    返回 (merged_dict, applied, visited, touched_rows)。
    """
    base = dict(base_state) if isinstance(base_state, Mapping) else {}

    def _region_base(name: str) -> dict[str, Any]:
        region = base.get(name)
        out = dict(region) if isinstance(region, Mapping) else {}
        rows = out.get("rows")
        out["rows"] = list(rows) if isinstance(rows, list) else []
        out.setdefault("totalAmount", 0)
        out.setdefault("totalQuantity", 0)
        return out

    regions: dict[str, dict[str, Any]] = {
        "current": _region_base("current"),
        "prior": _region_base("prior"),
    }
    by_id: dict[str, dict[str, dict[str, Any]]] = {"current": {}, "prior": {}}
    order: dict[str, list[str]] = {"current": [], "prior": []}
    table_to_region = {
        ROWS_TABLE_KEY_CURRENT: "current",
        ROWS_TABLE_KEY_PRIOR: "prior",
    }
    for region_name, region in regions.items():
        for row in region["rows"]:
            if not isinstance(row, Mapping):
                continue
            rid = str(row.get(ROW_IDENTITY_STORE_KEY_D49) or "").strip()
            if not rid:
                continue
            by_id[region_name][rid] = dict(row)
            order[region_name].append(rid)

    applied = 0
    visited = 0
    touched_rows: set[str] = set()

    totals_prefix = f"{TOTALS_TABLE_KEY}/"
    cur_prefix = f"{ROWS_TABLE_KEY_CURRENT}/"
    pri_prefix = f"{ROWS_TABLE_KEY_PRIOR}/"

    for key in projection.stable_keys():
        sk = str(key)
        fv = projection.get(key)
        if fv is None or getattr(fv, "is_protected", False):
            continue
        new_val = getattr(fv, "value", None)
        if sk.startswith(totals_prefix):
            column_key = sk.rsplit("/", 1)[-1]
            leaf = _TOTALS_STORE_LEAF.get(column_key)
            if leaf is None:
                continue
            region_name, field_name = leaf
            visited += 1
            if regions[region_name].get(field_name) != new_val:
                regions[region_name][field_name] = new_val
                applied += 1
            continue
        if sk.startswith(cur_prefix):
            table_key = ROWS_TABLE_KEY_CURRENT
        elif sk.startswith(pri_prefix):
            table_key = ROWS_TABLE_KEY_PRIOR
        else:
            continue
        rid = getattr(fv, "row_key", None)
        if not rid:
            continue
        rid = str(rid)
        region_name = table_to_region[table_key]
        target = by_id[region_name].get(rid)
        if target is None:
            target = {ROW_IDENTITY_STORE_KEY_D49: rid, "name": ""}
            by_id[region_name][rid] = target
            order[region_name].append(rid)
        column_key = sk.rsplit("/", 1)[-1]
        store_key = _COLUMN_KEY_TO_STORE_KEY.get(column_key)
        if store_key is None:
            continue
        visited += 1
        if target.get(store_key) != new_val:
            target[store_key] = new_val
            applied += 1
            touched_rows.add(rid)

    for region_name in ("current", "prior"):
        regions[region_name]["rows"] = [
            by_id[region_name][rid] for rid in order[region_name]
        ]

    merged = dict(base)
    merged["current"] = regions["current"]
    merged["prior"] = regions["prior"]
    return merged, applied, visited, touched_rows


def merge_projection_into_d49_store_state(
    *,
    projection: Any,
    base_state: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], int, int]:
    """oo_to_html 镜像用（merge_kind=state）：3-tuple 门面（丢弃 touched_rows）。"""
    merged, applied, visited, _touched = merge_projection_into_d49_store(
        projection=projection, base_state=base_state
    )
    return merged, applied, visited


# ═══════════════════════════════════════════════════════════════════════════
# 7. 用户自定义公式（wp_formula）→ xlsx 写入 + 运行时保护区 + 血缘（Task 9）
# ═══════════════════════════════════════════════════════════════════════════

#: D4-9 契约静态 formula_mask 覆盖的列（D/F 占比 + 合计行 C-F）—— 模板内置公式区。
#: 用户自定义公式落在**可编辑** cell（如 C24 总额引 D4-7、某客户金额引其他底稿）时，
#: 这些 cell 不在静态 mask 内，必须在运行时并入保护区（Requirement 5.3 / 5.6）。

#: D4-9 受管 sheet 上「模板内置公式区」的 A1 区间（与两区 formula_mask 一致）。
#: 运行时保护集合 = 本集合 ∪ 用户公式 cell 集合。
def contract_formula_mask_cells() -> tuple[str, ...]:
    """契约静态 formula_mask 的全部 A1 区间（本期 + 上期）。"""
    return tuple(FORMULA_MASK_CURRENT) + tuple(FORMULA_MASK_PRIOR)


def _normalize_cell_ref(target_cell: str) -> str | None:
    """把 wp_formula.target_cell 规范成裸 A1（去 $、去 sheet 前缀）；非 A1 返回 None。"""
    import re

    if not isinstance(target_cell, str):
        return None
    cell = target_cell.strip()
    if "!" in cell:
        cell = cell.rsplit("!", 1)[-1]
    cell = cell.replace("$", "").strip().upper()
    if re.fullmatch(r"[A-Z]{1,3}[1-9][0-9]*", cell):
        return cell
    return None


def _is_cell_in_managed_region(cell: str) -> bool:
    """cell 是否落在 D4-9 两受管区（数据行 + 合计 + 总额行）—— 用户公式只在受管区有意义。"""
    import re

    m = re.fullmatch(r"([A-Z]{1,3})([1-9][0-9]*)", cell)
    if m is None:
        return False
    row = int(m.group(2))
    # 本期：数据 13-22 / 合计 23 / 总额 24；上期：27-36 / 37 / 38。
    return (
        FIRST_DATA_ROW_CURRENT <= row <= TOTAL_ROW_CURRENT
        or FIRST_DATA_ROW_PRIOR <= row <= TOTAL_ROW_PRIOR
    )


def runtime_user_formula_cells(
    wp_formulas: Sequence[Any],
) -> tuple[str, ...]:
    """从某底稿的 wp_formula 行提取 D4-9 受管 sheet 上的用户公式 cell（裸 A1，去重排序）。

    只认 sheet_name==受管 sheet 且 target_cell 可解析为 A1 且落在受管区的行。
    这些 cell 在 materialize/extract 时并入运行时保护区（Requirement 5.3）。

    参数 wp_formulas：WpFormula 行序列（或含 .sheet_name / .target_cell 的对象）。
    """
    cells: set[str] = set()
    for f in wp_formulas or ():
        sheet = str(getattr(f, "sheet_name", "") or "")
        if sheet != MANAGED_SHEET_D49:
            continue
        cell = _normalize_cell_ref(getattr(f, "target_cell", ""))
        if cell is None:
            continue
        if not _is_cell_in_managed_region(cell):
            continue
        cells.add(cell)
    return tuple(sorted(cells))


def runtime_protected_cells(
    wp_formulas: Sequence[Any],
) -> tuple[str, ...]:
    """运行时保护 cell 集合 = 契约静态 formula_mask ∪ 用户公式 cell（去重排序）。

    Requirement 5.3 / 5.6：用户公式 cell 纳入双向受保护区，OO 侧对其编辑产生受保护
    字段冲突而非静默覆盖。契约声明的 formula 字段（D/F 占比、合计）本就受保护，二者一致。
    """
    from openpyxl.utils import get_column_letter
    from openpyxl.utils.cell import column_index_from_string

    from app.services.workpaper_sync.contracts import parse_a1_range

    static_cells: set[str] = set()
    for rng in contract_formula_mask_cells():
        try:
            col_from, row_from, col_to, row_to = parse_a1_range(rng, location="d49_mask")
        except Exception:  # noqa: BLE001 - 单区间解析失败不阻断其余
            continue
        c0 = column_index_from_string(col_from)
        c1 = column_index_from_string(col_to)
        for c in range(min(c0, c1), max(c0, c1) + 1):
            for r in range(min(row_from, row_to), max(row_from, row_to) + 1):
                static_cells.add(f"{get_column_letter(c)}{r}")
    user_cells = set(runtime_user_formula_cells(wp_formulas))
    return tuple(sorted(static_cells | user_cells))


def user_formulas_for_xlsx(
    wp_formulas: Sequence[Any],
) -> dict[str, dict[str, Any]]:
    """把 D4-9 用户公式行转成 `_fill_workpaper_data` 的 user_formulas 覆盖 dict。

    key = ``{sheet}!{cell_ref}``，value = ``{"formula": expression, ...}``。用户公式
    优先级最高（覆盖模板内置公式）—— 复用 wp_template_init 的 user_formulas 覆盖路径
    （Requirement 5.1）。
    """
    out: dict[str, dict[str, Any]] = {}
    for f in wp_formulas or ():
        sheet = str(getattr(f, "sheet_name", "") or "")
        if sheet != MANAGED_SHEET_D49:
            continue
        cell = _normalize_cell_ref(getattr(f, "target_cell", ""))
        if cell is None:
            continue
        expr = str(getattr(f, "expression", "") or "").strip()
        if not expr:
            continue
        # 归一成 =… 形态（wp_template 写 ws[cell].value = formula）。
        if not expr.startswith("="):
            expr = "=" + expr
        out[f"{sheet}!{cell}"] = {
            "formula": expr,
            "source": str(getattr(f, "formula_source", "custom") or "custom"),
        }
    return out


#: D4-9 公式血缘（可追溯 lineage）—— 供 formula 追溯 UI 消费（Requirement 5.4 / 5.5）。
#: 结构：{下游 cell: [上游引用]}。总额取数登记为来源且手工覆盖保留（不无条件覆盖）。
def formula_lineage() -> dict[str, dict[str, Any]]:
    """D4-9 内置公式的上下游血缘（静态声明，供追溯）。

    - 占比 D/F → 明细 C/E 与总额 $C$24/$E$24（本期）/$C$38/$E$38（上期）。
    - 合计 C23/E23 → 明细区间 C13:C22 / E13:E22（上期 C37/E37 → C27:C36 / E27:E36）。
    - 总额 C24/E24 ← D4-7 取数（可手填或从 D4-7 取；取数不覆盖手工值，Requirement 5.5）。
    """
    return {
        "D13:D22": {"refs": ["C13:C22", "$C$24"], "kind": "ratio", "period": "current"},
        "F13:F22": {"refs": ["E13:E22", "$E$24"], "kind": "ratio", "period": "current"},
        "C23": {"refs": ["C13:C22"], "kind": "sum", "period": "current"},
        "E23": {"refs": ["E13:E22"], "kind": "sum", "period": "current"},
        "D27:D36": {"refs": ["C27:C36", "$C$38"], "kind": "ratio", "period": "prior"},
        "F27:F36": {"refs": ["E27:E36", "$E$38"], "kind": "ratio", "period": "prior"},
        "C37": {"refs": ["C27:C36"], "kind": "sum", "period": "prior"},
        "E37": {"refs": ["E27:E36"], "kind": "sum", "period": "prior"},
        "C24": {
            "refs": ["D4-7!D26"],
            "kind": "auto_source",
            "period": "current",
            "manual_override_preserved": True,
            "note": "本期销售总额可手填或从 D4-7 按产品毛利分析合计取数；取数不覆盖手工值。",
        },
        "E24": {"refs": [], "kind": "manual", "period": "current"},
    }
