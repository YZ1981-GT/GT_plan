# Design Document: D1 背书贴现组专属组件

## Overview

将 `useD1NotesReceivable.ts`（1237行）中背书贴现相关的D1-6/D1-7/D1-8/D1-9四个sheet的逻辑拆分为独立子组件+子composable。每个sheet成为独立的Vue组件（200-400行）配套独立composable，全部以HTML精美组件（el-table + 金额格式化 + 动态行）为主渲染模式，OnlyOffice仅作降级/偏好切换。

核心设计挑战：
- D1-6的QA矩阵IF公式需在前端composable实现（4问×3列→自动判定业务模式+列报项目）
- D1-7的31列宽表需横向滚动+列分组（基本信息|流转|金额|审定四区）
- D1-7核对区需与D1-2跨sheet取数联动（纯computed响应式）
- D1-9贴息公式 P×R×D/360 在前端composable实现
- D1-8可从D1-7备查簿按状态筛选导入数据

## Architecture

### 组件依赖关系

```mermaid
graph TD
    subgraph "GtD1NotesReceivable.vue (主入口)"
        MAIN[el-tabs 容器]
    end

    subgraph "新增子组件 (本spec)"
        BM[D1TabBusinessMode.vue<br/>业务模式D1-6 ~250行]
        MEMO[D1TabMemoReconciliation.vue<br/>备查簿D1-7 ~400行]
        END[D1TabEndorsementDetail.vue<br/>贴现背书明细D1-8 ~350行]
        INT[D1TabInterestCheck.vue<br/>贴息检查D1-9 ~300行]
    end

    subgraph "新增composables (本spec)"
        USE_BM[useD1BusinessMode.ts<br/>~200行]
        USE_MEMO[useD1MemoReconciliation.ts<br/>~350行]
        USE_END[useD1EndorsementDetail.ts<br/>~250行]
        USE_INT[useD1InterestCheck.ts<br/>~250行]
    end

    subgraph "已有基础设施 (复用)"
        FORMULA[useD1FormulaEngine.ts<br/>纯函数(已有)]
        FORM_DATA[useD1FormData.ts<br/>loadAll/saveImmediate]
        DISPLAY[displayPrefs.fmtAmount]
        OO[GtOnlyOfficeSheet.vue]
        REVIEW[useReviewDialogProvider]
    end

    MAIN --> BM & MEMO & END & INT
    BM --> USE_BM
    MEMO --> USE_MEMO
    END --> USE_END
    INT --> USE_INT

    USE_BM --> FORMULA & FORM_DATA
    USE_MEMO --> FORMULA & FORM_DATA
    USE_END --> FORMULA & FORM_DATA
    USE_INT --> FORMULA & FORM_DATA

    USE_MEMO -.->|跨sheet取数D1-2| FORM_DATA
    USE_END -.->|从D1-7筛选导入| USE_MEMO

    BM --> DISPLAY & OO & REVIEW
    MEMO --> DISPLAY & OO & REVIEW
    END --> DISPLAY & OO & REVIEW
    INT --> DISPLAY & OO & REVIEW
```

### 文件结构

```
audit-platform/frontend/src/components/workpaper/
├── GtD1NotesReceivable.vue          # 主入口（修改：新增4个tab-pane）
├── d1/                               # 已有目录
│   ├── D1TabBusinessMode.vue         # 业务模式D1-6（~250行）
│   ├── D1TabMemoReconciliation.vue   # 备查簿核对D1-7（~400行）
│   ├── D1TabEndorsementDetail.vue    # 贴现背书明细D1-8（~350行）
│   └── D1TabInterestCheck.vue        # 贴息检查D1-9（~300行）
├── composables/
│   ├── useD1BusinessMode.ts          # 业务模式逻辑（~200行）
│   ├── useD1MemoReconciliation.ts    # 备查簿逻辑（~350行）
│   ├── useD1EndorsementDetail.ts     # 贴现背书逻辑（~250行）
│   ├── useD1InterestCheck.ts         # 贴息检查逻辑（~250行）
│   └── useD1FormulaEngine.ts         # 已有，新增贴息公式函数
```

## Components and Interfaces

### 1. useD1FormulaEngine.ts — 新增贴息相关纯函数

