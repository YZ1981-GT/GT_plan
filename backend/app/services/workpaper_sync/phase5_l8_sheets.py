# -*- coding: utf-8 -*-
"""L8 财务费用 —— 受管 `明细表L8-2` 的身份/几何/字段声明。

spec: l8-true-bidirectional-2026-10-01 · 第3步（选型见 `.agents/tasks/l8-managed-table-choice/report.md`）

选型现算：明细表L8-2 是 L8 整册唯一的数据录入源（审定表 L8-1 / 两张附注 / 检查表 L8-6
全部跨 sheet 引用它），HTML 子组件 `L8TabDetail.vue` 是其渲染（23 列语义逐列对齐、行动态、
公式一致、持久化已是单 item JSON 数组 `L8-2-full-data`，单前缀 `L8-2-` 而非 L5/L6/L7 的双前缀）。
排除 L8-4 利息测算引擎 / L8-5 截止测试引擎 / L8-6 问句清单，保持原样不动。

🔴 **损益类（科目 6603 财务费用）**：取数=本期发生额，兜底 `tb_balance.debit_amount` 本身
（不是 `debit−credit`，后者在含年末结转损益的全年账上恒为 0），回写口径 `amount_kind='occurrence'`。
受管改线**不碰回写逻辑**：L8-2 本身不直接回写 TB（回写在下游 L8-1 发布门取 L8-2 合计 Q22）。
故 `amount_kind='occurrence'` 只作文档事实登记在 reviewed_basis / extra_review / ledger / registry，
不是契约里的一个机制字段（common 的 LEntryIdentity 无 amount_kind 字段）。

几何（openpyxl 逐格实测，sha d915e309…）：**单级表头 r8**（项目/1月~12月/本期未审合计/账项调整/
重分类调整/本期审定金额/各项目占比/与相关科目勾稽/上期未审金额/账项调整/重分类调整/上期审定金额），
数据区 **R9~R21（13 行）**、合计 **R22（A22「合计」）**、各月比例 **R23**。有效业务列 A..W（23 列）；
物理 max_column=W(23)，X/Y/Z 右侧全空 ⇒ UUID 列 **X**。

公式列（现算，照 r9 实测）：
  N `=SUM(B9:M9)`（本期未审合计）/ Q `=N9+O9+P9`（本期审定）/ W `=T9+U9+V9`（上期审定）
  R `=IF(Q9=0,0,Q9/$Q$22)`（各项目占比，裸 IF）。

🔴 **三件补课（与 L1~L7 根本不同，见 plan 顶部裁决）**：

补课① **3 个跨行派生行 R11/R13/R20**（R11=R9−R10 利息费用、R13=R11−R12 利息净支出、
R20=R17−R18−R19 汇兑净损失，B~M 每格对上面输入行同月份跨行减法）。引擎的「整列同形公式」
模型表达不了「B~M 列只有三行是公式、其余是输入」。处置：**B~M 不进 formula_columns**，对全部
13 行声明为 `editable`；R11/R13/R20 的 B~M 跨行减法公式作为模板预置、不受管的既有单元格留在
substrate 里 —— HTML 的 12 默认项不含「汇兑净损失」（13 行多 R20），这三「净额」行的 B~M
不属任何受管 editable 字段的回填目标，projection 不产 FieldValue ⇒ materialize 不写这些格 ⇒
模板预置的 `=B9-B10` 等跨行公式原样幸存。往返按**稳定 rowId（字段名 `key`）**对齐、不靠行序。

补课② **双 footer**（R22 合计 + R23 各月比例）。锚 R22「合计」作主 footer
（`footer_marker='合计'`、`footer_search_column='A'`、`footer_carries_total_formula=True`）；
R23「各月比例」作模板静态行保留（数据区 last_data_row=21 到 R21 止、footer_row=22，R23 在
footer 之下不被插行破坏，`RowTableSheetSpec` 单 footer_row 模型足够）。

补课③ **受管区 28 裸 IF**（R 列各行占比 + R23 各月比例跨 B~N）。`adapters/excel.py` materialize
前对 substrate 副本跑 `neutralize_oo_crash_if_formulas`，把含词界 `IF(` 的 `<f>` 整个摘掉（保留
`<v>`）。因此 R 列（占比，每行 `=IF(...)`）的 `<f>` 会在 materialize 前被摘除成纯值 ⇒ **R 列
声明为 formula mode（is_protected，OO 侧不被值覆盖），但不能对 R 列断言「往返后仍是公式」**
（它被中性化摘成纯值，与 G11-1102 的 NEUTRALIZED_COLUMNS 同型）。可往返「公式幸存」断言只对
N/Q/W 三列成立（非 IF 的本行算术）。store_item_registry 的 L8 条目挂
`oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas"`（与 L6/L7 一致）。
"""
from __future__ import annotations

