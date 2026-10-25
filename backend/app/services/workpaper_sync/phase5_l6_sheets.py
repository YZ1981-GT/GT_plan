# -*- coding: utf-8 -*-
"""L6 专项应付款（科目 2711）—— 受管 `明细表L6-2` 的身份/几何/字段声明。

spec: l6-true-bidirectional-2026-10-01 · 第3步（选型见 `.agents/tasks/l6-managed-table-choice/report.md`）

选型现算：L6-2 明细表是 L6 整册唯一的数据录入源（审定表 L6-1 / 两张附注 / 检查表 L6-4
全部跨 sheet 引用 `明细表L6-2`），HTML 子组件 `L6TabDetail.vue` 是其忠实渲染（24 有效业务列
A~X 语义逐列对齐、行动态、公式一致、持久化已是单 item JSON 数组 `L6-L6-2-rows`）。

几何（openpyxl 逐格实测，sha 08630e1c…；禁照抄 L7 常量）：两级表头 r8（组标题 序号/项目/
未审数/期初调整/账项调整/重分类调整/审定数/文件依据/索引号/拨款项目的完成情况/备注）+ r9
（叶子 期初余额/本期拨入/本期结转/本期返还/期末余额 等），数据区 r10~r19（10 行，A 列预置
1~10 整数序号骨架），footer r20 标签在 **A20「合计」**（C20~T20 连续 =SUM(..10:..19)），
r21「三、审计说明：」之下不受管。有效业务列 A..X（24 列）；物理 max_column=33(AG)（Y..AG
全空，源于标题合并/样式延伸）⇒ UUID 列取物理 max_col 右侧首个空列 = **AH**（避开 M~X，M~X 落
13~24 列，在业务列 A~X 内）。六个公式列 G/P/Q/R/S/T 逐行
G=C+D-E-F / P=C+H+I / Q=D+J+M / R=E+K+N / S=F+L+O / T=P+Q-R-S（负债口径）。
受管表零裸 IF（整册裸 IF 仅 审定表L6-1 11 格，per-file 中性化照挂）。

🔴 列语义错位（如实登记，不影响往返正确性）：HTML `L6DetailRow` 的调整区按
AJE×4(ajeBegin/ajeCredit/ajeCarryFwd/ajeRefund) + RJE×4(rjeBegin/rjeCredit/rjeCarryFwd/rjeRefund)
分组，而 Excel 调整区按 期初调整 H/I + 账项调整 J/K/L + 重分类调整 M/N/O 分组（维度不同）。
契约按**列位置**搬运（json_key 对齐前端存储、header_text 忠于模板），两者位置一一对应，往返
不受影响；header_text 仅用于契约文档/校验，不改 UI 显示。前端 fundSource/approvalNo/purpose
三字段无模板对应列 ⇒ HTML-only，不受管、不进契约。

🔴 sanitize 非必需（实测）：受管 sheet 的 `<f t="shared">` = 0、整册无 external/OLE，故用原始
sha，不展开共享公式组（报告 §四猜测的「打印副本镜像公式 + 横向共享组」在实测中不存在）。
"""
from __future__ import annotations

from typing import Final, Mapping

from app.services.workpaper_sync.models import AuthorityModel
from app.services.workpaper_sync.phase5_row_table_sheet import RowTableSheetSpec, StoreKind
from app.services.workpaper_sync.phase5_row_table_sheet import managed_field_specs as _fields

