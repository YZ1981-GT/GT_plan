# -*- coding: utf-8 -*-
"""L4 应付债券 —— 受管 sheet 层声明（身份 / 几何 / 字段 / RowTableSheetSpec）。

spec: l-cycle-true-adapter-registration · Task 12（L4，第二条 L entry）

═══ 受管表选型（重做 design §2.1 的裁决，不假设「都选明细表」）═══

| sheet | 判定 | 依据（openpyxl 逐格实测） |
|---|---|---|
| `审定表L4-1` | ❌ | 140 公式 / 40 文本，派生汇总（与 `审定表L1-1` 同型陷阱） |
| `应付债券明细表L4-2` | ❌ 本轮 | 89 列、每行 38 公式列、**两段**（普通 r15-16 / 可转换 r19-20）各带小计 + 总合计 ⇒ 单段行表引擎装不下，需多段支持，另立 |
| `…L4-7` / `…L4-8` 各两张 | ❌ | BP-8 同尾码折叠 + 内容是计算排程 |
| `调整分录汇总L4-4` | ❌ | 与调整分录模块重复，HTML 两条载体都位置化 |
| **`划分为金融负债的其他金融工具明细表L4-3`** | ✅ | 单段数据区 r13~r17、单 footer A18「合计」、10 个逐行公式列、尾码不重复（无 BP-8）、HTML 侧恰是 lane spec task 18 应去位置化而未做的那张 |

几何：三级表头 r10（组）/ r11（期初余额·本期增加·本期减少·期末余额…）/ r12（数量·金额），
数据 r13~r17，footer r18（标签 **A18**「合计」，A18:B18 合并），有效列 A..AM，
max_column=40（AN，仅 AN2「返回目录」）⇒ 隐藏 UUID 列 AO。册内零 definedName、零 Excel Table。

🔴 footer 行的 T18~W18 写的是 `=N18+P18-R18` 这类**错位交叉公式**（期初调整列本该 SUM），
属模板缺陷 —— 只登记不改（`backend/wp_templates/` 运行时只读，改模板须另立 spec）。
"""
from __future__ import annotations

from typing import Final, Mapping

from app.services.workpaper_sync.models import AuthorityModel
from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)
from app.services.workpaper_sync.phase5_row_table_sheet import (
    managed_field_specs as _engine_managed_field_specs,
)

# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量
# ═══════════════════════════════════════════════════════════════════════════