```typescript
// 在已有 useD1FormulaEngine.ts 中追加：

/** 贴息天数 = 到期日 - 贴现日（天数） */
export function calcDiscountDays(maturityDate: string, discountDate: string): number

/** 应计贴现利息 = 票面金额 × 贴现率 × 贴息天数 / 360 */
export function calcDiscountInterest(
  faceValue: number, discountRate: number, days: number
): number

/** 贴息差异 = 应计贴现利息 - 账面贴现利息 */
export function calcInterestDifference(calculated: number, booked: number): number

/** QA矩阵业务模式判定：根据4个Y/N答案返回业务模式描述 */
export function determineBusinessMode(
  q1: 'Y' | 'N' | '', q2: 'Y' | 'N' | '', q3: 'Y' | 'N' | '', q4: 'Y' | 'N' | ''
): string

/** 列报项目判定：根据业务模式返回列报科目 */
export function determineReportItem(businessMode: string): string
```

### 2. useD1BusinessMode.ts — 业务模式分析 composable

```typescript
export interface BusinessModeRow {
  rowId: string          // 'fixed-high-bank' | 'fixed-low-bank' | 'fixed-commercial'
  combinationName: string // 组合名称
  businessMode: string   // 业务模式（下拉）
  basis: string          // 具体依据
  indexRef: string       // 索引号
  remark: string         // 备注
  isFixed: boolean
}

export interface QACell {
  answer: 'Y' | 'N' | ''  // 是/否/未填
}

export interface QAMatrix {
  questions: string[]      // 4个问题文本（固定）
  columns: string[]        // 3个组合名（固定）
  cells: QACell[][]        // [4行][3列]
}

export interface UseD1BusinessModeOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: SaveFn
  isReadonly: Ref<boolean>
}

export function useD1BusinessMode(options: UseD1BusinessModeOptions) {
  return {
    // 业务模式依据表
    basisRows: Ref<BusinessModeRow[]>,
    // QA矩阵数据
    qaMatrix: Ref<QAMatrix>,
    // 自动判定结果（3组合各自的业务模式）
    businessModeResults: ComputedRef<string[]>,  // 3个结果
    // 自动判定列报项目
    reportItemResults: ComputedRef<string[]>,    // 3个结果
    // 审计说明/结论
    auditNote: Ref<string>,
    auditConclusion: Ref<string>,
    // 操作
    updateBasisRow: (rowId: string, field: string, value: string) => void,
    updateQACell: (questionIdx: number, columnIdx: number, answer: 'Y' | 'N') => void,
    saveAuditNote: (text: string) => void,
    saveAuditConclusion: (text: string) => void,
  }
}
```

### 3. useD1MemoReconciliation.ts — 备查簿核对 composable

```typescript
export interface MemoRow {
  rowId: string
  rowType: 'fixed' | 'dynamic' | 'summary'
  category: 'bank' | 'commercial'  // 所属分类
  // 基本信息区 (8列)
  noteType: string        // 票据类型（银行承兑/商业承兑）
  noteNumber: string      // 票据号
  receivedDate: string    // 收到日期
  endorser: string        // 前手
  issueDate: string       // 出票日
  issuer: string          // 出票人
  acceptor: string        // 承兑人
  amount: number          // 金额
  // 流转区 (6列)
  maturityDate: string    // 到期日
  transferDate: string    // 流转日
  status: string          // 状态
  endorsee: string        // 被背书人
  discountBank: string    // 贴现银行
  discountInterest: number // 贴现息
  // 金额区 (9列)
  isPledged: string       // 是否质押
  isDiscountedEndorsed: string // 审计日已贴现背书
  beginningBalance: number  // 年初余额
  currentReceived: number   // 本期收到
  currentEndorsed: number   // 本期背书
  currentMatured: number    // 本期到期承兑
  currentDiscounted: number // 本期贴现
  endingBalance: number     // 年末余额
  unexpiredEndorsedDiscounted: number // 期末未到期背书贴现
  // 审定区 (8列)
  isDerecognized: string    // 是否终止确认
  creditRating: string      // 信用评级
  auditedFinancing: number  // 审定应收款项融资
  auditedNotes: number      // 审定应收票据
  relatedParty: string      // 关联关系
  isOverdue: string         // 是否逾期
  overdueTransferAmount: number // 逾期转应收金额
  remarkText: string        // 备注
}

export interface ReconciliationRow {
  label: string           // '备查簿合计' | '明细账(D1-2)' | '差异'
  beginningBalance: number
  currentReceived: number
  currentEndorsed: number
  currentMatured: number
  currentDiscounted: number
  endingBalance: number
}

export interface UseD1MemoReconciliationOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: SaveFn
  isReadonly: Ref<boolean>
}

export function useD1MemoReconciliation(options: UseD1MemoReconciliationOptions) {
  return {
    // 截止日期
    cutoffDate: Ref<string>,
    // 票据明细行（含固定行+动态行）
    bankRows: Ref<MemoRow[]>,
    commercialRows: Ref<MemoRow[]>,
    // 小计/合计（computed）
    bankSubtotal: ComputedRef<MemoRow>,
    commercialSubtotal: ComputedRef<MemoRow>,
    grandTotal: ComputedRef<MemoRow>,
    // 核对区（computed，含跨sheet取数）
    reconciliationRows: ComputedRef<ReconciliationRow[]>,
    hasDifference: ComputedRef<boolean>,
    // 贴现背书统计区（SUMIFS）
    endorsedStats: ComputedRef<{ discountedTotal: number; endorsedTotal: number }>,
    // 审计说明/结论
    auditNote: Ref<string>,
    auditConclusion: Ref<string>,
    // 操作
    addRow: (category: 'bank' | 'commercial') => void,
    removeRow: (rowId: string) => void,
    updateCell: (rowId: string, field: string, value: string | number) => void,
    // 跨sheet状态
    crossSheetStatus: Ref<'loaded' | 'loading' | 'error'>,
  }
}
```

