# Implementation Plan: d2-ar-disclosure-soe-alignment

## Overview

4 个 Sprint：先修上市版遗留的过期测试拿到干净基线，再按「模型 → 同步 → UI → 附注模板」
逐层对齐国企版，最后补后端透传与契约测试收口。

## Tasks

- [x] 1. Sprint 0 — 基线归零
  - [x] 1.1 修正 `d2NoteSectionMap.spec.ts` 5 条过期断言
    - snapshot 工厂 `soeClassEndRows`/`soeClassPriorRows` → `classWideEndRows`/`classWidePriorRows`
    - 上市分类/单项双期 6/5 列断言、国企变动 6 列断言、`D2_NOTE_TEXT_SECTIONS` 9 键断言
    - _Requirements: 7.1_

- [x] 2. Sprint 1 — 底稿数据模型（国企）
  - [x] 2.1 `D2TwoPeriodManualRow` 增 `provision` / `priorProvision`
    - hydrate/persist/新增行默认 0；旧持久化行缺字段读入为 0（P8）
    - _Requirements: 2.4_
  - [x] 2.2 派生比例纯函数
    - `portfolioRatio(row, groupRows, period)`：应收账款 ÷ 组合本期合计 × 100
    - `otherPortfolioRate(row, period)`：坏账准备 ÷ 账面余额 × 100
    - 分母 0 → 0（P3）
    - _Requirements: 1.2, 2.2_
  - [x] 2.3 `buildSnapshot` 补国企字段
    - 组合分表行带 `provision`/`priorProvision`/`lossRate`/`priorLossRate`
    - `otherPortfolioRows` 带 `provision`/`priorProvision`
    - _Requirements: 1.3, 2.3_

- [x] 3. Sprint 2 — 同步层（国企列头与新表）
  - [x] 3.1 新增 `PORTFOLIO_COLUMNS_SOE`（7 列，双期分组）
    - `账 龄` + `期末数{应收账款, 比例(%), 坏账准备}` + `期初数{...}`
    - SOE 分支不再复用 `AGING_COLUMNS_SOE`
    - _Requirements: 1.1, 1.3_
  - [x] 3.2 改写 `OTHER_PORTFOLIO_COLUMNS_SOE`（7 列，双期分组）
    - `组合名称` + `期末数{账面余额, 计提比例（%）, 坏账准备}` + `期初数{...}`
    - _Requirements: 2.1, 2.3_
  - [x] 3.3 `MOVEMENT_COLUMNS_SOE` 三变动列加 `group: 本期变动金额` 并改 label 为源模板字面
    - _Requirements: 3.1, 3.2_
  - [x] 3.4 国企继续涉入表
    - `D2_TABLE_NAMES.soe.continuedInvolvement`；`CONTINUED_INVOLVEMENT_COLUMNS_SOE`（2 列）
    - SOE 分支按资产/负债分块转形推送（P4）
    - _Requirements: 4.1, 4.2_

- [x] 4. Checkpoint — Sprint 1~2 验收
  - `npx vitest run` D2 子集全绿

- [x] 5. Sprint 3 — 底稿 UI（国企）
  - [x] 5.1 组合分表两级表头 7 列
    - `el-table-column` 分组：期末数 / 期初数 各 3 子列，比例列只读派生
    - _Requirements: 1.1, 1.2_
  - [x] 5.2 其他组合表 7 列
    - 双期 账面余额（可编辑）/ 计提比例（%）（只读派生）/ 坏账准备（可编辑）
    - _Requirements: 2.1, 2.2_
  - [x] 5.3 终止确认块补「说明」textarea（含 A/B 范式占位）
    - `note-derecognition` 键；autosize minRows 3
    - _Requirements: 4.3, 4.4_