PHASE5_WAVE: Final[str] = "l_cycle_special_payables"
ENTRY_ID: Final[str] = "xlsx/gt-l6-special-payables"
ADAPTER_ID: Final[str] = "l6.special_payables"
#: manifest 冻结的 wp_code_pattern（宿主 GtL6SpecialPayables CamelCase 幻影码，finder 零命中）。
#: 现算：manifest `wp_code_patterns == ['L6S']`（与 L7 的 L7O 同型）。
WP_CODES: Final[frozenset[str]] = frozenset({"L6S"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "L/L6 专项应付款.xlsx"
#: 🔴 现算 sha（`_l6p_probe.py`）；受管 sheet 无共享公式组 ⇒ 不 sanitize，用原始字节。
TEMPLATE_SHA256: Final[str] = "08630e1cbc962fabbbf580f591374157a2d6705966c2f3c8ecba4a0705f59f62"
MANAGED_SHEET: Final[str] = "明细表L6-2"
TEMPLATE_ID: Final[str] = "L62"
SHEET_KEY: Final[str] = f"{TEMPLATE_ID.lower()}-managed"
ROWS_TABLE_KEY: Final[str] = "special_payable_detail_rows"
TABLE_NAME: Final[str] = f"GT_{TEMPLATE_ID}_ROWS"
AUTHORITY_MODEL: Final[AuthorityModel] = AuthorityModel.projection_contract
HEADER_GROUP_ROW: Final[int] = 8
HEADER_LEAF_ROW: Final[int] = 9
FIRST_DATA_ROW: Final[int] = 10
LAST_DATA_ROW: Final[int] = 19
FOOTER_ROW: Final[int] = 20
#: 有效业务列右边界 X（A~X 共 24 列；Y..AG 物理存在但全空）。
MANAGED_LAST_COL: Final[str] = "X"
#: 🔴 UUID 列 = 物理 max_col(AG=33) 右侧首个真正空列 = AH（现算，禁照抄 L7 的 AB）。
UUID_COL: Final[str] = "AH"
FOOTER_MARKER: Final[str] = "合计"
STORE_ITEM_ID: Final[str] = "L6-L6-2-rows"
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
ROW_IDENTITY_STORE_KEY: Final[str] = "rowId"
#: 前端 fundSource/approvalNo/purpose 三字段无模板列 ⇒ HTML-only，不受管。
HTML_ONLY_ROW_KEYS: Final[tuple[str, ...]] = ("fundSource", "approvalNo", "purpose")

#: 组标题单元格（两级表头第一维）：C/H/J/M/P 五个 merged 组（r8 组标题行）。A/B/U/V/W/X 无组。
_G: Final[Mapping[str, str]] = {
    "unadjusted": f"C{HEADER_GROUP_ROW}",   # C8:G8「未审数」
    "prior_adj": f"H{HEADER_GROUP_ROW}",     # H8:I8「期初调整」
    "aje": f"J{HEADER_GROUP_ROW}",           # J8:L8「账项调整」
    "rje": f"M{HEADER_GROUP_ROW}",           # M8:O8「重分类调整」
    "audited": f"P{HEADER_GROUP_ROW}",       # P8:T8「审定数」
}

#: 24 个受管字段，7 元组 `(column_key, 列标, mode, value_type, store json 键, 表头文本, 组标题单元格)`，
#: 顺序即 Excel 列序 A→X。
#: 🔴 json_key 对齐前端 `useL6Detail.L6DetailRow`（camelCase）—— 按**列位置**搬运（差异点4）。
#: 🔴 G/P/Q/R/S/T 六列 mode=formula —— 模板里逐行有真公式，OO 侧不得被值覆盖。
#: 🔴 有组标题的列（C..T）header_text 取**叶子行** r9 文本，无组的（A/B/U/V/W/X）取组标题行 r8 文本。
MANAGED_FIELD_SPECS_7: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("seq", "A", "editable", "amount", "seq", "序号", ""),
    ("item_name", "B", "editable", "text", "project", "项目", ""),
    ("begin_balance", "C", "editable", "amount", "beginBalance", "期初余额", _G["unadjusted"]),
    ("credit_in", "D", "editable", "amount", "creditIn", "本期拨入", _G["unadjusted"]),
    ("carry_forward", "E", "editable", "amount", "carryForward", "本期结转", _G["unadjusted"]),
    ("refund", "F", "editable", "amount", "refund", "本期返还", _G["unadjusted"]),
    ("end_balance", "G", "formula", "amount", "endBalance", "期末余额", _G["unadjusted"]),
    ("prior_aje", "H", "editable", "amount", "ajeBegin", "账项调整", _G["prior_adj"]),
    ("prior_rje", "I", "editable", "amount", "rjeBegin", "重分类调整", _G["prior_adj"]),
    ("aje_credit", "J", "editable", "amount", "ajeCredit", "本期拨入", _G["aje"]),
    ("aje_carry_forward", "K", "editable", "amount", "ajeCarryFwd", "本期结转", _G["aje"]),
    ("aje_refund", "L", "editable", "amount", "ajeRefund", "本期返还", _G["aje"]),
    ("rje_credit", "M", "editable", "amount", "rjeCredit", "本期拨入", _G["rje"]),
    ("rje_carry_forward", "N", "editable", "amount", "rjeCarryFwd", "本期结转", _G["rje"]),
    ("rje_refund", "O", "editable", "amount", "rjeRefund", "本期返还", _G["rje"]),
    ("audited_begin", "P", "formula", "amount", "auditedBegin", "期初余额", _G["audited"]),
    ("audited_credit", "Q", "formula", "amount", "auditedCredit", "本期拨入", _G["audited"]),
    ("audited_carry_forward", "R", "formula", "amount", "auditedCarryFwd", "本期结转", _G["audited"]),
    ("audited_refund", "S", "formula", "amount", "auditedRefund", "本期返还", _G["audited"]),
    ("audited_end", "T", "formula", "amount", "auditedEnd", "期末余额", _G["audited"]),
    ("doc_ref", "U", "editable", "text", "docRef", "文件依据", ""),
    ("index_ref", "V", "editable", "text", "indexRef", "索引号", ""),
    ("completion_status", "W", "editable", "text", "completionStatus", "拨款项目的完成情况", ""),
    ("remark", "X", "editable", "text", "remark", "备注", ""),
)

#: 六个公式列的模板形态（负债口径，逐格实测）。
FORMULA_TEMPLATES: Final[Mapping[str, str]] = {
    "G": "=C{row}+D{row}-E{row}-F{row}",
    "P": "=C{row}+H{row}+I{row}",
    "Q": "=D{row}+J{row}+M{row}",
    "R": "=E{row}+K{row}+N{row}",
    "S": "=F{row}+L{row}+O{row}",
    "T": "=P{row}+Q{row}-R{row}-S{row}",
}
FORMULA_COLUMNS: Final[tuple[str, ...]] = tuple(FORMULA_TEMPLATES)

SPEC_L62: Final[RowTableSheetSpec] = RowTableSheetSpec(
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
    #: L6-2 无账龄组 —— 两级表头是「调整类型 × 增减方向」。
    aging_layout=None,
    aging_groups=(),
    footer_marker=FOOTER_MARKER,
    #: footer C20~T20 连续 =SUM(X10:X19) ⇒ 真有公式。
    footer_carries_total_formula=True,
    #: 🔴 footer 标签在 A20「合计」。
    footer_search_column="A",
    error_label="L6-2 专项应付款明细表",
    #: 🔴 锚点取第 1 位 item_name（B 列项目名，真业务文本）—— A 列是整数序号（0 是合法真值不是
    #: 空信号，照 D5/D6 的 seq_no 处置），不能当锚点。
    ghost_row_anchor_index=1,
)

#: 24 个受管字段（6 元组视图），由框架层现算 —— provider 不复制展开结果。
MANAGED_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str], ...]] = tuple(
    row[:6] for row in _fields(SPEC_L62)
)

