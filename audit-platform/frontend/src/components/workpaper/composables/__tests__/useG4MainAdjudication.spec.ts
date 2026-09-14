/**
 * useG4MainAdjudication / useG4MainAdjustment — 对齐 Excel 模板后的单元测试
 * G4-1：未审 + 账项调整 = 审定；三层原值/减值/净值
 * G4-3：叙述式调整列 + 回写 G4-1
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { ref } from 'vue'
import { useG4MainAdjudication } from '../useG4MainAdjudication'
import { useG4MainAdjustment } from '../useG4MainAdjustment'
import type { ChecklistResponse } from '../useF1FormData'
import { calcAmortizedCost, isDebitCreditBalanced } from '@/composables/useG4MainFormulaEngine'

vi.mock('element-plus', () => ({
  ElMessageBox: { prompt: vi.fn(), confirm: vi.fn() },
}))

const disposers: Array<() => void> = []
afterEach(() => {
  while (disposers.length) disposers.pop()?.()
})

function setupAdjudication(seed?: Record<string, string>) {
  const map = new Map<string, ChecklistResponse>()
  if (seed) {
    for (const [k, v] of Object.entries(seed)) {
      map.set(k, { item_id: k, conclusion: null, remark: v })
    }
  }
  const allResponses = ref(map)
  const adj = useG4MainAdjudication({
    wpId: ref('wp-g4'),
    projectId: ref('proj-1'),
    allResponses,
    isReadonly: ref(false),
  })
  disposers.push(adj.dispose)
  return { adj, allResponses, dispose: adj.dispose }
}

function setupAdjustment(seed?: Record<string, string>, onWriteback?: (s: any[]) => void) {
  const map = new Map<string, ChecklistResponse>()
  if (seed) {
    for (const [k, v] of Object.entries(seed)) {
      map.set(k, { item_id: k, conclusion: null, remark: v })
    }
  }
  const allResponses = ref(map)
  const adjustment = useG4MainAdjustment({
    allResponses,
    isReadonly: ref(false),
    onWritebackG4_1: onWriteback,
  })
  return { adjustment, allResponses }
}

describe('G4-1审定表 — Excel 三层结构', () => {
  it('原值小计 = 单项 + 组合（未审+账项调整）', () => {
    const store = JSON.stringify({
      'original-individual': {
        openingUnadjusted: 5000000,
        openingAdjustment: 0,
        closingUnadjusted: 6000000,
        closingAdjustment: 0,
      },
      'original-portfolio': {
        openingUnadjusted: 3000000,
        openingAdjustment: 200000,
        closingUnadjusted: 3600000,
        closingAdjustment: 0,
      },
    })
    const { adj } = setupAdjudication({ 'G4-1-rows': store })
    const subtotal = adj.originalValueSubtotal.value
    expect(subtotal.openingAudited).toBe(5000000 + 3200000)
    expect(subtotal.closingAudited).toBe(6000000 + 3600000)
  })

  it('兼容旧 AJE/RJE + 借方贷方迁移', () => {
    const rows = JSON.stringify([
      {
        rowKey: 'ov-individual',
        label: '单项计提',
        openingUnadjusted: 5000000,
        openingAJE: 100000,
        openingRJE: -50000,
        periodDebit: 3000000,
        periodCredit: 1000000,
        closingAJE: 200000,
        closingRJE: 0,
        reasonAnalysis: '',
        indexRef: '',
      },
    ])
    const { adj } = setupAdjudication({ 'G4-1-adj-groups-original-value': rows })
    const row = adj.originalValueRows.value[0]
    // 期初审定 = 5000000 + (100000-50000) = 5050000
    expect(row.openingAudited).toBe(5050000)
    // 期末未审 = 5050000 + 3000000 - 1000000 = 7050000
    expect(row.closingUnadjusted).toBe(7050000)
    // 期末审定 = 7050000 + 200000 = 7250000
    expect(row.closingAudited).toBe(7250000)
  })

  it('净值 = 原值审定 − 减值审定', () => {
    const store = JSON.stringify({
      'original-individual': {
        openingUnadjusted: 10000000,
        openingAdjustment: 0,
        closingUnadjusted: 11500000,
        closingAdjustment: 0,
      },
      'impairment-individual': {
        openingUnadjusted: 500000,
        openingAdjustment: 0,
        closingUnadjusted: 600000,
        closingAdjustment: 0,
      },
    })
    const { adj } = setupAdjudication({ 'G4-1-rows': store })
    const amortized = adj.amortizedCostRow.value
    // 净值合计：原值合计 11500000 - 减值合计 600000（无一年内到期）
    expect(amortized.closingAudited).toBe(10900000)
    expect(calcAmortizedCost(11500000, 600000)).toBe(10900000)
  })

  it('|变动率|>30% 触发原因分析必填', () => {
    const store = JSON.stringify({
      'original-individual': {
        openingUnadjusted: 100,
        openingAdjustment: 0,
        closingUnadjusted: 140,
        closingAdjustment: 0,
        reasonAnalysis: '',
      },
    })
    const { adj } = setupAdjudication({ 'G4-1-rows': store })
    const row = adj.originalValueRows.value[0]
    expect(row.changeRateHighlight).toBe(true)
    expect(row.reasonRequired).toBe(true)
  })
})

describe('G4-1 公式列', () => {
  it('审定 = 未审 + 账项调整', () => {
    const store = JSON.stringify({
      'original-individual': {
        openingUnadjusted: 8000000,
        openingAdjustment: 300000,
        closingUnadjusted: 9000000,
        closingAdjustment: 100000,
      },
    })
    const { adj } = setupAdjudication({ 'G4-1-rows': store })
    const row = adj.originalValueRows.value[0]
    expect(row.openingAudited).toBe(8300000)
    expect(row.closingAudited).toBe(9100000)
    expect(row.changeAmount).toBe(800000)
  })
})

describe('G4-3调整分录 — 模板列 + 借贷平衡', () => {
  it('借贷相等 → isBalanced', () => {
    const entries = JSON.stringify([
      {
        description: '确认利息收入',
        category: '账项调整',
        accountCode: '1501',
        accountName: '债权投资',
        debitAmount: 500000,
        creditAmount: 0,
      },
      {
        description: '确认利息收入',
        category: '账项调整',
        accountCode: '6011',
        accountName: '利息收入',
        debitAmount: 0,
        creditAmount: 500000,
      },
    ])
    const { adjustment } = setupAdjustment({ 'G4-3-rows': entries })
    expect(adjustment.totalDebits.value).toBe(500000)
    expect(adjustment.totalCredits.value).toBe(500000)
    expect(adjustment.isBalanced.value).toBe(true)
    expect(
      isDebitCreditBalanced(
        adjustment.entries.value.map((e) => e.debitAmount),
        adjustment.entries.value.map((e) => e.creditAmount),
      ),
    ).toBe(true)
  })

  it('兼容旧 entryType=AJE 导入', () => {
    const entries = JSON.stringify([
      {
        id: 'e1',
        seq: 1,
        entryType: 'AJE',
        summary: '调整',
        accountCode: '1501',
        debitAmount: 100,
        creditAmount: 0,
      },
      {
        id: 'e2',
        seq: 2,
        entryType: 'AJE',
        summary: '调整',
        accountCode: '6011',
        debitAmount: 0,
        creditAmount: 100,
      },
    ])
    const { adjustment } = setupAdjustment({ 'G4-3-rows': entries })
    expect(adjustment.entries.value[0].category).toBe('账项调整')
    expect(adjustment.isBalanced.value).toBe(true)
  })

  it('saveAndWriteback 回写 G4-1-rows 期末账项调整', () => {
    const entries = JSON.stringify([
      {
        description: '补提成本',
        category: '账项调整',
        accountCode: '1501',
        accountName: '债权投资',
        debitAmount: 100000,
        creditAmount: 0,
      },
      {
        description: '补提成本',
        category: '账项调整',
        accountCode: '6011',
        accountName: '利息收入',
        debitAmount: 0,
        creditAmount: 100000,
      },
    ])
    const { adjustment, allResponses } = setupAdjustment({
      'G4-3-rows': entries,
      'G4-1-rows': JSON.stringify({
        'original-portfolio': {
          openingUnadjusted: 0,
          openingAdjustment: 0,
          closingUnadjusted: 1000000,
          closingAdjustment: 0,
        },
      }),
    })
    expect(adjustment.entries.value.length).toBe(2)
    expect(adjustment.netAjeToG4.value).toBe(100000)
    adjustment.saveAndWriteback()
    const stored = JSON.parse(allResponses.value.get('G4-1-rows')!.remark!)
    expect(stored['original-portfolio'].closingAdjustment).toBe(100000)
  })
})
