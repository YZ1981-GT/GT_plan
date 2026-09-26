# -*- coding: utf-8 -*-
"""D1-10「应收票据监盘表」—— sheet 层薄声明（**单区**，核对区不受管）。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 28 · Requirements 5.1 / 5.5

═══ 几何（openpyxl 直读实测，2026-09-26）═══

本 sheet 含三段，只有第一段（监盘日结存表）进受管区：

| 段 | 行范围 | 表头 | 管理方式 |
|---|---|---|---|
| 监盘日结存 | R12-R21 | R12-13 两级表头 | ✅ `RowTableSheetSpec`（本声明） |
| 两个倒轧表 | R24-R25 | R24 表头 | ❌ **纯公式区**（全部 =SUM/=±，无可编辑格） |
| 监盘人/日期/审计说明 | R22, R26+ | 无 | ❌ HTML-only 文本区 |

🔴 倒轧表 R24-R25 **全部是公式格**（A25=H21, D25=A25+B25-C25, F25=D25-E25 / 右侧同构），
零可编辑格 ⇒ 引擎不应管理它们（OO 打开时 Excel 自行重算即可）。如果硬把它们声明为
`static_region`，materialize 反而会往纯公式格写值从而覆盖公式。

🔴 前端 `useD1InventoryCount.ts` 的核对区（`reconArea` computed）只有 3 个标量文本键
（`D1-inventory-recon-explanation`/`-conclusion`/`-indexRef`），不是行数组 store —— 它们由
HTML 侧的 debounce/select 保存机制处理，不进入 Excel 契约层。

🔴 监盘日结存表的两级表头：R12 是"监盘日结存"（A12 合并区）+ "是否存在差异"(M12) +
"差异原因"(N12) + "索引号"(O12)；R13 是逐列叶子表头。所以 A-L 列的叶子在 R13，
M/N/O 列的叶子在 R12（它们不参与 R12 的合并）。

🔴 数据区无行级公式（全 editable），公式仅在 footer H21=SUM。

🔴 `row_identity_key = "id"`（前端 `InventoryCountRow.id`）。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = ["SPEC_D110", "MANAGED_SHEET_D110"]

MANAGED_SHEET_D110: Final[str] = "应收票据监盘D1-10"
TEMPLATE_ID_D110: Final[str] = "D110"
SHEET_KEY_D110: Final[str] = f"{TEMPLATE_ID_D110.lower()}-managed"

HEADER_GROUP_ROW_D110: Final[int] = 12
HEADER_LEAF_ROW_D110: Final[int] = 13
FOOTER_ROW_D110: Final[int] = 21
#: 🔴 footer marker「合计」（[5408 8ba1]），与 D1-15 的「小计」不同。
FOOTER_MARKER_D110: Final[str] = "合计"

#: 15 列 A-O。无数据区行级公式，公式仅在 footer H21=SUM。
#: 🔴 **列顺序按 Excel 模板 R13 实测，不按前端 InventoryCountRow 注释**——前端 UI 展示顺序
#: 与 Excel 列顺序不同（前端把"收到日期"排到第 C 位而 Excel 排到 I 位），field_specs 必须
#: 按 Excel 列字母（materialize/extract 用）。json_key 按前端 store 字段名（JSON 载荷用）。
_FIELD_SPECS_D110: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("note_type", "A", "editable", "text", "noteType", "票据类型", ""),
    ("note_no", "B", "editable", "text", "noteNo", "票据号", ""),
    ("receive_date", "C", "editable", "text", "receiveDate", "收到票据日期", ""),
    ("predecessor", "D", "editable", "text", "predecessor", "票据前手名称", ""),
    ("issue_date", "E", "editable", "text", "issueDate", "出票日期", ""),
    ("drawer", "F", "editable", "text", "drawer", "出票人名称", ""),
    ("acceptor", "G", "editable", "text", "acceptor", "承兑人名称", ""),
    ("amount", "H", "editable", "amount", "amount", "票据金额", ""),
    ("maturity_date", "I", "editable", "text", "maturityDate", "票据到期日", ""),
    ("endorsee", "J", "editable", "text", "endorsee", "被背书人名称", ""),
    ("payer", "K", "editable", "text", "payer", "付款人名称", ""),
    ("is_pledged", "L", "editable", "text", "noteStatus", "是否质押", ""),
    ("has_difference", "M", "editable", "text", "hasDifference", "是否存在差异", ""),
    ("difference_reason", "N", "editable", "text", "differenceReason", "差异原因", ""),
    ("index_ref", "O", "editable", "text", "indexRef", "索引号", ""),
)

#: footer 公式列（仅 H 列 SUM = 票据金额合计）。
_FORMULA_COLUMNS_D110: Final[tuple[str, ...]] = ("H",)
_FORMULA_TEMPLATES_D110: Final[dict[str, str]] = {"H": "=SUM(H14:H{r})"}

SPEC_D110: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_D110,
    sheet_key=SHEET_KEY_D110,
    table_key="inventory_count_rows",
    template_id=TEMPLATE_ID_D110,
    table_name=f"GT_{TEMPLATE_ID_D110}_ROWS",
    uuid_col="P",  # max_col=O=15, 注入列 P
    first_data_row=14,
    last_data_row=20,
    footer_row=FOOTER_ROW_D110,
    header_group_row=HEADER_GROUP_ROW_D110,
    header_leaf_row=HEADER_LEAF_ROW_D110,
    store_item_id="D1-inventory-rows",
    empty_payload="[]",
    row_identity_key="id",
    store_kind=StoreKind.rows,
    field_specs=_FIELD_SPECS_D110,
    formula_columns=_FORMULA_COLUMNS_D110,
    formula_templates=_FORMULA_TEMPLATES_D110,
    footer_marker=FOOTER_MARKER_D110,
    error_label="D1-10 票据监盘",
)
