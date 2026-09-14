# Design Document

K2 披露表 ↔ 附注对齐

## Overview

单一真源分三层：

```
源 xlsx（取数逻辑 + 红/蓝字方法论）
   └─ backend/wp_templates/K/K2 其他流动资产.xlsx
附注模版 JSON（列结构 + 行名 + 表名，交付物权威）
   └─ backend/data/note_template_{listed,soe}.json §五、13 / §八、14
校验预设（勾稽裁决）
   └─ backend/data/note_check_preset_formulas.json  F13-1 / F13-1a / F13-2
```

三者冲突时：附注是交付物 → 列结构与行名随附注模版；勾稽关系随校验预设；源 xlsx 决定取数来源与方法论文字。

## Architecture

```
K2-2 明细表审定数 ──┐
K2-1 审定表合计  ──┼─> K2TabDisclosure{Listed,Soe}.vue（录入 + 公式 + 勾稽面板）
                    │        │
                    │        └─ buildK2SyncPayload() ──> POST /api/projects/{id}/disclosure-notes/sync-from-workpaper
                    │                                        │
                    └─ useDisclosureAutoSync（防抖 800ms）    └─> disclosure_notes.table_data
                                                                  ├─ sub_table_data     {表名: 行[]}
                                                                  ├─ _sub_table_columns {表名: ColumnDef[]}
                                                                  ├─ _last_sync_sheet   源 xlsx tab 名
                                                                  └─ text_content       ← _note_texts
```

模板侧独立一条链（只影响新建项目 / 重新生成附注的 seed 路径）：

```
fix_note_k2_structure.py --apply
   └─> note_template_{listed,soe}.json（表名 / headers / columns.flat / guidance）
         └─> disclosure_engine._carry_seed_column_meta + _carry_seed_table_guidance
```

## Components and Interfaces

### 1. `composables/k2NoteSectionMap.ts`（重写）

```ts
export const K2_NOTE_SECTION = { listed: '五、13', soe: '八、14' }

/** 源 xlsx 真实 tab 名（全角括号，勿"修正"为半角） */
export const K2_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国企）',
}

export const K2_LISTED_SUBTABLE = {
  main: '其他流动资产',
  contractCost: '合同取得成本',
  carbon: '碳排放配额变动情况',
}
export const K2_SOE_SUBTABLE = { main: '其他流动资产' }

/** 历史表名（md 重建产物），改版后须删除 */
export const K2_LEGACY_OBSOLETE_TABLES: readonly string[]

export function buildK2ListedColumns(categories?: readonly string[]): Record<string, ColumnDef[]>
export function buildK2SoeColumns(): Record<string, ColumnDef[]>
export function buildK2SyncPayload(variant, wpId, snapshot): K2SyncPayload
```

`buildK2ListedColumns` 入参可选（默认 `['佣金支出']`），零参调用返回 seed 形态 —— 满足 `disclosureColumnsCoverage` sweep 的空入参调用，且列头非空。

#### 列定义

| 表 | 列 | key | flat |
|---|---|---|---|
| 其他流动资产（上市） | 项目 / 期末余额 / 上年年末余额 | `label` / `end_amount` / `prior_amount` | ✔ |
| 其他流动资产（国企） | 项目 / 期末余额 / 期初余额 | `label` / `end_amount` / `prior_amount` | ✔ |
| 合同取得成本 | 项目 / {类别…} / 合计 | `label` / `cat_{i}` / `total` | ✔ |
| 碳排放配额变动情况 | 项目 / 本期发生额 / 上期发生额 | `label` / `current_amount` / `prior_amount` | ✔ |

国企与上市的 `prior_amount` 同键不同 label（附注模版一个是「上年年末余额」一个是「期初余额」），故 `buildK2SoeColumns` 独立声明。

#### 行常量

