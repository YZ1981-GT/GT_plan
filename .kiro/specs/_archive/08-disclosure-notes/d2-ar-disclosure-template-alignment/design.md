# Design: d2-ar-disclosure-template-alignment

## Overview

三层同构：**底稿录入模型**（`useD2DisclosureNote`）→ **同步映射**（`d2NoteSectionMap`）
→ **附注呈现**（sub_table_data 投影 / 模板初始化）。源模板列结构必须在三层字面一致，
差异只允许出现在「续表键名唯一化」等既有 4 处渲染必需偏差（见 `d2NoteSectionMap.ts` 文件头）。

现状根因：底稿层 UI 已按源模板渲染 6 列宽表（上市版复用 `soeClassEndRows`），
但同步层把它压扁成 `label + end_amount` 两列，附注层模板又是 md 抽取时丢了多级表头的
3 列表。三处口径各不相同 → 审计师在底稿看到的和附注/Word 导出看到的不是同一张表。

## Architecture

```
D2DisclosureNoteBody.vue ──uses──> useD2DisclosureNote.ts ──buildSnapshot()──┐
        (渲染/录入)                    (取数 + 派生 + 持久化)                │
                                                                             v
                                                        d2NoteSectionMap.buildD2SyncPayload()
                                                                             │
                                     POST /workpapers/{id}/disclosure-sync   v
                                                        wp_disclosure_sync_service.sync_from_workpaper()
                                                                             │
                                         disclosure_notes.table_data.sub_table_data + _sub_table_columns
                                                                             v
                                              note_sub_table_projector.project_sub_tables() → _tables[]
                                                                     (附注模块渲染 / Word 导出)

note_template_listed.json 五、5  ──> disclosure_engine（仅模板初始化路径，未同步过的项目）
```

## Components and Interfaces

### C1 `useD2DisclosureNote.ts`（底稿数据模型）

| 变更 | 说明 |
|------|------|
| `soeClassEndRows` → `classWideEndRows`、`soeClassPriorRows` → `classWidePriorRows` | 上市版同样使用，`soe` 前缀名不实；语义重命名（含 override key `soeClass:*` → `classWide:*` 并保留旧键读取兼容） |
| `D2PortfolioRow` 增 `priorProvision: number` | 组合分表上年坏账准备（源 F 列）；派生损失率不落库 |
| `classWide*Rows` 组合子行 `provision` | 由 `provision: 0` 改为按组合分表坏账准备合计（期末取 `provision`、上年取 `priorProvision`），修掉「组合分表未单独存坏账准备」缺口（R1.3） |
| `ratio` 分母 | 期末表用期末合计、上年表用上年合计（R1.4） |
| `D2DerecognizedRow` 增 `transferMethod: string` | 源模板「转移方式」列（R4.1） |
| `MOVEMENT_LABELS[0].label` | `期初余额` → `上年年末余额`（R5.1） |
| `movementValues.priorBalance` 自动取数 | 改为「账龄表『减：坏账准备』上年年末列」，D2-3 期初审定合计作次级回退（R5.2） |
| `sectionNotes` 新键 | `derecognition`（既有 `continuedInvolvement` 保持） |
| 一致性检查 | 新增：变动表期末余额 ↔ 分类披露期末坏账准备合计（R5.3） |

**向后兼容**：`rehydrate()` 读 override 时先读新键 `classWide:*`，未命中回退旧键
`soeClass:*`（一次性读迁移，写只写新键）。这不是 fallback 死代码，而是持久化数据的
版本兼容读取，随下一次保存自然收敛。

### C2 `d2NoteSectionMap.ts`（同步映射，表名/列头唯一真源）

新增/改写列头常量：

