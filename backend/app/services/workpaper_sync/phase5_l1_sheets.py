# -*- coding: utf-8 -*-
"""L1 短期借款 —— 受管 sheet 层声明（身份 / 几何 / 字段 / RowTableSheetSpec）。

spec: l-cycle-true-adapter-registration · Task 4

按 `phase5_a51_sheets.py` 的既有范式从 `phase5_l1_short_term_loans.py` 拆出 ——
拆分动因是硬约束：`check_file_size.py` 对 **新增** `.py` 强制 ≤800 行
（whitelist 只许历史大文件），主模块含本层时为 897 行。

受管 sheet = `明细表L1-2`（openpyxl 逐格实测）：两级表头 r8 组标题 + r9 叶子、
数据区 r10~r25、footer r26（标签在 **C26**「合计」，A26 为空）、30 列 A-AD
（有效业务列到 AB，28 个受管字段）、五个公式列 K/R/S/T/U 逐行。

🔴 `审定表L1-1` 是**派生只读投影**：R7~R11 无一个可输入格（B/C/D/F/G/H 全是 SUMIF
引用本表、E/I/J/L 加总、K 裸 IF、R11 SUM），写它会毁掉整册取数联动。
"""
from __future__ import annotations

from typing import Any, Final, Mapping

from app.services.workpaper_sync.models import AuthorityModel
from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)
from app.services.workpaper_sync.phase5_row_table_sheet import (
    managed_field_specs as _engine_managed_field_specs,
)

# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量（从真实 manifest / 模板实测）
# ═══════════════════════════════════════════════════════════════════════════

