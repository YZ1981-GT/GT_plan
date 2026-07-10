# Design Document: F4 应付账款专属HTML精美组件

## Overview

F4应付账款专属组件`f4-accounts-payable`。覆盖1个xlsx源模板(105KB)/12有效sheet。科目2202应付账款（贷方/负债类）。独立组件，el-tabs模式(12个tab)。

核心架构：
- componentType `f4-accounts-payable`，主入口 GtF4AccountsPayable.vue
- **el-tabs模式**：12 sheets用tabs
- 每个sheet独立子组件 + composable
- 宽表拆分：F4-2(27列→3区段Tab) / F4-8(18列→借方/贷方独立区块)
- 贷方科目公式：期末未审 = 期初审定 + 贷方 - 借方
- F4-7未入账检查：反向截止测试，集成useCutoffAutoSampling（序时账±5天自动提取）
- F4-9供应商融资检查：保理/票据融资/供应链融资3区域
- EventBus联动：publish substantive:adjudicated(accountCode='2202')
- 双模式（HTML ↔ OnlyOffice）+ 导入导出(useF4ImportExport) + AI(6 section)

## Architecture

### sheetName分发模式 + el-tabs组织

```
sheetName → regex提取编码 → v-if匹配 → 子组件渲染
                                     ↘ 未匹配 → OnlyOffice fallback

el-tabs 12 tabs:
├── F4A  实质性程序表 (a-program-console)
├── F4-1 审定表 (按性质+按账龄两级)
├── 附注披露(上市)
├── 附注披露(国企)
├── F4-2 明细表 (27列→3区段Tab)
├── F4-3 调整分录
├── F4-4 实质性分析
├── F4-5 长期挂账检查
├── F4-6 关联方检查表
├── F4-7 未入账检查表 (反向截止测试，104行)
├── F4-8 应付账款检查表 (借方/贷方区块)
└── F4-9 供应商融资检查表 (3区域，84行)
```

### 文件结构

```
audit-platform/frontend/src/components/workpaper/
├── GtF4AccountsPayable.vue                 # 主入口 sheetName v-if分发 + el-tabs
├── f4-accounts-payable/
│   ├── F4TabAdjudication.vue               # F4-1 审定表（按性质+按账龄两级）
│   ├── F4TabDisclosureListed.vue           # 附注披露(上市)
│   ├── F4TabDisclosureSOE.vue              # 附注披露(国企)
│   ├── F4TabDetail.vue                     # F4-2 明细表(27列→3区段Tab)
│   ├── F4TabAdjustment.vue                 # F4-3 调整分录
│   ├── F4TabSubstantiveAnalysis.vue        # F4-4 实质性分析
│   ├── F4TabLongOutstanding.vue            # F4-5 长期挂账检查
│   ├── F4TabRelatedParty.vue              # F4-6 关联方检查表
│   ├── F4TabUnrecordedCheck.vue           # F4-7 未入账检查表(截止测试)
│   ├── F4TabVoucherCheck.vue              # F4-8 检查表(借方/贷方区块)
│   └── F4TabSupplierFinancing.vue         # F4-9 供应商融资检查表
├── composables/
│   ├── useF4FormulaEngine.ts               # F4公式引擎(贷方余额/审定/账龄/集中度/挂账/变动率/借贷平衡)
│   ├── useF4FormData.ts                    # 数据加载/保存/selfLoad
│   ├── useF4Adjudication.ts               # F4-1审定表逻辑(两级结构)
│   ├── useF4Detail.ts                      # F4-2明细表逻辑(3区段)
│   ├── useF4SubstantiveAnalysis.ts        # F4-4实质性分析逻辑
│   ├── useF4LongOutstanding.ts            # F4-5长期挂账逻辑
│   ├── useF4RelatedParty.ts               # F4-6关联方检查逻辑
│   ├── useF4UnrecordedCheck.ts            # F4-7未入账检查逻辑(截止测试)
│   ├── useF4VoucherCheck.ts               # F4-8检查表逻辑(借方/贷方)
│   ├── useF4SupplierFinancing.ts          # F4-9供应商融资逻辑
│   ├── useF4ImportExport.ts               # 导入导出composable
│   └── useF4DualMode.ts                    # 双模式OO切换

backend/app/routers/wp_render_strategies/
├── _f4_accounts_payable.py                 # render策略+注册RENDERER_DISPATCH
├── _f4_accounts_payable_import_export.py   # 导入导出3端点
└── _f4_accounts_payable_ai.py              # AI生成6 section
```