`K2_LISTED_MAIN_ROWS`（13）/ `K2_SOE_MAIN_ROWS`（8）/ `K2_CONTRACT_COST_ROWS`（5）/ `K2_CARBON_ROWS`（10）
逐字取自 `note_template_*.json`，含全角句点 `．` 与全角括号 `（1）`。

### 2. `composables/useK2DisclosureEngine.ts`（纯函数，无 Vue 依赖）

```ts
export function sumMainRows(rows): { end: number; prior: number }
export function recalcContractCost(cells, catCount): number[][]   // 期末余额行按公式派生，返回新矩阵
export function contractCostRowTotal(cells, rowIdx, catCount): number
export function checkK2Consistency(input): K2ConsistencyItem[]     // 勾稽面板数据
export function k2ConsistencySummary(items): { total; failed; level }
```

容差 `K2_TOLERANCE = 0.01` 元。审定数缺失时跳过该校验项（不制造假阳性）。

### 3. 底稿组件

`K2TabDisclosureListed.vue` 结构（自上而下）：

1. 方法论上下文块（琥珀色左边线）：源模板标题注 + 蓝字原文。
2. 勾稽校验 bar（紧凑单行 + 折叠明细表 + 规则 tooltip）+ 同步按钮。
3. 区块①「其他流动资产」`el-card shadow="never"`：13 固定行 + 动态行 + 合计公式行；金额列用 `WpAmountInput`（**不用 `el-input-number :formatter`**，该 prop 在 EP 2.13.6 不存在）。
4. 区块②「合同取得成本」：启用开关 + 类别列增删改名（`ElMessageBox.prompt` 命名）+ 5 行；`本年摊销` / `本年计提减值损失` 录入为正数，公式行按减项计算。
5. 区块③「碳排放配额变动情况」：启用开关 + 10 固定行。
6. 文本区三段 + 每段 AI 按钮。
7. `details` 折叠编制提示。

`K2TabDisclosureSoe.vue`：同款但只有区块① + 一段文本 + 勾稽 2 项。

### 4. 附注模板修订脚本

`backend/scripts/fix/fix_note_k2_structure.py`，范式照 `fix_note_prepayment_structure.py`：

- `--dry-run`（打印 diff 不写）/ 默认 apply / `--check`（exit 1 表示未对齐，供 CI）
- 幂等：`_aligned_by == 'k2-other-current-assets-disclosure-alignment'` + 结构实测双判定
- 动作：①表②③重命名（按别名 + 游标定位）②表② `headers[0]` 修正 ③表③删 `header_label` 行 ④4 张表补 `columns`（含 `flat`）+ `guidance` ⑤删 `_column_groups`（单级靠 `flat` 表态）
- 写入前跑 `validate_section`，校验不过则不写

## Data Models

`sub_table_data` 形态（`{key: list[dict]}` 业务键行，唯一规范形态）：

```json
{
  "其他流动资产": [
    {"label": "进项税额", "end_amount": 0, "prior_amount": 0},
    {"label": "合计", "end_amount": 0, "prior_amount": 0, "is_total": true}
  ],
  "合同取得成本": [
    {"label": "期初余额", "cat_1": 0, "total": 0},
    {"label": "期末余额", "cat_1": 0, "total": 0}
  ],
  "碳排放配额变动情况": [{"label": "1．本期期初碳排放配额", "current_amount": 0, "prior_amount": 0}],
  "_note_texts": [{"section": "k2-significant", "title": "…", "text": "…"}],
  "_removed_table_keys": ["项  目", "[披露与合同取得成本…"]
}
```

底稿持久化（`checklist_responses`，JSON 串）：
`K2-disc-listed-main` / `-contract-cost` / `-carbon` / `-texts`；`K2-disc-soe-main` / `-text`。

## Correctness Properties

### Property 1: columns 键集 ≡ sub_table_data 行键集

每张表 `columns` 的 `key` 集合与该表行对象的业务键集合相等（`is_total` 为元数据键不计）。违反 → 附注侧拿英文字段键当列头或数据列落空。