PHASE5_WAVE: Final[str] = "l_cycle_bonds_payable"
ENTRY_ID: Final[str] = "xlsx/gt-l4-bonds-payable"
ADAPTER_ID: Final[str] = "l4.bonds_payable"
#: manifest 冻结的幻影码（GtL4BondsPayable → L4B），finder 单册与 sheet 级均零命中（实测）。
WP_CODES: Final[frozenset[str]] = frozenset({"L4B"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "L/L4 应付债券.xlsx"
#: 🔴 2026-10-01 净化后的哨兵（`scripts/fix/sanitize_l4_template_external_links.py`，I/J/D 同款）：
#:    删 `权益与负债划分检查表L4-5` 的 1 个外部 hyperlink（单元格文字保留），并把受管表
#:    74 格共享公式展开为显式公式（R13:S18 横向共享组使结构性插行 fail-closed）；
#:    受管 sheet openpyxl 逐格 0 diff。净化前 `9df73e02…c562b`/122,085 B 被首版发布 OOXML
#:    `external_relationships` 门拒绝（slice 冻结的是净化前值，append-only）。
TEMPLATE_SHA256: Final[str] = (
    "b4ba30cfde3d929908ab4989363c04944ed1134b9c25813370307db54443c255"
)
#: 净化前哨兵。
PRE_SANITIZE_TEMPLATE_SHA256: Final[str] = (
    "9df73e02d7af61f287732102cc6367011df09d2e52863c9c80432216ee1c562b"
)
MANAGED_SHEET: Final[str] = "划分为金融负债的其他金融工具明细表L4-3"
TEMPLATE_ID: Final[str] = "L43"
SHEET_KEY: Final[str] = f"{TEMPLATE_ID.lower()}-managed"
ROWS_TABLE_KEY: Final[str] = "financial_liability_instrument_rows"
TABLE_NAME: Final[str] = f"GT_{TEMPLATE_ID}_ROWS"
AUTHORITY_MODEL: Final[AuthorityModel] = AuthorityModel.projection_contract

#: 三级表头：组 r10 / 中层 r11 / 叶子 r12 ⇒ 契约 `header_rows = 3`。
HEADER_GROUP_ROW: Final[int] = 10
HEADER_MID_ROW: Final[int] = 11
HEADER_LEAF_ROW: Final[int] = 12
FIRST_DATA_ROW: Final[int] = 13
LAST_DATA_ROW: Final[int] = 17
FOOTER_ROW: Final[int] = 18
MANAGED_LAST_COL: Final[str] = "AM"
UUID_COL: Final[str] = "AO"
FOOTER_MARKER: Final[str] = "合计"
FOOTER_LABEL_CELL: Final[str] = f"A{FOOTER_ROW}"

STORE_ITEM_ID: Final[str] = "L4-3-rows"
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
ROW_IDENTITY_STORE_KEY: Final[str] = "rowId"

#: 🔴 前端旧 `FinLiabRow` 有、模板无对应列的字段 —— 保留为 HTML-only，**不入契约**。
#: `endBalance` 是用户手填数，与模板 S 列（=M+O-Q 公式）语义不同，不能映射过去。
HTML_ONLY_ROW_KEYS: Final[tuple[str, ...]] = (
    "instrumentType",
    "contractTerms",
    "liabilityReason",
    "initialAmount",
    "endBalance",
    "isFairValue",
)

#: 组标题单元格（第一维）。
_G: Final[Mapping[str, str]] = {
    "unaudited": f"L{HEADER_GROUP_ROW}",
    "prior_adj": f"T{HEADER_GROUP_ROW}",
    "aje": f"X{HEADER_GROUP_ROW}",
    "rje": f"AB{HEADER_GROUP_ROW}",
    "audited": f"AF{HEADER_GROUP_ROW}",
}


def _pair(prefix: str, label: str, col_qty: str, col_amt: str, json_stem: str, group: str,
          mode: str = "editable") -> tuple[tuple[str, str, str, str, str, str, str], ...]:
    """数量 + 金额一对（模板 r12 叶子即「数量」「金额」，r11 中层给出期间口径）。"""
    return (
        (f"{prefix}_qty", col_qty, mode, "amount", f"{json_stem}Qty", f"{label}·数量", group),
        (f"{prefix}_amount", col_amt, mode, "amount", f"{json_stem}Amount", f"{label}·金额", group),
    )


#: 38 个受管字段（10 标量 + 14 对数量/金额），7 元组 `(column_key, 列标, mode, value_type, json 键, 表头文本, 组标题格)`，
#: 按 Excel 列序 A→AM（B 列在数据行无内容，属 A10:B12 表头合并的视觉宽度，不受管）。
MANAGED_FIELD_SPECS_7: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("instrument_name", "A", "editable", "text", "instrumentName", "发行在外的金融工具", ""),
    ("issue_date", "C", "editable", "date", "issueDate", "发行时间", ""),
    ("accounting_class", "D", "editable", "text", "accountingClass", "会计分类", ""),
    ("dividend_or_interest_rate", "E", "editable", "rate", "rate", "股利率或利息率", ""),
    ("issue_price", "F", "editable", "amount", "issuePrice", "发行价格", ""),
    ("issue_qty", "G", "editable", "amount", "issueQty", "数量", ""),
    ("issue_amount", "H", "editable", "amount", "issueAmount", "金额", ""),
    ("maturity", "I", "editable", "text", "maturity", "到期日或续期情况", ""),
    ("conversion_terms", "J", "editable", "text", "conversionTerms", "转股条件", ""),
    ("conversion_status", "K", "editable", "text", "conversionStatus", "转换情况", ""),
    *_pair("unaudited_prior", "未审期初余额", "L", "M", "unauditedPrior", _G["unaudited"]),
    *_pair("unaudited_increase", "未审本期增加", "N", "O", "unauditedIncrease", _G["unaudited"]),
    *_pair("unaudited_decrease", "未审本期减少", "P", "Q", "unauditedDecrease", _G["unaudited"]),
    *_pair("unaudited_end", "未审期末余额", "R", "S", "unauditedEnd", _G["unaudited"], "formula"),
    *_pair("prior_aje", "期初账项调整", "T", "U", "priorAje", _G["prior_adj"]),
    *_pair("prior_rje", "期初重分类调整", "V", "W", "priorRje", _G["prior_adj"]),
    *_pair("aje_increase", "账项调整本期增加", "X", "Y", "ajeIncrease", _G["aje"]),
    *_pair("aje_decrease", "账项调整本期减少", "Z", "AA", "ajeDecrease", _G["aje"]),
    *_pair("rje_increase", "重分类调整本期增加", "AB", "AC", "rjeIncrease", _G["rje"]),
    *_pair("rje_decrease", "重分类调整本期减少", "AD", "AE", "rjeDecrease", _G["rje"]),
    *_pair("audited_prior", "审定期初余额", "AF", "AG", "auditedPrior", _G["audited"], "formula"),
    *_pair("audited_increase", "审定本期增加", "AH", "AI", "auditedIncrease", _G["audited"], "formula"),
    *_pair("audited_decrease", "审定本期减少", "AJ", "AK", "auditedDecrease", _G["audited"], "formula"),
    *_pair("audited_end", "审定期末余额", "AL", "AM", "auditedEnd", _G["audited"], "formula"),
)

#: 十个逐行公式列（模板 r13~r17 逐格实测；期末 = 期初 + 增加 − 减少）。
FORMULA_TEMPLATES: Final[Mapping[str, str]] = {
    "R": "=L{row}+N{row}-P{row}",
    "S": "=M{row}+O{row}-Q{row}",
    "AF": "=L{row}+T{row}+V{row}",
    "AG": "=M{row}+U{row}+W{row}",
    "AH": "=N{row}+X{row}+AB{row}",
    "AI": "=O{row}+Y{row}+AC{row}",
    "AJ": "=P{row}+Z{row}+AD{row}",
    "AK": "=Q{row}+AA{row}+AE{row}",
    "AL": "=AF{row}+AH{row}-AJ{row}",
    "AM": "=AG{row}+AI{row}-AK{row}",
}
FORMULA_COLUMNS: Final[tuple[str, ...]] = tuple(FORMULA_TEMPLATES)

SPEC_L43: Final[RowTableSheetSpec] = RowTableSheetSpec(
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
    field_specs=MANAGED_FIELD_SPECS_7,
    formula_columns=FORMULA_COLUMNS,
    formula_templates=FORMULA_TEMPLATES,
    aging_layout=None,
    aging_groups=(),
    footer_marker=FOOTER_MARKER,
    footer_carries_total_formula=True,
    footer_search_column="A",
    error_label="L4-3 金融负债工具明细表",
    #: 锚点取 [0] `instrument_name`（工具名称，真业务名称、文本型）。
    ghost_row_anchor_index=0,
)

MANAGED_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str], ...]] = tuple(
    row[:6] for row in _engine_managed_field_specs(SPEC_L43)
)
FORMULA_MASK: Final[tuple[str, ...]] = SPEC_L43.formula_mask