- [x] 6. Sprint 4 — 附注模板与后端透传
  - [x] 6.1 复用既有 `_carry_seed_column_meta` 透传（**不新增实现**）
    - 实测该机制已由 spec `f2-inventory-disclosure-template-alignment` R5 落地并接线；
      本任务只确认接线覆盖 `八、5` 走的多表分支，并在 7.2 补契约测试
    - _Requirements: 6.1, 6.2, 6.3_
  - [x] 6.2 幂等脚本 `fix_note_ar_soe_structure.py`
    - 重写 `八、5` 的 `tables`（13 张）与 `text_sections`（8 条）+ `_aligned_by` 标记
    - _Requirements: 5.1~5.7_
  - [x] 6.3 执行脚本并核对产出
    - JSON 合法、`八、5` 结构符合 design §4、连跑两次逐字节相等
    - _Requirements: 5.7_

- [x] 7. Sprint 5 — 契约测试与收口
  - [x]* 7.1 前端契约测试（P1/P2/P3/P4/P5）
    - **Validates: Requirements 1.1, 1.3, 2.1, 2.3, 3.1, 4.2, 7.2, 7.3**
  - [x]* 7.2 后端模板结构 + 幂等测试（P6/P7）
    - **Validates: Requirements 5.1~5.7, 6.1~6.3, 7.4**
  - [x] 7.3 清理临时脚本与 dump 产物，跑回归
    - `python -m pytest` 相关子集 + `npx vitest run` D2 子集

- [x] 8. Checkpoint — 最终验收
  - Playwright 实测：底稿国企版录入 → 同步到附注 → `八、5` 呈现 13 TAB / 两级表头 / 说明文本

## Task Dependency Graph