### F4-2明细表 3区段Tab设计（27列）

```
┌─────────────────────────────────────────────────────────────────────────┐
│ ┌──────────────┐ ┌──────────────────┐ ┌──────────────┐                 │
│ │ 基础信息(9列) │ │ 账龄与核对(10列)  │ │ 调整与审定(8列)│ ← 3区段Tab    │
│ └──────────────┘ └──────────────────┘ └──────────────┘                 │
│                                                                         │
│ ┌──────────────────────────────────────────────────────────────────┐   │
│ │ el-table (动态行，区段间行同步)                                    │   │
│ │ 基础信息: 序号|债权人|公司代码|关联方类型|款项性质|期初|借方|贷方|期末│   │
│ │ 账龄核对: 1年内|1-2年|2-3年|3年以上|合计|是否函证|函证结果|期后付|日期|备注│
│ │ 调整审定: 账项调整|重分类|审定余额|审定1年内|1-2年|2-3年|3年以上|索引  │   │
│ └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│ 底部合计：期初/借方/贷方/期末/各账龄段/审定                              │
└─────────────────────────────────────────────────────────────────────────┘
```

### F4-7未入账检查 3区域设计（反向截止测试）

```
┌─────────────────────────────────────────────────────────────────────────┐
│ [截止自动提取] 按钮 ← useCutoffAutoSampling(序时账±5天)                  │
├─────────────────────────────────────────────────────────────────────────┤
│ ┌── 期后采购检查 ─────────────────────────────────────────────────────┐ │
│ │ el-table: 序号|采购日期|供应商|金额|采购单号|商品/服务|应入当期|建议|备注│ │
│ │ 底部小计：总金额/应入当期笔数/金额                                    │ │
│ └──────────────────────────────────────────────────────────────────────┘ │
│ ┌── 期后入库检查 ─────────────────────────────────────────────────────┐ │
│ │ el-table: 序号|入库日期|供应商|金额|入库单号|商品名称|应入当期|建议|备注│ │
│ │ 底部小计：总金额/应入当期笔数/金额                                    │ │
│ └──────────────────────────────────────────────────────────────────────┘ │
│ ┌── 期后收票检查 ─────────────────────────────────────────────────────┐ │
│ │ el-table: 序号|收票日期|开票方|金额|发票号|服务期间|应入当期|建议|备注  │ │
│ │ 底部小计：总金额/应入当期笔数/金额                                    │ │
│ └──────────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│ 底部总结：未入账应付合计 + 建议调整金额 + 审计结论textarea(AI)            │
└─────────────────────────────────────────────────────────────────────────┘
```

### F4-9供应商融资检查 3区域设计

```
┌─────────────────────────────────────────────────────────────────────────┐
│ ┌── 保理融资 ────────────────────────────────────────────────────────┐  │
│ │ el-table 12列: 供应商|保理公司|金额|日期|到期|费率|追索权|终止确认|...│  │
│ └──────────────────────────────────────────────────────────────────────┘ │
│ ┌── 票据融资 ────────────────────────────────────────────────────────┐  │
│ │ el-table 12列: 供应商|票据类型|金额|出票|到期|贴现额|利率|背书转让|... │  │
│ └──────────────────────────────────────────────────────────────────────┘ │
│ ┌── 供应链融资 ──────────────────────────────────────────────────────┐  │
│ │ el-table 12列: 供应商|核心企业|金额|日期|到期|利率|平台|修改条件|重分类│  │
│ └──────────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│ 底部总结：融资合计+重分类建议+审计结论textarea(AI)                        │
└─────────────────────────────────────────────────────────────────────────┘
```

### 数据流

```
F4-1 审定表 ── EventBus(substantive:adjudicated, accountCode='2202') ──→ 附注披露 + trial_balance

F4-8 检查表 ←── GtVoucherSamplingEngine(科目2202) ──── 抽凭引擎

F4-7 未入账检查 ←── useCutoffAutoSampling(序时账±5天) ──── 截止自动提取

F4-2 明细表 ←── 📎OCR(发票扫描件) ──── 金额/供应商自动识别

useVersionTrail ── autoSnapshot on save ──→ 版本快照
```

### EventBus事件

