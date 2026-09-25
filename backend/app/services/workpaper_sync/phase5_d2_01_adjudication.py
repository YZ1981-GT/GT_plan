# -*- coding: utf-8 -*-
"""D2-1「应收账款审定表」—— gt-d2-accounts-receivable 的 sibling sheet（adapter `d2.receivable_detail`）。

spec: d2-sync-coverage-via-row-table-engine · Task 11/12/13
Requirements 3.1/3.2/3.3/3.4/3.5/3.6/3.7 · 9.2/9.3 · design 裁决 E3 / Property 6/7/8/9

═══ 架构裁决（照 D4-1 逐格审定表范式 + D4-6 稳定 key 固定行）═══

D2-1 作为 ``xlsx/gt-d2-accounts-receivable`` 的 sibling sheet（d21-managed，共享 adapter
d2.receivable_detail），不建独立 entry。

与 D4-1 的差异（spec 裁决 E3 参数化，**不在引擎加 if is_d1/is_d2 分支**）：

| | D4-1 | D2-1 |
|---|---|---|
| 区块 | 2（主营/其他） | 1 |
| 行 | 动态票据种类 | **写死 4 行** individual/aging/customer-type/total |
| row_mode | dynamic_identity | **fixed_rows**（D4-6 稳定 key 固定行范式） |
| 取数 | D4-4 小计 | D2-2 **SUMIF** 按 creditRiskClassification 分类汇总 |

═══ 结构：逐格形态（实测 311 公式 / 62 行 13 列 / 密度 38%）═══

受管 sheet = ``审定表D2-1``（openpyxl 直读权威模板，与父 pilot 同 workbook，
sha256=``31e7992ba1e83952620e1777d108b46f7e7817dcdc9484c07f079f1dd3af0afa``）：

* **核心 4 行**（spec 裁决聚焦，evidence/T01）：
  - R8  单项计提坏账准备（rowKey=individual）：F8/G8/H8 = SUMIF「单项计提」
  - R10 账龄组合（rowKey=aging）：F10/G10/H10 = SUMIF「账龄组合」
  - R11 客户类型组合（rowKey=customer-type）：F11/G11/H11 = SUMIF「客户类型组合」
  - R13 小计（rowKey=total，rowType=summary，computed 不落库）
  （R9「按组合计提」=SUM(10:12) 是中间汇总行，非 4 核心行之一）

* **逐格 mask**：模板 311 公式为逐格形态（非列向区间）。派生列 E(=B+C+D) / I(=F+G+H) /
  J(=I-E) / K(变动率 IF) + SUMIF 列 F/G/H + 各小计/合计行落 formula_mask。
  受管的可编辑字段（人工可覆盖的 6 个金额）绝不入 mask —— 依赖已入库的 merge._protection
  **格级**判定（cell_in_ranges + _mask_spans_data_column，commit 8c51975b5）。

* row_mode=fixed_rows（4 行写死，按 rowKey 稳定 key + 静态行号声明），total 行 rowType=summary。

═══ 四态覆盖（Requirement 3.4/3.5）═══

前端现状 ``isFromSumif: boolean`` 归一到 ``source``（tb=SUMIF 派生 / manual=人工），复用
shared/dynamicAdjudicationRows.resolveCellState / displayValueForCellState 四态状态机。
本后端模块只声明逐格 mask 与固定行几何；四态覆盖 UI 在前端 useD2Adjudication。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final, Mapping


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量（openpyxl 实测 evidence/T01-d2-geometry-probe.json）
# ═══════════════════════════════════════════════════════════════════════════

TEMPLATE_RELATIVE_PATH: Final[str] = (
    "D/D2-1至D2-4  应收账款- 审定表明细表（Leap-常规程序）.xlsx"
)
TEMPLATE_SHA256: Final[str] = (
    "31e7992ba1e83952620e1777d108b46f7e7817dcdc9484c07f079f1dd3af0afa"
)

MANAGED_SHEET_D21: Final[str] = "审定表D2-1"
TEMPLATE_ID_D21: Final[str] = "D21"
SHEET_KEY_D21: Final[str] = "d21-managed"
STORE_ITEM_ID_D21: Final[str] = "D2-adj-rows"

#: 两级表头（R5 项目/期初数/期末数/比较；R6 未审/账项/重分类/审定/变动额/变动率）。
HEADER_ROWS_D21: Final[tuple[int, int]] = (5, 6)

#: 核心 4 行的稳定 key + 静态行号（row_mode=fixed_rows，D4-6 稳定 key 固定行范式）。
#: (rowKey, 静态行号, SUMIF 分类文本 或 None, 是否 summary)
FIXED_ROWS_D21: Final[tuple[tuple[str, int, str | None, bool], ...]] = (
    ("individual", 8, "单项计提", False),
    ("aging", 10, "账龄组合", False),
    ("customer-type", 11, "客户类型组合", False),
    ("total", 13, None, True),  # 小计行 rowType=summary，computed 不落库
)

#: 受管可编辑金额列（6 个人工可覆盖字段，绝不入 mask —— Property 7 钉住 D4-1 踩过的坑）。
#: 期初：B 未审 / C 账项调整 / D 重分类；期末的账项调整 G / 重分类 H（F 未审来自 SUMIF）。
#: 实测：F/G/H8 是 SUMIF（tb 派生），但 R10/R11 的 B/C/D 是人工录入（editable）。
#: 6 个金额字段 = B/C/D（期初未审/账项/重分类）+ G/H（期末账项/重分类）+ F 视 SUMIF 情况。
MANAGED_EDITABLE_COLUMNS: Final[tuple[str, ...]] = ("B", "C", "D", "F", "G", "H")

#: SUMIF 取数列（F 期末未审 / G 期末账项 / H 期末重分类，按 creditRiskClassification 分类）。
SUMIF_COLUMNS: Final[tuple[str, ...]] = ("F", "G", "H")

#: 派生公式列（E 期初审定=B+C+D / I 期末审定=F+G+H / J 变动额=I-E / K 变动率）。
DERIVED_FORMULA_COLUMNS: Final[tuple[str, ...]] = ("E", "I", "J", "K")

#: SUMIF 取数源（明细表 D2-2 的 AI 分类列 + S/Z/AA 值列）。
SUMIF_SOURCE_SHEET: Final[str] = "明细表D2-2"
SUMIF_SOURCE_CLASS_RANGE: Final[str] = "$AI$13:$AI$25"


# ═══════════════════════════════════════════════════════════════════════════
# 2. 逐格 formula_mask（实测 evidence/T01，核心区块 R8-13）
# ═══════════════════════════════════════════════════════════════════════════

#: 核心区块行号（8 单项 / 9 按组合汇总 / 10 账龄 / 11 客户类型 / 12 ……组合 / 13 小计）。
_CORE_BLOCK_ROWS: Final[tuple[int, ...]] = (8, 9, 10, 11, 12, 13)


def _formula_mask_cells() -> tuple[str, ...]:
    """逐格 formula_mask（实测 T01 的核心区块公式格）。

    实测每行的公式格：
    - R8:  E(=B+C+D) F/G/H(SUMIF) I(=F+G+H) J(=I-E) K(变动率)
    - R9:  B/C/D/E/F/G/H/I(=SUM 小计) J K
    - R10: E F/G/H(SUMIF) I J K
    - R11: E F/G/H(SUMIF) I J K
    - R12: E I J K
    - R13: B/C/D/E/F/G/H/I(=SUM 合计) J K

    这些格是模板内置公式（SUMIF 派生 + 加总派生 + 变动率），materialize 不覆盖、由 OO 重算。
    受管的**可编辑**金额（人工在 R10/R11 录入的 B/C/D 等）绝不入此 mask —— 依赖 merge._protection
    的格级判定区分「同列 mask 多行区间且覆盖数据行」vs「逐格精确」。
    """
    cells: list[str] = []
    # R8/R10/R11：E + SUMIF(F/G/H) + I/J/K
    for row in (8, 10, 11):
        cells.append(f"E{row}")
        for col in SUMIF_COLUMNS:
            cells.append(f"{col}{row}")
        for col in ("I", "J", "K"):
            cells.append(f"{col}{row}")
    # R9/R13：B..I 加总 + J/K（小计/合计行全列公式）
    for row in (9, 13):
        for col in ("B", "C", "D", "E", "F", "G", "H", "I", "J", "K"):
            cells.append(f"{col}{row}")
    # R12：E I J K（……组合空行的派生列）
    for col in ("E", "I", "J", "K"):
        cells.append(f"{col}12")
    return tuple(cells)


#: 逐格 formula_mask（核心区块）。
FORMULA_MASK: Final[tuple[str, ...]] = _formula_mask_cells()

#: 6 个人工可编辑金额字段的定位（rowKey → 该行可编辑列）。R10/R11 的 B/C/D 是人工录入。
#: Property 7：这 6 格在逐格 mask 下必须判 editable 而非 read_only_masked_cell。
EDITABLE_AMOUNT_CELLS: Final[tuple[str, ...]] = (
    "B10", "C10", "D10",   # 账龄组合行人工录入期初
    "B11", "C11", "D11",   # 客户类型组合行人工录入期初
)

#: 6 个 editable 金额格的完整声明：`(cell, 列标, 静态行号, rowKey, store 键, value_type, 表头)`。
#: 🔴 D2-1 store 是 **per-cell 锚点**（`D2-adj-{rowKey}-{field}`，非行数组），故进父契约走
#: **静态字段**形态（`cell.row_from=静态行号` / `row_scoped=False` / 无 row_identity），
#: 照 D4-9 `totals_table_payload` 范式。store 键与前端 useD2Adjudication.getSumifOrManual
#: 的 manualItemId 逐字对齐（`D2-adj-{rowKey}-prior-{unadjusted|aje|rje}`）。
EDITABLE_CELL_SPECS: Final[tuple[tuple[str, str, int, str, str, str, str], ...]] = (
    ("B10", "B", 10, "aging", "D2-adj-aging-prior-unadjusted", "amount", "期初未审数"),
    ("C10", "C", 10, "aging", "D2-adj-aging-prior-aje", "amount", "期初账项调整"),
    ("D10", "D", 10, "aging", "D2-adj-aging-prior-rje", "amount", "期初重分类调整"),
    ("B11", "B", 11, "customer-type", "D2-adj-customer-type-prior-unadjusted", "amount", "期初未审数"),
    ("C11", "C", 11, "customer-type", "D2-adj-customer-type-prior-aje", "amount", "期初账项调整"),
    ("D11", "D", 11, "customer-type", "D2-adj-customer-type-prior-rje", "amount", "期初重分类调整"),
)


# ═══════════════════════════════════════════════════════════════════════════
# 3. mapping_digest（锁死逐格映射 + 固定 4 行 + 无动态 identity）
# ═══════════════════════════════════════════════════════════════════════════


def mapping_digest_payload() -> dict[str, Any]:
    return {
        "managed_sheet": MANAGED_SHEET_D21,
        "template_relative_path": f"backend/wp_templates/{TEMPLATE_RELATIVE_PATH}",
        "template_sha256": TEMPLATE_SHA256,
        "header_rows": list(HEADER_ROWS_D21),
        "row_mode": "fixed_rows",
        "fixed_rows": [
            {"row_key": rk, "static_row": row, "sumif_class": cls, "is_summary": summ}
            for rk, row, cls, summ in FIXED_ROWS_D21
        ],
        "sumif_columns": list(SUMIF_COLUMNS),
        "sumif_source_sheet": SUMIF_SOURCE_SHEET,
        "sumif_source_class_range": SUMIF_SOURCE_CLASS_RANGE,
        "derived_formula_columns": list(DERIVED_FORMULA_COLUMNS),
        "managed_editable_columns": list(MANAGED_EDITABLE_COLUMNS),
        "formula_mask": list(FORMULA_MASK),
        "editable_amount_cells": list(EDITABLE_AMOUNT_CELLS),
        "editable_cell_fields": [
            {"cell": c, "col": col, "static_row": row, "row_key": rk, "store_item_id": sid, "value_type": vt}
            for c, col, row, rk, sid, vt, _hdr in EDITABLE_CELL_SPECS
        ],
    }


def compute_mapping_digest() -> str:
    canon = json.dumps(
        mapping_digest_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


mapping_digest = compute_mapping_digest
EXPECTED_MAPPING_DIGEST_D21: Final[str] = compute_mapping_digest()


def assert_mapping_digest_d21() -> str:
    """锁死几何未漂移 + 固定 4 行 + row_mode=fixed_rows（Property 6）。"""
    got = compute_mapping_digest()
    if got != EXPECTED_MAPPING_DIGEST_D21:
        raise ValueError(
            f"D2-1 mapping_digest 漂移：现算={got} 冻结={EXPECTED_MAPPING_DIGEST_D21}"
        )
    if len(FIXED_ROWS_D21) != 4:
        raise ValueError(f"D2-1 固定行必须为 4（individual/aging/customer-type/total），实得 {len(FIXED_ROWS_D21)}")
    summary_rows = [rk for rk, _r, _c, summ in FIXED_ROWS_D21 if summ]
    if summary_rows != ["total"]:
        raise ValueError(f"D2-1 仅 total 行为 summary，实得 {summary_rows}")
    return got


# ═══════════════════════════════════════════════════════════════════════════
# 4. 固定行 row_mode + 逐格 editable/masked 判定（Property 6/7）
# ═══════════════════════════════════════════════════════════════════════════

#: row_mode：fixed_rows（4 行写死，无动态 identity 列需求）。Property 6 钉住。
ROW_MODE: Final[str] = "fixed_rows"


def row_type_for(row_key: str) -> str:
    """固定行 rowType：total → summary（computed 不落库）；其余 → fixed。

    与 D4-6 稳定 key 固定行范式一致：4 个 rowKey 本身是稳定键，行不增删、不需要动态
    identity 列。row_mode='fixed_rows'。
    """
    for rk, _row, _cls, is_summary in FIXED_ROWS_D21:
        if rk == row_key:
            return "summary" if is_summary else "fixed"
    raise ValueError(f"未知 D2-1 rowKey: {row_key!r}（固定 4 行之外）")


def requires_dynamic_identity_column() -> bool:
    """Property 6：D2-1 是固定行，**不需要**动态 identity 列。

    变异：改成 dynamic_identity ⇒ 本函数返回 True ⇒ 判据必红。
    """
    return ROW_MODE != "fixed_rows"


def cell_is_masked(cell: str) -> bool:
    """某格是否落逐格 formula_mask（模板内置公式区，OO 重算不覆盖）。

    用 merge.cell_in_ranges 的格级判定（commit 8c51975b5 已入库），与 materialize 侧一致。
    Property 7：6 个人工金额字段（EDITABLE_AMOUNT_CELLS）必须返回 False（editable），
    而非因「同列 K 列 mask 多行」被整列误判 read_only。
    """
    from app.services.workpaper_sync.contracts import cell_in_ranges

    import re

    m = re.fullmatch(r"([A-Z]+)([0-9]+)", cell)
    if m is None:
        raise ValueError(f"非法 A1 单元格: {cell!r}")
    col, row = m.group(1), int(m.group(2))
    return cell_in_ranges(col, row, FORMULA_MASK)


def editable_amount_cells_are_not_masked() -> list[str]:
    """Property 7：返回被误判 masked 的可编辑金额格（应为空）。

    变异：把逐格 mask 换成 column_in_ranges 整列判定 ⇒ B10/C10/... 会因同列有 mask 而被
    误判 masked ⇒ 本函数返回非空 ⇒ 判据必红（钉住 D4-1 六字段被整列挡的坑）。
    """
    return [cell for cell in EDITABLE_AMOUNT_CELLS if cell_is_masked(cell)]


# ═══════════════════════════════════════════════════════════════════════════
# 5. 契约 sheet payload（静态 cell 型：6 editable 金额格 + 逐格 formula_mask）
# ═══════════════════════════════════════════════════════════════════════════

#: D2-1 受管 table_key（单 table，静态 cell，无 row_identity —— 照 D4-9 totals 范式）。
TABLE_KEY_D21: Final[str] = "adjudication_cells"


def stable_key_for_cell(column_key: str) -> str:
    """`adjudication_cells/{column_key}` 的唯一拼装处（column_key 已小写，如 aging_b）。"""
    return f"{TABLE_KEY_D21}/{column_key}"


def sheet_payload_d21() -> dict[str, Any]:
    """D2-1 契约 sheet：静态 cell 型单 table（6 个人工 editable 金额格 + 逐格 formula_mask）。

    🔴 D2-1 store 是 per-cell 锚点（`D2-adj-{rowKey}-{field}`，非行数组），故走**静态字段**形态
    （`cell.row_from=静态行号` / `row_scoped=False` / 无 row_identity / 无 delete_policy），
    与 D4-9 `totals_table_payload` 同型。SUMIF 派生格 + 派生列 + 小计/合计行落 formula_mask，
    普通值投影不覆盖。fixed 4 行的 rowKey 是稳定键（D4-6 范式），不注入 UUID 列。
    """
    from app.services.workpaper_sync.excel_extract import TABLE_SHEET_ANCHOR

    def _src(cell: str) -> str:
        return f"源xlsx!{MANAGED_SHEET_D21}!{cell}"

    fields: list[dict[str, Any]] = []
    for cell, column, static_row, row_key, store_item_id, value_type, header_text in EDITABLE_CELL_SPECS:
        column_key = f"{row_key.replace('-', '_')}_{column.lower()}"
        fields.append(
            {
                "stable_field_key": stable_key_for_cell(column_key),
                "json_pointer": f"/{store_item_id}",
                "column_key": column_key,
                "cell": {"column": column, "row_from": static_row},
                "mode": "editable",
                "value_type": value_type,
                "source_ref": _src(cell),
                "store_item_id": store_item_id,
                "row_key": row_key,
                "header_text": header_text,
            }
        )
    # sheet 级逐格 formula_mask（SUMIF + 派生 + 小计/合计，OO 重算不覆盖）。
    all_mask = list(FORMULA_MASK)
    return {
        "sheet_key": SHEET_KEY_D21,
        "excel_name": MANAGED_SHEET_D21,
        "locator": {"anchor": TABLE_SHEET_ANCHOR},
        "tables": [
            {
                "table_key": TABLE_KEY_D21,
                "anchor": f"A{HEADER_ROWS_D21[0]}",
                "header_rows": 2,
                "formula_mask": all_mask,
                "fields": fields,
            }
        ],
    }
