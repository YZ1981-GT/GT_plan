# -*- coding: utf-8 -*-
"""D3-1「预收账款审定表」—— `AdjudicationSheetSpec` 实例声明。

spec: d3-sync-coverage-via-row-table-engine · Task 13 · Requirements 4.1 / 4.2 / 4.3

═══ 几何（openpyxl 直读实测复核，2026-09-26 复算，裁决 F3 要求实测不推演）═══

**两区块**（🔴 **不是** D1-1 的 3 区 gross/bd/net，也**不是** D2-1 的 1 区 × 写死 4 行 —— 三个
循环的审定表形态实测互不相同，这正是 `AdjudicationSheetSpec` 要参数化的维度）：

- **区1 一、按照性质分类**：两级表头 6-7（B6=期初数/F6=期末数/J6=比较/L6=原因分析；
  B7-K7 子表头）；数据行 **8-12**（模板画 5 行：A8-A11 四项固定标签 `预收销售固定资产款`/
  `预收销售土地使用权款`/`合同不成立时已收取的对价`/`其他`，A12 无标签是**模板占位第 5 行**；
  前端 `NATURE_ROWS` 只有 4 项，行 12 是占位冗余）；合计行 **13**（`B13=SUM(B8:B12)` 等，
  SUM 区间覆盖含占位的 5 行）。
- **区2 二、按照账龄分类**：两级表头 15-16；数据行 **17-20**（4 行，A17-A20 与前端
  `AGING_ROWS` 4 项逐字对应：`1年以内（含1年）`/`1至2年（含2年）`/`2至3年（含3年）`/`3年以上`）；
  合计行 **21**（`B21=SUM(B17:B20)` 等）。
- 调节行（非独立区，两区合计后的试算平衡校验）：行 22 `A22='试算平衡表数'`（人工/自动填）；
  行 23 `A23='差异数'`（`E23=E21-E22` / `I23=I21-I22`，🔴 **只对账龄区合计做差异**，
  不含性质区）。

30 行 × 12 列（A1:L30），88 公式，无 Excel Table ⇒ 走 `AdjudicationSheetSpec`。

🔴 `row_mode = fixed_rows`：两区都是固定行数（不可增删），前端 `useD3Adjudication.ts` 的
   `NATURE_ROWS` / `AGING_ROWS` 是固定枚举常量。区1「模板 5 行 vs 前端 4 项」的落差在
   section 几何里如实处理（`last_data_row=12` 覆盖占位行，subtotal SUM 区间 8:12）。

🔴 前端 store 键是 per-cell 锚点 `D3-adj-{section}-{rowKey}-{field}`，`section ∈ {nature, aging}`
   （实测 `useD3Adjudication.makeItemId`——注意是 `nature`/`aging`，不是 `by-nature`/`by-aging`，
   后者是 sectionKey 展示用）。field 名：`priorUnadjusted`/`priorAje`/`priorRje`/
   `currentUnadjusted`/`currentAje`/`currentRje`/`reasonAnalysis`（`audited`/`change` 是
   computed 不落库）。另有三个 note item（`D3-adj-note-aging-reason`/`-change-analysis`/
   `-conclusion`，落 footer 之下 A25/A26/A30，HTML-only）+ 一个 TB 种子
   （`D3-adj-trial-balance-amount`）。

🔴 值来源：`currentUnadjusted` 跨 sheet（从 D3-2 聚合 SUMIF）优先、否则手工；`prior*` 手工；
   `audited`/`change` computed。派生格不可 OO 直写（框架层 `is_oo_writable` 纪律）。

🔴 本声明只交付**几何 + 逐格 mask + 值来源**（Task 13 范围，同 Task 6/8/9/11「只声明不翻
   开关」模式）。四态状态机接入与覆盖 UI 是 Task 14。**不翻灰度开关、不重生成契约。**

🔴 框架层纪律：本模块零 wp_code 分支，**不在引擎里加 `if is_d3`**——几何全部由本 sheet 层
   实例化时传入 `AdjudicationSheetSpec`。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_adjudication_sheet import (
    AdjudicationRowMode,
    AdjudicationSection,
    AdjudicationSheetSpec,
    AdjudicationValueSource,
)

__all__ = ["SPEC_D301", "MANAGED_SHEET_D301"]

#: 🔴 实测模板 sheet 真名（`审定表D3-1`，openpyxl 直读确认）。
MANAGED_SHEET_D301: Final[str] = "审定表D3-1"
TEMPLATE_ID_D301: Final[str] = "D31"
SHEET_KEY_D301: Final[str] = f"{TEMPLATE_ID_D301.lower()}-managed"

#: per-cell 锚点键的前缀（前端 `makeItemId` 拼 `D3-adj-{section}-{rowKey}-{field}`）。
D3_ADJ_PREFIX: Final[str] = "D3-adj-"

#: ─── 两个 section（性质分类 / 账龄分类）────────────────────────────────────
#: 🔴 固定行不需 UUID（同 D1-1）：`uuid_col=""`。两区 `table_key` 必须唯一（框架层构造校验）。
SECTION_NATURE: Final[AdjudicationSection] = AdjudicationSection(
    section_key="nature",  # 🔴 与前端 makeItemId 的 section token 逐字对齐（非 by-nature）
    table_key="adj_nature_rows",
    title_row=5,           # 「一、按照性质分类」小标题行
    first_data_row=8,
    last_data_row=12,      # 🔴 模板画 5 行（8-12），A12 是占位冗余行，SUM 区间覆盖到 12
    subtotal_row=13,       # B13=SUM(B8:B12)
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_D301}NATURE",
)

SECTION_AGING: Final[AdjudicationSection] = AdjudicationSection(
    section_key="aging",   # 🔴 与前端 makeItemId 的 section token 逐字对齐（非 by-aging）
    table_key="adj_aging_rows",
    title_row=14,          # 「二、按照账龄分类」小标题行
    first_data_row=17,
    last_data_row=20,      # 4 行，与前端 AGING_ROWS 逐字对应
    subtotal_row=21,       # B21=SUM(B17:B20)
    uuid_col="",
    table_name="",
    template_id=f"{TEMPLATE_ID_D301}AGING",
)

#: ─── 受管字段（审定表列 A-K + L 原因分析）────────────────────────────────
#: 🔴 列级默认 mode：B-K 全部声明为 formula（每个数据行都是公式：区1 B/C/D 跨 sheet SUMIF、
#:    E=B+C+D、F/G/H 跨 sheet SUMIF、I=F+G+H、J=I-E、K=IF；区2 只有 E/I/J/K 公式，B/C/D/F/G/H
#:    为手工空格）。A（项目名）和 L（原因分析）是 editable。
#:    🔴 实际可编辑数据格（区2 的 B/C/D/F/G/H 手工录入）**不进 cell_mask**——它们在列级声明为
#:    formula 只是因为列在区1 是公式列，但逐格判定时未 mask ⇒ 视为可写（同 D1-1 的 D12/D13
#:    手工格处理逻辑）。
_FIELD_SPECS_D301: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("item_name", "A", "editable", "text", "itemName", "项目", ""),
    ("prior_unadjusted", "B", "formula", "amount", "priorUnadjusted", "未审数", "B6"),
    ("prior_aje", "C", "formula", "amount", "priorAje", "账项调整", "B6"),
    ("prior_rje", "D", "formula", "amount", "priorRje", "重分类调整", "B6"),
    ("prior_audited", "E", "formula", "amount", "priorAudited", "审定数", "B6"),
    ("current_unadjusted", "F", "formula", "amount", "currentUnadjusted", "未审数", "F6"),
    ("current_aje", "G", "formula", "amount", "currentAje", "账项调整", "F6"),
    ("current_rje", "H", "formula", "amount", "currentRje", "重分类调整", "F6"),
    ("current_audited", "I", "formula", "amount", "currentAudited", "审定数", "F6"),
    ("change_amount", "J", "formula", "amount", "changeAmount", "变动额", "J6"),
    ("change_rate", "K", "formula", "ratio", "changeRate", "变动率", "J6"),
    ("reason_analysis", "L", "editable", "text", "reasonAnalysis", "原因分析", ""),
)


#: ─── 逐格 mask（实测 88 公式里属两区数据/合计/差异行的公式格）────────────────
#: 🔴 用现算函数生成，**不手写字面量给 formula_mask**（Property 5 纪律）。
#:    实测明细（openpyxl 直读复核，2026-09-26）：
#:    - 区1 数据行 8-11：B/C/D 跨 sheet SUMIF + E=B+C+D + F/G/H SUMIF + I=F+G+H + J=I-E + K=IF
#:      （每行 10 公式格 B..K）
#:    - 区1 占位行 12：仅 E/I/J/K（B12/C12/D12/F12/G12/H12 为空，无 SUMIF）
#:    - 区1 合计行 13：B/C/D/E/F/G/H/I 为 SUM + J=I-E + K=IF（10 格）
#:    - 区2 数据行 17-20：仅 E/I/J/K（账龄区无跨 sheet SUMIF，B/C/D/F/G/H 手工空格）
#:    - 区2 合计行 21：B..J 为 SUM + K=IF（10 格）
#:    - 差异行 23：E23=E21-E22 / I23=I21-I22（🔴 只有 E/I 两格，只对账龄区做差异）
#:    合计 = 4*10 + 4 + 10 + 4*4 + 10 + 2 = 82（+ 表头 6 个底稿目录引用格不计入受管 mask）= 88 公式。
def _build_cell_mask() -> tuple[str, ...]:
    """构建逐格 formula mask（大写 A1 形态）。数字/坐标全部现算，与模板实测一致。"""
    cells: list[str] = []

    # 区1 数据行 8-11：全列 B..K 公式
    for row in range(8, 12):
        for col in "BCDEFGHIJK":
            cells.append(f"{col}{row}")
    # 区1 占位行 12：仅 E/I/J/K（B/C/D/F/G/H 为空）
    for col in ("E", "I", "J", "K"):
        cells.append(f"{col}12")
    # 区1 合计行 13：B..I SUM + J + K
    for col in "BCDEFGHIJK":
        cells.append(f"{col}13")

    # 区2 数据行 17-20：仅 E/I/J/K（账龄区 B/C/D/F/G/H 手工空格，无公式）
    for row in range(17, 21):
        for col in ("E", "I", "J", "K"):
            cells.append(f"{col}{row}")
    # 区2 合计行 21：B..J SUM + K
    for col in "BCDEFGHIJK":
        cells.append(f"{col}21")

    # 差异行 23：只有 E/I 两格（对账龄区合计做差异）
    cells.append("E23")
    cells.append("I23")

    return tuple(sorted(set(cells)))


_CELL_MASK_D301: Final[tuple[str, ...]] = _build_cell_mask()

#: ─── 字段值来源声明（供四态覆盖状态机用，Task 14 接入）───────────────────────
#: 🔴 `current_unadjusted` 从 D3-2 跨 sheet SUMIF 聚合（区1 B8-B11 是 SUMIF；前端优先取
#:    crossSheet 值，为 0 才回落手工）；`prior*` 手工；`audited`/`change` computed。
_VALUE_SOURCES: Final[dict[str, AdjudicationValueSource]] = {
    "prior_unadjusted": AdjudicationValueSource.manual,
    "prior_aje": AdjudicationValueSource.manual,
    "prior_rje": AdjudicationValueSource.manual,
    "prior_audited": AdjudicationValueSource.computed,
    "current_unadjusted": AdjudicationValueSource.cross_sheet,  # D3-2 SUMIF 聚合
    "current_aje": AdjudicationValueSource.manual,
    "current_rje": AdjudicationValueSource.manual,
    "current_audited": AdjudicationValueSource.computed,
    "change_amount": AdjudicationValueSource.computed,
    "change_rate": AdjudicationValueSource.computed,
    "reason_analysis": AdjudicationValueSource.manual,
}

#: ─── HTML-only item 子集（footer 之下的 note 类文本字段 + TB 种子）──────────────
#: 🔴 三个 note item 落在 A25/A26/A30（footer 之下），无对应受管单元格坐标 ⇒ HTML-only
#:    （evidence task1 §3.1「footer 下 static_row 与插行 fail-closed 冲突」判例，同 D4-5）。
#:    `D3-adj-trial-balance-amount` 是 TB 核对种子（行 22 人工/自动填），非公式格，属 HTML-only。
_HTML_ONLY_ITEM_IDS_D301: Final[tuple[str, ...]] = (
    "D3-adj-note-aging-reason",
    "D3-adj-note-change-analysis",
    "D3-adj-note-conclusion",
    "D3-adj-trial-balance-amount",
)


SPEC_D301: Final[AdjudicationSheetSpec] = AdjudicationSheetSpec(
    managed_sheet=MANAGED_SHEET_D301,
    sheet_key=SHEET_KEY_D301,
    template_id=TEMPLATE_ID_D301,
    header_rows=(6, 7, 15, 16),  # 两区各两级表头（区1 6-7 / 区2 15-16）
    sections=(SECTION_NATURE, SECTION_AGING),
    row_mode=AdjudicationRowMode.fixed_rows,
    total_row=21,   # 合计行 = 账龄区小计行（TB 差异对齐账龄区）
    tb_row=22,      # 试算平衡表数
    diff_row=23,    # 差异数（只 E/I）
    footer_marker="合计",
    store_item_id="",     # per-cell 锚点，无单一 store item
    row_identity_key="",  # 固定行无行身份
    per_cell_key_template=f"{D3_ADJ_PREFIX}{{section}}-{{slug}}-{{field}}",
    field_specs=_FIELD_SPECS_D301,
    cell_mask=_CELL_MASK_D301,
    value_sources=_VALUE_SOURCES,
    html_only_item_ids=_HTML_ONLY_ITEM_IDS_D301,
)
