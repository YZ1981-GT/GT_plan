# Design Document: F3 应付票据专属HTML精美组件

## Overview

F3应付票据专属组件`f3-notes-payable`。覆盖1个xlsx源模板(77KB)/10有效sheet。科目2201应付票据（贷方/负债类）。独立组件，el-tabs模式(10个tab)。

核心架构：
- componentType `f3-notes-payable`，主入口 GtF3NotesPayable.vue
- **el-tabs模式**：10 sheets适合用tabs
- 每个sheet独立子组件 + composable
- 宽表拆分：F3-2(25列→3区段Tab) / F3-7(18列→借方/贷方独立区块)
- 贷方科目公式：期末未审 = 期初审定 + 贷方 - 借方（与F1借方科目方向相反）
- EventBus联动：publish substantive:adjudicated(accountCode='2201')
- 特色：带息票据利息测算(面值×利率×天数/360) + 逾期票据风险评估
- 双模式（HTML ↔ OnlyOffice）+ 导入导出(useF3ImportExport) + AI(5 section)

## Architecture

### sheetName分发模式 + el-tabs组织

GtF3NotesPayable.vue 接收 `sheetName` prop，用正则提取编码(F3A/F3-1~F3-7/附注)，`v-if` 分发到对应子组件。外层采用el-tabs展示10个tab。

```
sheetName → regex提取编码 → v-if匹配 → 子组件渲染
                                     ↘ 未匹配 → OnlyOffice fallback

el-tabs 10 tabs:
├── F3A  实质性程序表 (a-program-console)
├── F3-1 审定表
├── 附注披露(上市)
├── 附注披露(国企)
├── F3-2 明细表 (3区段Tab)
├── F3-3 调整分录
├── F3-4 带息票据利息测算表
├── F3-5 逾期票据检查
├── F3-6 关联方检查表
└── F3-7 应付票据检查表 (借方/贷方区块)
```

### 文件结构

```
audit-platform/frontend/src/components/workpaper/
├── GtF3NotesPayable.vue                    # 主入口 sheetName v-if分发 + el-tabs
├── f3-notes-payable/
│   ├── F3TabAdjudication.vue               # F3-1 审定表（贷方科目）
│   ├── F3TabDisclosureListed.vue           # 附注披露(上市)
│   ├── F3TabDisclosureSOE.vue              # 附注披露(国企)
│   ├── F3TabDetail.vue                     # F3-2 明细表(25列→3区段Tab)
│   ├── F3TabAdjustment.vue                 # F3-3 调整分录
│   ├── F3TabInterestCalc.vue              # F3-4 带息票据利息测算表
│   ├── F3TabOverdueCheck.vue              # F3-5 逾期票据检查
│   ├── F3TabRelatedParty.vue              # F3-6 关联方检查表
│   └── F3TabVoucherCheck.vue              # F3-7 应付票据检查表(借方/贷方区块)
├── composables/
│   ├── useF3FormulaEngine.ts               # F3公式引擎(利息/逾期/贷方余额/审定/集中度/借贷平衡)
│   ├── useF3FormData.ts                    # 数据加载/保存/selfLoad
│   ├── useF3Adjudication.ts               # F3-1审定表逻辑(贷方科目)
│   ├── useF3Detail.ts                      # F3-2明细表逻辑(3区段)
│   ├── useF3InterestCalc.ts               # F3-4利息测算逻辑
│   ├── useF3OverdueCheck.ts               # F3-5逾期检查逻辑
│   ├── useF3RelatedParty.ts               # F3-6关联方检查逻辑
│   ├── useF3VoucherCheck.ts               # F3-7检查表逻辑(借方/贷方分区)
│   ├── useF3ImportExport.ts               # 导入导出composable
│   └── useF3DualMode.ts                    # 双模式OO切换

backend/app/routers/wp_render_strategies/
├── _f3_notes_payable.py                    # render策略+注册RENDERER_DISPATCH
├── _f3_notes_payable_import_export.py      # 导入导出3端点
└── _f3_notes_payable_ai.py                 # AI生成5 section
```

### F3-2明细表 3区段Tab设计（25列）

```
┌─────────────────────────────────────────────────────────────────────────┐
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                     │
│ │ 基础信息(9列) │ │ 票据详情(8列) │ │ 审定调整(8列) │  ← 3区段Tab       │
│ └──────────────┘ └──────────────┘ └──────────────┘                     │
│                                                                         │
│ ┌──────────────────────────────────────────────────────────────────┐   │
│ │ el-table (动态行，区段间行同步)                                    │   │
│ │ 基础信息: 序号|出票日期|到期日|票据类型|出票人|收票人|面值|币种|用途  │   │
│ │ 票据详情: 票面利率|期限|是否带息|是否逾期|逾期天数|承兑银行|状态|备注│   │
│ │ 审定调整: 期初余额|本期增加|本期减少|期末余额|账项调整|重分类|审定|索引│   │
│ └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│ 底部合计：面值合计 / 期末余额合计 / 审定余额合计                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### F3-7检查表 借方/贷方独立区块设计

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 抽凭引擎按钮 [使用抽凭引擎]    导入导出▾                                  │
├─────────────────────────────────────────────────────────────────────────┤
│ ┌── 贷方检查区（增加）─────────────────────────────────────────────────┐ │
│ │ el-table: 序号|摘要|对方科目|金额|凭证日期|凭证编号|票据类型|承兑方|   │ │
│ │           采购合同核对|商品验收核对|审计结论|备注                       │ │
│ │ 底部小计：金额合计 / 异常笔数                                        │ │
│ └──────────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│ ┌── 借方检查区（减少）─────────────────────────────────────────────────┐ │
│ │ el-table: 序号|摘要|对方科目|金额|凭证日期|凭证编号|付款方式|银行流水|  │ │
│ │           是否逾期付款|审计结论|备注                                   │ │
│ │ 底部小计：金额合计 / 异常笔数                                        │ │
│ └──────────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│ 审计结论 textarea + AI按钮                                               │
└─────────────────────────────────────────────────────────────────────────┘
```

