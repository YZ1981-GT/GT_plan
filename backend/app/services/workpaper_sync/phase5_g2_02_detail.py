# -*- coding: utf-8 -*-
"""G2-2「明细表」—— sheet 层薄声明（G 循环首张接入 canary）。

spec: `g-cycle-sync-foundation-and-first-canary` · Task 12

═══ 为什么选 G2-2 作 canary（裁决 GF-H1）═══

它是全 G 循环「表头最简 + 公式列最少 + 有真实载荷」的唯一交集：
单级表头 R9 · 公式列只有 3 个（E/H/J）· 无行级 mask · 真库 475 B 真实载荷 · 无专属 BP。
另两条加分理由（都是**难度加分**而非取巧）：
* 它带 FD-1 **唯一**的 null 占位子形态 —— 首张就把最易误判的那条锁死
  （Task 49 首轮守卫在此翻过车：不剔占位会把 G2 判成 dual_write）；
* 它是 G 循环**唯一**包共享基座 `useWorkpaperEntryDualMode.ts` 的（`useG2DualMode.ts` 59 行），
  接桥路径最接近平台标准形态，验通后对其余 16 条是「更难不是更易」的诚实基线。

否决 G4-7（数据区零公式更简）：它属 G4 册、被 BP-8 卡住 representation 发布，
而 canary 必须走完发布链。

═══ 几何（openpyxl 逐格实测，禁推演）═══

`max_row=32` / `max_column=16`（N/O/P **全空**，0 个 definedName）。

* **单级**表头 **R9**（13 列 A..M，逐字见 `FIELD_SPECS_G202` 的 header_text）
* 数据区 **R10-R15**（6 行）
* footer **R16**「合计」，`C16..K16` 各为 `=SUM(x10:x15)`
* 公式列 **E / H / J**（逐行实测 6×3 = 18 个公式格）：
  - `E{r} = C{r}+D{r}`　期初余额审定数
  - `H{r} = C{r}+F{r}-G{r}`　期末余额
  - `J{r} = H{r}+I{r}`　应收利息余额审定数
* UUID 列 **N** = 有效内容列（13）+ 1；N/O/P 无内容，写入不覆盖任何东西
* 单元格保护与公式列**自洽**：数据行里恰好 E/H/J 三列 `locked=True`、其余 10 列 unlocked；
  footer R16 整行 locked ⇒ `merge._protection` 的格级判定不会与本声明冲突

footer 之下的保护区（**不进** `field_specs`，登记 HTML-only）：
R17 注 · R18「三、审计说明：」· R21「四、审计结论：」· R24-R26 编制说明。

═══ 字段键逐字取自前端行接口 ═══

`useG2Detail.InterestDetailRow`（A-M 十三列）。`seq` 是前端显示序号、**不是**受管列
也**不是**行身份 —— 行身份是 `id`（`generated_prefixed_opaque_string`，
`useG2Detail.generateId()` = `` `detail-${Date.now()}-${Math.random().toString(36).slice(2,8)}` ``，
带随机后缀 ⇒ 无 G1/G3 那种同毫秒撞 id 风险）。

🔴 **L / M 两列的中文标题在模板与前端不同措辞**（FC-5「以模板为权威」）：

| 列 | 模板 R9 逐字 | 前端 el-table-column label 逐字 | 处置 |
|---|---|---|---|
| L | `预计收取日期` | `原计收项目期`（`accrualPeriod`） | `header_text` 取**模板**、`json_key` 取前端键 |
| M | `发函或期后收款情况` | `流通或期后收款情况`（`collectionStatus`） | 同上 |

两处语义对应明确（日期/期间 · 期后收款情况），不是字段错配 ⇒ 不改前端标签
（改可见文案属 UX 变更，不在本 spec 作业面），但**登记**在此免得下一个人以为映射错了。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_G202",
    "MANAGED_SHEET_G202",
    "STORE_ITEM_ID_G202",
    "FORMULA_TEMPLATES_G202",
    "HTML_ONLY_ROWS_BELOW_FOOTER_G202",
]

MANAGED_SHEET_G202: Final[str] = "明细表G2-2"
TEMPLATE_ID_G202: Final[str] = "G22"
SHEET_KEY_G202: Final[str] = "g202-managed"
ROWS_TABLE_KEY_G202: Final[str] = "interest_detail_rows"

#: 🔴 按值取自 `useG2Detail.ts:122` 的 `STORAGE_KEY`，**不按 sheet 号推演**
#: （RG-9/GC-6：该键在生产源码有多处声明，推演会漂）。
#: 变异 `G2-2-rows`（不存在）⇒ 投影恒空。
STORE_ITEM_ID_G202: Final[str] = "G2-2-detail-rows"
ROW_IDENTITY_STORE_KEY_G202: Final[str] = "id"

HEADER_ROW_G202: Final[int] = 9
FIRST_DATA_ROW_G202: Final[int] = 10
LAST_DATA_ROW_G202: Final[int] = 15
FOOTER_ROW_G202: Final[int] = 16
FOOTER_MARKER_G202: Final[str] = "合计"
UUID_COL_G202: Final[str] = "N"

#: footer 之下的保护区行号（HTML-only，不进 field_specs；位移链须整体下移）。
HTML_ONLY_ROWS_BELOW_FOOTER_G202: Final[tuple[int, ...]] = (17, 18, 21, 24, 25, 26)


#: 13 个受管字段（7 元组，末位 `group_header_cell=""` —— **单级**表头无分组）。
#: 顺序即 Excel 列序 A→M；`header_text` 逐字取模板 R9；`json_key` 逐字取
#: `useG2Detail.InterestDetailRow`。E/H/J 三列模板逐行有真公式 ⇒ `formula`，其余 10 列 `editable`。
FIELD_SPECS_G202: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("invest_type", "A", "editable", "text", "investType", "投资种类", ""),
    ("invest_target", "B", "editable", "text", "investTarget", "投资项目", ""),
    ("opening_unadjusted", "C", "editable", "amount", "openingUnadjusted", "期初余额", ""),
    ("opening_adjustment", "D", "editable", "amount", "openingAdjustment", "期初调整数", ""),
    ("opening_audited", "E", "formula", "amount", "openingAudited", "期初余额审定数", ""),
    ("debit", "F", "editable", "amount", "debit", "借方发生", ""),
    ("credit", "G", "editable", "amount", "credit", "贷方发生", ""),
    ("closing_unadjusted", "H", "formula", "amount", "closingUnadjusted", "期末余额", ""),
    ("closing_adjustment", "I", "editable", "amount", "closingAdjustment", "账项调整", ""),
    ("closing_audited", "J", "formula", "amount", "closingAudited", "应收利息余额审定数", ""),
    (
        "interest_due_date",
        "K",
        "editable",
        "text",
        "interestDueDate",
        "应收取的日期（结息日）",
        "",
    ),
    # 🔴 L / M 的 header_text 取**模板**措辞（见模块 docstring 的对照表）
    ("accrual_period", "L", "editable", "text", "accrualPeriod", "预计收取日期", ""),
    (
        "collection_status",
        "M",
        "editable",
        "text",
        "collectionStatus",
        "发函或期后收款情况",
        "",
    ),
)

#: 公式列 → 数据行公式模板（`{r}` 为行号）。逐字实测自 R10-R15。
FORMULA_TEMPLATES_G202: Final[dict[str, str]] = {
    "E": "=C{r}+D{r}",
    "H": "=C{r}+F{r}-G{r}",
    "J": "=H{r}+I{r}",
}

SPEC_G202: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_G202,
    sheet_key=SHEET_KEY_G202,
    table_key=ROWS_TABLE_KEY_G202,
    template_id=TEMPLATE_ID_G202,
    table_name=f"GT_{TEMPLATE_ID_G202}_ROWS",
    uuid_col=UUID_COL_G202,
    first_data_row=FIRST_DATA_ROW_G202,
    last_data_row=LAST_DATA_ROW_G202,
    footer_row=FOOTER_ROW_G202,
    header_row=HEADER_ROW_G202,
    store_item_id=STORE_ITEM_ID_G202,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_G202,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_G202,
    formula_columns=("E", "H", "J"),
    formula_templates=FORMULA_TEMPLATES_G202,
    footer_marker=FOOTER_MARKER_G202,
    error_label="G2-2 应收利息明细表",
)
