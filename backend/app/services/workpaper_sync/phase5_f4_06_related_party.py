# -*- coding: utf-8 -*-
"""F4-6「关联方及交易检查表」—— sheet 层薄声明（F4 首张 canary）。

spec: f4-sync-coverage-and-first-canary · Task 7 · Requirements 1.1 / 2.2
几何证据: .kiro/specs/f4-sync-coverage-and-first-canary/evidence/task2-morphology-and-geometry.md

═══ 为什么它排 F4 首张（裁决 F4-H1）═══

与 F1-6 / F3-6 三家同型：单级表头 + 期末余额 1 个公式列 + footer 合计 + `rowId` 行身份 +
零跨 sheet 取数 + **FC-10 零命中**（全表无任何百分比格式格，逐格实测）⇒ 失败面最小。

🔴 **同型不等于同式**：F4-6 的 `F=C+E-D`（期初 + 贷方 − 借方，**负债类**）与 F1-6 的
`F=C+D-E`（资产类借方在前）互为镜像。声明层写法可复用，公式模板必须逐格实测（FC-4）。

═══ 几何（openpyxl 逐格实测）═══

单级表头 **R6**（12 列 A-L）· 数据区 **R7-11**（5 行）· footer **R12**「合计」（纯两字无空格）。

    A 关联方名称  B 关联关系  C 期初余额  D 本期借方  E 本期贷方  F 期末余额(公式)
    G 账龄  H 定价政策  I 发生原因（款项性质）  J 期后付款金额  K 索引号  L 备注

公式实测：数据区仅 **F 列**逐行 `=C{r}+E{r}-D{r}`（R7-R11 五行同款）；
footer R12 有 `SUM(C7:C11)` / `SUM(D…)` / `SUM(E…)` / `SUM(F…)` / `SUM(J7:J11)` 五列。
页眉 R3/R4 引「底稿目录」7 格。全表 17 公式 = 7 页眉 + 5 数据行 + 5 footer。

UUID 列：全空列 M/N/O/P/Q/R/S ⇒ 取最靠近受管区的 **M**。
（🔴 sheet 的 `max_column` 实测是 **O**，不是 spec 受管区清单写的 Q ——
不影响声明，因为受管列止于 L。）

═══ 🔴 模板缺陷（登记，不在本 spec 处理）═══

数据验证实测两条，**其中一条是悬空引用**：

| 区间 | `formula1` | 判定 |
|---|---|---|
| `B7` | `$B$18:$B$25` | ✅ 正确 —— 指向 footer 之下的「勿改、勿删」关联方类型源（8 项：实际控制人 / 控股股东 / …） |
| `B8:B11` | **`$N$7:$N$14`** | 🔴 **N 列全空**（逐格实测非空计数 0）⇒ R8-R11 四行的关联关系下拉是**空列表** |

即模板只给第一行配了可用下拉，后四行的 DV 指向一片空区（与 F5-7!G31 引越界空区同型的
模板缺陷）。本 spec **不改模板字节**（`backend/wp_templates/` 运行时只读 + sha 冻结），
登记为顺带发现；受管不受影响（UUID 列取 M，不碰 N 列；DV 区间随位移由框架层维护）。

═══ store-only 字段（模板无对应列，登记以证明"不是漏声明"）═══

`seq`（模板 A 列是关联方名称不是序号）· `sourceRowId`（来源 F4-2 明细行 id）·
`linked` / `sourceClosingBalance` / `reconciliationDifference` / `concentration` /
`riskFlags` / `riskLevel`（全部前端派生，用于与 F4-2 明细对账与风险提示）。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_F406",
    "MANAGED_SHEET_F406",
    "STORE_ITEM_ID_F406",
    "STORE_ONLY_KEYS_F406",
    "TEMPLATE_DEFECT_F406",
]

MANAGED_SHEET_F406: Final[str] = "关联方及交易检查表F4-6"
TEMPLATE_ID_F406: Final[str] = "F46"
SHEET_KEY_F406: Final[str] = "f46-managed"
ROWS_TABLE_KEY_F406: Final[str] = "related_party_ap_rows"
#: 按值 grep 实测（`useF4RelatedParty.ts` 的 `STORAGE_KEY`）。无 legacy 别名主键。
STORE_ITEM_ID_F406: Final[str] = "F4-6-rows"

#: 行身份 `rowId`（同 F3，与 F5 的 `id` 相反 —— 逐 entry 按值实测，FC-4）。
ROW_IDENTITY_STORE_KEY_F406: Final[str] = "rowId"

HEADER_ROW_F406: Final[int] = 6
FIRST_DATA_ROW_F406: Final[int] = 7
LAST_DATA_ROW_F406: Final[int] = 11
FOOTER_ROW_F406: Final[int] = 12
FOOTER_MARKER_F406: Final[str] = "合计"
MANAGED_LAST_COL_F406: Final[str] = "L"
UUID_COL_F406: Final[str] = "M"

#: 🔴 模板缺陷登记（不改字节）。
TEMPLATE_DEFECT_F406: Final[dict[str, str]] = {
    "kind": "dangling_data_validation_source",
    "where": "B8:B11",
    "formula1": "$N$7:$N$14",
    "why_broken": "N 列全空（逐格实测非空计数 0）⇒ R8-R11 的关联关系下拉是空列表",
    "correct_sibling": "B7 的 DV 指向 $B$18:$B$25（8 个关联方类型），是正确形态",
    "handling": "不改模板字节（运行时只读 + sha 冻结）；UUID 列取 M 不碰 N 列；登记为顺带发现",
}

#: store-only 键（模板无对应列）。
STORE_ONLY_KEYS_F406: Final[tuple[tuple[str, str], ...]] = (
    ("seq", "行序号；模板 A 列是「关联方名称」不是序号列"),
    ("sourceRowId", "来源 F4-2 明细行 id，用于与明细对账"),
    ("linked", "是否已与 F4-2 明细关联（前端派生）"),
    ("sourceClosingBalance", "F4-2 明细侧期末余额（前端拉取）"),
    ("reconciliationDifference", "本表期末余额 − 明细侧期末余额（前端派生）"),
    ("concentration", "占应付账款总额比重（前端派生）"),
    ("riskFlags", "风险提示数组（前端派生）"),
    ("riskLevel", "风险等级 none/warning/danger（前端派生）"),
)

#: 12 个受管字段（7 元组）。单级表头 ⇒ 第 7 位 group_header_cell 全为 ""。
FIELD_SPECS_F406: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("party_name", "A", "editable", "text", "partyName", "关联方名称", ""),
    ("relationship", "B", "editable", "text", "relationship", "关联关系", ""),
    ("opening_balance", "C", "editable", "amount", "openingBalance", "期初余额", ""),
    ("current_debit", "D", "editable", "amount", "currentDebit", "本期借方", ""),
    ("current_credit", "E", "editable", "amount", "currentCredit", "本期贷方", ""),
    ("closing_balance", "F", "formula", "amount", "closingBalance", "期末余额", ""),
    ("aging", "G", "editable", "text", "aging", "账龄", ""),
    ("pricing_policy", "H", "editable", "text", "pricingPolicy", "定价政策", ""),
    ("transaction_nature", "I", "editable", "text", "transactionNature", "发生原因（款项性质）", ""),
    ("post_payment_amount", "J", "editable", "amount", "postPaymentAmount", "期后付款金额", ""),
    ("index_no", "K", "editable", "text", "indexNo", "索引号", ""),
    ("remark", "L", "editable", "text", "remark", "备注", ""),
)

#: 🔴 负债类方向：期初 + 贷方 − 借方。与 F1-6 的 `=C+D-E`（资产类）镜像，逐格实测所得。
FORMULA_TEMPLATES_F406: Final[dict[str, str]] = {
    "F": "=C{r}+E{r}-D{r}",
}

SPEC_F406: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_F406,
    sheet_key=SHEET_KEY_F406,
    table_key=ROWS_TABLE_KEY_F406,
    template_id=TEMPLATE_ID_F406,
    table_name=f"GT_{TEMPLATE_ID_F406}_ROWS",
    uuid_col=UUID_COL_F406,
    first_data_row=FIRST_DATA_ROW_F406,
    last_data_row=LAST_DATA_ROW_F406,
    footer_row=FOOTER_ROW_F406,
    header_row=HEADER_ROW_F406,
    store_item_id=STORE_ITEM_ID_F406,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_F406,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_F406,
    formula_columns=("F",),
    formula_templates=FORMULA_TEMPLATES_F406,
    footer_marker=FOOTER_MARKER_F406,
    error_label="F4-6 关联方及交易检查表",
)