### 4. useD1EndorsementDetail.ts — 贴现背书明细 composable

```typescript
export interface EndorsementRow {
  rowId: string
  rowType: 'dynamic' | 'summary'
  noteType: string        // 票据种类
  receivedDate: string    // 收到日期
  issuer: string          // 出票人
  noteNumber: string      // 票据号
  billAmount: number      // 汇票金额
  accruedInterest: number // 已计利息
  issueDate: string       // 出票日
  maturityDate: string    // 到期日
  acceptorBank: string    // 承兑银行
  creditRating: string    // 信用等级
  discountBank: string    // 贴现银行
  discountAmount: number  // 贴现金额
  discountInterest: number // 贴现息
  isDerecognized: string  // 是否终止确认
  isCorrect: string       // 会计处理是否正确
  indexRef: string        // 索引号
}

export interface UseD1EndorsementDetailOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: SaveFn
  isReadonly: Ref<boolean>
}

export function useD1EndorsementDetail(options: UseD1EndorsementDetailOptions) {
  return {
    // 贴现检查表行
    discountRows: Ref<EndorsementRow[]>,
    discountTotal: ComputedRef<EndorsementRow>,
    // 背书检查表行
    endorseRows: Ref<EndorsementRow[]>,
    endorseTotal: ComputedRef<EndorsementRow>,
    // 审计说明/结论
    auditNote: Ref<string>,
    auditConclusion: Ref<string>,
    // 操作
    addDiscountRow: () => void,
    removeDiscountRow: (rowId: string) => void,
    addEndorseRow: () => void,
    removeEndorseRow: (rowId: string) => void,
    updateCell: (table: 'discount' | 'endorse', rowId: string, field: string, value: string | number) => void,
    // 从备查簿导入
    importFromMemo: (table: 'discount' | 'endorse', memoRows: MemoRow[]) => void,
  }
}
```

### 5. useD1InterestCheck.ts — 贴息检查 composable

```typescript
export interface InterestCheckRow {
  rowId: string
  rowType: 'dynamic' | 'summary'
  noteType: string        // 票据类型
  faceValue: number       // 票面金额
  faceRate: number        // 票面利率
  issueDate: string       // 出票日期
  maturityDate: string    // 到期日
  maturityValue: number   // 到期日票据价值
  discountDate: string    // 贴现日期
  discountDays: number    // 贴息天数（自动计算）
  discountRate: number    // 贴现率
  calculatedInterest: number // 应计贴现利息（自动计算）
  bookedInterest: number  // 账面贴现利息
  difference: number      // 差异（自动计算）
  remark: string          // 备注
}

export interface UseD1InterestCheckOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: SaveFn
  isReadonly: Ref<boolean>
}

export function useD1InterestCheck(options: UseD1InterestCheckOptions) {
  return {
    // 贴息计算行
    rows: Ref<InterestCheckRow[]>,
    totalRow: ComputedRef<InterestCheckRow>,
    // 差异统计
    totalDifference: ComputedRef<number>,
    differenceCount: ComputedRef<number>,  // 有差异的笔数
    maxDifference: ComputedRef<number>,    // 最大单笔差异
    // 审计说明/结论
    auditNote: Ref<string>,
    auditConclusion: Ref<string>,
    // 操作
    addRow: () => void,
    removeRow: (rowId: string) => void,
    updateCell: (rowId: string, field: string, value: string | number) => void,
  }
}
```