```ts
const CLASS_COLUMNS_LISTED_END: ColumnDef[] = [
  { key: 'label',          label: '类 别',              is_label: true },
  { key: 'book_amount',    label: '金额',               format: AMT, group: '账面余额' },
  { key: 'ratio',          label: '比例(%)',            format: PCT, group: '账面余额' },
  { key: 'provision',      label: '金额',               format: AMT, group: '坏账准备' },
  { key: 'loss_rate',      label: '预期信用损失率(%)',  format: PCT, group: '坏账准备' },
  { key: 'carrying_value', label: '账面价值',           format: AMT },
]
// PRIOR 同构（表名已含「续：上年年末余额」标识期间）
const INDIVIDUAL_COLUMNS_LISTED_END = [名 称 | 账面余额 | 坏账准备 | 预期信用损失率（%） | 计提依据]
const PORTFOLIO_COLUMNS_LISTED = [
  账龄 | (期末余额){应收账款, 坏账准备, 预期信用损失率(%)}
       | (上年年末余额){应收账款, 坏账准备, 预期信用损失率(%)}
]
const DERECOGNIZED_COLUMNS_LISTED = [项 目 | 转移方式 | 终止确认金额 | 与终止确认相关的利得或损失]
const CONTINUED_INVOLVEMENT_COLUMNS = [项 目 | 资产转移方式 | 继续涉入形成的资产金额 | 继续涉入形成的负债金额]
```

`D2_TABLE_NAMES.listed` 新增两键：
`derecognized: '因金融资产转移而终止确认的应收账款情况'`、
`continuedInvolvement: '转移应收账款且继续涉入形成的资产、负债'`。

`D2_NOTE_TEXT_SECTIONS` 追加 `derecognition`（终止确认说明）、`continuedInvolvement`（继续涉入说明）。

`D2_LISTED_OBSOLETE_TABLE_KEYS`：旧实现遗留的表名（`按坏账计提方法分类披露（上年年末金额）`、
`按单项计提坏账准备的应收账款（上年年末金额）`），随载荷以 `_removed_table_keys` 上报清理。

`D2DisclosureSnapshot` 相应扩字段（`classWideEndRows`/`classWidePriorRows` 必填、
`portfolios[].rows[].provision/priorProvision`、`derecognizedRows[].transferMethod`、
`continuedInvolvementRows`）。

### C3 `D2DisclosureNoteBody.vue`（底稿渲染）

- ④ 组合分表：上市版改为两级表头 6 值列（应收账款/坏账准备/损失率 × 双期），
  损失率为 `auto-cell` 只读派生。
- ⑥ 终止确认：新增「转移方式」列（仅上市版）；上市版标签列 label 改 `项 目`；
  新增说明文本框（key `derecognition`），占位含 A/B/C 范式摘要。
- ⑤ 变动表首行行名随 `MOVEMENT_LABELS` 自动变为「上年年末余额」。
- ⑦ 前五名：新增「汇总披露格式」范式文本块 + 二选一提示。
- 法规上下文：受 15 号文约束的 5 处新增 `.methodology-context`（琥珀色左边线 + 浅黄背景）
  内嵌源模板法规原文（复用现有 `.methodology-*` 样式约定）。

### C4 `note_template_listed.json` 五、5（附注模板）

md → JSON 抽取器（`scripts/fix/rebuild_note_from_md.py`）会丢多级表头，直接改 JSON
会被重建覆盖。故采用**幂等修订脚本** `backend/scripts/fix/fix_note_ar_listed_structure.py`：

- 以源模板结构为准，重写 五、5 的 `tables`（14 → 15 张，含双期拆表、两级表头
  `columns` + `_column_groups`、终止确认表、前五名表名、账龄 10 行、变动首行）；
- 追加缺失 `text_sections`（终止确认 A/B/C、继续涉入说明）；
- 幂等：以表名集合与 `_aligned_by` 标记判断，重复执行不产生重复表；
- 重建模板后重跑该脚本即可恢复（写入 README 提示 + 契约测试兜底）。

### C5 后端 `wp_disclosure_sync_service.sync_from_workpaper`

新增可选参数 `removed_table_keys: list[str] | None`：
在浅合并之后，从 `merged_sub` / `merged_cols` 删除这些键，**但跳过本次推送的键**（R8.2）。
路由 schema `wp_disclosure_sync.py` 增 `_removed_table_keys` 字段（sub_table_data 的
`_` 前缀元数据键与显式 body 字段二者取并集，前端走元数据键即可，无需改路由契约）。

