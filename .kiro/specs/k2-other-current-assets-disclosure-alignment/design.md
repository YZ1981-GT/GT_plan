# 设计：K2 披露表 ↔ 附注对齐

## 概览

单一真源分三层：

```
源 xlsx（取数逻辑 + 红/蓝字方法论）
   └─ backend/wp_templates/K/K2 其他流动资产.xlsx
附注模版 JSON（列结构 + 行名 + 表名，交付物权威）
   └─ backend/data/note_template_{listed,soe}.json §五、13 / §八、14
校验预设（勾稽裁决）
   └─ backend/data/note_check_preset_formulas.json  F13-1 / F13-1a / F13-2
```

数据流：

```
K2-2 明细表审定数 ──┐
K2-1 审定表合计  ──┼─> K2TabDisclosure{Listed,Soe}.vue（录入 + 公式）
                    │        │
                    │        └─ buildK2SyncPayload() ──> POST /api/projects/{id}/disclosure-notes/sync-from-workpaper
                    │                                        │
                    └─ useDisclosureAutoSync（防抖 800ms）    └─> disclosure_notes.table_data
                                                                  ├─ sub_table_data     {表名: 行[]}
                                                                  ├─ _sub_table_columns {表名: ColumnDef[]}
                                                                  └─ text_content       ← _note_texts
```

## 组件与接口

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
export const K2_LEGACY_OBSOLETE_TABLES = [
  '[披露与合同取得成本有关的资产相关的信息，包括确定该资产金额所做的判断、该资产的摊销方法、按该资产主要类别披露的期末账面价值以及本期确认的摊销及减值损失金额等。例如：',
  '项  目',
]

export function buildK2ListedColumns(categories?: string[]): Record<string, ColumnDef[]>
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

```ts
export const K2_LISTED_MAIN_ROWS = [
  '进项税额', '多交或预缴的增值税额', '待抵扣进项税额', '待认证进项税额',
  '增值税留抵税额', '预缴所得税', '委托贷款', '预缴其他税费',
  '短期债权投资', '短期其他债权投资', '合同取得成本', '应收退货成本', '碳排放权资产',
]
export const K2_SOE_MAIN_ROWS = [
  '待抵扣进项税额', '预缴税金', '委托贷款', '短期债权投资',
  '短期其他债权投资', '合同取得成本', '应收退货成本', '碳排放权资产',
]
export const K2_CONTRACT_COST_ROWS = ['期初余额', '本年增加', '本年摊销', '本年计提减值损失', '期末余额']
export const K2_CARBON_ROWS = [ /* 11 行，逐字取自附注模版 */ ]
```

### 2. 底稿组件

两版共用一个纯函数引擎 `composables/useK2DisclosureEngine.ts`（无 Vue 依赖，便于单测）：

```ts
export function sumMainRows(rows: K2MainRow[]): { end: number; prior: number }
export function recalcContractCost(matrix: ContractCostMatrix): ContractCostMatrix  // 合计列 + 期末余额行
export function checkK2Consistency(snapshot): ConsistencyItem[]                     // 勾稽面板数据
```

`K2TabDisclosureListed.vue` 结构（自上而下）：

1. 方法论上下文块（琥珀色左边线）：源模板标题注 + 蓝字原文。
2. 区块①「其他流动资产」`el-card shadow="never"`：13 固定行 + 动态行 + 合计公式行；金额列用 `WpAmountInput`（**不用 `el-input-number :formatter`**，该 prop 在 EP 2.13.6 不存在）。
3. 区块②「合同取得成本」：启用开关 + 类别列增删（`ElMessageBox.prompt` 命名）+ 5 行；`本年摊销` / `本年计提减值损失` 录入为正数，公式行按减项计算。
4. 区块③「碳排放配额变动情况」：启用开关 + 11 固定行。
5. 勾稽校验 bar（紧凑单行 + 折叠明细）：①合计=各行之和；①合计期末 vs K2-1 审定数；②合计列=各类别之和；②期末余额=期初+增加−摊销−减值。
6. 文本区三段 + 每段 AI 按钮。
7. `details` 折叠编制提示。

`K2TabDisclosureSoe.vue`：同款但只有区块① + 一段文本 + 勾稽 2 项。

### 3. 附注模板修订脚本

`backend/scripts/fix/fix_note_k2_structure.py`，范式照 `fix_note_prepayment_structure.py`：

- `--dry-run`（默认打印 diff）/ `--apply` / `--check`（exit 1 表示未对齐，供 CI）
- 幂等：以 `_aligned_by == 'fix_note_k2_structure'` + 结构实测双判定
- 动作：
  1. §五、13 表②③重命名；表②补 `headers[0]='项目'`；表③删 `header_label` 行
  2. 4 张表补 `columns`（含 `flat`）+ `guidance`
  3. `_column_groups` 显式置 `[]`（单级，抑制推断）

## 数据模型

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

## 正确性性质

- **P1** `columns` 键集 ≡ `sub_table_data` 行对象键集（除 `label` / `is_total`）。
- **P2** 每张表恰一个 `is_label` 且居首。
- **P3** 每张表显式 `flat: true`（K2 全部单行表头）。
- **P4** 子表名与 `note_template` `tables[].name` 逐字一致。
- **P5** `columns` 标签列 label = 模板 `headers[0]`。
- **P6** 关闭区块 → 该表名进 `_removed_table_keys`，且不在 `sub_table_data`。
- **P7** 合计行 = 明细行之和（逐列，容差 0.01 元）。
- **P8** 合同取得成本期末余额行 = 期初 + 增加 − 摊销 − 减值（逐列）。

## 风险

| 风险 | 缓解 |
|---|---|
| 改模板 JSON 对既有项目不生效（`_tables` 是生成时快照） | 交付说明写明「新建项目 / 重新生成附注才可见」；既有项目经底稿「同步到附注」整表覆盖 |
| 表名变更导致附注残留旧空表 | `_removed_table_keys` 携历史表名 |
| 并发会话回退同一文件 | 幂等脚本 + 契约测试；共享文件改动用 `str_replace` |