## Data Models

### checklist_responses item_id 命名规范

| Sheet | 前缀 | 示例 |
|-------|------|------|
| D1-6 业务模式 | `D1-bm-` | `D1-bm-basis-rows`(JSON), `D1-bm-qa-matrix`(JSON), `D1-bm-note`, `D1-bm-conclusion` |
| D1-7 备查簿 | `D1-memo-` | `D1-memo-cutoff-date`, `D1-memo-rows`(JSON), `D1-memo-note`, `D1-memo-conclusion` |
| D1-8 贴现背书 | `D1-endorse-` | `D1-endorse-discount-rows`(JSON), `D1-endorse-transfer-rows`(JSON), `D1-endorse-note`, `D1-endorse-conclusion` |
| D1-9 贴息 | `D1-interest-` | `D1-interest-rows`(JSON), `D1-interest-note`, `D1-interest-conclusion` |

### QA矩阵 JSON 存储格式

```json
// item_id: "D1-bm-qa-matrix", remark字段:
{
  "cells": [
    ["Y", "N", ""],   // Q1: 高信用银行=Y, 低信用银行=N, 商业=未填
    ["N", "Y", "Y"],  // Q2
    ["N", "Y", "Y"],  // Q3
    ["N", "Y", "N"]   // Q4
  ]
}
```

### 备查簿行 JSON 存储格式

```json
// item_id: "D1-memo-rows", remark字段:
{
  "bankRows": [
    {
      "rowId": "dynamic-abc123",
      "noteType": "银行承兑汇票",
      "noteNumber": "BA2024001",
      "receivedDate": "2024-03-15",
      "endorser": "ABC公司",
      "issueDate": "2024-03-01",
      "issuer": "XYZ公司",
      "acceptor": "工商银行",
      "amount": 1000000,
      "maturityDate": "2024-09-01",
      "transferDate": "",
      "status": "持有",
      "endorsee": "",
      "discountBank": "",
      "discountInterest": 0,
      "isPledged": "否",
      "isDiscountedEndorsed": "否",
      "beginningBalance": 0,
      "currentReceived": 1000000,
      "currentEndorsed": 0,
      "currentMatured": 0,
      "currentDiscounted": 0,
      "endingBalance": 1000000,
      "unexpiredEndorsedDiscounted": 0,
      "isDerecognized": "",
      "creditRating": "AAA",
      "auditedFinancing": 0,
      "auditedNotes": 1000000,
      "relatedParty": "非关联方",
      "isOverdue": "否",
      "overdueTransferAmount": 0,
      "remarkText": ""
    }
  ],
  "commercialRows": []
}
```

### 跨Sheet取数映射

| 目标位置 | 数据来源 | 取数路径 |
|---------|---------|---------|
| D1-7核对区.明细账.年初余额 | D1-2小计行.priorAudited | allResponses→D1-cat-rows→parse→sum(priorAudited) |
| D1-7核对区.明细账.本期增加 | D1-2小计行.currentIncrease | allResponses→D1-cat-rows→parse→sum(currentIncrease) |
| D1-7核对区.明细账.本期减少 | D1-2小计行.currentDecrease | allResponses→D1-cat-rows→parse→sum(currentDecrease) |
| D1-7核对区.明细账.期末余额 | D1-2小计行.currentAudited | allResponses→D1-cat-rows→parse→sum(currentAudited) |
| D1-8贴现表(从备查簿导入) | D1-7备查簿.status="已贴现" | allResponses→D1-memo-rows→filter(status=贴现) |
| D1-8背书表(从备查簿导入) | D1-7备查簿.status="已背书" | allResponses→D1-memo-rows→filter(status=背书) |
| D1-6判定结果→D1-1列报分类 | D1-6 QA矩阵判定 | allResponses→D1-bm-qa-matrix→determineBusinessMode |

