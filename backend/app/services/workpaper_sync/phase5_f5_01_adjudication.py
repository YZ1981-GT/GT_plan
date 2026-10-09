# -*- coding: utf-8 -*-
"""F5-1「营业务成本审定表」其他业务成本区 —— sheet 层薄声明。

spec: f5-sync-coverage-and-first-canary · Task 21 · Requirements 1.1 / 1.4 / 2.1
几何证据: .kiro/specs/f5-sync-coverage-and-first-canary/evidence/task21-adjudication-f5-1-geometry.md

═══ 🔴 为什么只声明「其他业务成本」一个区（主营区不可受管）═══

`营业务成本审定表F5-1` 有两个数据区，逐格实测（openpyxl）后的公式分布：

| 区 | 行范围 | 行数 | 每行公式列 | 可编辑格 |
|---|---|---|---|---|
| ① 主营业务成本 | R8~R17 | 10 | **A,B,C,D,E,F,G,H,I 九列全是公式** | **0 个** |
| ② 其他业务成本 | R20~R25 | 6 | E,I 两列 | A,B,C,D,F,G,H,J |

区①连**项目名 A 列**都是公式（`A8 = '主营业务成本月度明细表F5-2'!A11`，逐行递增到 A20），
B/C/D/F/G/H 直引 F5-2 的 N/O/P/R/S/T 列，E/I 是本行横向加总 ⇒ **零用户输入点**。

spec design 原记「主营区 HTML-only」结论正确但理由不足：实测给出的是更强判定 ——
OO 侧往区①写任何值都会被模板公式覆盖，受管它等于登记一个永远只读的投影。
故区①**不进受管清单**（不是"先不接"，是"不该接"）。

═══ 几何（openpyxl 逐格实测）═══

表级两级表头 **R5（组）/ R6（叶子）**：

    A 项目(A5:A6)   B-E 组「本期数」(B5:E5)：B 本期未审数 / C 账项调整 / D 重分类调整 / E 本期审定数
                    F-I 组(F5:I5)：F 上期未审数 / G 账项调整 / H 重分类调整 / I 上期审定数
    J 索引(J5:J6)

🔴 区② **自己没有列表头行**（R19 只有 A 列标题文字「其他业务成本」，B~J 全空），
故复用表级表头 ⇒ 契约 anchor = `A5`。anchor 与受管数据区 R20 之间隔着区① R8~R17 与
小计 R18 —— 按 D3-4 双区先例（`phase5_d3_04_analysis.py` 段② 数据区 R22-23 而
`header_row=10`，中间隔着段① R13-15 与 footer R17）**这是允许的**，不需要为区②造表头行。

数据区 **R20~R25**（6 行）· footer **R26** 小计。

═══ footer（携带合计公式）═══

`A26 = '小计'`，B26~I26 八列全是 `=SUM(B20:B25)` 形态 ⇒ `footer_carries_total_formula=True`
（与 F5-8 锚行型 `False` 相反）。其下 R27 合计 `=B26+B18`、R28 试算平衡表数、R29 差异数
`=E27-E28`，均在 footer 之下，属 HTML-only 区，不进 `field_specs`。

═══ 公式列（mask 由引擎现算，不手写字面量）═══

    E{r} = B{r}+C{r}+D{r}      本期审定数 = 本期未审 + AJE + RJE
    I{r} = F{r}+G{r}+H{r}      上期审定数 = 上期未审 + AJE + RJE

六行逐行同构（实测 R20~R25 公式集合完全一致）⇒ 无需拆区。

═══ UUID 列（逐格实测，修正 spec）═══

实测列占用 `J:2`（`J5:J6` 合并的索引表头 + `J3` 页眉公式）⇒ **J 不是全空列**。
spec design 记「J~N 全空」**有误**，真正的全空列从 **K** 起（K~R 共 8 个）。

取 **K**：fmt 纯 `General` 且 0 值（L 列虽空但带数字格式）。K 在 `max_column=N` 内 ⇒
**无需扩列**（与 F5-8 的 uuid_col `I` 超出 `max_column=H` 不同）。

═══ 字段（逐列对齐前端 `useF5Adjudication.StoredF5AdjRow`）═══

🔴 行身份是 **`rowKey`**（**不是** F5-2/3/5/8 四张用的 `id`）—— 同一册内两种行身份键，
按值 grep 实测所得（FC-4：形态判定禁推演）。

🔴 **无 BP-7**：载入路径 `storedOtherRows` 把 `safeParseRows` 结果原样透传、不按下标重算
`rowKey`；`addRow` 用 `${group}-${Date.now()}` 生成一次即持久化。与 F5-2/3/5 的
`m-${Date.now()}-${i}`（`i` 是 `map` 下标、每次载入重算）不同型，故本区无需 BP-7 处置。

`isFixed` 是前端固定行标记（小计/F5-4 同步行用），模板无对应列 ⇒ store-only。
`currentAdjusted` / `priorAdjusted` / `changeAmount` / `changeRate` / `isEditable` 是
`computeRow` 的派生出参（不在 `StoredF5AdjRow` 里）⇒ 不登记。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_F501_OTHER",
    "MANAGED_SHEET_F501",
    "STORE_ITEM_ID_F501_OTHER",
    "STORE_ONLY_KEYS_F501_OTHER",
    "HTML_ONLY_ANCHOR_ROWS_F501",
    "UNMANAGED_MAIN_ZONE_F501",
]

MANAGED_SHEET_F501: Final[str] = "营业务成本审定表F5-1"
TEMPLATE_ID_F501: Final[str] = "F51"
#: 单一 sheet_key（本表只受管一个区；若日后加区仍共享此值，见 D3-4 先例）。
SHEET_KEY_F501: Final[str] = "f51-managed"
ROWS_TABLE_KEY_F501_OTHER: Final[str] = "adjudication_other_rows"
#: 按值 grep 实测（`useF5Adjudication.ts` 的 `OTHER_STORAGE_KEY`）。
STORE_ITEM_ID_F501_OTHER: Final[str] = "F5-1-adj-other-rows"

#: 🔴 行身份 `rowKey` —— 与同册 F5-2/3/5/8 的 `id` 不同，按值实测所得。
ROW_IDENTITY_STORE_KEY_F501: Final[str] = "rowKey"

#: 表级两级表头（区② 无独立列表头，复用之；实测合并区 B5:E5 / F5:I5 / A5:A6 / J5:J6）。
HEADER_GROUP_ROW_F501: Final[int] = 5
HEADER_LEAF_ROW_F501: Final[int] = 6

FIRST_DATA_ROW_F501_OTHER: Final[int] = 20
LAST_DATA_ROW_F501_OTHER: Final[int] = 25
#: footer `A26='小计'`，B26~I26 全是 SUM(B20:B25) 形态 ⇒ 携带合计公式。
FOOTER_ROW_F501_OTHER: Final[int] = 26
FOOTER_MARKER_F501_OTHER: Final[str] = "小计"
MANAGED_LAST_COL_F501: Final[str] = "J"
#: 全空列 K~R 取 K（纯 General 且 0 值）。在 max_column=N 内 ⇒ 无需扩列。
UUID_COL_F501_OTHER: Final[str] = "K"

#: 🔴 主营业务成本区：九列全公式、零可编辑格 ⇒ 不可受管（登记以证明"不是漏声明"）。
UNMANAGED_MAIN_ZONE_F501: Final[tuple[str, str]] = (
    "R8:R17",
    "主营业务成本区 A~I 九列全是引用 F5-2 的模板公式（含 A 列项目名），"
    "零用户输入点；OO 侧写入必被公式覆盖 ⇒ 不进受管清单。store key F5-1-adj-main-rows。",
)

#: footer 之后的 HTML-only 区（登记以证明"不是漏声明"）。
HTML_ONLY_ANCHOR_ROWS_F501: Final[tuple[tuple[int, str], ...]] = (
    (7, "主营业业成本："),
    (18, "小计"),
    (19, "其他业务成本"),
    (27, "合计"),
    (28, "试算平衡表数"),
    (29, "差异数"),
    (30, "1、审计说明"),
)

#: store-only 键（模板无对应列）。
STORE_ONLY_KEYS_F501_OTHER: Final[tuple[tuple[str, str], ...]] = (
    ("isFixed", "前端固定行标记（小计行/F5-4 同步行不可删改）；模板无该列"),
)

#: 8 个受管字段（7 元组）。E/I 是公式列，不进 field_specs。
FIELD_SPECS_F501_OTHER: Final[
    tuple[tuple[str, str, str, str, str, str, str], ...]
] = (
    ("item_label", "A", "editable", "text", "label", "项目", ""),
    ("current_unadjusted", "B", "editable", "amount", "currentUnadjusted", "本期未审数", "B5"),
    ("current_aje", "C", "editable", "amount", "currentAje", "账项调整", "B5"),
    ("current_rje", "D", "editable", "amount", "currentRje", "重分类调整", "B5"),
    ("prior_unadjusted", "F", "editable", "amount", "priorUnadjusted", "上期未审数", "F5"),
    ("prior_aje", "G", "editable", "amount", "priorAje", "账项调整", "F5"),
    ("prior_rje", "H", "editable", "amount", "priorRje", "重分类调整", "F5"),
    ("index_ref", "J", "editable", "text", "indexRef", "索引", ""),
)

SPEC_F501_OTHER: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_F501,
    sheet_key=SHEET_KEY_F501,
    table_key=ROWS_TABLE_KEY_F501_OTHER,
    template_id=f"{TEMPLATE_ID_F501}OTHER",
    table_name=f"GT_{TEMPLATE_ID_F501}_OTHER_ROWS",
    uuid_col=UUID_COL_F501_OTHER,
    first_data_row=FIRST_DATA_ROW_F501_OTHER,
    last_data_row=LAST_DATA_ROW_F501_OTHER,
    footer_row=FOOTER_ROW_F501_OTHER,
    header_group_row=HEADER_GROUP_ROW_F501,
    header_leaf_row=HEADER_LEAF_ROW_F501,
    store_item_id=STORE_ITEM_ID_F501_OTHER,
    empty_payload="[]",
    row_identity_key=ROW_IDENTITY_STORE_KEY_F501,
    store_kind=StoreKind.rows,
    field_specs=FIELD_SPECS_F501_OTHER,
    formula_columns=("E", "I"),
    formula_templates={
        "E": "=B{r}+C{r}+D{r}",
        "I": "=F{r}+G{r}+H{r}",
    },
    footer_marker=FOOTER_MARKER_F501_OTHER,
    # footer B26~I26 全是 SUM(B20:B25) 形态。
    footer_carries_total_formula=True,
    error_label="F5-1 营业务成本审定表（其他业务成本区）",
)
