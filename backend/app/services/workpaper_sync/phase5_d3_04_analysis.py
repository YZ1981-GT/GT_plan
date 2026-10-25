# -*- coding: utf-8 -*-
"""D3-4「预收账款分析表」—— sheet 层薄声明（**双区**，D3 首次同 sheet 多受管区，Task 8）。

spec: d3-sync-coverage-via-row-table-engine · Task 8 · Requirements 2.1, 2.2
几何证据: .kiro/specs/d3-sync-coverage-via-row-table-engine/evidence/task1-sheet-morphology-and-geometry.md
裁决过程: .kiro/specs/d3-sync-coverage-via-row-table-engine/evidence/task8-d3-04-dual-zone-declaration.md

═══ 🔴 裁决：方案 A（标准动态行表双区），不是 D4-33 式 limited_bidirectional ═══

Task 1 证据发现了一个真实张力——模板段①②各只画了 4/3 行固定文字标签占位（13-16 / 22-24），
差异公式 `B17='=B11-B13-B14-B15-B16'` 还硬编码引用了段①这 4 行，形似"固定位置"。但前端
`useD3Analysis.ts` 的 `debitRows`/`creditRows` 是 `ref<AnalysisRow[]>`——真实任意长度数组，
没有任何固定长度常量约束（对比 D4-33 的 `bizTypes[]` 是"业务类型槎位"语义，`store.bizTypes[slot].id`
按位置映射到模板固定列组）。本任务独立复核后维持方案 A，理由：

🔴 **Task 10（阶段 2 验收）实测发现并修正的真实缺陷（两区都中，不止段①）**：Task 8 本身的
openpyxl 复核已经**看到** `A16=' ……'`（第 16 行空格+双省略号）与 `A24='         ……'`
（第 24 行多个前导空格+双省略号）却**没有识别出**它们是框架层 `excel_typography_rows.py`
（BP-21）专门定义的「续行省略号排版占位行」——这不是业务数据行，是中文审计模板在数据区末尾
放的排版符号。真正翻开关驱动一次 instrumentation（`instrument_workbook_bytes_multi`）后，
`assert_last_data_row_is_not_typography_placeholder` 门禁真实拦截并给出精确诊断：段①声明的
`last_data_row=16` 落在排版占位行上，应改为 `15`（剔除尾部 1 行占位行，footer 行 17 不变）。
段①**真实业务数据行只有 13-15**（资产处置损益/固定资产/增值税 三行），16 不是第四条数据、
是排版占位。**段②同款问题（本任务独立扫描发现，Task 8 只核过"段②无差异公式硬编码引用固定行"
这一点，没有意识到这是两个不同的问题）**：`last_data_row=24` 同样落在排版占位行上，应改为
`23`（其中：银行存款收款/应收票据 两行才是真实数据）。这两处缺陷只有在真实驱动
instrumentation 时才会被检出——Task 6/7/8/9 的判据全部用 monkeypatch/局部构造验证"开关打开后
的效果"，从未真实跑过 `instrument_workbook_bytes_multi` 这条真实注入路径（该路径专属于双区
位移链判据 `test_all_multi_region_sheets_shift_sibling_table_refs`），所以此前从未暴露。
详见 `evidence/task10-stage2-acceptance.md`。

1. **`static_region` 的判据是"无行维度"**（`excel_extract.BindingKind.static_region` 文档：
   "只有绝对坐标 static cell、无动态行/无 UUID 列"，D4-13/D4-33 单 cell 或矩阵锚点）。段①②
   每行是同构记录（label/amount/source/remark 四列一行一条），有清晰的行维度，不满足此判据。
2. **`phase5_row_table_sheet.RowTableSheetSpec.last_data_row` 的字段注释明确**："模板预画末行
   （超出按样式克隆扩行）"——引擎设计目标本身就是支持超出模板行数增长，不是"模板画几行就只能
   有几行"。
3. **D1-4 是几何同型的已判先例**：`phase5_d1_04_bad_debt.py` 的个别计提/组合计提两区（各 4 行，
   `SUM(13:16)`/`SUM(18:21)` 式硬编码 SUM 引用固定 4 行区间）被正确判定为标准 `excel_table`
   binding（非 `static_region`）。D1-4 第三区（票据种类小计）才判 `static_region`，真正原因是
   "无行身份维度"（两行是写死的银行承兑/商业承兑，不增删）+ "落在 footer 之下"——D3-4 段①②
   两条都不满足。
4. **D4-33 的 `limited_bidirectional` 本质是"位置映射"问题**：前端 N 个业务类型 → 模板固定
   3 个**列组**（列组不能插入，只能占位映射）。D3-4 是"前端 N 行 → 模板预画 4/3 **行**占位"的
   行数问题，本质不同——行表引擎的 row-shift 机制正是为后者设计（`_grow_managed_table_ref`）。

⇒ 声明两个标准 `RowTableSheetSpec`（`binding_kind` 用默认值 `excel_table`），`row_identity_key
='rowId'`（UUID 动态行，同 D3-6/D1-4 前两区）。

═══ 🔴 sheet_key 共享（不照抄 design.md 旧骨架的两个不同 sheet_key）═══

design.md 写的示意骨架用了 `sheet_key="d34-managed-credit"`/`"d34-managed-debit"`（两个不同
sheet_key）——这是 Task 1 实测前写的过时示意，与两个真实先例不符：`phase5_d4_customer_structure.py`
（D4-9，`SHEET_KEY_D49="d49-managed"` 单值，三个 table 共用）与 `phase5_d1_04_bad_debt.py`
（D1-4，`SHEET_KEY_D104` 单值，`_base_spec()` 共用）都是**单一共享 sheet_key**。契约层
`SheetSpec.tables` 本身是 `tuple[TableSpec, ...]`（一个 sheet 天然可含多 table），同
`managed_sheet` 若映射到两个不同 sheet_key 会在契约装配时产生"同 excel_name 两个 sheet 条目"
的重复/冲突声明。本文件用**单一共享** `SHEET_KEY_D304="d34-managed"`。

═══ 与 D4-9 的架构差异（不照抄 D4-9 的 dict store）═══

D4-9 的 store 是单一 `StoreKind.dict`（`{current:{...}, prior:{...}}`），需要手写专用投影/
合并函数。D3-4 的两个 store 键（`D3-ana-debit-rows`/`D3-ana-credit-rows`）各自是独立的
`ref<AnalysisRow[]>` 数组（`StoreKind.rows`），架构上更贴近 **D1-4** 的 individual/portfolio
两区（各自独立 `store_item_id`，共用引擎 `phase5_row_table_sheet` 的通用投影/合并逻辑，
不需要任何 provider 专用函数）。本文件走标准引擎路径，不新写任何投影/合并代码。

═══ 几何（openpyxl 直读实测，Task 1 已实测 + 本任务独立复核一致）═══

单级表头 R10（4 列 A..D：项目/金额/数据来源/备注）。

段①（一）预收账款借方发生额分析：
  数据区 R13-15（🔴 Task 10 修正：**3 行**真实业务标签占位：'资产处置损益'/'固定资产'/
  '增值税'。原第 16 行 `A16=' ……'` 是续行省略号排版占位（BP-21），不是第四条业务数据，
  已剔除——`last_data_row` 从 16 修正为 15，见上方模块级"Task 10 实测发现并修正的真实缺陷"）
  差异行 R17：A17='差异' B17=`=B11-B13-B14-B15-B16`（🔴 硬编码引用行 13-16 共 4 行，但行 16
  是排版占位不是数据行，见下方"模板预存缺陷"——这个公式本身横跨了受管区之外的排版占位行）
  ⇒ store 键 `D3-ana-debit-rows`（`useD3Analysis.ts` `ITEM_ID_DEBIT_ROWS`）

段②（三）预收账款贷方发生额分析：
  数据区 R22-23（🔴 Task 10 修正：**2 行**真实业务标签，非 3 行——原第 24 行
  `A24='         ……'`（多个前导空格+双省略号）**同样**是续行省略号排版占位（BP-21），Task 8
  当时只判断了"段②无差异计算公式硬编码引用固定行"（这个判断本身正确），但没有意识到"公式没
  硬编码引用它"与"它本身是不是有效数据行"是两个不同的问题——本行同样需要剔除，`last_data_row`
  从 24 修正为 23）
  R25='差异合理性分析'（纯文字说明，**无**类似段①的差异计算公式）
  ⇒ store 键 `D3-ana-credit-rows`（`useD3Analysis.ts` `ITEM_ID_CREDIT_ROWS`）

段③（四）期末预收账款主要债务人分析（R26-33）**不进本文件受管区**：`top5Debtors` 是从
`D3-det-rows`（明细表）交叉计算的纯派生 computed，前端无导入/导出按钮、无独立 store 键，
用户不能在这里手动增删行（与段①②各有"模板/导出/导入"三按钮的可编辑语义完全不同）。

🔴 **模板预存缺陷（Task 10 已用真实插行测试验证，结论：不会被自动纠正）**：段①差异公式
硬编码引用 `B13:B16`（固定 4 行，其中 16 是排版占位、13-15 是真实数据行）——若用户实际业务
数据插行超过受管区（13-15），第 4+ 行不会被这个差异公式计入。Task 8 曾把这个悬念留给 Task 10
用真实测试验证是否会被行表引擎的位移归一化机制自动纠正。**Task 10 实测结论：不会**——
`excel_materialize.assert_footer_formula_covers_managed_rows` 的区间检测正则
`_RANGE_IN_FORMULA_RE` 只匹配 `A1:B2` 式冒号区间（如 `SUM(B7:B25)`），`B17` 的公式文本
`=B11-B13-B14-B15-B16` 是纯散落单格引用相减，不含任何冒号区间，检测器对这类公式文本**不会
报错也不会扩张**——插入第 4 行后，B17 差异公式原样保持 `=B11-B13-B14-B15-B16`，新插入的
第 4 行金额不会被这个差异计算覆盖（漏算）。这是一个真实存在的引擎边界（不是本任务范围内的
bug，是"footer 合计公式区间归一化"机制目前只覆盖 `SUM(range)` 式结构化区间公式，不覆盖
"硬编码引用具体行号并相减"这种非结构化公式文本），已在 `evidence/task10-stage2-acceptance.md`
详细记录插行前后的公式文本对比。声明代码**不做任何特殊处理**（不代为修复模板或加规避逻辑），
按实测的公式模板原样声明，如实暴露这个边界。段②无此问题（无差异计算公式硬编码引用固定行）。

🔴 **note/conclusion 字段（登记，不进 field_specs）**：A34「三、审计说明」+ A38「四、审计
结论」落在段③（33）之后，属 Task 1「footer 下 note/conclusion 与插行 fail-closed 冲突」
登记的 HTML-only 候选（同 D4-5 判例）。前端由 `useD3Analysis.ts` 的 `auditNote`
（`D3-ana-note`）单一文本字段承载，不在本文件的两个 `RowTableSheetSpec` 受管范围内。

═══ ✅ 上游 D1 spec Task 24 前置缺口（Task 10 复核：已解除，Task 8 该节结论过期）═══

Task 8 当时核查 `d1-sync-row-table-engine-and-d1-coverage` 的 Task 24（`test_sibling_table_
ref_row_shift.py` 参数化判据改按 provider 取清单）状态为"仍是 `[ ]` 未完成"。**Task 10
（本任务）重新核查确认该结论已过期**：Task 24 现为 `[x]` 已完成（commit `787cc864c`
`feat(sync): D1 spec Task 24 位移判据参数化 + 修复聚合重复计入 bug`，已在本次 Task 10 开工前
入 HEAD）。`_multi_region_sheets()` 现已改为遍历 golden digest `PROVIDERS` 权威登记 +
`_COMPANION_EXPANSION_MODULES` 伴生模块清单（`phase5_d3_prepaid_receipts` 已显式登记伴生
`phase5_d3_expansion`），本文件声明的双区**已经**自动进入
`test_all_multi_region_sheets_shift_sibling_table_refs` 的参数化覆盖清单（灰度开关打开后
参数名含"预收账款分析表D3-4"），验证结果见 `evidence/task10-stage2-acceptance.md`。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_D304_DEBIT",
    "SPEC_D304_CREDIT",
    "SPECS_D304",
    "MANAGED_SHEET_D304",
]

MANAGED_SHEET_D304: Final[str] = "预收账款分析表D3-4"
TEMPLATE_ID_D304: Final[str] = "D34"
#: 🔴 单一共享 sheet_key（不是 design.md 旧骨架的两个不同值，见模块 docstring）。
SHEET_KEY_D304: Final[str] = "d34-managed"

HEADER_ROW_D304: Final[int] = 10

#: 段①借方发生额分析：数据区 13-15（🔴 Task 10 修正：3 行真实业务标签，非 4 行——原第 16
#: 行 `A16=' ……'` 是续行省略号排版占位，见模块 docstring "Task 10 实测发现并修正的真实缺陷"），
#: 差异行 17。
FIRST_DATA_ROW_DEBIT: Final[int] = 13
LAST_DATA_ROW_DEBIT: Final[int] = 15
FOOTER_ROW_DEBIT: Final[int] = 17
#: footer marker 实测为「差异」（A17 纯两字，非「合计」——本表两区都没有"合计"字样的 footer，
#: 段①是"差异"计算行，段②是纯文字说明行，见下方段②的 FOOTER_MARKER_CREDIT）。
FOOTER_MARKER_DEBIT: Final[str] = "差异"

#: 段②贷方发生额分析：数据区 22-23（🔴 Task 10 修正：2 行真实业务标签，非 3 行——原第 24
#: 行 `A24='         ……'` 同样是续行省略号排版占位，与段①同款缺陷，见模块 docstring），
#: 说明行 25。
FIRST_DATA_ROW_CREDIT: Final[int] = 22
LAST_DATA_ROW_CREDIT: Final[int] = 23
FOOTER_ROW_CREDIT: Final[int] = 25
#: footer marker 实测为「差异合理性分析」（A25，纯文字说明，无计算公式）。
FOOTER_MARKER_CREDIT: Final[str] = "差异合理性分析"

MANAGED_LAST_COL_D304: Final[str] = "D"
#: 🔴 两区必须各用不同 UUID 列（D1-4/D4-9 教训：同列会让行身份串区）。J/K 两列实测在 R1-38
#: 全空（独立复核确认，最靠近数据区 A-D 的候选，与 D3-6 选 K 列同款"最近空列"原则一致）。
UUID_COL_DEBIT: Final[str] = "J"
UUID_COL_CREDIT: Final[str] = "K"

#: 4 个受管字段（7 元组，末位 group_header_cell 为 "" —— 单级表头无分组）。
#: 顺序即 Excel 列序 A→D；表头文本与 R10 逐字相等（实测：项目/金额/数据来源/备注）。
#: 两区字段结构完全同构（同一份表头，只是数据行区间不同），共用同一份 field_specs。
FIELD_SPECS_D304: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("label", "A", "editable", "text", "label", "项目", ""),
    ("amount", "B", "editable", "amount", "amount", "金额", ""),
    ("source", "C", "editable", "text", "source", "数据来源", ""),
    ("remark", "D", "editable", "text", "remark", "备注", ""),
)


def _base_spec(
    *,
    section: str,
    table_key: str,
    store_item_id: str,
    first_data_row: int,
    last_data_row: int,
    footer_row: int,
    footer_marker: str,
    footer_carries_total_formula: bool,
    uuid_col: str,
) -> RowTableSheetSpec:
    """两区共用骨架，只差几何/键/身份列/footer 公式性质（同 `phase5_d1_04_bad_debt._base_spec`
    手法，不复制两份字段声明）。本表数据行本身无公式列（差异/说明在 footer 行，不在数据行区间
    内），故不传 `formula_columns`（默认空 tuple，`formula_mask` property 现算为空）。
    """
    return RowTableSheetSpec(
        managed_sheet=MANAGED_SHEET_D304,
        sheet_key=SHEET_KEY_D304,
        table_key=table_key,
        template_id=f"{TEMPLATE_ID_D304}{section.upper()}",
        table_name=f"GT_{TEMPLATE_ID_D304}_{section.upper()}_ROWS",
        uuid_col=uuid_col,
        first_data_row=first_data_row,
        last_data_row=last_data_row,
        footer_row=footer_row,
        header_row=HEADER_ROW_D304,
        store_item_id=store_item_id,
        empty_payload="[]",
        row_identity_key="rowId",
        store_kind=StoreKind.rows,
        field_specs=FIELD_SPECS_D304,
        footer_marker=footer_marker,
        footer_carries_total_formula=footer_carries_total_formula,
        error_label=f"D3-4 预收账款分析表（{section}）",
    )


#: 段①：借方发生额分析（数据行 13-15，UUID 列 J，footer=差异 R17）。
#: 🔴 R17 `B17='=B11-B13-B14-B15-B16'` 是真实公式（硬编码引用行 13-16 共 4 行，但 16 是
#:    排版占位不在受管区内，见模块 docstring "模板预存缺陷"）⇒ `footer_carries_total_formula
#:    =True`（footer 本身确有公式文本，与"公式区间是否覆盖受管末行"是两件事）。
SPEC_D304_DEBIT: Final[RowTableSheetSpec] = _base_spec(
    section="debit",
    table_key="analysis_debit_rows",
    store_item_id="D3-ana-debit-rows",
    first_data_row=FIRST_DATA_ROW_DEBIT,
    last_data_row=LAST_DATA_ROW_DEBIT,
    footer_row=FOOTER_ROW_DEBIT,
    footer_marker=FOOTER_MARKER_DEBIT,
    footer_carries_total_formula=True,
    uuid_col=UUID_COL_DEBIT,
)

#: 段②：贷方发生额分析（数据行 22-23，UUID 列 K，footer=差异合理性分析 R25）。
#: 🔴 R25「差异合理性分析」是纯文字说明行，**无**任何公式（openpyxl 实测该格 `value` 只是
#:    字符串标签，不以 `=` 开头）⇒ `footer_carries_total_formula=False`——本引擎首次出现
#:    footer 行无公式的场景，显式传值不沿用默认 True，见 `phase5_row_table_sheet.
#:    RowTableSheetSpec.footer_carries_total_formula` 字段注释。
SPEC_D304_CREDIT: Final[RowTableSheetSpec] = _base_spec(
    section="credit",
    table_key="analysis_credit_rows",
    store_item_id="D3-ana-credit-rows",
    first_data_row=FIRST_DATA_ROW_CREDIT,
    last_data_row=LAST_DATA_ROW_CREDIT,
    footer_row=FOOTER_ROW_CREDIT,
    footer_marker=FOOTER_MARKER_CREDIT,
    footer_carries_total_formula=False,
    uuid_col=UUID_COL_CREDIT,
)

#: 双区清单（顺序即 Excel 行序：段①在段②之上）。
SPECS_D304: Final[tuple[RowTableSheetSpec, ...]] = (
    SPEC_D304_DEBIT,
    SPEC_D304_CREDIT,
)