### QA矩阵IF公式实现逻辑

源模板公式 R21: `=IF(AND(B17="是",B18="否"),"属于以收取合同现金流量为目标的业务模式","...")`

前端实现（`determineBusinessMode`函数）：

```typescript
export function determineBusinessMode(
  q1: 'Y' | 'N' | '', q2: 'Y' | 'N' | '', q3: 'Y' | 'N' | '', q4: 'Y' | 'N' | ''
): string {
  if (q1 === 'Y' && q2 === 'N') {
    return '属于以收取合同现金流量为目标的业务模式'
  }
  if (q1 === 'Y' && q2 === 'Y' && q4 === 'Y') {
    return '属于以收取合同现金流量和出售金融资产为目标的业务模式'
  }
  if (q1 === 'N' || (q2 === 'Y' && q4 === 'N')) {
    return '其他业务模式（以公允价值计量且其变动计入当期损益）'
  }
  return '' // 未完全填写
}

export function determineReportItem(businessMode: string): string {
  if (businessMode.includes('收取合同现金流量为目标')) {
    return '应收票据'
  }
  if (businessMode.includes('收取合同现金流量和出售金融资产')) {
    return '应收款项融资'
  }
  if (businessMode.includes('其他业务模式')) {
    return '以公允价值计量且其变动计入当期损益的金融资产'
  }
  return ''
}
```

## Correctness Properties

### Property 1: QA矩阵业务模式判定正确性

*For any* 4元组 (Q1, Q2, Q3, Q4)，其中各值为 'Y'|'N'|''，`determineBusinessMode` 的返回值应满足：
- Q1='Y' ∧ Q2='N' → "以收取合同现金流量为目标"
- Q1='Y' ∧ Q2='Y' ∧ Q4='Y' → "以收取合同现金流量和出售金融资产为目标"
- Q1='N' ∨ (Q2='Y' ∧ Q4='N') → "其他业务模式"
- 其余情况 → ''

**Validates: Requirements 2.4, 2.5, 2.6**

### Property 2: 列报项目判定与业务模式映射一致性

*For any* 业务模式字符串（determineBusinessMode的返回值），`determineReportItem` 返回的列报项目应与业务模式一一对应且无遗漏。

**Validates: Requirements 2.7**

### Property 3: 贴息天数计算正确性

*For any* (到期日, 贴现日) 对，其中贴现日 ≤ 到期日，`calcDiscountDays` 返回值应等于两日期之间的自然天数差。

**Validates: Requirements 10.4**

### Property 4: 应计贴现利息公式正确性（P×R×D/360）

*For any* 三元组 (票面金额P, 贴现率R, 贴息天数D)，其中P≥0, 0≤R≤1, D≥0，`calcDiscountInterest(P, R, D)` 的返回值应等于 `P × R × D / 360`。

**Validates: Requirements 10.5**

### Property 5: 贴息差异计算正确性

*For any* (应计贴现利息, 账面贴现利息) 对，`calcInterestDifference` 返回值应等于 `应计 - 账面`。

**Validates: Requirements 10.6**

### Property 6: 备查簿核对区差异等于备查簿减明细账

*For any* (备查簿各列SUM, D1-2对应列) 数据对，核对区差异行每列应等于 `备查簿合计 - 明细账值`。

**Validates: Requirements 5.1, 5.2**

### Property 7: 合计行恒等于明细行之和

*For any* 明细行列表（D1-7/D1-8/D1-9均适用），合计行的每个数值列应等于对应列所有明细行值的SUM。

**Validates: Requirements 4.7, 7.3, 8.3, 10.8**

### Property 8: 动态行添加保持结构不变量

*For any* 当前行列表（长度N），执行 addRow() 后行列表长度应为 N+1，且新行位于合计行之前，新行所有数值字段为0/空。

**Validates: Requirements 4.8, 7.2, 8.2, 10.3**

### Property 9: 动态行序列化Round-Trip

*For any* 有效的动态行JSON数组（MemoRow[]/EndorsementRow[]/InterestCheckRow[]），将其 JSON.stringify 序列化后再 JSON.parse 反序列化，结果应与原数组深度相等。

**Validates: Requirements 13.7, 13.8, 13.9**

### Property 10: 从备查簿导入状态筛选正确性