from typing import Final, Mapping

from app.services.workpaper_sync.models import AuthorityModel
from app.services.workpaper_sync.phase5_row_table_sheet import RowTableSheetSpec, StoreKind
from app.services.workpaper_sync.phase5_row_table_sheet import managed_field_specs as _fields

PHASE5_WAVE: Final[str] = "l_cycle_financial_expenses"
ENTRY_ID: Final[str] = "xlsx/gt-l8-financial-expenses"
ADAPTER_ID: Final[str] = "l8.financial_expenses"
#: manifest 冻结的 wp_code_pattern（宿主 GtL8FinancialExpenses CamelCase 幻影码 L8F，finder 零命中）。
WP_CODES: Final[frozenset[str]] = frozenset({"L8F"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "L/L8 财务费用.xlsx"
#: 🔴 净化后 sha（sanitize_l8_template_external_links.py 把受管 sheet 的横向共享公式组展开为
#: 逐格显式公式，受管 sheet openpyxl 逐格 0 diff）。净化前原始值见 PRE_SANITIZE_TEMPLATE_SHA256
#: （真 OO 往返 materialize 对横向共享组抛 excel_row_shift_shared_formula_orientation_unsupported，
#: 故净化在五环发布前执行；现算受管 sheet 横向共享组 C11:L11/O11:P11/C13:L13/O13:P13/C20:P20/
#: C22:P22/T22:V22/C23:N23 等）。
TEMPLATE_SHA256: Final[str] = "f56843b02c3a34a443107d69207904b363187e887d2a359163fd2175381a368c"
PRE_SANITIZE_TEMPLATE_SHA256: Final[str] = "d915e3091a426aadab3828bf4ba43502e9cb3a967392d177d2c22a139c6634e6"
MANAGED_SHEET: Final[str] = "明细表L8-2"
TEMPLATE_ID: Final[str] = "L82"
SHEET_KEY: Final[str] = f"{TEMPLATE_ID.lower()}-managed"
ROWS_TABLE_KEY: Final[str] = "financial_expense_detail_rows"
TABLE_NAME: Final[str] = f"GT_{TEMPLATE_ID}_ROWS"
AUTHORITY_MODEL: Final[AuthorityModel] = AuthorityModel.projection_contract
#: 🔴 单级表头 r8（非 L6/L7 两级 ⇒ header_row=8，header_group_row/header_leaf_row 留 None）。
HEADER_ROW: Final[int] = 8
FIRST_DATA_ROW: Final[int] = 9
LAST_DATA_ROW: Final[int] = 21
FOOTER_ROW: Final[int] = 22
MANAGED_LAST_COL: Final[str] = "W"
UUID_COL: Final[str] = "X"
FOOTER_MARKER: Final[str] = "合计"
FOOTER_SEARCH_COLUMN: Final[str] = "A"
#: 🔴 单前缀 `L8-2-`（非 L5/L6/L7 的 L8-L8-2- 双前缀），身份字段是 `key`（非 L6/L7 的 rowId）。
STORE_ITEM_ID: Final[str] = "L8-2-full-data"
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
ROW_IDENTITY_STORE_KEY: Final[str] = "key"
#: 损益类回写口径（文档事实，非契约机制字段）。
AMOUNT_KIND: Final[str] = "occurrence"
ACCOUNT_CODE: Final[str] = "6603"
#: A..W 23 列全部映射到 L8DetailRow ⇒ 无 HTML-only。
HTML_ONLY_ROW_KEYS: Final[tuple[str, ...]] = ()
#: R 列占比裸 IF 被 neutralize_oo_crash_if_formulas 摘 <f> ⇒ 中性化后无公式 ⇒ mode=auto_source
#: （与 AUTO_SOURCE_COLUMNS 同一列，照 G11-1102 的 NEUTRALIZED_COLUMNS_G1102==AUTO_SOURCE_COLUMNS_G1102）。
#: 不做往返「公式幸存」断言（它是服务端字面量，不是公式）。
NEUTRALIZED_COLUMNS: Final[tuple[str, ...]] = ("R",)
#: 受管 sheet 自身的裸 IF 个数（R 列占比 R9~R22 共 14 + R23 各月比例共 14）。
MANAGED_SHEET_BARE_IF: Final[int] = 28
#: 跨行派生行（模板预置公式作幸存，B~M editable 不受管回填）。
DERIVED_ROWS: Final[tuple[str, ...]] = ("R11", "R13", "R20")

#: 23 个受管字段，7 元组 `(column_key, 列标, mode, value_type, store json 键, 表头文本, 组标题单元格)`，
#: 顺序即 Excel 列序 A→W。单级表头 ⇒ group_header_cell 全为 ""。
#: 🔴 月度列 B~M 的 json_key 对齐 HTML：`L8DetailRow.monthly` 是长度 12 的数组
#:    ⇒ json_key 用 `monthly/0`…`monthly/11`（json_path 模块对非白名单键泛化支持任意长度数组段）。
#: 🔴 B~M 为 editable（不进 formula_columns）：R11/R13/R20 的跨行预置公式靠「不被受管字段回填」幸存。
#: 🔴 N/Q/W 为 formula（本行算术，往返幸存）；R 为 formula（占比裸 IF，被中性化摘成纯值）。
MANAGED_FIELD_SPECS_7: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("item_name", "A", "editable", "text", "itemName", "项目", ""),
    ("month_1", "B", "editable", "amount", "monthly/0", "1月", ""),
    ("month_2", "C", "editable", "amount", "monthly/1", "2月", ""),
    ("month_3", "D", "editable", "amount", "monthly/2", "3月", ""),
    ("month_4", "E", "editable", "amount", "monthly/3", "4月", ""),
    ("month_5", "F", "editable", "amount", "monthly/4", "5月", ""),
    ("month_6", "G", "editable", "amount", "monthly/5", "6月", ""),
    ("month_7", "H", "editable", "amount", "monthly/6", "7月", ""),
    ("month_8", "I", "editable", "amount", "monthly/7", "8月", ""),
    ("month_9", "J", "editable", "amount", "monthly/8", "9月", ""),
    ("month_10", "K", "editable", "amount", "monthly/9", "10月", ""),
    ("month_11", "L", "editable", "amount", "monthly/10", "11月", ""),
    ("month_12", "M", "editable", "amount", "monthly/11", "12月", ""),
    ("period_unadjusted", "N", "formula", "amount", "periodUnadjusted", "本期未审合计", ""),
    ("aje", "O", "editable", "amount", "aje", "账项调整", ""),
    ("rje", "P", "editable", "amount", "rje", "重分类调整", ""),
    ("period_audited", "Q", "formula", "amount", "periodAudited", "本期审定金额", ""),
    #: 🔴 R 列占比裸 IF，中性化后 substrate 无公式 ⇒ `auto_source`（照 G11-1102 的 G/K 列先例）。
    #: formula mode 要求 substrate 该格仍有公式，但 neutralize 摘掉了 <f> ⇒ materialize 对已锚定
    #: 的骨架行 _emit 会抛 ProtectedRegionWriteError。auto_source = 服务端提供字面量（HTML 侧
    #: computedRows 已算好 ratio），引擎只在 substrate 仍是公式时才拒写 ⇒ 中性化后写字面量通过。
    ("ratio", "R", "auto_source", "amount", "ratio", "各项目占比", ""),
    ("cross_ref", "S", "editable", "text", "crossRef", "与相关科目勾稽", ""),
    ("prior_unadjusted", "T", "editable", "amount", "priorUnadjusted", "上期未审金额", ""),
    ("prior_aje", "U", "editable", "amount", "priorAje", "账项调整", ""),
    ("prior_rje", "V", "editable", "amount", "priorRje", "重分类调整", ""),
    ("prior_audited", "W", "formula", "amount", "priorAudited", "上期审定金额", ""),
)

#: 三个公式列的模板形态（损益类，本行算术，中性化后仍有公式 ⇒ mode=formula 往返幸存）。
#: 🔴 R 列（占比裸 IF）**不在**此表：它中性化后无公式 ⇒ mode=auto_source（见下 AUTO_SOURCE_COLUMNS）。
FORMULA_TEMPLATES: Final[Mapping[str, str]] = {
    "N": "=SUM(B{row}:M{row})",
    "Q": "=N{row}+O{row}+P{row}",
    "W": "=T{row}+U{row}+V{row}",
}
FORMULA_COLUMNS: Final[tuple[str, ...]] = tuple(FORMULA_TEMPLATES)
#: 🔴 R 列占比：中性化后 substrate 无公式 ⇒ auto_source（服务端字面量，照 G11-1102 的 G/K 列）。
#: R 列占比裸 IF 的逐字模板（供文档/断言，不进 formula_templates —— 那张表驱动 formula mode 比对）。
AUTO_SOURCE_COLUMNS: Final[tuple[str, ...]] = ("R",)
RATIO_TEMPLATE: Final[str] = "=IF(Q{row}=0,0,Q{row}/$Q$22)"

SPEC_L82: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET,
    sheet_key=SHEET_KEY,
    table_key=ROWS_TABLE_KEY,
    template_id=TEMPLATE_ID,
    table_name=TABLE_NAME,
    uuid_col=UUID_COL,
    first_data_row=FIRST_DATA_ROW,
    last_data_row=LAST_DATA_ROW,
    footer_row=FOOTER_ROW,
    #: 🔴 单级表头 ⇒ 走 header_row（group/leaf 留 None）；spec_to_contract_sheet_payload
    #: 据此算 header_rows=1、anchor=A8。
    header_row=HEADER_ROW,
    store_item_id=STORE_ITEM_ID,
    empty_payload=EMPTY_STORE_PAYLOAD,
    #: 🔴 身份字段是 `key`（L8DetailRow.key），不是 L6/L7 的 rowId。
    row_identity_key=ROW_IDENTITY_STORE_KEY,
    store_kind=StoreKind.rows,
    field_specs=MANAGED_FIELD_SPECS_7,
    #: 🔴 只 N/Q/W 进 formula_columns（本行算术，中性化后仍有公式）；R 是 auto_source（占比裸 IF
    #: 中性化后无公式）；B~M 是 editable（派生行 B~M 预置公式靠不回填幸存）。
    formula_columns=FORMULA_COLUMNS,
    formula_templates=FORMULA_TEMPLATES,
    #: L8-2 无账龄组。
    aging_layout=None,
    aging_groups=(),
    footer_marker=FOOTER_MARKER,
    #: footer R22 B22~Q22 携带签名小计公式。
    footer_carries_total_formula=True,
    #: 🔴 footer 标签在 A22「合计」（现算 A22==合计）。
    footer_search_column=FOOTER_SEARCH_COLUMN,
    error_label="L8-2 财务费用明细表",
    #: 🔴 锚点取第 0 位 item_name（项目名称，真业务文本；无整数序号列）。
    ghost_row_anchor_index=0,
)

