# -*- coding: utf-8 -*-
"""D3-5「账龄1年以上的预收账款检查表」—— sheet 层薄声明（单区，D3 六张里几何最小）。

spec: d3-sync-coverage-via-row-table-engine · Task 9 · Requirements 2.3
几何证据: .kiro/specs/d3-sync-coverage-via-row-table-engine/evidence/task1-sheet-morphology-and-geometry.md

═══ 形态判定（Task 1 已判，本任务独立 openpyxl 复核一致）═══

数据区行 11-13（**仅 3 行模板占位，A 列无预填文字标签** —— 与 D3-1 那种"预收销售固定资产款"
等固定文字标签的稳定 key 固定行完全不同），前端 `useD3LongTerm.ts` docstring 明确"rows
reactive（从 D3-lt-rows 加载 JSON）"、无固定长度常量数组约束。

⇒ 判「**UUID 动态行**」：`row_identity_key='rowId'`、`excel_table` binding（默认值，不显式
   传），行可插删。公式集中在 footer 是因为数据区本身很小（3 行），不是"行不可增删"的证据
   （design.md/Task 1 已阐明：`static_region` 判据是"无行维度"，本表有清晰的行维度——对方
   单位名称/期末余额/账龄/说明 四列一行一条记录，只是行数少）。

═══ 几何（本任务独立 openpyxl 直读复核，不盲信 Task 1 转述）═══

复核命令：`openpyxl.load_workbook(...).load_workbook('账龄1年以上的预收账款检查表D3-5',
data_only=False)`，逐格扫描全表 + 候选空列 I-N + note/conclusion 区。

单级表头 R10（8 列 A..H：A10='对方单位名称' B10='期末余额' C10='账龄' D10='经济业务说明'
E10='未结转或未偿还的原因' F10='至审计日结转或偿还金额' G10='处理计划' H10='备注'）·
数据区 R11-13（3 行，A..H 全部为 `None`，逐格确认）· footer R14「合计」（纯两字无空格，
同 D3-6，A14 本身也是 `None`——marker 落在 A 列由 footer_marker 声明，非本 sheet 该处
实际预填文字，`search_column='A'` 由框架层扫描定位）。

🔴 **数据行区间（11-13）内逐行没有任何公式**——本任务独立扫描全表 9 处公式坐标（`A3/C3/E3/
H3/A4/C4/E4` 七处页眉引用公式 + `B14/F14` 两处 footer SUM 公式），逐行确认 R11/R12/R13
的 A-H 全部为 `None`，无一处公式落在数据行内。⇒ 本文件的 `field_specs` 全部 10 列（8 业务
列，`formula_columns` 传空 tuple（引擎默认值），不传任何列——与"数据行区间内逐行都有公式的
列才进 formula_columns"的纪律一致（同 Task 8 D3-4 段②的处置：无数据行公式的区不传
formula_columns，`formula_mask` 现算为空 tuple，不是遗漏）。footer 的两处 SUM 公式属
footer 层，不是"数据行列向公式"，不影响 `formula_columns` 的判断——`formula_columns` 语义
是"数据区间内哪些列逐行都有公式"，footer 公式由 `footer_carries_total_formula` 单独表达。

footer R14 的 SUM 公式`B14='=SUM(B11:B13)'`/`F14='=SUM(F11:F13)'`**确有覆盖全部 3 行数据区**
（与 D3-6 footer 只覆盖 3/5 行、D3-4 段①差异公式硬编码 4 行的"模板预存缺陷"不同，本表 SUM
区间与数据区行数完全匹配，无落差）。⇒ `footer_carries_total_formula=True`（显式传，保持与
Task 8 D3-4 的显式声明风格一致，避免歧义——即便默认值本身也是 `True`）。

候选空列独立复核：I/J/K/L/M/N 在行 10-17 范围内全部为 `None`（本任务扫描确认，与 Task 1
"I/J/K 全空"结论一致，本任务扩大扫描范围到 L/M/N 进一步确认，选 **I** 列——数据区最后一列
是 H（备注），I 是紧邻数据区（A-H）的最近候选空列，同 D3-6 选 K（紧邻其 A-J 数据区）的
选列原则一致）。

═══ note/conclusion 字段（登记，不进 field_specs）═══

A15「三、审计说明」+ A19「四、审计结论」落在 footer(14) 之下，落在数据区之外，属 Task 1
「footer 下 note/conclusion 与插行 fail-closed 冲突」登记的 HTML-only 候选（同 D3-6/D4-5
判例）。这些字段**不进**本文件的 `field_specs`——受管字段只覆盖数据区（11-13）内实测有列
语义的 8 列（A-H）。

═══ 模板缺陷修复（Task 10 第 3c 段，用户批准"修模板"）═══

🔴 上文「A14 本身也是 None——marker 由 footer_marker 声明…由框架层扫描定位」的原始形态**已被修正**：
原模板 A14 为空，`footer_anchor(marker='合计', search_column='A')` 靠 A 列文字定位 footer，但整个 A 列一处
「合计」都没有 ⇒ materialize 计划期 `assert_footer_anchor_stable` 抛 `FooterAnchorDriftError`（见证据
task10-d3-05-footer-anchor-investigation.md §1/§7 修法 B）。Task 10 第 3c 段经用户批准，用
`scripts/fix/fix_d3_template_footer_defects.py` 在权威模板 A14 写入 inlineStr「合计」（保留 style s=12，
不动 sharedStrings 索引），SUM 区间 11:13 覆盖数据区 11-13 全部 3 行、无需改。修复后 A14=='合计'，
footer marker 可被 `_find_marker_row` 命中，D3-5 进 materialize 不再被 footer 锚点门拦。模板新
sha256=`33165493…`（旧净化值 `699a9be0…`）。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_D305",
    "MANAGED_SHEET_D305",
    "STORE_ITEM_ID_D305",
]

MANAGED_SHEET_D305: Final[str] = "账龄1年以上的预收账款检查表D3-5"
TEMPLATE_ID_D305: Final[str] = "D35"
SHEET_KEY_D305: Final[str] = "d35-managed"
ROWS_TABLE_KEY_D305: Final[str] = "long_term_rows"
#: 🔴 逐字对照 Task 3 判据文件顶部 REAL_STORE_ITEM_IDS 表实测值——不是 D3-5-rows（裁决 F2）。
STORE_ITEM_ID_D305: Final[str] = "D3-lt-rows"

#: 🔴 UUID 动态行（Task 1 实测 + 本任务独立复核确认）—— 不是稳定 key 固定行。
ROW_IDENTITY_STORE_KEY_D305: Final[str] = "rowId"

HEADER_ROW_D305: Final[int] = 10
FIRST_DATA_ROW_D305: Final[int] = 11
LAST_DATA_ROW_D305: Final[int] = 13
FOOTER_ROW_D305: Final[int] = 14
#: footer marker 实测为纯「合计」两字（无空格），同 D3-6。
FOOTER_MARKER_D305: Final[str] = "合计"
MANAGED_LAST_COL_D305: Final[str] = "H"
#: I 列实测全空（I10..I17 均为 None），是最靠近数据区（A-H）的候选空列。
UUID_COL_D305: Final[str] = "I"

#: 8 个受管字段（7 元组，末位 group_header_cell 为 "" —— 单级表头无分组）。
#: 顺序即 Excel 列序 A→H；表头文本与 R10 逐字相等（本任务独立 openpyxl 复核确认）。
#: 数据行区间（11-13）内逐行没有任何公式列 ⇒ 全部 8 列均为 editable，无 formula 列。
FIELD_SPECS_D305: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("counterparty_name", "A", "editable", "text", "counterpartyName", "对方单位名称", ""),
    ("ending_balance", "B", "editable", "amount", "endingBalance", "期末余额", ""),
    ("aging", "C", "editable", "text", "aging", "账龄", ""),
    ("business_reason", "D", "editable", "text", "businessReason", "经济业务说明", ""),
    ("unsettled_reason", "E", "editable", "text", "unsettledReason", "未结转或未偿还的原因", ""),
    ("settled_by_audit_date", "F", "editable", "amount", "settledByAuditDate", "至审计日结转或偿还金额", ""),
    ("plan", "G", "editable", "text", "plan", "处理计划", ""),
    ("remark", "H", "editable", "text", "remark", "备注", ""),
)

SPEC_D305: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_D305,
    sheet_key=SHEET_KEY_D305,
    table_key=ROWS_TABLE_KEY_D305,
    template_id=TEMPLATE_ID_D305,
    table_name=f"GT_{TEMPLATE_ID_D305}_ROWS",
    uuid_col=UUID_COL_D305,
    first_data_row=FIRST_DATA_ROW_D305,
    last_data_row=LAST_DATA_ROW_D305,
    footer_row=FOOTER_ROW_D305,
    header_row=HEADER_ROW_D305,
    store_item_id=STORE_ITEM_ID_D305,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_D305,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_D305,
    # 🔴 数据行区间（11-13）内逐行没有任何公式列 ⇒ 不传 formula_columns（沿用引擎默认值
    # 空 tuple），formula_mask 现算为空 tuple，不是遗漏——同 Task 8 D3-4 段②的处置原则。
    footer_marker=FOOTER_MARKER_D305,
    # 🔴 footer R14 的 SUM 公式（B14/F14）确覆盖全部 3 行数据区，无落差——显式传 True
    # 保持与 Task 8 的显式声明风格一致（即便默认值本身也是 True，避免歧义）。
    footer_carries_total_formula=True,
    error_label="D3-5 账龄1年以上的预收账款检查表",
    # 🔴 formula_mask 不手写——它是引擎 property 现算（Property 5），由 formula_columns
    # （本表为空 tuple）× 数据行区间自动导出为空 tuple，见 phase5_row_table_sheet.py
    # RowTableSheetSpec.formula_mask。
)