*For any* MemoRow[] 列表和筛选状态 'already_discounted'|'already_endorsed'，`importFromMemo` 后的结果行应仅包含对应状态的票据，且数量等于源列表中该状态行的数量。

**Validates: Requirements 17.1, 17.2**

### Property 11: D1-7 SUMIFS统计正确性

*For any* 备查簿行列表，贴现统计总额应等于 `status="已贴现"` 行的金额之和；背书统计总额应等于 `status="已背书"` 行的金额之和。

**Validates: Requirements 5.6**

### Property 12: 贴息差异高亮判定

*For any* 差异数值 d，当 d≠0 时应标记红色高亮；当 d===0 时不标记。

**Validates: Requirements 10.7**

## Error Handling

| 场景 | 处理方式 |
|------|---------|
| 跨sheet D1-2数据加载失败 | 核对区明细账行显示"-"占位符 + 黄色三角警告图标 |
| QA矩阵未完全填写 | 判定结果显示"请完成所有问题的回答"灰色提示文字 |
| 贴息日期输入异常（贴现日>到期日） | 贴息天数显示为0 + 橙色警告tooltip |
| checklist_responses API 失败 | ElMessage.warning提示；保留本地已有数据 |
| 导入xlsx格式不匹配 | 返回400 + 错误列名列表；前端ElMessage.error展示 |
| 导入xlsx行数超限(>500行) | 后端截断 + 返回警告摘要 |
| 备查簿JSON解析失败 | 回退空数组 + ElMessage.warning |
| OnlyOffice健康检查失败 | 禁用"在线编辑"选项 + tooltip说明 |
| 从备查簿导入时D1-7数据为空 | ElMessage.info提示"备查簿暂无数据，请先在D1-7中录入" |
| 金额列输入非数字 | parseNum安全降级为0 |

## Testing Strategy

### 单元测试（vitest）

- useD1FormulaEngine.ts 新增贴息纯函数：边界值（0天/0金额/最大值）、日期解析
- QA矩阵判定逻辑：全部8种有效组合 + 部分填写 + 空矩阵
- 各composable的computed逻辑：初始状态、添加/删除行后状态
- 跨sheet取数：D1-2数据变更→核对区自动刷新
- 从备查簿导入：筛选逻辑+字段映射
- SUMIFS统计逻辑

### Property-Based Tests（fast-check）

每个correctness property对应一个PBT测试，最少100次迭代。

| Property | 测试文件 | 生成器 |
|----------|---------|--------|
| P1 QA矩阵判定 | `useD1BusinessMode.spec.ts` | `fc.oneof('Y','N','')` × 4 |
| P2 列报项目映射 | `useD1BusinessMode.spec.ts` | 先生成QA→determineBusinessMode→determineReportItem |
| P3 贴息天数 | `useD1FormulaEngine.spec.ts` | 自定义日期对生成器（贴现日≤到期日） |
| P4 贴息公式P×R×D/360 | `useD1FormulaEngine.spec.ts` | `fc.float({min:0,max:1e9})` × P + `fc.float({min:0,max:1})` × R + `fc.integer({min:0,max:365})` × D |
| P5 贴息差异 | `useD1FormulaEngine.spec.ts` | `fc.float` × 2 |
| P6 核对区差异 | `useD1MemoReconciliation.spec.ts` | 自定义备查簿SUM+D1-2值生成器 |
| P7 合计行SUM | `useD1FormulaEngine.spec.ts` | `fc.array(fc.float, {minLength:1, maxLength:30})` |
| P8 动态行添加 | `useD1MemoReconciliation.spec.ts` | `fc.array(MemoRow生成器)` |
| P9 Round-trip | `useD1MemoReconciliation.spec.ts` | 自定义 MemoRow[] JSON 生成器 |
| P10 备查簿导入筛选 | `useD1EndorsementDetail.spec.ts` | `fc.array(MemoRow)` + `fc.oneof('已贴现','已背书')` |
| P11 SUMIFS统计 | `useD1MemoReconciliation.spec.ts` | `fc.array(MemoRow)` 含随机status |
| P12 差异高亮判定 | `useD1InterestCheck.spec.ts` | `fc.float` |

### 后端集成测试（hypothesis）

- 导入导出round-trip：生成随机行数据→export→import→验证等价
- D1-7宽表模板格式校验：31列名匹配验证

### 测试配置

```typescript
// fast-check 配置
fc.assert(fc.property(...), { numRuns: 100 })
```