| 事件名 | 发布者 | 消费者 |
|--------|--------|--------|
| `substantive:adjudicated` | F4-1审定表 | 附注披露组件 + trial_balance |
| `disclosure:note-text-updated` | 附注披露 | 附注模块 |

### 后端AI Section清单

```
substantive-analysis / long-outstanding / related-evaluation / 
unrecorded-conclusion / voucher-check / financing-evaluation
```

## Components and Interfaces

### 前端组件接口

```typescript
// GtF4AccountsPayable.vue props
interface F4AccountsPayableProps {
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}

// F4-1 审定表（两级结构）
interface AdjudicationTwoLevel {
  byNature: AdjudicationRow[]     // 按性质：货款/工程款/服务费/其他/小计
  byAging: AdjudicationRow[]      // 按账龄：1年内/1-2年/2-3年/3年以上/小计
  total: AdjudicationRow          // 合计
  trialBalanceAmount: number
  variance: number
  crossCheckPassed: boolean       // 按性质小计===按账龄小计
}

interface AdjudicationRow {
  id: string
  item: string
  openingUnadjusted: number
  openingAJE: number
  openingRJE: number
  openingAdjusted: number
  closingUnadjusted: number
  closingAJE: number
  closingRJE: number
  closingAdjusted: number
  indexRef: string
}

// F4-2 明细表行（27列分3区段）
interface APDetailRow {
  id: string
  seq: number
  // 基础信息区段
  creditor: string
  companyCode: string
  relatedPartyType: string
  paymentNature: string
  openingAdjusted: number
  currentDebit: number
  currentCredit: number
  closingBalance: number          // 公式=期初+贷方-借方
  // 账龄与核对区段
  aging1Year: number
  aging1to2Year: number
  aging2to3Year: number
  aging3YearPlus: number
  agingTotal: number              // 公式=各账龄段SUM
  isConfirmed: string
  confirmationResult: string
  subsequentPayment: number
  subsequentPaymentDate: string
  remark: string
  // 调整与审定区段
  ajeAdjustment: number
  rjeReclassification: number
  adjustedBalance: number         // 公式=期末+AJE+RJE
  adjustedAging1: number
  adjustedAging2: number
  adjustedAging3: number
  adjustedAging4: number
  indexRef: string
}

// F4-7 未入账检查行（通用结构）
interface UnrecordedCheckRow {
  id: string
  seq: number
  date: string                    // 采购日期/入库日期/收票日期
  counterparty: string            // 供应商/开票方
  amount: number
  documentNo: string              // 采购单号/入库单号/发票号
  description: string             // 商品/服务名称
  shouldRecordCurrent: 'yes' | 'no' | ''  // 是否应入当期
  suggestion: string              // 入账建议
  remark: string
}

// F4-9 供应商融资行
interface FactoringRow {
  id: string
  seq: number
  supplier: string
  factoringCompany: string
  amount: number
  date: string
  dueDate: string
  feeRate: number
  hasRecourse: string
  isDerecognized: string
  reportingAccount: string
  auditEvaluation: string
  remark: string
}

interface NoteFinancingRow {
  id: string
  seq: number
  supplier: string
  noteType: string
  amount: number
  issueDate: string
  dueDate: string
  discountAmount: number
  discountRate: number
  isEndorsed: string
  reportingAdequacy: string
  auditEvaluation: string
  remark: string
}

interface SupplyChainFinanceRow {
  id: string
  seq: number
  supplier: string
  coreEnterprise: string
  amount: number
  date: string
  dueDate: string
  rate: number
  platform: string
  hasModifiedTerms: string
  shouldReclassify: string
  auditEvaluation: string
  remark: string
}
```

### 后端接口

```python
# _f4_accounts_payable.py
def render_f4_accounts_payable(wp_id: str, config: dict) -> dict:
    """Render策略函数，返回componentType='f4-accounts-payable'和sheets配置"""

# _f4_accounts_payable_import_export.py
POST /api/workpapers/{wp_id}/f4/export-template?sheet={code}
POST /api/workpapers/{wp_id}/f4/export-data?sheet={code}
POST /api/workpapers/{wp_id}/f4/import-data?sheet={code}  # multipart/form-data

# _f4_accounts_payable_ai.py
POST /api/workpapers/{wp_id}/f4/ai/{section}
# section: substantive-analysis/long-outstanding/related-evaluation/
#          unrecorded-conclusion/voucher-check/financing-evaluation
```

## Data Models