**选择**：走 `sub_table_data['_removed_table_keys']` 元数据键（`_extract_note_texts`
同款剥离方式），零路由契约变更，且天然被 `normalize_sub_table_data` 的 `_` 前缀分支保留。

## Data Models

同步后附注 `sub_table_data` 上市版键集合（15 张固定 + N 张组合分表）：

```
按账龄披露
按坏账计提方法分类披露 / 按坏账计提方法分类披露（续：上年年末余额）
按单项计提坏账准备的应收账款 / 按单项计提坏账准备的应收账款（续：上年年末余额）
组合计提项目：{组合名} × N
本期计提、收回或转回的坏账准备情况
转回或收回金额重要的坏账准备
本期实际核销的应收账款情况
重要的应收账款核销情况（逐项披露）
按欠款方归集的应收账款和合同资产期末余额前五名单位情况
因金融资产转移而终止确认的应收账款情况
转移应收账款且继续涉入形成的资产、负债
_note_texts / _removed_table_keys（元数据）
```

## Correctness Properties

### Property 1: 列头字面一致

`d2NoteSectionMap` 各列头 label 与源模板 sheet 对应表头行字面一致（去 `<br/>` 后比较）。

**Validates: Requirements 1.1, 2.1, 3.1**

### Property 2: 双期同构

期末表与（续：上年年末余额）表的列 `key` 序列长度相同、label 逐字相同。

**Validates: Requirements 1.1, 2.1**

### Property 3: 派生列可复算

对任意行：`carrying_value == book_amount - provision`；
`book_amount != 0` 时 `loss_rate == provision / book_amount`；
`ratio == book_amount / 本表合计 book_amount`（合计为 0 时取 0）。

**Validates: Requirements 1.2, 1.4, 3.2**

### Property 4: 合计口径

分类披露表合计 == 「按单项计提」行 + 「按组合计提」行（非全部明细行之和）。

**Validates: Requirements 1.1, 1.3**

### Property 5: 变动表滚动

`期末余额 == 上年年末余额 + 本期计提 − 本期收回或转回 − 本期核销 − 本期转销 − 其他`。

**Validates: Requirements 5.1, 5.3**

### Property 6: 表集合完整

上市同步载荷固定表名集合 ⊇ 源模板 9 个披露块所需表名集合。

**Validates: Requirements 4.2, 6.1**

### Property 7: 删除不误伤

仅删除 `_removed_table_keys` 中不属于本次推送键的键；交集元素一律保留。

**Validates: Requirements 8.1, 8.2, 8.3**

### Property 8: 模板幂等

修订脚本连续执行两次，五、5 的 `tables` / `text_sections` 完全相等。

**Validates: Requirements 7.1, 7.7**

## Error Handling

- 组合分表无坏账准备录入 → 损失率显示 `0.00`，不抛错、不写 NaN。
- `_removed_table_keys` 含不存在的键 → 静默跳过（幂等）。
- 分类表合计账面余额为 0 → 比例列取 0（对齐源模板 `IFERROR(...,0)`）。

## Testing Strategy

| 层 | 测试 | 位置 |
|----|------|------|
| 同步映射 | 列头/表名/双期同构/删除键（P1/P2/P6/P7） | `__tests__/d2NoteSectionMap.spec.ts`、`d2DisclosureNote.spec.ts` |
| 底稿派生 | 派生列可复算 + 合计口径 + 变动滚动（P3/P4/P5） | `__tests__/useD2DisclosureNote.spec.ts` |
| 附注模板 | 五、5 结构契约 + 脚本幂等（P8 + R7） | `backend/tests/services/test_note_ar_listed_structure.py` |
| 后端删除键 | `_removed_table_keys` 行为（R8） | `backend/tests/test_wp_disclosure_sync.py` |
| 端到端 | 底稿录入 → 同步 → 附注渲染 6 列 | Playwright 实测（人工验收） |
