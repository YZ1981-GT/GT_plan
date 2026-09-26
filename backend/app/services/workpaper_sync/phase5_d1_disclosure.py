# -*- coding: utf-8 -*-
"""D1 附注披露（上市公司/国企）—— 形态评估登记（混合布局，无对应框架类型）。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 29 追加 · Requirement 5.6

═══ 评估结论 ═══

两张附注 sheet（上市公司 119 行 / 国企 89 行）是**混合布局**：多个独立小表（分类/质押/
背书贴现/坏账变动/单项计提/ECL/增减变动等），每个有自己的表头和"合计"行，中间夹着提示文字
和"可无限量添加行"标记。大部分格是跨 sheet 公式（引用 D1-1 审定表），少数小表有可编辑行。

**RowTableSheetSpec** 要求单一表头 + 单一数据区 + 单一 footer ⇒ 覆盖不了多个独立小表。
**AdjudicationSheetSpec** 的 sections 模型更接近，但它假设所有 section 共享同一列结构，
附注各小表的列数/列义各不相同（分类表 7 列 / 质押表 2 列 / 背书贴现表 3 列 / 坏账变动表 6 列
等）。**TransposedSheetSpec** 更不适用（前端不是一列一实体的转置矩阵）。

前端 `useD1Disclosure.ts` 按 variant（`listed`/`soe`）+ 小表名（`pledged-rows`/
`endorsed-rows`/`writeoff-change-rows` 等）拼 store 键（`D1-disc-listed-pledged-rows`），
每个小表独立 CRUD——天然适合**每个小表各一个 RowTableSheetSpec**，但前提是要在 Excel 模板里
为每个小表各建一个 Excel Table（当前模板未建），这属模板侧改造而非 provider 侧声明。

🔴 **现状维持 HTML-only**（前端纯 checklist_responses 存储，不接入 Excel 双向同步）。
接入路径：先模板改造（为每个可编辑小表建 Excel Table + 注 UUID 列），再逐表声明
RowTableSheetSpec——这是 D4 的 26 个 per-sheet 模块的同款模式，但在附注 sheet 上首次遇到
"同一 sheet 多个独立 Table"的组合数显著更高（上市公司版至少 8 个可编辑小表）。
"""
from __future__ import annotations

from typing import Final

DISCLOSURE_MIXED_LAYOUT_NOT_EXPRESSIBLE: Final[str] = (
    "D1 附注披露（上市公司/国企）是混合布局：多个独立小表（各有不同列数/列义）+ "
    "跨 sheet 公式 + 提示文字交错。现有三种框架类型（RowTableSheetSpec / "
    "AdjudicationSheetSpec / TransposedSheetSpec）都无法整张覆盖。"
    "接入路径：需先模板改造（为每个可编辑小表建 Excel Table），再逐表声明——"
    "属模板侧改造，不在本 spec 范围。现状维持 HTML-only。"
)

__all__ = ["DISCLOSURE_MIXED_LAYOUT_NOT_EXPRESSIBLE"]
