# Design Document: I6 研发费用底稿专属HTML精美组件

## Overview

I6研发费用底稿专属组件`i6-research-development-expense`。I循环唯一损益类底稿（1个xlsx/11有效sheet/~120+公式）。科目6602研发费用（**损益类/贷方科目**，取发生额非余额！）。

核心架构：
- componentType `i6-research-development-expense`，主入口 GtI6ResearchDevelopmentExpense.vue
- **损益类科目！**取发生额非余额（与H10同款处理）
- **I6↔I2双向联动**：费用化+资本化=研发总额（VR-I6-01）
- **月度12列横向宽表**（类D4-2月度矩阵）
- **截止测试双向**
- composable分层：useI6FormData + useI6FormulaEngine(损益类！) + useI6CrossSheet + useI6DualMode + useI6ImportExport
- EventBus联动：TB回写(6602发生额) + I2双向 + 附注

## Architecture

### sheetName分发模式

```
sheetName → regex提取编码 → v-if匹配 → 子组件渲染
                                     ↘ 未匹配 → OnlyOffice fallback
```

### 损益类取数逻辑（与H10同款）

```
资产类(I1~I5): TB取期末余额 → audited_amount = 期末余额
损益类(I6):    TB取发生额   → audited_amount = 借方发生 - 贷方发生 (6602借方=费用)
               来源: tb_ledger 发生额汇总，而非 tb_balance 期末余额
```

### I6↔I2双向联动架构

```
┌──────────────┐  EventBus   ┌──────────────┐
│  I6 研发费用  │◄────────────►│  I2 开发支出  │
│  (费用化)    │              │  (资本化)    │
└──────┬───────┘              └──────┬───────┘
       │                             │
       ▼                             ▼
  research:expense-updated    development:capitalized-updated
       │                             │
       └──────────┬──────────────────┘
                  ▼
         VR-I6-01: 费用化 + 资本化 = 研发总额
```

### 文件结构

```
audit-platform/frontend/src/components/workpaper/
├── GtI6ResearchDevelopmentExpense.vue          # 主入口 sheetName v-if分发
├── i6/
│   ├── core/
│   │   ├── I6TabIndex.vue                     # 底稿目录
│   │   ├── I6TabAdjudication.vue              # I6-1 审定表（73公式！损益类）
│   │   ├── I6TabDetail.vue                    # I6-2 明细表（月度12列横向65列）
│   │   ├── I6TabAdjustment.vue                # I6-3 调整分录
│   │   ├── I6TabTargetedCheck.vue             # I6-4 针对性检查
│   │   ├── I6TabDisclosureListed.vue          # 附注上市
│   │   └── I6TabDisclosureSoe.vue             # 附注国企
│   └── cutoff/
│       ├── I6TabCutoffForward.vue             # I6-5 截止(账→单据)
│       └── I6TabCutoffBackward.vue            # I6-6 截止(单据→账)

├── composables/
│   ├── useI6FormData.ts                       # selfLoad + writebackTB(**发生额**，6602)
│   ├── useI6FormulaEngine.ts                  # 纯函数公式引擎（损益类！）
│   ├── useI6CrossSheet.ts                     # 跨sheet + I2双向联动
│   ├── useI6Adjudication.ts
│   ├── useI6Detail.ts                         # 月度12列矩阵
│   ├── useI6Cutoff.ts                         # 截止测试双向
│   ├── useI6Disclosure.ts
│   ├── useI6ImportExport.ts
│   └── useI6DualMode.ts

backend/app/routers/wp_render_strategies/
├── _i6_research_development_expense.py        # render策略+RENDERER_DISPATCH
├── _i6_import_export.py                       # 导入导出3端点
└── _i6_ai_generate.py                         # AI生成
```

## Composable接口设计