### F4-5 长期挂账行

```typescript
interface LongOutstandingRow {
  id: string
  seq: number
  creditor: string
  amount: number
  startDate: string
  outstandingDays: number         // 公式
  paymentNature: string
  reason: string
  hasDispute: string
  shouldTransferIncome: string
  suggestion: string
  remark: string
}
```

### F4-6 关联方检查行

```typescript
interface RelatedPartyAPRow {
  id: string
  seq: number
  partyName: string
  relationship: string
  paymentNature: string
  openingBalance: number
  currentIncrease: number
  currentDecrease: number
  closingBalance: number          // 公式
  concentration: number           // 占比(公式)
  settlementCycle: string
  isOverdue: string
  fairness: 'fair' | 'basically-fair' | 'unfair' | 'unknown'
  aging: string
  auditEvaluation: string
  remark: string
}
```

## Error Handling

1. **selfLoad失败**：render-config返回404/500时显示错误卡片+重试按钮
2. **公式计算异常**：parseNum兜底（NaN/Infinity→0），除零保护
3. **两级审定交叉校验失败**：按性质小计≠按账龄小计时红色高亮两个小计行
4. **账龄交叉校验失败**：账龄合计≠期末余额时红色高亮
5. **useCutoffAutoSampling失败**：序时账无数据时toast提示"无法提取截止数据"
6. **区段Tab切换**：切换时保持行选中状态
7. **借贷不平衡**：实时校验，不平衡时底部红色警告
8. **虚拟滚动边界**：F4-7(104行)/F4-9(84行)/F4-8(73行)启用虚拟滚动
9. **导入格式错误**：后端返回详细错误列表

## Testing Strategy

### 前端PBT测试

| 测试文件 | 覆盖Property | 框架 |
|----------|-------------|------|
| useF4FormulaEngine.pbt.spec.ts | P1~P8 | vitest + fast-check |

### 后端测试

| 测试文件 | 覆盖范围 |
|----------|----------|
| test_f4_accounts_payable_pbt.py | 贷方余额/账龄校验/截止逻辑 |
| test_f4_accounts_payable.py | render策略+注册契约 |

### 集成测试

- sheetName分发正确性（12个sheet→对应组件）
- 贷方余额公式链
- 两级审定交叉校验（按性质小计===按账龄小计）
- F4-7截止自动提取→3区域分配
- F4-8抽凭引擎→借贷分配
- F4-2三区段Tab行同步+账龄交叉校验
- EventBus(substantive:adjudicated)跨组件传递
- 导入导出round-trip

## Correctness Properties

### Property 1: 贷方余额公式
∀ opening, credit, debit ∈ ℝ≥0: calcCreditBalance(opening, credit, debit) === opening + credit - debit
**Validates: Requirements 13.1, 3.3, 5.2**

### Property 2: 审定数公式
∀ unadjusted, aje, rje ∈ ℝ: calcAdjustedAmount(unadjusted, aje, rje) === unadjusted + aje + rje
**Validates: Requirements 13.2, 3.4**

### Property 3: 账龄交叉校验
∀ a1, a2, a3, a4, closing ∈ ℝ≥0: calcAgingCrossCheck(a1+a2+a3+a4, closing) === (a1+a2+a3+a4 === closing)
**Validates: Requirements 13.8, 5.3, 5.5**

### Property 4: 集中度公式
∀ amount ∈ ℝ≥0, total ∈ ℝ>0: calcConcentration(amount, total) === amount/total × 100
**Validates: Requirements 13.4, 9.3**

### Property 5: 变动率公式
∀ current, prior ∈ ℝ, prior≠0: calcChangeRate(current, prior) === (current-prior)/prior × 100
**Validates: Requirements 13.6, 7.3**

### Property 6: 借贷平衡恒等
∀ debits[], credits[] ∈ ℝ[]: isDebitCreditBalanced(debits, credits) ↔ (|SUM(debits)-SUM(credits)| < 0.01)
**Validates: Requirements 13.7, 6.2**

### Property 7: 挂账天数非负
∀ currentDate, startDate: calcOutstandingDays(currentDate, startDate) ≥ 0
**Validates: Requirements 13.5, 8.2**

### Property 8: 两级审定交叉校验
∀ natureRows[], agingRows[]: SUM(natureRows.closingAdjusted) === SUM(agingRows.closingAdjusted)
**Validates: Requirements 3.5, 3.8**