### 数据流

```
F3-1 审定表 ── EventBus(substantive:adjudicated, accountCode='2201') ──→ 附注披露 + trial_balance

F3-7 检查表 ←── GtVoucherSamplingEngine(科目2201) ──── 抽凭引擎

F3-4 利息测算 ←── 📎OCR(票据扫描件) ──── 面值/利率/期限自动识别

useVersionTrail ── autoSnapshot on save ──→ 版本快照
```

### EventBus事件

| 事件名 | 发布者 | 消费者 |
|--------|--------|--------|
| `substantive:adjudicated` | F3-1审定表 | 附注披露组件 + trial_balance |
| `disclosure:note-text-updated` | 附注披露 | 附注模块 |

### 后端AI Section清单

```
interest-conclusion / overdue-evaluation / related-evaluation / 
debit-check-conclusion / credit-check-conclusion
```

## Components and Interfaces

### 前端组件接口

```typescript
// GtF3NotesPayable.vue props
interface F3NotesPayableProps {
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}

// F3-4 利息测算行
interface InterestCalcRow {
  id: string
  seq: number
  drawer: string              // 出票人
  principal: number           // 票据面值
  rate: number                // 票面利率(%)
  issueDate: string           // 出票日
  dueDate: string             // 到期日
  termDays: number            // 期限(天)
  accrualStart: string        // 计息起始日
  accrualEnd: string          // 计息截止日
  accrualDays: number         // 应计天数(公式)
  calculatedInterest: number  // 应付利息(公式)
  companyInterest: number     // 企业计提利息
  variance: number            // 差异(公式)
}

// F3-5 逾期票据行
interface OverdueNoteRow {
  id: string
  seq: number
  drawer: string              // 出票人
  noteType: string            // 票据类型
  amount: number              // 面值
  issueDate: string           // 出票日
  dueDate: string             // 到期日
  overdueDays: number         // 逾期天数(公式)
  overdueReason: string       // 逾期原因
  acceptor: string            // 承兑方
  creditRating: string        // 承兑方信用等级
  convertedToAP: string       // 是否已转应付账款
  collectionStatus: string    // 催收情况
  riskLevel: 'low' | 'medium' | 'high' | 'extreme'  // 风险等级
  auditSuggestion: string     // 审计建议
  remark: string
}

// F3-2 明细表行
interface NoteDetailRow {
  id: string
  seq: number
  // 基础信息区段
  issueDate: string
  dueDate: string
  noteType: 'bank' | 'commercial'
  drawer: string
  payee: string
  faceValue: number
  currency: string
  purpose: string
  // 票据详情区段
  rate: number
  termDays: number
  isInterestBearing: string
  isOverdue: string
  overdueDays: number         // 公式
  acceptorBank: string
  status: 'circulating' | 'matured' | 'overdue' | 'endorsed'
  remark: string
  // 审定调整区段
  openingBalance: number
  currentIncrease: number     // 贷方增加
  currentDecrease: number     // 借方减少
  closingBalance: number      // 公式=期初+增加-减少
  ajeAdjustment: number
  rjeReclassification: number
  adjustedBalance: number     // 公式=期末+AJE+RJE
  indexRef: string
}

// F3-7 检查表行（通用）
interface VoucherCheckRow {
  id: string
  seq: number
  summary: string             // 摘要
  counterAccount: string      // 对方科目
  amount: number              // 金额
  voucherDate: string         // 凭证日期
  voucherNo: string           // 凭证编号
  auditConclusion: string     // 审计结论
  remark: string
  // 贷方区特有
  noteType?: string
  acceptor?: string
  purchaseContractCheck?: string
  goodsReceiptCheck?: string
  // 借方区特有
  paymentMethod?: string
  bankReconciliation?: string
  isOverduePayment?: string
}
```

### 后端接口

```python
# _f3_notes_payable.py
def render_f3_notes_payable(wp_id: str, config: dict) -> dict:
    """Render策略函数，返回componentType='f3-notes-payable'和sheets配置"""

# _f3_notes_payable_import_export.py
POST /api/workpapers/{wp_id}/f3/export-template?sheet={code}
POST /api/workpapers/{wp_id}/f3/export-data?sheet={code}
POST /api/workpapers/{wp_id}/f3/import-data?sheet={code}  # multipart/form-data

# _f3_notes_payable_ai.py
POST /api/workpapers/{wp_id}/f3/ai/{section}
# section: interest-conclusion/overdue-evaluation/related-evaluation/
#          debit-check-conclusion/credit-check-conclusion
```

