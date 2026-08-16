# Design — 可编辑金额控件迁移与列类型判据

## Overview

把 4260 处 `el-input-number` 里**属于金额列**的那部分迁移到 `WpAmountInput`，
并在迁移**之前**建立可区分的列类型判据。

核心设计判断：**判据必须先行，且必须比旧探针强**。理由是本次实测暴露的两件事：

1. 旧探针以「有没有写 `:formatter`」为必要条件 ⇒ 漏掉「连 `formatter` 都没有的
   `el-input-number` 金额列」（I1-10/I1-11 就是，Task 18 在此报 0 处合规）
2. 现有反向边界断言（「非金额列没被误换成 `WpAmountInput`」）在未迁移代码上**恒真**
   ⇒ 没有区分能力，迁移过程本身会引入「年限显示 `1,000.00`」这类新缺陷

## Architecture

### 判定链

```
el-table-column 块
   │
   ├─ 抽 label（含多级表头的父组名拼接）
   │        │
   │        ├─→ 命中非金额模式（比率/年限/月数/…）→ NON_AMOUNT
   │        ├─→ 命中金额模式（金额/余额/原值/成本/…）→ AMOUNT
   │        └─→ 两者都命中 → AMBIGUOUS（人工裁决，不静默二选一）
   │
   └─ 抽控件类型
            ├─ <WpAmountInput>        → 已迁移
            ├─ <el-input-number>      → 未迁移
            └─ 纯文本 / fmtAmount     → 只读展示（本 spec 不动，归 displayPrefs 口径）

判定矩阵：
              │ AMOUNT              │ NON_AMOUNT          │ AMBIGUOUS
──────────────┼─────────────────────┼─────────────────────┼──────────────
WpAmountInput │ ok                  │ ❌ 反向边界违规      │ 人工裁决
el-input-numb │ ❌ confirmed_viol.  │ ok                  │ 人工裁决
```

⇒ 一个探针同时覆盖正向（金额列未迁移）与反向（非金额列误迁移）两个方向，
且反向方向在迁移后**扫描面非空**（因为会有真实的已迁移文件），解决 R3.1 的恒真问题。

### 为何不能用固定字符窗口

I 循环 Task 18 首版探针用「label 后 400 字符窗口内是否有 `WpAmountInput`」判定，
报出 22 处违规，逐标签复核后发现**全是误报** —— `style="width:100%"` 的 `%`
落进了窗口被当成百分比列。

⇒ 本 spec 一律按 **`<el-table-column>` … `</el-table-column>` 块配对扫描**
（自闭合标签单独处理），不用字符窗口。这与平台铁律「截函数体禁固定字符窗口、
一律花括号/圆括号配对」同源。

### 单一真源位置

```
audit-platform/frontend/src/components/workpaper/shared/amountColumnSemantics.ts
   ├─ AMOUNT_LABEL_PATTERNS      金额语义模式
   ├─ NON_AMOUNT_LABEL_PATTERNS  非金额语义模式（R1.2 的 19 类）
   ├─ EXPLICIT_OVERRIDES         按 `文件:列label` 显式裁决（歧义与例外）
   └─ classifyColumnLabel(label) → 'amount' | 'non_amount' | 'ambiguous'
```

前端运行时**不消费**这个模块（它只服务判据与迁移脚本），但放在 `src` 下便于
vitest 直接 import，避免前后端两份关键词副本。

`EXPLICIT_OVERRIDES` 的每条必须带 `evidence` 字段（源模板依据或实测证据，R1.4）。

## Components and Interfaces

### 新建产物

| 产物 | 作用 |
|---|---|
| `.../shared/amountColumnSemantics.ts` | 列类型判定单一真源（纯函数） |
| `.../shared/__tests__/amountColumnSemantics.spec.ts` | 真源自身的守卫（含歧义清单非空自检） |
| `backend/scripts/check/audit_amount_input_columns.py` | 全库探针，`--check` / `--json` |
| `backend/data/amount_input_migration_status.json` | 探针产物（三类清单 + 批次归属） |
| `.../__tests__/amountInputColumnTyping.spec.ts` | 正反双向断言（迁移后扫描面非空） |
| `backend/scripts/fix/fix_amount_input_batch.py` | 分批迁移脚本（幂等 + `--check` + 反向自检） |

### 受影响存量（实测分布）

`:formatter` 空操作 80 处集中在 13 个文件：

| 文件 | 处数 |
|---|---|
| `k1/core/K1TabDisclosureSoe.vue` | 21 |
| `k1/core/K1TabDisclosureListed.vue` | 15 |
| `e1/E1TabBankDetail.vue` | 11 |
| `e1/E1TabAnalysis.vue` | 9 |
| `e1/E1TabCashDetail.vue` | 5 |
| `e1/E1TabDigitalCurrency.vue` | 5 |
| `e1/E1TabInterestAnalysis.vue` | 4 |
| `e1/E1TabReconciliation.vue` | 3 |
| `e1/E1TabAdjustment.vue` | 2 |
| `k1/core/K1StageEclTable.vue` | 2 |
| `e1/E1TabAccruedInterest.vue` | 1 |
| `e1/E1TabCertificateCount.vue` | 1 |
| 其余 1 文件 | 1 |