```typescript
// useI6FormulaEngine.ts — 纯函数（损益类！与H10同款）
export function calcAuditedAmount(unadj: number, aje: number, rje: number): number
export function calcIncomeStatementNet(debit: number, credit: number): number
// 损益类(6602借方科目): 净发生额 = 借方发生 - 贷方发生
export function calcSubtotal(arr: number[]): number
export function calcMonthlyTotal(monthlyAmounts: number[]): number  // SUM(1月~12月)
export function calcChangeRate(current: number, prior: number): number | null
export function calcResearchTotal(expenseI6: number, capitalizedI2: number): number
export function validateVRI601(expenseI6: number, capitalizedI2: number, expectedTotal: number): {
  isValid: boolean
  difference: number
}

// useI6CrossSheet.ts — I2双向联动
export function useI6CrossSheet(allResponses: Ref<Map<string, any>>): {
  detailMonthlyTotals: ComputedRef<number[]>  // 12个月合计
  i2LinkageStatus: ComputedRef<{capitalized: number, total: number, isBalanced: boolean}>
  cutoffSamples: ComputedRef<Array<{date: string, amount: number, isCrossover: boolean}>>
}
```

## 跨Sheet数据流图

```mermaid
graph TD
    subgraph I6核心
        I6_2[I6-2 明细表月度12列] -->|月合计| I6_1[I6-1 审定表]
        I6_3[I6-3 调整分录] -->|AJE/RJE| I6_1
        I6_1 -->|审定数回写发生额| TB[(trial_balance 6602)]
    end

    subgraph I6↔I2双向联动
        I6_1 -->|费用化金额| VR[VR-I6-01校验]
        I2[I2 开发支出] -->|资本化金额| VR
        VR -->|校验结果| I6_1
    end

    subgraph 截止组
        I6_5[I6-5 截止账→单] --> I6_1
        I6_6[I6-6 截止单→账] --> I6_1
    end

    subgraph 附注
        I6_1 -->|发生额| DISC[附注披露]
        I2 -->|资本化额| DISC
    end
```

## Architecture Decision Records (ADR)

### ADR-1: 损益类取数逻辑

**决策**：I6使用`calcIncomeStatementNet`而非`calcAssetEndBalance`，TB回写发生额。

**理由**：
- 6602研发费用是损益类科目，借方=费用增加，贷方=冲回/结转
- 与H10(6115资产处置损益)完全同款处理
- 必须从tb_ledger取发生额，不能用tb_balance期末余额

### ADR-2: I6↔I2双向EventBus

**决策**：I6保存时publish 'research:expense-updated'，subscribe I2的'development:capitalized-updated'。

**理由**：
- 费用化(I6)+资本化(I2)=研发总额是核心校验规则(VR-I6-01)
- 双向订阅确保任一方变化都能实时校验
- cross_wp_references提供静态跳转，EventBus提供动态通知

### ADR-3: 月度12列横向矩阵

**决策**：明细表固定列+12月份列横向排列（类D4-2模式）。

**理由**：
- 源xlsx就是月度横向结构（65列=基础列+12月+合计+辅助列）
- 月度趋势是审计关注重点（识别异常月份）
- 固定前2列+横滚12月是最佳交互模式

## Correctness Properties

| ID | Property | 验证方式 |
|----|----------|---------|
| CP-I6-01 | 审定数=未审+AJE+RJE | PBT |
| CP-I6-02 | 损益净发生额=借方-贷方（6602借方科目） | PBT |
| CP-I6-03 | 月度合计=SUM(1月~12月) | PBT |
| CP-I6-04 | VR-I6-01: 费用化+资本化=研发总额 | PBT |
| CP-I6-05 | 合计行恒等 | PBT |
| CP-I6-06 | 借贷平衡 | PBT |
| CP-I6-07 | 截止测试日期差判断 | PBT |
| CP-I6-08 | 变动率=(本期-同期)/同期×100% | PBT |

## 错误处理

| 场景 | 处理 |
|------|------|
| I2联动数据不可用 | "I2数据未就绪"灰色+手工输入 |
| VR-I6-01校验失败 | 红色警告面板+差额显示 |
| 月度明细65列渲染 | 固定列+横滚+虚拟列 |
| tb_ledger发生额取数失败 | "发生额暂不可用"灰色占位 |
| 截止样本提取失败 | 降级手工输入 |