**Validates: Requirements 6.1, 6.2**

### Property 2: 标签列唯一且居首

每张表恰有一个 `is_label: true` 的列，且位于索引 0。

**Validates: Requirements 1.1, 1.2**

### Property 3: 每张表显式 flat

K2 四张表源模板皆单行表头 → `columns` 至少一列带 `flat: true`，且不得同时出现 `group`。违反 → 后端 `_infer_groups_from_headers` 塞凭空父表头。

**Validates: Requirements 4.4, 5.2**

### Property 4: 子表名与模板逐字一致

`K2_LISTED_SUBTABLE` / `K2_SOE_SUBTABLE` 每个值都能在对应 `note_template` 章节的 `tables[].name` 中找到。违反 → 孤儿子表（附注 TAB 永空 + 底稿数据丢失）。

**Validates: Requirements 4.1, 4.2, 6.1**

### Property 5: 标签列头对齐模板 headers[0]

`columns` 中标签列的 `label` 等于该表模板 `headers[0]`。违反 → 同步后附注首列名漂移。

**Validates: Requirements 4.3, 6.1**

### Property 6: 关闭区块即清理

条件性表关闭时，其表名出现在 `_removed_table_keys`，且不出现在 `sub_table_data` 与 `columns`；开启时相反。

**Validates: Requirements 2.4, 5.3**

### Property 7: 合计行等于明细行之和

主表末行 `is_total` 且每个数值列 = 各明细行该列之和（容差 0.01 元）。

**Validates: Requirements 1.5**

### Property 8: 合同取得成本期末余额为派生值

对每个类别列，`期末余额 = 期初余额 + 本年增加 − 本年摊销 − 本年计提减值损失`；`total` 列 = 各类别列之和。

**Validates: Requirements 2.2**

## Error Handling

- 自动同步失败静默（不打断录入），手动按钮亦不弹错 —— 与平台既有披露 Tab 一致；落库真相以 `_last_sync_at` 为准。
- `WpAmountInput` 非法输入回退上一次有效值且不 emit（不把 `NaN` 写进底稿）。
- 类别列删除时同步收缩 `cells` 各行，避免残留列值被当成下一类别。
- 模板脚本写入前自校验；校验不过只打印不落盘，避免半成品结构进仓库。

## Testing Strategy

| 层 | 文件 | 覆盖 |
|---|---|---|
| 契约（前端） | `composables/__tests__/k2NoteSubtableContract.spec.ts` | 共享 helper P1~P5 + 模板 3 表恒等 + 历史表名清除 + 固定行逐字 + 载荷键集 / 合计 / 开关 / `_note_texts` |
| 单元（前端） | `composables/__tests__/useK2DisclosureEngine.spec.ts` | 求和 / 公式 / 容差 / 缺失审定数跳过 / summary 级别优先 |
| 跨循环守卫 | `__tests__/disclosureColumnsCoverage.spec.ts` | `P1_ROUTE` 登记 + sweep 性质 |
| 结构（后端） | `tests/services/test_note_k2_structure.py` | 表集合 / 列键 / flat / guidance / 无假行 / `_aligned_by` + 反向自检 |
| CI | `governance-checks.yml::note-k2-structure` | `--check` + pytest |
| 实测 | chrome-devtools 驱动 + postgres 只读 | 录入 → 自动同步 → 落库 → 附注渲染 |

## 风险

| 风险 | 缓解 |
|---|---|
| 改模板 JSON 对既有项目不生效（`_tables` 是生成时快照） | 交付说明写明「新建项目 / 重新生成附注才可见」；既有项目经底稿「同步到附注」整表覆盖 |
| 表名变更导致附注残留旧空表 | `_removed_table_keys` 携历史表名 |
| 并发会话回退同一文件 | 幂等脚本 + 契约测试；共享文件改动用 `str_replace` |