`el-input-number` 密度最高的文件（前 10，含只读/非金额，需探针细分）：
`h2/impairment/H2TabRecoverable.vue`(21) · `g5-…/G5TabDisclosureListed.vue`(20) ·
`j1/analysis/J1TabIndustryCompare.vue`(20) · `f2/analysis/F2TabOverallAnalysis.vue`(19) ·
`f2/core/F2TabDisclosureListed.vue`(19) · `g5-…/G5TabDisclosureSOE.vue`(19) ·
`g5-…/G5TabLeaseAmortization.vue`(19) · `h3/impairment/H3TabRecoverable.vue`(19) ·
`i2/impairment/I2TabRecoverable.vue`(19) · `d4/analysis/D4TabProductMargin.vue`(18)

⚠️ `J1TabIndustryCompare`（行业对比）与 `D4TabProductMargin`（产品毛利）大概率
**多为比率列**，是反向边界的天然测试样本，不是迁移目标。

### 迁移的等价性保留清单

| 原 prop | 迁移后处理 |
|---|---|
| `v-model` | 逐字保留绑定路径 |
| `@change` | 保留（`WpAmountInput` 须支持同名事件） |
| `:controls="false"` | `WpAmountInput` 无步进按钮，语义自然满足（R5.2） |
| `:min="0"` | 保留；**若原无 `:min` 则不得新增**（备抵/调整列需负数，R5.3） |
| `:precision="2"` | 金额列保留 2；**非金额列不迁移故不涉及** |
| `:disabled` / `v-if="!isReadonly"` | 逐字保留 |

## Data Models

### 探针产物 schema

`backend/data/amount_input_migration_status.json`：

```jsonc
{
  "scanned_files": 798,
  "totals": {
    "el_input_number": 4260,
    "el_input_number_with_formatter": 80,
    "wp_amount_input": 682
  },
  "confirmed_violation": [
    {
      "file": "src/components/workpaper/i1/amortization/I1TabAmortizationNoImpair.vue",
      "line": 132,
      "label": "原值",
      "control": "el-input-number",
      "has_formatter": false,
      "batch": 2
    }
  ],
  "reverse_violation": [],
  "ambiguous": [
    { "file": "…", "line": 0, "label": "…", "hit_amount": "余额", "hit_non_amount": "比率" }
  ],
  "ok_count": 0
}
```

`has_formatter: false` 字段的存在本身就是**本 spec 立项依据的固化**
—— 它证明旧探针（要求 `:formatter` 存在）为何漏掉这些点。

### 批次划分

| 批次 | 范围 | 确定性 |
|---|---|---|
| 1 | 80 处 `:formatter` 空操作（13 文件） | 最高（写了 formatter = 作者本意就是要千分符） |
| 2 | I 循环摊销测算表 I1-10 / I1-11（本次浏览器实证） | 高（已实测同行两种格式） |
| 3+ | `confirmed_violation` 剩余项，按循环分批 | 需逐项复核 label |

## Correctness Properties

### Property 1: 非金额语义关键词全覆盖

`classifyColumnLabel` 对 R1.2 列举的 19 类非金额语义关键词全部返回 `'non_amount'`。

**Validates: Requirements 1.2**

### Property 2: 歧义 label 不静默二选一

同时命中金额与非金额模式的 label 返回 `'ambiguous'`，不返回二者之一。

**Validates: Requirements 1.3**

### Property 3: override 必带 evidence

`EXPLICIT_OVERRIDES` 每条含非空 `evidence` 字段。

**Validates: Requirements 1.4**

### Property 4: 判据不依赖 formatter 存在

探针判据不含「`:formatter` 存在」这一必要条件。
判据：探针源码中 `confirmed_violation` 的产生路径不依赖 `has_formatter`
（`has_formatter` 只作为输出字段，不参与筛选条件）。

**Validates: Requirements 2.1**

### Property 5: 摊销测算表金额列必报违规

探针在 `I1TabAmortizationNoImpair.vue` 与 `I1TabAmortizationWithImpair.vue` 上
报出金额列违规，且违规列 label 含「原值」与「残值」。

**Validates: Requirements 2.2**

### Property 6: 使用期限列不报违规

探针在上述两文件的「使用期限(年)」列上不报违规。

**Validates: Requirements 2.3**

### Property 7: 输出严格三分无遗漏桶

探针输出严格三分（`confirmed_violation` / `ambiguous` / `ok`），三者之和等于
扫到的「表列 × 可编辑控件」总数，无遗漏桶。

**Validates: Requirements 2.4**

### Property 8: 探针反向自检三条

探针反向自检三条成立：已迁移金额列不报违规 / `el-input-number` 年限列不报违规 /
`el-input-number` 金额列必报违规。

