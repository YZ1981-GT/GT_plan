"""D1-6「应收票据业务模式分析」—— 可行性评估登记（**不声明** `RowTableSheetSpec`）。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 30 · Requirement 5.6
证据: .kiro/specs/d1-sync-row-table-engine-and-d1-coverage/evidence/task30-d1-6-feasibility.md

═══ 评估对象 ═══

D1-6 有两个受管候选：`D1-bm-basis-rows`（3 固定行，已判定标准行表，不在本模块登记范围）与
`D1-bm-qa-matrix`（4×3 真二维矩阵，`B17:D20`，本模块登记对象）。前端
`useD1BusinessMode.ts` 的 `QAMatrix{questions[4], columns[3], cells:QACell[4][3]}`——
4 个固定问题 × 3 个固定组合，格子值域 `'Y'|'N'|''`，矩阵形状永不增删。

═══ 🔴 裁决：`TransposedSheetSpec` 与 `static_region` 都表达不了 ═══

**`TransposedSheetSpec`**：核心设计假设是动态多实体（一列一实体，超模板末列即扩列）+
异构字段类型（`field_rows` 一字段一行，各字段语义/类型不同——对照真实先例 D4-12：21 个
不同语义字段行 × N 份合同列）。D1-6 的 3 列组合永久固定（无扩列）、12 格统一同类型枚举，
`identity_carrier_row`/`identity_carrier_prefix`（给每实体列打隐藏 UUID）对写死的列头
标签毫无意义。设计契约与实际语义不匹配。

**`static_region`**：`contracts.py:_parse_field`（第 908-934 行）的 schema 硬约束——
`cell.row_from` 只接受字面量 `"row_identity"` 或单个 `int >= 1`，**没有「行区间」表达**。
字段粒度永远是单格（一个 field_spec ↔ 一个绝对坐标），不存在"一个 field_spec 横跨
first_data_row..last_data_row 多行"的机制。排查全部现存 `static_region` 真实先例
（E1-11 `STATIC_CELL_ANCHORS_E111` 四个互不相关坐标 / D1-4 第三区 `SPEC_D104_NOTETYPE`
灰度从未开启、从未真实跑过引擎），均无"两个正交维度都需要被结构化表达"的矩阵先例。
拆成 12 个独立单格 field_specs 技术上合法，但等于放弃矩阵结构，需额外手写 12 键映射表，
超出本任务范围。
"""
from __future__ import annotations

from typing import Final

#: 🔴 **Requirement 5.6 登记**：D1-6 的 4×3 QA 矩阵（`D1-bm-qa-matrix`，`B17:D20`）用现有两条
#: 引擎表达路径都表达不了——不是语法凑不出来，是设计契约与实际语义不匹配。
#:
#: 1. `TransposedSheetSpec` 假设动态多实体（D4-12 先例：N 份合同列可动态扩列）+ 异构字段
#:    类型；D1-6 是 3 列永久固定 + 12 格统一同类型枚举，`identity_carrier_*` 这套给
#:    实体列打隐藏 UUID 的机制对写死的列头标签无业务含义。
#: 2. `static_region`（`RowTableSheetSpec.binding_kind`）经 `contracts.py:_parse_field`
#:    实测确认 `cell.row_from` 只接受 `"row_identity"` 或单个 `int>=1`，无「行区间」
#:    表达——字段粒度恒为单格，不支持一个 field_spec 横跨多行的矩阵语义。排查全部
#:    现存 static_region 先例（E1-11/D1-4 第三区）均为互不相关的散列单格集合，
#:    无本引擎处理过矩阵形态的真实先例。
#:
#: 唯一技术可行但被排除的路径：拆成 12 个独立单格 `static_region` field_specs（放弃
#: 矩阵结构，需额外手写 12 键 ↔ `cells[4][3]` 映射表）——超出本任务范围，不在此登记为解。
#:
#: 现状维持：`useD1BusinessMode.ts` 纯 `checklist_responses` JSON 存储，不接入 Excel
#: 双向同步契约。`D1-bm-basis-rows`（3 固定行，标准行表）不受本登记影响，其接入路径由
#: 后续批次任务决定。owner 建议：若未来确有强需求要让矩阵走 OO 双向同步，需先扩展
#: `contracts.py` schema 支持"行区间字段"这一新原语（设计级变更，同 H1 的
#: `UPSTREAM_DEBT_FOUR_LEVEL_HEADER_NOT_EXPRESSIBLE` 修法路径），不在框架层开特例分支。
QA_MATRIX_NO_ROW_RANGE_CELL_MAPPING_NOT_EXPRESSIBLE: Final[str] = (
    "Task 30 评估：D1-6 的 4×3 QA 矩阵（D1-bm-qa-matrix，模板绝对坐标 B17:D20）用 "
    "TransposedSheetSpec 与 static_region 均表达不了。TransposedSheetSpec 假设动态多"
    "实体+异构字段类型（D4-12 先例：N 份合同列可扩列），D1-6 是 3 列永久固定+12 格统一"
    "同类型枚举，identity_carrier_* 机制对写死列头标签无意义。static_region 经 "
    "contracts.py:_parse_field 实测确认 cell.row_from 只接受 row_identity 或单个 "
    "int>=1，无「行区间」表达——字段粒度恒为单格，本引擎从未处理过需要两个正交维度"
    "同时结构化表达的矩阵形态（E1-11/D1-4 第三区均为散列单格集合，非矩阵先例）。"
    "拆成 12 个独立单格 field_specs 技术上合法但放弃矩阵结构，超出本任务范围。"
    "现状维持 useD1BusinessMode.ts 纯 JSON 存储，不接入 Excel 双向同步契约。"
    "修法需扩展 contracts.py schema 支持「行区间字段」新原语，属设计级变更，"
    "owner 建议归 contract schema 侧后续任务。"
)

__all__ = ["QA_MATRIX_NO_ROW_RANGE_CELL_MAPPING_NOT_EXPRESSIBLE"]