## Data Models

### F3-1 审定表数据模型

```typescript
interface AdjudicationData {
  rows: AdjudicationRow[]
  trialBalanceAmount: number   // 从TB自动取数
  variance: number             // 审定-试算表差异
}

interface AdjudicationRow {
  id: string
  item: string                 // 项目名（银行承兑/商业承兑/合计）
  // 期初
  openingUnadjusted: number
  openingAJE: number
  openingRJE: number
  openingAdjusted: number      // 公式=未审+AJE+RJE
  // 期末
  closingUnadjusted: number    // 公式=期初审定+贷方-借方
  closingAJE: number
  closingRJE: number
  closingAdjusted: number      // 公式=未审+AJE+RJE
  indexRef: string
}
```

### F3-6 关联方检查行

```typescript
interface RelatedPartyNoteRow {
  id: string
  seq: number
  partyName: string
  relationship: string
  noteType: string
  faceValue: number
  issueDate: string
  dueDate: string
  termDays: number
  rate: number
  purpose: string
  concentration: number       // 占比(公式)
  isNormalSettlement: string
  settlementMethod: string
  fairness: 'fair' | 'basically-fair' | 'unfair' | 'unknown'
  auditEvaluation: string
  remark: string
}
```

## Error Handling

1. **selfLoad失败**：render-config返回404/500时显示错误卡片+重试按钮
2. **公式计算异常**：parseNum兜底（NaN/Infinity→0），除零保护（total=0时占比显示0%）
3. **利息计算日期异常**：计息截止日<起始日→应计天数0，toast警告
4. **逾期天数负值保护**：到期日>当前日期→逾期天数0
5. **区段Tab切换**：切换时保持行选中状态
6. **借贷不平衡**：实时校验，不平衡时底部红色警告
7. **EventBus发布失败**：5秒无消费确认→toast提示
8. **导入格式错误**：后端返回详细错误列表（行号/字段/原因）
9. **OCR识别失败**：返回空结果时toast"未识别到有效票据信息"

## Testing Strategy

### 前端PBT测试

| 测试文件 | 覆盖Property | 框架 |
|----------|-------------|------|
| useF3FormulaEngine.pbt.spec.ts | P1~P8 | vitest + fast-check |

### 后端测试

| 测试文件 | 覆盖范围 |
|----------|----------|
| test_f3_notes_payable_pbt.py | 利息计算/贷方余额round-trip |
| test_f3_notes_payable.py | render策略+注册契约 |

### 集成测试

- sheetName分发正确性（10个sheet名→对应组件）
- 贷方余额公式链（期初+贷方-借方=期末未审→+AJE+RJE=审定）
- 利息测算公式全链路（面值×利率×天数/360）
- F3-7抽凭引擎→样本分配到借方/贷方区
- F3-2三区段Tab切换+行同步
- EventBus(substantive:adjudicated)跨组件传递
- 导入导出round-trip

## Correctness Properties

### Property 1: 带息票据利息公式
∀ principal ∈ ℝ≥0, rate ∈ [0,100], days ∈ ℤ≥0: calcInterest(principal, rate, days) === principal × rate/100 × days/360
**Validates: Requirements 11.1, 7.3**

### Property 2: 贷方余额公式
∀ opening, credit, debit ∈ ℝ≥0: calcCreditBalance(opening, credit, debit) === opening + credit - debit
**Validates: Requirements 11.3, 3.3, 5.2**

### Property 3: 审定数公式
∀ unadjusted, aje, rje ∈ ℝ: calcAdjustedAmount(unadjusted, aje, rje) === unadjusted + aje + rje
**Validates: Requirements 11.4, 3.4**

### Property 4: 借贷平衡恒等
∀ debits[], credits[] ∈ ℝ[]: isDebitCreditBalanced(debits, credits) ↔ (SUM(debits) === SUM(credits))
**Validates: Requirements 11.6, 6.2**

### Property 5: 集中度公式
∀ amount ∈ ℝ≥0, total ∈ ℝ>0: calcConcentration(amount, total) === amount/total × 100
**Validates: Requirements 11.5, 9.2**

### Property 6: 逾期天数非负
∀ currentDate, dueDate: calcOverdueDays(currentDate, dueDate) ≥ 0
**Validates: Requirements 11.2, 8.2**

### Property 7: 利息与面值正比
∀ p1, p2 ∈ ℝ≥0, p2≠0, rate, days固定: calcInterest(p1, rate, days) / calcInterest(p2, rate, days) === p1/p2
**Validates: Requirements 11.1, 7.3**

### Property 8: 贷方余额方向性
∀ opening, credit, debit ∈ ℝ≥0: credit > debit → calcCreditBalance(opening, credit, debit) > opening
**Validates: Requirements 11.3, 3.3**