PHASE5_WAVE: Final[str] = "l_cycle_short_term_loans"
ENTRY_ID: Final[str] = "xlsx/gt-l1-short-term-loans"
ADAPTER_ID: Final[str] = "l1.short_term_loans"
#: manifest 冻结的 wp_code_pattern（宿主 GtL1ShortTermLoans CamelCase 幻影码，finder 零命中）。
WP_CODES: Final[frozenset[str]] = frozenset({"L1S"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "L/L1 短期借款.xlsx"
TEMPLATE_SHA256: Final[str] = (
    "78033d804a379d42e7e0bc500aefb617fe6175537373126f88827d70b728ceeb"
)
MANAGED_SHEET: Final[str] = "明细表L1-2"
#: 🔴 派生只读投影表：R7~R11 全公式（SUMIF 引用受管表），一格不写。
DERIVED_SHEET: Final[str] = "审定表L1-1"
TEMPLATE_ID: Final[str] = "L12"
SHEET_KEY: Final[str] = f"{TEMPLATE_ID.lower()}-managed"
ROWS_TABLE_KEY: Final[str] = "short_term_loan_detail_rows"

#: 两级表头：组标题在行 8，叶子（期初余额/本期增加/…）在行 9（openpyxl 逐格实测）。
HEADER_GROUP_ROW: Final[int] = 8
HEADER_LEAF_ROW: Final[int] = 9

#: 数据区与 footer（实测：数据 10-25，合计 26）。
FIRST_DATA_ROW: Final[int] = 10
LAST_DATA_ROW: Final[int] = 25
FOOTER_ROW: Final[int] = 26

#: 最后一列受管业务列（AB 备注）与隐藏 row UUID 列（= max_column + 1）。
MANAGED_LAST_COL: Final[str] = "AB"
UUID_COL: Final[str] = "AE"

TABLE_NAME: Final[str] = f"GT_{TEMPLATE_ID}_ROWS"
AUTHORITY_MODEL: Final[AuthorityModel] = AuthorityModel.projection_contract
#: 🔴 footer 标签实测在 **C26**、文本 `合计`（无 d6 的 3 半角空格）。A26 为空 ——
#: 按 A 列找 marker 会得空并误判「无 footer」。
FOOTER_MARKER: Final[str] = "合计"
FOOTER_LABEL_CELL: Final[str] = f"C{FOOTER_ROW}"

STORE_ITEM_ID: Final[str] = "L1-2-rows"
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
ROW_IDENTITY_STORE_KEY: Final[str] = "rowId"

#: 🔴 前端 DetailRow 有、模板无对应列的两个字段 —— 保留为 HTML-only，**不入契约**。
HTML_ONLY_ROW_KEYS: Final[tuple[str, ...]] = ("amount", "currency")


#: 组标题单元格（两级表头的第一维）：H/L/N/P/R 五个 merged 组。
_G: Final[Mapping[str, str]] = {
    "unadjusted": f"H{HEADER_GROUP_ROW}",
    "prior_adj": f"L{HEADER_GROUP_ROW}",
    "aje": f"N{HEADER_GROUP_ROW}",
    "rje": f"P{HEADER_GROUP_ROW}",
    "audited": f"R{HEADER_GROUP_ROW}",
}

#: 28 个受管字段，7 元组 `(column_key, 列标, mode, value_type, store json 键, 表头文本,
#: 组标题单元格)`，顺序即 Excel 列序 A→AB。
#:
#: 🔴 `json_key` 对齐前端 `useL1FormData.DetailRow`：12 个已存在（bank/contractNo/loanType/
#: rate/startDate/endDate/purpose/guarantee/beginning/creditAmount/debitAmount/endBalance），
#: 其余 16 个是本 spec 按模板列补齐的（design §2.4.1）。
#: 🔴 K/R/S/T/U 五列 mode=formula —— 模板里逐行有真公式，OO 侧不得被值覆盖。
#: 🔴 有组标题的列（H..U）`header_text` 取**叶子行**文本，无组的取组标题行文本。
MANAGED_FIELD_SPECS_7: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("seq_no", "A", "editable", "integer", "seqNo", "序号", ""),
    ("loan_type", "B", "editable", "enum", "loanType", "借款种类", ""),
    ("bank", "C", "editable", "text", "bank", "贷款单位", ""),
    ("start_date", "D", "editable", "date", "startDate", "起始日期", ""),
    ("end_date", "E", "editable", "date", "endDate", "讫止日期", ""),
    #: 🔴 年利率用封闭枚举里的 `rate`（不是 `number` —— 该值不在
    #: `contracts.ValueType` 的 10 个合法值里，首版写 `number` 被 schema 打红）。
    ("rate", "F", "editable", "rate", "rate", "年利率", ""),
    ("rate_kind", "G", "editable", "enum", "rateKind", "固定/浮动利率", ""),
    ("prior_unadjusted", "H", "editable", "amount", "beginning", "期初余额", _G["unadjusted"]),
    ("unadjusted_increase", "I", "editable", "amount", "creditAmount", "本期增加", _G["unadjusted"]),
    ("unadjusted_decrease", "J", "editable", "amount", "debitAmount", "本期减少", _G["unadjusted"]),
    ("unadjusted_end", "K", "formula", "amount", "endBalance", "期末余额", _G["unadjusted"]),
    ("prior_aje", "L", "editable", "amount", "priorAje", "账项调整", _G["prior_adj"]),
    ("prior_rje", "M", "editable", "amount", "priorRje", "重分类调整", _G["prior_adj"]),
    ("aje_increase", "N", "editable", "amount", "ajeIncrease", "本期增加", _G["aje"]),
    ("aje_decrease", "O", "editable", "amount", "ajeDecrease", "本期减少", _G["aje"]),
    ("rje_increase", "P", "editable", "amount", "rjeIncrease", "本期增加", _G["rje"]),
    ("rje_decrease", "Q", "editable", "amount", "rjeDecrease", "本期减少", _G["rje"]),
    ("audited_prior", "R", "formula", "amount", "auditedPrior", "期初余额", _G["audited"]),
    ("audited_increase", "S", "formula", "amount", "auditedIncrease", "本期增加", _G["audited"]),
    ("audited_decrease", "T", "formula", "amount", "auditedDecrease", "本期减少", _G["audited"]),
    ("audited_end", "U", "formula", "amount", "auditedEnd", "期末余额", _G["audited"]),
    ("purpose", "V", "editable", "text", "purpose", "借款用途", ""),
    ("guarantee", "W", "editable", "text", "guarantee", "保证人/抵押物/质押物", ""),
    ("contract_no", "X", "editable", "text", "contractNo", "借款合同（索引）", ""),
    ("is_overdue", "Y", "editable", "text", "isOverdue", "是否逾期", ""),
    ("confirmation_ref", "Z", "editable", "text", "confirmationRef", "询证函（索引）", ""),
    ("credit_report_checked", "AA", "editable", "text", "creditReportChecked", "与征信报告核对(√)", ""),
    ("remark", "AB", "editable", "text", "remark", "备注", ""),
)

#: 五个公式列的模板形态（负债口径：期末 = 期初 + 增加 − 减少）。
FORMULA_TEMPLATES: Final[Mapping[str, str]] = {
    "K": "=H{row}+I{row}-J{row}",
    "R": "=H{row}+L{row}+M{row}",
    "S": "=I{row}+N{row}+P{row}",
    "T": "=J{row}+O{row}+Q{row}",
    "U": "=R{row}+S{row}-T{row}",
}
FORMULA_COLUMNS: Final[tuple[str, ...]] = tuple(FORMULA_TEMPLATES)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 单一权威声明（引擎行为全由本 spec 驱动，provider 不手写 mask / 字段展开）
# ═══════════════════════════════════════════════════════════════════════════

SPEC_L12: Final[RowTableSheetSpec] = RowTableSheetSpec(
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
    #: 🔴 L1 无账龄组（与 D3/D6/D7 的关键差异）—— 两级表头纯粹是「调整类型 × 增减方向」。
    aging_layout=None,
    aging_groups=(),
    footer_marker=FOOTER_MARKER,
    #: footer H26~U26 连续 14 列全是 `=SUM(X10:X25)` ⇒ 真有公式。
    footer_carries_total_formula=True,
    #: 🔴 **L1 是本引擎首个 footer 标签不在 A 列的表**：A26 为空、标签在 C26。
    #: 框架层此前把 `search_column` 硬编码成 "A"，会让 `_find_marker_row` 找不到 marker
    #: 并抛 `FooterAnchorDriftError`（d3-05 踩过同一坑）⇒ 已补 `footer_search_column` 声明位。
    footer_search_column="C",
    error_label="L1-2 明细表",
    #: 🔴 锚点取第 2 位 `bank`（贷款单位，真业务名称）：
    #: [0] `seq_no` 是整数序号（`0` 是合法真值不是"空"信号，同 d6 不可用）；
    #: [1] `loan_type` 是枚举（同 d5 的 `category`，枚举不适合当幽灵行锚点）。
    ghost_row_anchor_index=2,
)

#: 28 个受管字段（6 元组视图），由框架层现算 —— provider 不复制展开结果。
MANAGED_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str], ...]] = tuple(
    row[:6] for row in _engine_managed_field_specs(SPEC_L12)
)

