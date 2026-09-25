# -*- coding: utf-8 -*-
"""E1-11「银行账户情况承诺」—— 第一册**唯一** `static_region`。

spec: e1-sync-coverage-and-first-canary · Task 14 · Requirements 2.1 / 2.2 / 2.4 / 2.6
形态证据: docs/operations/evidence/e1-sync-coverage/e1-form-verdicts.json

═══ 🔴 为什么它是 static_region（三元组实证，不是公式数推演）═══

| 维度 | 实测 |
|---|---|
| store 键 | **零 `-rows` 键** —— 只有 `E1-account-commit` + `E1-account-commit-check-summary` |
| addRow/removeRow 信号 | **零** |
| 模板数据区 | R10 有表头（开户银行名称/银行账号/账户性质/开户日期/销户日期/目前状态），但
  **R11-19 完全空白** —— 它是一份**承诺函正文**（R5-9 段落 + R20 盖章 + R22 声明日期），
  表格只是承诺函里的一个空白填写区 |

⇒ `binding_kind = static_region`：只声明 workbook-scope `defined_name` 锚点，**不建** Excel
   Table、**不注** 隐藏 UUID 列；binding 由 `_static_region_bindings(provider=…)` 自动生成，
   不需手动接线 `sibling_bindings`。

🔴 **本张的价值 = 验证「绕开整条位移链」**（spec Task 14 的转绿判据）：
   `static_region` 走 `_plan_static_writes` 按绝对坐标直写，**不经**
   `row_shift` / footer 两门 / minted UUID / workbook 传播
   （`excel_materialize.py:1657`）。那条位移链是本 spec 家族最脆弱的一段 ——
   能走静态就不该硬塞行表。

🔴 **公式数阈值是错的判据**（spec 裁决 H8 / 自省变异）：E1-9 / E1-10 / E1-11 三张**各只 7 公式**，
   首版据此把三张全判 `static_region`。实证只有本张成立：E1-9 的键是模板化
   `` `E1-cash-count-${variant}-rows` ``、E1-10 是 `E1-account-list-rows`，两张都是动态行表。

═══ OCR 第二写入方（spec E1-P16）═══

本张 OCR 提及 **43 次**，与 E1-10（同 43 次）**成对出现** ⇒ 受管后必须让 OCR 确认入口在 OO
编辑态下 `disabled` 且给可见中文原因。OCR 对 `-rows` 键是**整表替换**语义，与 OO forcesave
构成两个批量写入方；D4 范式**零 OCR**（d4 目录弹窗 0 个）⇒ 无先例可抄。
本模块以 :data:`OCR_DIALOG_COMPONENTS_E111` 显式登记该事实，供宿主 gating 与判据引用。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.excel_extract import BindingKind
from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

__all__ = [
    "SPEC_E111",
    "MANAGED_SHEET_E111",
    "STORE_ITEM_ID_PREFIX_E111",
    "STORE_ITEM_IDS_E111",
    "CROSS_SHEET_SNAPSHOT_KEY_E111",
    "STATIC_CELL_ANCHORS_E111",
    "OCR_DIALOG_COMPONENTS_E111",
    "HOST_COMPONENT_E111",
]

#: 宿主组件（**无 composable**，直接用 allResponses；段落表单形态）。
HOST_COMPONENT_E111: Final[str] = (
    "audit-platform/frontend/src/components/workpaper/e1/E1TabAccountCommitment.vue"
)

MANAGED_SHEET_E111: Final[str] = "银行账户情况承诺E1-11"
TEMPLATE_ID_E111: Final[str] = "E111"
SHEET_KEY_E111: Final[str] = f"{TEMPLATE_ID_E111.lower()}-managed"
TABLE_KEY_E111: Final[str] = "account_commitment_static"

#: 🔴 零 `-rows` 键（按值 grep 实测，**在 `.vue` 组件里而非 composable** ——
#:    `E1TabAccountCommitment.vue` 明写「No composable — directly uses allResponses」）。
#:    全部是 `fixed_text` 形态，非行数组。
#:
#: 🔴 **命名不一致陷阱**：note/conclusion 两键用 `E1-commit-` 前缀，而主键用
#:    `E1-account-commit` 前缀 —— **不是**同一前缀派生。照「统一前缀」推演会造出不存在的键。
STORE_ITEM_ID_PREFIX_E111: Final[str] = "E1-account-commit"
STORE_ITEM_IDS_E111: Final[tuple[str, ...]] = (
    "E1-account-commit-check-summary",
    "E1-commit-audit-note",
    "E1-commit-audit-conclusion",
)

#: E1-10 ↔ E1-11 联动键（`useE1AccountList.E1_ACCOUNT_COMMIT_SNAPSHOT_KEY`）。
#: 🔴 它由 **E1-10 侧**写入，本张只读 ⇒ 受管本张时不得把它当自身 store（否则两方向写同一键）。
CROSS_SHEET_SNAPSHOT_KEY_E111: Final[str] = "E1-account-commit-snapshot"

#: workbook-scope definedName 锚点（`static_region` 的区域边界，动态区必空的那个字段）。
DEFINED_NAME_E111: Final[str] = f"GT_MANAGED_REGION_{TEMPLATE_ID_E111}"

#: 承诺函的空白填写表区（R10 表头 + R11-19 空白区）。
#: 🔴 `static_region` 按**绝对坐标**直写 ⇒ 这里记的是坐标区间，不是「数据行范围 + 插行规则」。
HEADER_ROW_E111: Final[int] = 10
FIRST_STATIC_ROW_E111: Final[int] = 11
LAST_STATIC_ROW_E111: Final[int] = 19
MANAGED_LAST_COL_E111: Final[str] = "F"

#: 静态受管格锚点：`(store 字段键, 绝对坐标, 说明)`。
#: 🔴 承诺函正文段落与盖章/日期区是 HTML-only（它们是版式文本，不是结构化数据）。
STATIC_CELL_ANCHORS_E111: Final[tuple[tuple[str, str, str], ...]] = (
    ("commitment_entity", "A7", "承诺主体段落（「本公司（XXX公司）…」）"),
    ("commitment_date_text", "A9", "承诺截止日段落（「截至 20XX年X月…」）"),
    ("seal_note", "D20", "（公司盖章）"),
    ("declaration_date", "E22", "声明日期"),
)

#: 🔴 OCR 确认弹窗组件（提及 43 次，与 E1-10 成对）—— 受管后须在 OO 编辑态下 disabled。
#:    OCR 对受管键是**整表替换**语义，与 OO forcesave 构成两个批量写入方（spec 裁决 H10）。
OCR_DIALOG_COMPONENTS_E111: Final[tuple[str, ...]] = (
    "E1AccountCommitOcrConfirmDialog",
)

#: 静态区无受管业务字段列表（按绝对坐标直写，不走 field_specs 的列映射）。
#: 保留空元组以显式表达「本区无行维度字段」——引擎据 `row_identity_key == ""` 拒绝行表投影。
FIELD_SPECS_E111: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = ()

SPEC_E111: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_E111,
    sheet_key=SHEET_KEY_E111,
    table_key=TABLE_KEY_E111,
    template_id=TEMPLATE_ID_E111,
    table_name="",   # 🔴 static_region 必空（BindingKind 分派铁律）
    uuid_col="",     # 🔴 static_region 必空
    first_data_row=FIRST_STATIC_ROW_E111,
    last_data_row=LAST_STATIC_ROW_E111,
    # static_region 不经 footer 两门；此处记模板实际无 footer 合计行的事实（取末行 +1 占位）
    footer_row=LAST_STATIC_ROW_E111 + 1,
    header_row=HEADER_ROW_E111,
    binding_kind=BindingKind.static_region,
    defined_name=DEFINED_NAME_E111,
    store_item_id=STORE_ITEM_ID_PREFIX_E111,
    empty_payload="",   # fixed_text 形态的 per-item 缺省是空串（**不是** "[]"）
    row_identity_key="",   # 🔴 无行维度
    store_kind=StoreKind.fixed_text,
    field_specs=FIELD_SPECS_E111,
    formula_columns=(),
    footer_marker="",
    error_label="E1-11 银行账户情况承诺",
    html_only_item_ids=(),
)