_HTML_STORE_NOTE: Final[str] = (
    "整张 L4-3 明细表存成这一条 item 的 remark（JSON 数组字符串，L4TabFinLiabOther 的 "
    "JSON.stringify(rows)），每行带稳定 rowId。🔴 旧形态 `L4-3-row-{index+1}-data` 是位置化"
    "行身份，且 removeRow 只 splice 不重存、组件无 hydration（刷新即丢）；真库 `L4-3-row-*` "
    "现算 0 行 ⇒ 零迁移负担。旧 FinLiabRow 的 instrumentType/contractTerms/liabilityReason/"
    "initialAmount/endBalance/isFairValue 模板无对应列，保留为 HTML-only 不入契约。"
)
_REVIEWED_BASIS: Final[str] = (
    "2026-10-01 openpyxl 逐格实测 `L/L4 应付债券.xlsx`（净化后 sha256 b4ba30cf…，16 sheet；"
    "净化前 9df73e02… 因 1 个外部 hyperlink 被 OOXML 门拒）："
    "受管表选型见模块 docstring；L4-3 三级表头 r10/r11/r12、数据 r13~r17、footer A18「合计」、"
    "R/S/AF~AM 十列逐行公式；manifest 幻影码 L4B 经 wp_template_finder 单册/sheet 级均零命中；"
    "wp_index 中 wp_code=L4 有 3 份带真 file_path 的底稿。"
)
