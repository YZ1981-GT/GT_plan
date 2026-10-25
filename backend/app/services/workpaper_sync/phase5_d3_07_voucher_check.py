# -*- coding: utf-8 -*-
"""D3-7「预收账款检查表」（凭证抽查）—— sheet 层薄声明（**双区**，Task 11）。

spec: d3-sync-coverage-via-row-table-engine · Task 11 · Requirements 3.1
几何证据: .kiro/specs/d3-sync-coverage-via-row-table-engine/evidence/task1-sheet-morphology-and-geometry.md
        + .kiro/specs/.../evidence/task10-d3-05-footer-anchor-investigation.md §5（合计行 A~R 精确文本）
        + .kiro/specs/.../evidence/task11-d3-07-dual-zone-declaration.md（本任务 openpyxl 独立复核）

═══ 形态判定（Task 1 已判，本任务独立 openpyxl 复核一致）═══

区①「（1）本期增减变动检查」/ 区②「（2）期后结转检查」两区均为标准 `excel_table` UUID 动态
行（`row_identity_key='rowId'`）——两区数据行 A 列空白无固定文字标签、前端 `useD3VoucherCheck.ts`
的 `currentRows`/`postRows` 是任意长度数组，无固定长度常量约束。这是 D3 六张里几何最规整的
一张：两区 SUM 区间与数据区行数逐项对齐、无 D3-6 那种落差，A 列合计行是精确「合计」两字（可被
`_find_marker_row` 命中），也无 D3-5 那种 marker 缺失、更无 D3-4 那种 BP-21 排版占位行问题
（本任务已用 openpyxl 逐格确认，见下文「BP-21 末行核查」）。

⇒ 声明两个标准 `RowTableSheetSpec`（`binding_kind` 默认 `excel_table`），共享同一
   `SHEET_KEY_D307="d37-managed"`（同 managed_sheet），各自独立 UUID 列 / table_key /
   store_item_id / 行段 / **field_specs**（🔴 两区并非结构全同，见下文「两区列语义差异」）。

═══ 几何（openpyxl 直读实测，Task 1 + Task 10 §5 + 本任务独立复核三方一致）═══

**两级表头**（不同于 D3-4/D3-5 的单级表头——本任务独立复核发现，Task 1 只标了行段没标两级）：
组标题行（区① R15 / 区② R29）+ 叶子行（区① R16 / 区② R30）。组标题的合并跨列：
  区①：`A15:A16`(客户名称) `B15:H15`(记账凭证组) `I15:I16`(支持性文件) `J15:N15`(核对内容组)
        `O15:O16`(索引号) `P15:P16`(是否异常) `Q15:Q16`(备注说明)
  区②：`A29:A30`(客户名称) `B29:G29`(记账凭证组) `H29:I30`(支持性文件，🔴 H:I 合并两行两列)
        `J29:N29`(核对内容组) `O29:O30`(索引号) `P29:P30`(是否异常) `Q29:Q30`(备注说明)

区①（本期增减变动检查）：
  数据区 R17-26（**10 行**模板占位，A..R 逐格实测全为 None——非 BP-21 续行省略号占位行）
  合计行 R27：`A27='合计'`（精确两字）`G27='=SUM(G17:G26)'` `H27='=SUM(H17:H26)'`
  ⇒ store 键 `D3-vc-current-rows`（`useD3VoucherCheck.ts` ITEM_ID_CURRENT_ROWS）

区②（期后结转检查）：
  数据区 R31-38（**8 行**模板占位，A..R 逐格实测全为 None——非 BP-21 占位行；🔴 H:I 逐行合并
  `H31:I31`…`H38:I38`）
  合计行 R39：`A39='合计'`（精确两字）`G39='=SUM(G31:G38)'`（H39:I39 合并，值 None——区②只有
  G 列一列 SUM，与区①的 G+H 双列 SUM 不同）
  ⇒ store 键 `D3-vc-post-rows`（`useD3VoucherCheck.ts` ITEM_ID_POST_ROWS）

═══ 🔴 两区列语义差异（本任务独立复核发现，不能照 D3-4 那样两区共用 field_specs）═══

D3-4 双区共用一份 `FIELD_SPECS_D304`（两区同一份单级表头，只是行段不同）。D3-7 **不能这样**——
两区叶子行（R16 / R30）的 G/H 列语义不同：
  区① R16：G='借方金额' H='贷方金额'（借贷两列分列，合计行 G27/H27 各自 SUM）
  区② R30：G='贷方金额'，H:I 合并为单列'支持性文件'（区② 无借方列，合计行只 G39 一列 SUM）
⇒ 两区各声明一份 field_specs（`FIELD_SPECS_CURRENT` / `FIELD_SPECS_POST`），共用 `_base_spec()`
   骨架（同 D3-4 `_base_spec()` 手法，只是把 field_specs 也参数化，因为两区不同构）。

**🔴 合并列 H:I 的处置（Task 11 原文要求，参照 E1-02 `HTML_ONLY_ROWS`/合并列范式）**：区②
`支持性文件` 是 `H:I` 合并格——值写**主列 H**（合并块左上角），**不把 I 声明成独立字段**
（同 openpyxl 合并块语义：合并块的值只在左上角 cell，I 列在合并块内是空 anchor）。区① `支持性
文件` 落在单列 I（`I15:I16` 只跨行不跨列），故区① I 是独立字段、区② 无独立 I 字段。

**核对内容 J..N（5 子列）**：两区叶子行 J-N 分别是数字 1/2/3/4/5（`核对内容` 组下的 5 个抽查
勾选子列），逐列声明为 `check1`..`check5` 五个字段（editable text，勾选标记如 √）。

═══ 数据行区间内无任何公式（区① 17-26 / 区② 31-38）═══

🔴 本任务独立扫描全表 19 处公式坐标（7 处页眉引用 `A3/F3/I3/Q3/A4/F4/I4` + 3 处 footer SUM
`G27/H27/G39` + 9 处比例检查块 `E42/F42/G42/E43/F43/G43/E44/F44/G44`），逐行确认区①（17-26）
与区②（31-38）数据行区间内**无一处公式**。⇒ 两区 field_specs 全部业务列均 editable、**不传**
`formula_columns`（沿用引擎默认空 tuple，`formula_mask` 现算为空——同 D3-4 段②/D3-5 处置：无
数据行列向公式的区不传 formula_columns，不是遗漏）。合计行 SUM 属 footer 层，由
`footer_carries_total_formula=True` 表达（两区合计行都真有 SUM 公式），不进 formula_columns。

═══ note/conclusion 字段（登记，不进 field_specs）═══

A40「三、审计说明：」+ A45「2.……」+ A46「四、审计结论：」落在区②合计行（39）+ 比例检查块
（41-44）之下，属 Task 1「footer 下 note/conclusion 与插行 fail-closed 冲突」登记的 HTML-only
候选（同 D3-4/D3-5/D3-6/D4-5 判例）。**不进**本文件两个 `RowTableSheetSpec` 的 field_specs。

═══ 比例检查块（41-44）不是第三个受管区（登记，纯派生）═══

R41-44 是「检查比例」计算块：`F42='=G27'`/`F43='=H27'`/`F44='=G39'`（引用本表两区合计行）+
`E42..E44` 跨 sheet 引用 `'预收账款明细表D3-2'!M24/N24/T24`（D3-2 footer 行）+ `G42..G44` 是
`=ROUND(...)` 比例。E/F/G 三列全是公式、无行维度、用户不可增删 ⇒ 纯派生汇总，不受管
（同 Task 1 结论「区②之后的比例检查块…不是第三个受管区」）。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_D307_CURRENT",
    "SPEC_D307_POST",
    "SPECS_D307",
    "MANAGED_SHEET_D307",
]

MANAGED_SHEET_D307: Final[str] = "预收账款检查表D3-7"
TEMPLATE_ID_D307: Final[str] = "D37"
#: 🔴 单一共享 sheet_key（同 managed_sheet；两区归一个契约 sheet 条目含两 table，同 D3-4）。
SHEET_KEY_D307: Final[str] = "d37-managed"

#: 区①（本期增减变动检查）：两级表头 15/16，数据区 17-26（10 行），合计行 27。
HEADER_GROUP_ROW_CURRENT: Final[int] = 15
HEADER_LEAF_ROW_CURRENT: Final[int] = 16
FIRST_DATA_ROW_CURRENT: Final[int] = 17
LAST_DATA_ROW_CURRENT: Final[int] = 26
FOOTER_ROW_CURRENT: Final[int] = 27

#: 区②（期后结转检查）：两级表头 29/30，数据区 31-38（8 行），合计行 39。
HEADER_GROUP_ROW_POST: Final[int] = 29
HEADER_LEAF_ROW_POST: Final[int] = 30
FIRST_DATA_ROW_POST: Final[int] = 31
LAST_DATA_ROW_POST: Final[int] = 38
FOOTER_ROW_POST: Final[int] = 39

#: footer marker 两区都是精确「合计」两字（Task 10 §5 + 本任务独立复核，A27/A39 逐字）。
FOOTER_MARKER_D307: Final[str] = "合计"

#: 🔴 两区各用不同 UUID 列（D1-4/D3-4/D4-9 教训：同列会让行身份串区）。R/S/T/U 在 R14-44
#: 实测全空（本任务独立复核确认），受管业务列止于 Q（备注说明）⇒ R 是最靠近数据区的候选空列
#: （同 D3-5 选 I、D3-6 选 K 的"最近空列"原则）。区① UUID=R / 区② UUID=S（各异）。
UUID_COL_CURRENT: Final[str] = "R"
UUID_COL_POST: Final[str] = "S"

#: 区①字段（7 元组，第 7 位 group_header_cell）。叶子行 R16 逐格实测：
#:   A(客户名称,A15:A16 组标题) B(日期) C(凭证编号) D(业务内容) E(对方科目) F(对方明细科目)
#:   G(借方金额) H(贷方金额) —— B..H 同属 R15 组标题「记账凭证」(B15:H15)
#:   I(支持性文件,I15:I16 组标题，单列不跨列) J..N(核对内容 1..5，同属 R15 组标题 J15:N15)
#:   O(索引号,O15:O16) P(是否异常,P15:P16) Q(备注说明,Q15:Q16)
#: 数据行区间(17-26)内逐行无公式 ⇒ 全部 editable，不传 formula_columns。
FIELD_SPECS_CURRENT: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("customer_name", "A", "editable", "text", "customerName", "客户名称", ""),
    ("voucher_date", "B", "editable", "text", "voucherDate", "日期", f"B{HEADER_GROUP_ROW_CURRENT}"),
    ("voucher_no", "C", "editable", "text", "voucherNo", "凭证编号", f"B{HEADER_GROUP_ROW_CURRENT}"),
    ("business_content", "D", "editable", "text", "businessContent", "业务内容", f"B{HEADER_GROUP_ROW_CURRENT}"),
    ("counter_account", "E", "editable", "text", "counterAccount", "对方科目", f"B{HEADER_GROUP_ROW_CURRENT}"),
    ("counter_sub_account", "F", "editable", "text", "counterSubAccount", "对方明细科目", f"B{HEADER_GROUP_ROW_CURRENT}"),
    ("debit_amount", "G", "editable", "amount", "debitAmount", "借方金额", f"B{HEADER_GROUP_ROW_CURRENT}"),
    ("credit_amount", "H", "editable", "amount", "creditAmount", "贷方金额", f"B{HEADER_GROUP_ROW_CURRENT}"),
    ("supporting_doc", "I", "editable", "text", "supportingDoc", "支持性文件", ""),
    ("check1", "J", "editable", "text", "check1", "核对内容1", f"J{HEADER_GROUP_ROW_CURRENT}"),
    ("check2", "K", "editable", "text", "check2", "核对内容2", f"J{HEADER_GROUP_ROW_CURRENT}"),
    ("check3", "L", "editable", "text", "check3", "核对内容3", f"J{HEADER_GROUP_ROW_CURRENT}"),
    ("check4", "M", "editable", "text", "check4", "核对内容4", f"J{HEADER_GROUP_ROW_CURRENT}"),
    ("check5", "N", "editable", "text", "check5", "核对内容5", f"J{HEADER_GROUP_ROW_CURRENT}"),
    ("index_no", "O", "editable", "text", "indexNo", "索引号", ""),
    ("is_abnormal", "P", "editable", "text", "isAbnormal", "是否异常", ""),
    ("remark", "Q", "editable", "text", "remark", "备注说明", ""),
)

#: 区②字段（7 元组）。叶子行 R30 逐格实测，与区①的差异：
#:   G(贷方金额，区② 无借方列) · H:I 合并为单列「支持性文件」(H29:I30) ⇒ 值写主列 H、**不**
#:   声明 I 独立字段（合并块语义，见模块 docstring "合并列 H:I 的处置"）。
#:   B..G 同属 R29 组标题「记账凭证」(B29:G29) · J..N 核对内容 · O/P/Q 同区①。
#: 数据行区间(31-38)内逐行无公式 ⇒ 全部 editable，不传 formula_columns。
FIELD_SPECS_POST: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("customer_name", "A", "editable", "text", "customerName", "客户名称", ""),
    ("voucher_date", "B", "editable", "text", "voucherDate", "日期", f"B{HEADER_GROUP_ROW_POST}"),
    ("voucher_no", "C", "editable", "text", "voucherNo", "凭证编号", f"B{HEADER_GROUP_ROW_POST}"),
    ("business_content", "D", "editable", "text", "businessContent", "业务内容", f"B{HEADER_GROUP_ROW_POST}"),
    ("counter_account", "E", "editable", "text", "counterAccount", "对方科目", f"B{HEADER_GROUP_ROW_POST}"),
    ("counter_sub_account", "F", "editable", "text", "counterSubAccount", "对方明细科目", f"B{HEADER_GROUP_ROW_POST}"),
    ("credit_amount", "G", "editable", "amount", "creditAmount", "贷方金额", f"B{HEADER_GROUP_ROW_POST}"),
    # 🔴 支持性文件 = H:I 合并单列，值写主列 H；I 不声明为独立字段（合并块语义）。
    ("supporting_doc", "H", "editable", "text", "supportingDoc", "支持性文件", ""),
    ("check1", "J", "editable", "text", "check1", "核对内容1", f"J{HEADER_GROUP_ROW_POST}"),
    ("check2", "K", "editable", "text", "check2", "核对内容2", f"J{HEADER_GROUP_ROW_POST}"),
    ("check3", "L", "editable", "text", "check3", "核对内容3", f"J{HEADER_GROUP_ROW_POST}"),
    ("check4", "M", "editable", "text", "check4", "核对内容4", f"J{HEADER_GROUP_ROW_POST}"),
    ("check5", "N", "editable", "text", "check5", "核对内容5", f"J{HEADER_GROUP_ROW_POST}"),
    ("index_no", "O", "editable", "text", "indexNo", "索引号", ""),
    ("is_abnormal", "P", "editable", "text", "isAbnormal", "是否异常", ""),
    ("remark", "Q", "editable", "text", "remark", "备注说明", ""),
)


def _base_spec(
    *,
    section: str,
    table_key: str,
    store_item_id: str,
    header_group_row: int,
    header_leaf_row: int,
    first_data_row: int,
    last_data_row: int,
    footer_row: int,
    uuid_col: str,
    field_specs: tuple[tuple[str, str, str, str, str, str, str], ...],
) -> RowTableSheetSpec:
    """两区共用骨架，只差几何 / 键 / 身份列 / **field_specs**（🔴 两区不同构，故 field_specs
    也参数化，不同于 D3-4 的两区共用一份——见模块 docstring "两区列语义差异"）。

    两区数据行本身无公式列（合计 SUM 在 footer 行、不在数据行区间），故不传 `formula_columns`
    （默认空 tuple，`formula_mask` property 现算为空）。两级表头传 `header_group_row`/
    `header_leaf_row`（同 E1-02 范式），不传单级 `header_row`。
    """
    return RowTableSheetSpec(
        managed_sheet=MANAGED_SHEET_D307,
        sheet_key=SHEET_KEY_D307,
        table_key=table_key,
        template_id=f"{TEMPLATE_ID_D307}{section.upper()}",
        table_name=f"GT_{TEMPLATE_ID_D307}_{section.upper()}_ROWS",
        uuid_col=uuid_col,
        first_data_row=first_data_row,
        last_data_row=last_data_row,
        footer_row=footer_row,
        header_group_row=header_group_row,
        header_leaf_row=header_leaf_row,
        store_item_id=store_item_id,
        empty_payload="[]",
        row_identity_key="rowId",
        store_kind=StoreKind.rows,
        field_specs=field_specs,
        footer_marker=FOOTER_MARKER_D307,
        # 🔴 两区合计行都真有 SUM 公式（区① G27+H27 / 区② G39）⇒ True。
        footer_carries_total_formula=True,
        error_label=f"D3-7 预收账款检查表（{section}）",
    )


#: 区①：本期增减变动检查（数据行 17-26，UUID 列 R，合计行 27 = G+H 双列 SUM）。
SPEC_D307_CURRENT: Final[RowTableSheetSpec] = _base_spec(
    section="current",
    table_key="voucher_check_current_rows",
    store_item_id="D3-vc-current-rows",
    header_group_row=HEADER_GROUP_ROW_CURRENT,
    header_leaf_row=HEADER_LEAF_ROW_CURRENT,
    first_data_row=FIRST_DATA_ROW_CURRENT,
    last_data_row=LAST_DATA_ROW_CURRENT,
    footer_row=FOOTER_ROW_CURRENT,
    uuid_col=UUID_COL_CURRENT,
    field_specs=FIELD_SPECS_CURRENT,
)

#: 区②：期后结转检查（数据行 31-38，UUID 列 S，合计行 39 = G 单列 SUM；H:I 合并支持性文件）。
SPEC_D307_POST: Final[RowTableSheetSpec] = _base_spec(
    section="post",
    table_key="voucher_check_post_rows",
    store_item_id="D3-vc-post-rows",
    header_group_row=HEADER_GROUP_ROW_POST,
    header_leaf_row=HEADER_LEAF_ROW_POST,
    first_data_row=FIRST_DATA_ROW_POST,
    last_data_row=LAST_DATA_ROW_POST,
    footer_row=FOOTER_ROW_POST,
    uuid_col=UUID_COL_POST,
    field_specs=FIELD_SPECS_POST,
)

#: 双区清单（顺序即 Excel 行序：区①在区②之上）。
SPECS_D307: Final[tuple[RowTableSheetSpec, ...]] = (
    SPEC_D307_CURRENT,
    SPEC_D307_POST,
)