```
1.1 ─> 2.1 ─> 2.2 ─> 2.3 ─┐
                          ├─> 4 ─> 5.1 ─┐
        3.1 ─ 3.2 ─ 3.3 ─ 3.4 ─┘   5.2 ─┼─> 7.1 ─┐
                                    5.3 ─┘        │
        6.1 ─> 6.2 ─> 6.3 ─────────────> 7.2 ─────┴─> 7.3 ─> 8
```

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1.1"] },
    { "wave": 2, "tasks": ["2.1", "6.1"] },
    { "wave": 3, "tasks": ["2.2"] },
    { "wave": 4, "tasks": ["2.3"] },
    { "wave": 5, "tasks": ["3.1", "3.2", "3.3", "3.4"] },
    { "wave": 6, "tasks": ["4"] },
    { "wave": 7, "tasks": ["5.1", "5.2", "5.3", "6.2"] },
    { "wave": 8, "tasks": ["6.3"] },
    { "wave": 9, "tasks": ["7.1", "7.2"] },
    { "wave": 10, "tasks": ["7.3"] },
    { "wave": 11, "tasks": ["8"] }
  ]
}
```

## Notes

- **`*` 任务同样必须完成**（本项目约定），仅表示测试类任务。
- **🔴 本次涉及的已修改文件禁用 `readFile` 校对**：实测 `readFile` 会返回 HEAD 版本，
  一律用 python 直读（`open(...).read()`）确认落盘内容。
- **禁用 PowerShell 多行 `python -c`**：PSReadLine 会崩；一律写脚本文件执行。
- **Vue 模板属性禁用中文引号**：占位文本里的 `“-”` 只能出现在 `.ts` 常量或 textarea 文本节点，
  不能进 `placeholder="..."` 属性值。
- **不改编号口径**（见 design D1），不动 `note_template_bindings.json`。
- **不新造 row_type**（见 design D6），`减：坏账准备` 沿用 `data`。

## 附带修复：附注表头分组启发式误判（已解决，用平台既有 `flat` 三态）

**现象**：`（4）本期实际核销的应收账款` 在附注呈现出不存在的父表头「核销」——
列头 `核销金额` / `核销原因` 共享前缀「核销」，被后端
`note_sub_table_projector._infer_groups_from_headers` 反猜成分组。
该行为改动前即存在（核销表列头一直无 `group`），非本 spec 引入。

**修法**：不改推断逻辑默认值（那会让全平台依赖推断取得分组的表退化为扁平列），
而是用平台既有的 `ColumnDef.flat` 三态显式声明单级表头
（`_extract_column_groups`：`None`=未声明可推断 / `[]`=任一列带 `flat` 禁推断 / 非空=显式分组）。

给国企 7 组源模板单行表头列定义补 `flat: true`（标在标签列即对整表生效）：
`AGING` / `INDIVIDUAL` / `REVERSAL` / `WRITEOFF_DETAIL` / `TOP5` /
`DERECOGNIZED` / `CONTINUED_INVOLVEMENT`。

**守卫**：`d2NoteSectionMap.spec.ts` 新增断言「SOE 每张表要么显式分组要么显式 `flat`」
+ 二者互斥 + 核销表 `flat` 锚点，防止后续漂移。

**实测**：重新同步后附注 `（4）本期实际核销的应收账款` 恢复单行 6 列，
其余 4 张宽表两级表头不受影响。

## 附带修复 2：国企版多推「1年以内小计」结构行（已解决）

**事实核对**：`1年以内小计：` 只存在于**上市版**源模板（r9~r12 把 1年以内细分为
`其中：0-X个月` / `X-Y个月`，故需小计）；**国企版** r7~r15 为 6 档账龄无细分，**无此行**。
底稿 `agingRows` 原先无条件产出该行 → 国企附注多一行凭空结构行。

**修法**：不按 variant 硬分，改按语义——`within1Keys.length > 1`（1年以内确被细分为多段）
才产出。段数为 1 时小计恒等于该段本身，产出无意义。该规则对两版同时正确。

**守卫**：新增 `d2AgingWithin1Subtotal.spec.ts`（mock `useAgingConfig`）双向覆盖：
5 年段预设 → 无小计行；1年以内细分两段 → 有小计行且金额 = 各细分段之和，
且「小计」仍为全部账龄段之和（不重复计入）。

**实测**：底稿账龄表与附注 `（1）按账龄披露应收账款` 均为
`6 档 + 小计 + 减：坏账准备 + 合计`（9 行），与源模板一致。

## 遗留两项已收口 → 并入 `disclosure-columns-coverage-rollout`

用户 2026-07-29 决策：
- **O1 走方案 A**（同步层加标签映射，项目账龄配置继续只服务底稿内部）
  → 落为 rollout spec **R6 + 任务 13**
- **O2 先立 spec 并并进 rollout**（跨组件契约变更）
  → 落为 rollout spec **R7 + 任务 14**

本 spec 不再跟踪这两项实现，仅保留下方诊断记录作为依据来源。

### O1 账龄档位标签用哪套口径

附注同步后显示的是**项目账龄配置**的短标签，与源模板/附注模板字面不一致：

| 附注实际（项目配置） | 源模板 / 附注模板 |
|---|---|
| `1年以内` | `1年以内（含1年）` |
| `1-2年` | `1至2年` |
| `2-3年` | `2至3年` |

两种收敛方向（属披露口径判断，不由实现方定）：
- **A** 同步层加标签映射（配置标签 → 披露口径标签），项目账龄配置继续只服务底稿内部
- **B** 以项目配置为准，把附注模板 seed 的字面一并改成配置口径

### O2 组合分表改名/删除留孤儿表

实测：把组合「应收中央企业客户」改名为「应收政府客户」再同步，附注
`sub_table_data` 与 `_sub_table_columns` 同时残留两个 key → 附注永久多一个空 TAB。

根因：同步按 key 浅合并（为支持 H4 只推自己那张表而不清空 H2 的明细），
删除须显式上报 `_removed_table_keys`。平台机制齐全（`_drop_removed_tables`
且保证「本次推送的 key 绝不删」），但：
- 只有上市分支上报，国企分支未接；
- 上市侧用的是**静态**常量 `D2_LISTED_OBSOLETE_TABLE_KEYS`，而组合表名是**动态**的，静态列表覆盖不了。

建议方案（待确认后实施）：底稿持久化「上次成功同步的组合分表名清单」
（`D2-disc-{variant}-synced-portfolio-tables`），下次同步时以
`上次 − 本次` 作为 `_removed_table_keys` 上报；两版共用，同时替掉上市侧的静态常量。
需改动 `useD2DisclosureNote`（持久化 + 快照字段）、`d2NoteSectionMap`（diff 产出）、
`D2DisclosureNoteBody`（同步成功回调写入），属跨组件契约变更 → 另立 spec 或并入
`disclosure-columns-coverage-rollout`。