#: 23 个受管字段（6 元组视图），由框架层现算 —— provider 不复制展开结果。
MANAGED_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str], ...]] = tuple(
    row[:6] for row in _fields(SPEC_L82)
)

#: 四个公式列的只读区域，由框架层 property 现算（N9:N21 / Q9:Q21 / R9:R21 / W9:W21）。
FORMULA_MASK: Final[tuple[str, ...]] = SPEC_L82.formula_mask

#: 单级表头 ⇒ 无组标题单元格。
GROUP_HEADER_CELLS: Final[Mapping[str, str]] = {
    row[0]: row[6] for row in MANAGED_FIELD_SPECS_7 if row[6]
}

_HTML_STORE_NOTE: Final[str] = (
    "整张 L8-2 明细表存成 `L8-2-full-data` 的 remark JSON 数组（useL8Detail 的 _triggerSave 写 "
    "JSON.stringify(detailRows)）；🔴 单前缀 `L8-2-`（非 L5/L6/L7 的 L8-L8-2- 双前缀）。每行身份字段"
    "是 `key`（非 L6/L7 的 rowId，2026-10-01 把私有 Date.now+Math.random 生成器换成平台共享 "
    "newRowIdentity('l82det')，已有 key 优先不重铸）。契约按 stable field + row key 拆开。"
    "月度列 B~M 对应 HTML 的 `monthly[0..11]` 数组 ⇒ json_key 用 `monthly/0`…`monthly/11`。"
    "sibling 键 `L8-2-row-N-data` / `L8-2-row-N-audited` / `L8-2-netFinExpense` 本轮不受管、不预登记。"
    "真库 `L8-2-%` 现算 0 行，零迁移负担。A..W 23 列全部映射到 L8DetailRow ⇒ 无 HTML-only 字段。"
)
_REVIEWED_BASIS: Final[str] = (
    "2026-10-01 openpyxl 逐格实测 L/L8 财务费用.xlsx（10 sheet，sha d915e309…）：受管 明细表L8-2 "
    "单级表头 r8（项目/1月~12月/本期未审合计/账项调整/重分类调整/本期审定金额/各项目占比/"
    "与相关科目勾稽/上期未审金额/账项调整/重分类调整/上期审定金额）、数据区 R9~R21（13 行）、"
    "footer A22「合计」（B22~Q22 签名小计 =B13+B14-B15+B16+B20+B21）、R23「各月比例」作模板静态行"
    "（在 footer 之下不受管）、A..W 23 字段与前端 L8DetailRow 对齐；物理 max_column=W(23) ⇒ UUID=X。"
    "formula 列 N=SUM(B:M) / Q=N+O+P / W=T+U+V（本行算术，往返幸存）+ R=IF(Q=0,0,Q/$Q$22)"
    "（各项目占比裸 IF，materialize 前被 neutralize_oo_crash_if_formulas 摘 <f> 成纯值 ⇒ 不做公式"
    "幸存断言，NEUTRALIZED_COLUMNS=('R',)）。🔴 B~M 列为 editable（不进 formula_columns）：跨行派生行 "
    "R11=R9-R10（利息费用）/ R13=R11-R12（利息净支出）/ R20=R17-R18-R19（汇兑净损失）的 B~M 预置公式"
    "作模板预置格幸存（HTML 12 默认项缺「汇兑净损失」R20，往返按稳定 key 对齐不靠行序，这三「净额」行"
    "B~M 不属任何受管 editable 字段回填目标 ⇒ projection 不产 FieldValue ⇒ materialize 不写 ⇒ 公式幸存）。"
    "受管 sheet 自身 28 裸 IF（R 列占比 + R23 各月比例），与 L1~L7「受管表零裸 IF」相反。"
    "🔴 损益类（科目 6603 财务费用）：取数=本期发生额、兜底 tb_balance.debit_amount 本身（非 debit−credit，"
    "含年末结转损益全年账上恒 0），回写 amount_kind='occurrence'；受管改线不碰回写逻辑，L8-2 本身不直接"
    "回写 TB（回写在下游 L8-1 发布门取 L8-2 合计 Q22）。报表行次 IS-007（上市）/IS-025（国企）。"
    "canary 不选 审定表L8-1（R7~R16 全跨 sheet SUMIF 聚合 明细表L8-2 的下游视图，非录入表）。"
    "manifest 幻影码 L8F finder 零命中。真库 `L8-2-%` 现算 0 行，零迁移负担。"
)
