# -*- coding: utf-8 -*-
"""D1-14「应收票据坏账准备会计政策检查」—— **不声明 RowTableSheetSpec**（纯文本段落表）。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 29 · Requirement 5.6

═══ 评估结论：不进 Excel 双向同步 ═══

openpyxl 实测（2026-09-26）：`应收票据坏账准备会计政策检查D1-14` 是纯文本段落表（四个
「节」：政策概述/历史损失/前瞻性信息/同行业对比 + 审计说明/结论），无表头行、无数据区、
无 footer SUM、无 UUID 痕迹、无 definedName。

前端 `useD1PolicyCheck.ts` 存储为 **10 个独立文本键**（`D1-policy-overview-left/right` /
`ecl-portfolio/individual/migration/right` / `change-flag/content/reason` / `conclusion`），
不是行数组 store —— 属 `fixed_text` 段落表单形态。`D1TabIndex.vue` 的 progressKeys 是
`['D1-policy-paragraphs']`（单一聚合键，非 `-rows` 后缀）。

tasks.md 原描述 D1-14 为「10 个标量，`static_region` 候选」，实测后发现不准确：它不是
10 个**绝对坐标标量格**（那是 D4-13 那种有固定行列坐标的格子），而是 10 个**无结构纯文本**
段落，在 Excel 模板里就是空白区域（无数据验证、无公式、无受管结构）。用 `static_region` 或
`RowTableSheetSpec` 表达都没有意义，因为 Excel 侧根本没有"应该映射到哪个格子"的坐标。

🔴 按 Requirement 5.6 的 `NOT_EXPRESSIBLE` 范式登记。现状维持 HTML-only 文本键存储。
"""
from __future__ import annotations

from typing import Final

#: Requirement 5.6 登记：D1-14 是纯文本段落，既无行表几何也无标量绝对坐标，
#: RowTableSheetSpec / static_region / TransposedSheetSpec 三条路径**都不适用**。
POLICY_CHECK_NO_TABULAR_GEOMETRY_NOT_EXPRESSIBLE: Final[str] = (
    "Task 29 评估：D1-14（应收票据坏账准备会计政策检查）是纯文本段落表——"
    "四个「节」（政策概述/历史损失/前瞻性信息/同行业对比）+ 审计说明/结论，"
    "前端存为 10 个独立文本键（D1-policy-overview-left 等），"
    "模板里全部是空白区域（无表头行/无数据区/无 footer SUM/无绝对坐标标量格）。"
    "tasks.md 原描述「10 个标量 static_region 候选」不准确——static_region 要求"
    "绝对行列坐标（如 D4-13 的固定 cell 锚点），D1-14 连『应该映射到哪个格子』都没有。"
    "现状维持 useD1PolicyCheck.ts 纯 checklist_responses 文本键存储，不接入 Excel 双向同步。"
    "修法需要先在模板里定义 10 个 definedName 锚点区域，不在本 spec 范围。"
)

__all__ = ["POLICY_CHECK_NO_TABULAR_GEOMETRY_NOT_EXPRESSIBLE"]