#: 五个公式列的只读区域，由框架层 property 现算。
FORMULA_MASK: Final[tuple[str, ...]] = SPEC_L12.formula_mask

#: column_key → 组标题单元格（只有 H..U 十四列有）。
GROUP_HEADER_CELLS: Final[Mapping[str, str]] = {
    row[0]: row[6] for row in MANAGED_FIELD_SPECS_7 if row[6]
}

_HTML_STORE_NOTE: Final[str] = (
    "整张短期借款明细表存成这一条 item 的 remark（JSON 数组字符串，useL1Detail 的 "
    "JSON.stringify(rows)）。本契约按 stable field + row rowId 拆开。🔴 旧形态是 "
    "`L1-det-{rowIndex+1}-{field}` **位置化行身份**（removeRow 后 _triggerSaveAll 重建整个"
    "序列 ⇒ 删中间行会让后续行 item_id 全部错位），contract schema 明令拒绝 index/ordinal ⇒ "
    "已切稳定 rowId。真库 `L1-det-*` 现算 0 行，零迁移负担。🔴 前端 DetailRow 的 "
    "`amount` / `currency` 模板无对应列 ⇒ 保留为 HTML-only，不入契约。"
)

_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐格实测权威模板 L/L1 短期借款.xlsx（13 sheet，sha256 78033d80）的受管 sheet "
    "明细表L1-2：两级表头 行 8（组标题 序号/借款种类/贷款单位/起始日期/讫止日期/年利率/"
    "固定浮动利率/未审数/期初调整/账项调整/重分类调整/审定数/借款用途/保证人/借款合同/"
    "是否逾期/询证函/征信核对/备注）+ 行 9（叶子 期初余额/本期增加/本期减少/期末余额 等），"
    "30 列 A-AD（有效业务列到 AB），数据区 10-25，footer 26 —— 🔴 footer 标签在 C26「合计」"
    "（A26 为空，非 d6 的 A 列 3 空格形态），H26~U26 连续 14 列全 =SUM(X10:X25)；"
    "五个公式列逐行 K=H+I-J / R=H+L+M / S=I+N+P / T=J+O+Q / U=R+S-T（负债口径 期初+增加-减少，"
    "与前端 calcLiabilityEndBalance 语义一致）。册内零 Excel Table、零 definedName ⇒ "
    "GT_L12_ROWS 为本契约新建、UUID 列取 max_column+1 = AE。整册裸 IF 112 格全在别的 sheet，"
    "受管表零命中（per-file 策略仍挂中性化）。字段键与前端 useL1FormData.DetailRow 对齐："
    "12 个已存在，16 个按模板列补齐（含 R/S/T/U 审定数四列 —— 缺它们审定表L1-1 的 SUMIF "
    "无从取数）。🔴 canary 不选 审定表L1-1：该表 R7~R11 无一个可输入格（全 SUMIF/加总/裸 IF）。"
)