#: 六个公式列的只读区域，由框架层 property 现算。
FORMULA_MASK: Final[tuple[str, ...]] = SPEC_L62.formula_mask

#: column_key → 组标题单元格（只有 C..T 有）。
GROUP_HEADER_CELLS: Final[Mapping[str, str]] = {
    row[0]: row[6] for row in MANAGED_FIELD_SPECS_7 if row[6]
}

_HTML_STORE_NOTE: Final[str] = (
    "整张 L6-2 明细表存成 `L6-L6-2-rows` 的 remark JSON 数组（useL6Detail 的 "
    "JSON.stringify(detailRows)）；每行已有稳定 rowId（2026-10-01 把私有 Date.now+Math.random "
    "生成器换成平台共享 newRowIdentity('l62det')，已有 rowId 优先不重铸）。契约按 stable "
    "field + row rowId 拆开。store 键是单键 `L6-L6-2-rows`（非 L7 的 -full-data）。sibling 键 "
    "`L6-L6-2-row-N-end_balance`（供 CrossSheet 读）本轮不受管、不预登记。真库 `L6-L6-2-%` "
    "现算 0 行，零迁移负担。🔴 前端 fundSource/approvalNo/purpose 三字段无模板对应列 ⇒ "
    "HTML-only（不入契约，merge 不触碰，保留）。"
)
_REVIEWED_BASIS: Final[str] = (
    "2026-10-01 openpyxl 逐格实测 L/L6 专项应付款.xlsx（9 sheet，sha 08630e1c…）：受管 "
    "明细表L6-2 两级表头 r8（组标题 序号/项目/未审数/期初调整/账项调整/重分类调整/审定数/"
    "文件依据/索引号/拨款项目的完成情况/备注）+ r9 叶子、数据区 r10~r19（10 行，A 列预置 1~10 "
    "整数序号骨架）、footer A20「合计」（C20~T20 连续 =SUM(X10:X19)）、A..X 24 字段按列位置与前端 "
    "L6DetailRow 对齐（fundSource/approvalNo/purpose HTML-only）、六个公式列 "
    "G=C+D-E-F / P=C+H+I / Q=D+J+M / R=E+K+N / S=F+L+O / T=P+Q-R-S（负债口径）；物理 "
    "max_column=AG(33)（Y..AG 全空）故 UUID 列取右侧首个空列 AH；manifest 幻影码 L6S finder "
    "零命中。受管表零裸 IF（整册裸 IF 仅 审定表L6-1 11 格，per-file 中性化照挂）。canary 不选 "
    "审定表L6-1（R7~R16 全跨 sheet 公式，下游视图非录入表）。科目 2711 专项应付款（"
    "l6AccountScope.L6_GROSS_FALLBACK_STANDARD）。sanitize 非必需：受管 sheet 共享公式组 0、"
    "整册无 external/OLE，用原始字节。A 列预置序号的行身份对齐已在真 OO 往返里核（行命中数"
    "==输入数，无幽灵行）。"
)