**Validates: Requirements 2.5**

### Property 9: 块配对扫描禁字符窗口

探针按 `<el-table-column>` 块配对扫描，源码中不得出现固定字符窗口式切片
（如 `[i:i+400]` / `slice(idx, idx + 400)`）。

**Validates: Requirements 2.6**

### Property 10: 反向边界具备区分能力

反向边界断言在「把已迁移文件里的非金额列改成 `WpAmountInput`」时打红（变异检验证明），
且断言的扫描面非空（至少一个已迁移文件参与）。

**Validates: Requirements 3.1, 3.2**

### Property 11: 反向失败消息含语义类别

反向边界断言失败消息含文件名、列 label 与命中的非金额语义类别。

**Validates: Requirements 3.3**

### Property 12: 已完成批次零违规

每个已完成批次在 `amount_input_migration_status.json` 里的 `confirmed_violation`
条目数为 0（按 `batch` 字段筛选）。

**Validates: Requirements 4.1, 4.2**

### Property 13: 迁移 prop 等价性

迁移前后同一列的 `v-model` 绑定路径、`@change` 处理器名、`:min`/`:max`/`:disabled`
表达式逐字相同（迁移脚本的 `--check` 做前后比对）。

**Validates: Requirements 5.1, 5.3**

### Property 14: 迁移后无步进按钮

迁移后的列不出现步进按钮：源码不得残留 `:controls`（`WpAmountInput` 无此 prop）。

**Validates: Requirements 5.2**

### Property 15: 非法输入不写 NaN

`WpAmountInput` 对非法输入不写 `NaN`（既有行为，以单测锁死防回归）。

**Validates: Requirements 5.4**

### Property 16: 持久化值仍为 number

迁移后该列持久化值类型仍为 number；以 `WpAmountInput` 的 `update:modelValue`
载荷类型断言锁死（不得为带逗号字符串）。

**Validates: Requirements 5.5**

### Property 17: precision 不被机械改动

`:precision` 未被机械改动：迁移脚本不得修改任何 `:precision` 值，
只允许在人工裁决后单独提交。

**Validates: Requirements 4.4**

### Property 18: 全批次完成后 check 归零

探针 `--check` 在全部批次完成后返回 0（`confirmed_violation` 为空）。

**Validates: Requirements 6.5**

### Property 19: 只读展示金额不在判定范围

只读展示金额不进入本 spec 的违规判定 —— 探针只对**可编辑控件**
（`el-input-number` / `WpAmountInput` / `el-input`）分类，纯文本列与
`fmtAmount()` 调用点一律归 `ok`，不报违规。
真源模块 doc 里显式声明该边界（只读展示归 `displayPrefs.fmtAmount()` 口径，
I 循环 Task 18 已收口 16 个 SFC 的 7 种本地 `fmtAmount`）。

**Validates: Requirements 1.5**

## Error Handling

- **label 抽取失败**（多级表头 / 动态 label / `:label` 绑定表达式）：记入 `ambiguous`
  并标注 `reason: 'dynamic_label'`，**不静默丢弃**；若此类占比 >10% 视为探针能力不足
- **迁移脚本遇到已迁移的列**：跳过并计数（幂等），不重复包裹
- **迁移脚本遇到 `git status` 为 `M` 的目标文件**：**跳过并登记**，不覆盖并发会话在途改动
- **探针与人工复核冲突**：以人工为准并修探针（R2.6）；冲突记录须留档，
  作为「窗口式匹配不可靠」的持续证据
- **fail-open 禁令**：探针不得用裸 `except` 吞解析异常后当 `ok`；
  解析失败必须记 ERROR 并影响退出码

## Testing Strategy

### 分层

1. **真源纯函数单测**：`classifyColumnLabel` 的 19 类关键词 + 歧义 + override（Property 1/2/3）
2. **探针能力定向验收**：I1-10/I1-11 作为正向锚点、`使用期限(年)` 作为反向锚点
   （Property 5/6）—— 这两条是本 spec 相对 Task 18 的能力增量证明
3. **探针反向自检**：三条替身（Property 8）
4. **迁移等价性**：脚本 `--check` 做前后 prop 逐字比对（Property 13/14/17）
5. **浏览器实测**：输 `1234567.5` → 失焦 `1,234,567.50`，且**同行只读派生列格式一致**
   （本次实测暴露的正是同行 `50000.00` 与 `9,871.40` 并存）
6. **变异检验**：反向边界断言必须在「年限列误换」时打红（Property 10）

### 不做的事

- **不跑前端全量**：1999 files / 4-worker 并发会产出大量资源竞争型 flaky
  （实测报 73 files failed，单独复跑只剩 1 个真红）。一律按引用关系反查辐射面 + 串行
- **不改 `:precision`**：业务粒度需确认，本 spec 只登记
- **不动只读展示金额**：那部分归 `displayPrefs.fmtAmount()` 口径，I 循环 Task 18 已收口
  16 个 SFC 的 7 种本地 `fmtAmount`
