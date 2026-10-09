# -*- coding: utf-8 -*-
"""D3-6「关联关系及交易检查表」—— sheet 层薄声明（D3 首张接入，单区最简样本）。

spec: d3-sync-coverage-via-row-table-engine · Task 6 · Requirements 1.1 / 1.2 / 1.3
几何证据: .kiro/specs/d3-sync-coverage-via-row-table-engine/evidence/task1-sheet-morphology-and-geometry.md

═══ 为什么它排 D3 接入首张 ═══

单区最简（六张待接入 sheet 里几何最小、形态最不含糊）：证明「一个 entry 多受管 sheet」在 D3
上成立、失败面最小（若挂，挂的是这一个 binding，灰度开关可立即关掉），且不依赖任何双区位移链
能力（那要等 D3-4/D3-7 才验）。

═══ 形态判定（Task 1 已判，本任务实测复核一致）═══

openpyxl 直读权威模板（`backend/wp_templates/D/D3 预收账款.xlsx`）逐格实测：数据区行 12-16
（**5 行模板占位，A 列无预填文字标签** —— 与 D3-1 那种"预收销售固定资产款"等固定文字标签的
稳定 key 固定行完全不同），前端 `useD3RelatedParty.ts` docstring 明确"rows reactive（从
D3-rp-rows 加载 JSON）"、无固定长度常量数组约束。

⇒ 判「**UUID 动态行**」：`row_identity_key='rowId'`（**不是** D1-2 的 `'key'`）、`excel_table`
   binding、行可插删。这与 D1-2 是本 spec 唯一照抄 D1-2 结构但**不照抄**其行身份形态的地方。

═══ 几何（逐格实测，禁推演）═══

单级表头 R11（10 列 A..J，A11='关联方名称'…J11='备注'）· 数据区 R12-16（5 行）· footer R17
「合计」（纯两字无空格）· 公式列仅 **F**（数据行列向）：`=Cn+En-Dn`（期末余额=期初+贷方-借方）。

🔴 **模板本身的预存缺陷（如实记录，不在本任务处理）**：footer R17 的 SUM 公式硬编码只覆盖
   `C12:C14`/`D12:D14`/`E12:E14`/`F12:F14`（3 行，12-14），**没有覆盖到 15-16 两行**——数据区
   模板画了 5 行占位但合计只累加前 3 行。这是模板本身的落差（或"预留 5 行画框但常规业务场景
   只有 3 行"的编制约定），不是本次声明代码的错误。行表引擎的职责就是在插行/接入后重新归一化
   footer 公式的 SUM 区间——这个缺陷理论上会在 Task 7 接入验收时被引擎的区间归一化机制纠正，
   但不能想当然认为"接入后自动就对了"，需要在 Task 7 用真实测试验证。本声明代码**不做任何
   特殊处理**，按 Task 1 实测的公式模板原样声明。

🔴 A2/A3/D3/G3/J3 等页眉引用公式（行 3/4，跨 sheet 引用「底稿目录」+ 页码引用）**不进**
   `formula_columns` —— 那是与 D1-2 的 header_row 组标题无关的另一类公式（页眉装订线），不在
   数据行区间内，本表数据行区间（12-16）唯一逐行有公式的列只有 F。

═══ note/conclusion 字段（登记，不进 field_specs）═══

A18「三、审计说明：」+ A22「四、审计结论：」落在 footer(17) 之下，落在数据区之外，属 Task 1
「footer 下 note/conclusion 与插行 fail-closed 冲突」登记的 HTML-only 候选（同 D4-5 判例）。
B26-B34 是「关联方类型」下拉枚举辅助区（B26='勿改、勿删' 明确的保护性文字标记），不是数据行，
不受本 spec 判定影响。这些字段**不进**本文件的 `field_specs`——受管字段只覆盖数据区（12-16）
内实测有列语义的 10 列（A-J）。

═══ 模板缺陷修复（Task 10 第 3c 段，用户批准"修模板"）═══

🔴 上文「footer R17 的 SUM 只覆盖 12-14 三行、漏 15-16」的预存缺陷**已被修正**：Task 7 曾只做注入 +
`verify_unmanaged_regions(before=after)`、从未跑过 materialize；Task 10 整册 materialize 实证该缺陷令
`assert_footer_formula_covers_managed_rows` 覆盖门每次都抛 `FooterFormulaRangeError`（「footer 格 C17 的
公式 SUM(C12:C14) 区间只到 14，而受管行区间已到 16 —— 合计漏算 2 行」，与插不插行无关；见证据
task10-d3-05-footer-anchor-investigation.md §2.2）。Task 10 第 3c 段经用户批准，用
`scripts/fix/fix_d3_template_footer_defects.py` 把 C17/D17/E17/F17 四格 SUM 区间 12:14→12:16（覆盖全部
5 个数据行）：C17 是独立公式直接改，D17:F17 是共享公式组（si=1，master 在 D17），只改 D17 master 的
`SUM(D12:D14)`→`SUM(D12:D16)`，E17/F17 靠列偏移自动派生。修复后覆盖门不再拦，D3-6 可进 materialize。
模板新 sha256=`33165493…`（旧净化值 `699a9be0…`）。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_D306",
    "MANAGED_SHEET_D306",
    "STORE_ITEM_ID_D306",
]

MANAGED_SHEET_D306: Final[str] = "关联关系及交易检查表D3-6"
TEMPLATE_ID_D306: Final[str] = "D36"
SHEET_KEY_D306: Final[str] = "d36-managed"
ROWS_TABLE_KEY_D306: Final[str] = "related_party_rows"
#: 🔴 逐字对照 Task 3 判据文件顶部 REAL_STORE_ITEM_IDS 表实测值——不是 D3-6-rows（裁决 F2）。
STORE_ITEM_ID_D306: Final[str] = "D3-rp-rows"

#: 🔴 UUID 动态行（Task 1 实测确认）—— 不是 D1-2 的稳定 key 固定行。
ROW_IDENTITY_STORE_KEY_D306: Final[str] = "rowId"

HEADER_ROW_D306: Final[int] = 11
FIRST_DATA_ROW_D306: Final[int] = 12
LAST_DATA_ROW_D306: Final[int] = 16
FOOTER_ROW_D306: Final[int] = 17
#: footer marker 实测为纯「合计」两字（无空格），同 D1-2、不同于 D7 的「合   计」。
FOOTER_MARKER_D306: Final[str] = "合计"
MANAGED_LAST_COL_D306: Final[str] = "J"
#: K 列实测全空（K11/K17 均为 None），是最靠近数据区（A-J）的候选空列。
UUID_COL_D306: Final[str] = "K"

#: 10 个受管字段（7 元组，末位 group_header_cell 为 "" —— 单级表头无分组）。
#: 顺序即 Excel 列序 A→J；表头文本与 R11 逐字相等（实测）。
#: F 列模板内逐行有真公式 ⇒ formula；其余 9 列无公式 ⇒ editable。
FIELD_SPECS_D306: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("related_party_name", "A", "editable", "text", "relatedPartyName", "关联方名称", ""),
    ("related_relationship", "B", "editable", "text", "relatedRelationship", "关联关系", ""),
    ("opening_balance", "C", "editable", "amount", "openingBalance", "期初余额", ""),
    ("debit_amount", "D", "editable", "amount", "debitAmount", "借方发生", ""),
    ("credit_amount", "E", "editable", "amount", "creditAmount", "贷方发生", ""),
    ("closing_balance", "F", "formula", "amount", "closingBalance", "期末余额", ""),
    ("aging_info", "G", "editable", "text", "agingInfo", "发生时间及账龄", ""),
    ("transaction_reason", "H", "editable", "text", "transactionReason", "发生原因（款项性质）", ""),
    ("index_no", "I", "editable", "text", "indexNo", "索引号", ""),
    ("remark", "J", "editable", "text", "remark", "备注", ""),
)

#: 公式列 → 数据行公式模板（`{r}` 为行号）。逐格实测（`=Cn+En-Dn`：期末余额=期初+贷方-借方），
#: 已用 openpyxl 独立复核公式方向未反（F12='=C12+E12-D12' 等，逐行同款）。
FORMULA_TEMPLATES_D306: Final[dict[str, str]] = {
    "F": "=C{r}+E{r}-D{r}",
}

SPEC_D306: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_D306,
    sheet_key=SHEET_KEY_D306,
    table_key=ROWS_TABLE_KEY_D306,
    template_id=TEMPLATE_ID_D306,
    table_name=f"GT_{TEMPLATE_ID_D306}_ROWS",
    uuid_col=UUID_COL_D306,
    first_data_row=FIRST_DATA_ROW_D306,
    last_data_row=LAST_DATA_ROW_D306,
    footer_row=FOOTER_ROW_D306,
    header_row=HEADER_ROW_D306,
    store_item_id=STORE_ITEM_ID_D306,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_D306,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_D306,
    formula_columns=("F",),
    formula_templates=FORMULA_TEMPLATES_D306,
    footer_marker=FOOTER_MARKER_D306,
    error_label="D3-6 关联关系及交易检查表",
    # 🔴 formula_mask 不手写——它是引擎 property 现算（Property 5），由 formula_columns ×
    # 数据行区间 [first_data_row, last_data_row] 自动导出，见 phase5_row_table_sheet.py
    # RowTableSheetSpec.formula_mask。
)
