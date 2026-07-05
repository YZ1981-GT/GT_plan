/**
 * useG4MainAdjudication 单元测试 — G4-1审定表公式链 + G4-3借贷平衡校验
 *
 * Spec: .kiro/specs/g4-bond-investment-main/ Task 5.5
 * 验证：
 *   1. 三层结构小计汇总正确性
 *   2. 借方余额公式链完整性
 *   3. G4-3 借贷平衡→回写 G4-1 流程
 * Requirements: 3.3~3.6, 6.2, 6.5
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import { useG4MainAdjudication } from '../useG4MainAdjudication'
import { useG4MainAdjustment } from '../useG4MainAdjustment'
import type { ChecklistResponse } from '../useF1FormData'
import {
  calcDebitBalance,
  calcAdjustedAmount,
  calcAmortizedCost,
  isDebitCreditBalanced,
} from '@/composables/useG4MainFormulaEngine'

// ═══ Mock ElMessageBox（G4-3 动态行需要） ═══
vi.mock('element-plus', () => ({
  ElMessageBox: { prompt: vi.fn() },
}))

// ═══ 辅助函数 ═══

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
  return { adj, allResponses }
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

// ═══ 1. 三层结构小计汇总正确性 ═══

describe('G4-1审定表 — 三层结构小计汇总', () => {
  it('原值组小计 = 单项计提 + 按组合计提', () => {
    const rows = JSON.stringify([
      {
        rowKey: 'ov-individual',
        label: '单项计提',
        openingUnadjusted: 5000000,
        openingAJE: 0,
        openingRJE: 0,
        periodDebit: 1000000,
        periodCredit: 0,
        closingAJE: 0,
        closingRJE: 0,
        reasonAnalysis: '',
        indexRef: '',
      },
      {
        rowKey: 'ov-portfolio',
        label: '按组合计提',
        openingUnadjusted: 3000000,
        openingAJE: 200000,
        openingRJE: 0,
        periodDebit: 500000,
        periodCredit: 100000,
        closingAJE: 0,
        closingRJE: 0,
        reasonAnalysis: '',
        indexRef: '',
      },
    ])
    const { adj } = setupAdjudication({ 'G4-1-adj-groups-original-value': rows })

    const subtotal = adj.originalValueSubtotal.value
    // 单项: 期初审定 = 5000000, 期末审定 = 5000000 + 1000000 - 0 = 6000000
    // 组合: 期初审定 = 3000000 + 200000 = 3200000, 期末未审 = 3200000 + 500000 - 100000 = 3600000
    expect(subtotal.openingAdjusted).toBe(5000000 + 3200000)    // 8200000
    expect(subtotal.closingAdjusted).toBe(6000000 + 3600000)    // 9600000
  })

  it('减值组小计 = 单项计提 + 按组合计提', () => {
    const rows = JSON.stringify([
      {
        rowKey: 'imp-individual',
        label: '单项计提',
        openingUnadjusted: 100000,
        openingAJE: 0,
        openingRJE: 0,
        periodDebit: 50000,
        periodCredit: 0,
        closingAJE: 0,
        closingRJE: 0,
        reasonAnalysis: '',
        indexRef: '',
      },
      {
        rowKey: 'imp-portfolio',
        label: '按组合计提',
        openingUnadjusted: 200000,
        openingAJE: 0,
        openingRJE: 0,
        periodDebit: 30000,
        periodCredit: 10000,
        closingAJE: 0,
        closingRJE: 0,
        reasonAnalysis: '',
        indexRef: '',
      },
    ])
    const { adj } = setupAdjudication({ 'G4-1-adj-groups-impairment': rows })

    const subtotal = adj.impairmentSubtotal.value
    // 单项: 期初审定 = 100000, 期末审定 = 100000 + 50000 - 0 = 150000
    // 组合: 期初审定 = 200000, 期末未审 = 200000 + 30000 - 10000 = 220000
    expect(subtotal.openingAdjusted).toBe(100000 + 200000)   // 300000
    expect(subtotal.closingAdjusted).toBe(150000 + 220000)   // 370000
  })

  it('摊余成本 = 原值小计 - 减值小计', () => {
    const ovRows = JSON.stringify([
      {
        rowKey: 'ov-individual',
        label: '单项计提',
        openingUnadjusted: 10000000,
        openingAJE: 0,
        openingRJE: 0,
        periodDebit: 2000000,
        periodCredit: 500000,
        closingAJE: 0,
        closingRJE: 0,
        reasonAnalysis: '',
        indexRef: '',
      },
    ])
    const impRows = JSON.stringify([
      {
        rowKey: 'imp-individual',
        label: '单项计提',
        openingUnadjusted: 500000,
        openingAJE: 0,
        openingRJE: 0,
        periodDebit: 100000,
        periodCredit: 0,
        closingAJE: 0,
        closingRJE: 0,
        reasonAnalysis: '',
        indexRef: '',
      },
    ])
    const { adj } = setupAdjudication({
      'G4-1-adj-groups-original-value': ovRows,
      'G4-1-adj-groups-impairment': impRows,
    })

    const amortized = adj.amortizedCostRow.value
    // 原值期初审定 = 10000000, 期末审定 = 10000000 + 2000000 - 500000 = 11500000
    // 减值期初审定 = 500000, 期末审定 = 500000 + 100000 = 600000
    // 摊余成本期初 = 10000000 - 500000 = 9500000
    // 摊余成本期末 = 11500000 - 600000 = 10900000
    expect(amortized.openingAdjusted).toBe(9500000)
    expect(amortized.closingAdjusted).toBe(10900000)
    expect(amortized.changeAmount).toBe(10900000 - 9500000)   // 1400000
  })
})

// ═══ 2. 借方余额公式链完整性 ═══

describe('G4-1审定表 — 借方余额公式链', () => {
  it('期初审定 = 期初未审 + 期初AJE + 期初RJE', () => {
    const rows = JSON.stringify([
      {
        rowKey: 'ov-individual',
        label: '单项计提',
        openingUnadjusted: 8000000,
        openingAJE: 500000,
        openingRJE: -200000,
        periodDebit: 0,
        periodCredit: 0,
        closingAJE: 0,
        closingRJE: 0,
        reasonAnalysis: '',
        indexRef: '',
      },
    ])
    const { adj } = setupAdjudication({ 'G4-1-adj-groups-original-value': rows })
    const row = adj.originalValueRows.value[0]

    // 直接验证公式
    expect(row.openingAdjusted).toBe(8000000 + 500000 + (-200000))  // 8300000
    expect(row.openingAdjusted).toBe(calcAdjustedAmount(8000000, 500000, -200000))
  })

  it('期末未审 = 期初审定 + 借方发生额 - 贷方发生额（借方科目）', () => {
    const rows = JSON.stringify([
      {
        rowKey: 'ov-individual',
        label: '单项计提',
        openingUnadjusted: 5000000,
        openingAJE: 0,
        openingRJE: 0,
        periodDebit: 3000000,
        periodCredit: 1000000,
        closingAJE: 0,
        closingRJE: 0,
        reasonAnalysis: '',
        indexRef: '',
      },
    ])
    const { adj } = setupAdjudication({ 'G4-1-adj-groups-original-value': rows })
    const row = adj.originalValueRows.value[0]

    // 期初审定 = 5000000
    // 期末未审 = 5000000 + 3000000 - 1000000 = 7000000
    expect(row.closingUnadjusted).toBe(7000000)
    expect(row.closingUnadjusted).toBe(calcDebitBalance(5000000, 3000000, 1000000))
  })

  it('期末审定 = 期末未审 + 期末AJE + 期末RJE', () => {
    const rows = JSON.stringify([
      {
        rowKey: 'ov-individual',
        label: '单项计提',
        openingUnadjusted: 5000000,
        openingAJE: 0,
        openingRJE: 0,
        periodDebit: 2000000,
        periodCredit: 500000,
        closingAJE: 300000,
        closingRJE: -100000,
        reasonAnalysis: '',
        indexRef: '',
      },
    ])
    const { adj } = setupAdjudication({ 'G4-1-adj-groups-original-value': rows })
    const row = adj.originalValueRows.value[0]

    // 期末未审 = 5000000 + 2000000 - 500000 = 6500000
    // 期末审定 = 6500000 + 300000 + (-100000) = 6700000
    expect(row.closingUnadjusted).toBe(6500000)
    expect(row.closingAdjusted).toBe(6700000)
    expect(row.closingAdjusted).toBe(calcAdjustedAmount(6500000, 300000, -100000))
  })

  it('完整公式链联测：opening_adjusted → closing_unadjusted → closing_adjusted', () => {
    const rows = JSON.stringify([
      {
        rowKey: 'ov-individual',
        label: '单项计提',
        openingUnadjusted: 10000000,
        openingAJE: 1000000,
        openingRJE: -500000,
        periodDebit: 4000000,
        periodCredit: 1500000,
        closingAJE: 600000,
        closingRJE: -200000,
        reasonAnalysis: '',
        indexRef: '',
      },
    ])
    const { adj } = setupAdjudication({ 'G4-1-adj-groups-original-value': rows })
    const row = adj.originalValueRows.value[0]

    // Step 1: 期初审定 = 10000000 + 1000000 + (-500000) = 10500000
    const expectedOpeningAdj = calcAdjustedAmount(10000000, 1000000, -500000)
    expect(row.openingAdjusted).toBe(expectedOpeningAdj)
    expect(row.openingAdjusted).toBe(10500000)

    // Step 2: 期末未审 = 10500000 + 4000000 - 1500000 = 13000000
    const expectedClosingUnadj = calcDebitBalance(expectedOpeningAdj, 4000000, 1500000)
    expect(row.closingUnadjusted).toBe(expectedClosingUnadj)
    expect(row.closingUnadjusted).toBe(13000000)

    // Step 3: 期末审定 = 13000000 + 600000 + (-200000) = 13400000
    const expectedClosingAdj = calcAdjustedAmount(expectedClosingUnadj, 600000, -200000)
    expect(row.closingAdjusted).toBe(expectedClosingAdj)
    expect(row.closingAdjusted).toBe(13400000)
  })

  it('摊余成本 = 原值小计审定 - 减值小计审定（calcAmortizedCost）', () => {
    // 验证公式函数直接调用
    const originalSubtotal = 15000000
    const impairmentSubtotal = 800000
    expect(calcAmortizedCost(originalSubtotal, impairmentSubtotal)).toBe(14200000)
  })
})

// ═══ 3. G4-3借贷平衡校验 ═══

describe('G4-3调整分录 — 借贷平衡校验', () => {
  it('借贷相等 → isBalanced = true', () => {
    const entries = JSON.stringify([
      {
        id: 'e1', seq: 1, entryType: 'AJE', date: '2024-12-31',
        summary: '确认利息收入', accountCode: '1501', accountName: '债权投资——成本',
        debitAmount: 500000, creditAmount: 0, preparedBy: '张三', remark: '',
      },
      {
        id: 'e2', seq: 2, entryType: 'AJE', date: '2024-12-31',
        summary: '确认利息收入', accountCode: '6011', accountName: '利息收入',
        debitAmount: 0, creditAmount: 500000, preparedBy: '张三', remark: '',
      },
    ])
    const { adjustment } = setupAdjustment({ 'G4-3-rows': entries })

    expect(adjustment.totalDebits.value).toBe(500000)
    expect(adjustment.totalCredits.value).toBe(500000)
    expect(adjustment.isBalanced.value).toBe(true)
    expect(adjustment.balanceDiff.value).toBe(0)
  })

  it('借贷不等 → isBalanced = false，差额正确', () => {
    const entries = JSON.stringify([
      {
        id: 'e1', seq: 1, entryType: 'AJE', date: '2024-12-31',
        summary: '调整减值', accountCode: '1502', accountName: '债权投资减值准备',
        debitAmount: 300000, creditAmount: 0, preparedBy: '李四', remark: '',
      },
      {
        id: 'e2', seq: 2, entryType: 'AJE', date: '2024-12-31',
        summary: '调整减值', accountCode: '6011', accountName: '利息收入',
        debitAmount: 0, creditAmount: 250000, preparedBy: '李四', remark: '',
      },
    ])
    const { adjustment } = setupAdjustment({ 'G4-3-rows': entries })

    expect(adjustment.totalDebits.value).toBe(300000)
    expect(adjustment.totalCredits.value).toBe(250000)
    expect(adjustment.isBalanced.value).toBe(false)
    expect(adjustment.balanceDiff.value).toBe(50000)
  })

  it('多分录借贷平衡 — 复杂场景', () => {
    const entries = JSON.stringify([
      {
        id: 'e1', seq: 1, entryType: 'AJE', date: '2024-12-31',
        summary: '利息调整', accountCode: '1501', accountName: '债权投资——成本',
        debitAmount: 1000000, creditAmount: 0, preparedBy: '王五', remark: '',
      },
      {
        id: 'e2', seq: 2, entryType: 'AJE', date: '2024-12-31',
        summary: '利息调整', accountCode: '150101', accountName: '债权投资——利息调整',
        debitAmount: 200000, creditAmount: 0, preparedBy: '王五', remark: '',
      },
      {
        id: 'e3', seq: 3, entryType: 'AJE', date: '2024-12-31',
        summary: '利息调整', accountCode: '1012', accountName: '银行存款',
        debitAmount: 0, creditAmount: 800000, preparedBy: '王五', remark: '',
      },
      {
        id: 'e4', seq: 4, entryType: 'AJE', date: '2024-12-31',
        summary: '利息调整', accountCode: '6011', accountName: '利息收入',
        debitAmount: 0, creditAmount: 400000, preparedBy: '王五', remark: '',
      },
    ])
    const { adjustment } = setupAdjustment({ 'G4-3-rows': entries })

    // 借方合计 = 1000000 + 200000 = 1200000
    // 贷方合计 = 800000 + 400000 = 1200000
    expect(adjustment.totalDebits.value).toBe(1200000)
    expect(adjustment.totalCredits.value).toBe(1200000)
    expect(adjustment.isBalanced.value).toBe(true)
  })

  it('isDebitCreditBalanced容忍0.01以内误差', () => {
    // 直接验证公式函数
    expect(isDebitCreditBalanced([100.005], [100.001])).toBe(true)   // 差0.004 < 0.01
    expect(isDebitCreditBalanced([100.00], [100.02])).toBe(false)    // 差0.02 >= 0.01
  })
})

// ═══ 4. G4-3回写G4-1流程 ═══

describe('G4-3 → G4-1 回写聚合', () => {
  it('aggregateForWriteback 按科目汇总 AJE 净额', () => {
    const entries = JSON.stringify([
      {
        id: 'e1', seq: 1, entryType: 'AJE', date: '2024-12-31',
        summary: '调整', accountCode: '1501', accountName: '债权投资——成本',
        debitAmount: 500000, creditAmount: 0, preparedBy: '张三', remark: '',
      },
      {
        id: 'e2', seq: 2, entryType: 'AJE', date: '2024-12-31',
        summary: '调整', accountCode: '1501', accountName: '债权投资——成本',
        debitAmount: 200000, creditAmount: 0, preparedBy: '张三', remark: '',
      },
      {
        id: 'e3', seq: 3, entryType: 'AJE', date: '2024-12-31',
        summary: '调整', accountCode: '6011', accountName: '利息收入',
        debitAmount: 0, creditAmount: 700000, preparedBy: '张三', remark: '',
      },
    ])
    const { adjustment } = setupAdjustment({ 'G4-3-rows': entries })

    const summaries = adjustment.aggregateForWriteback()
    // 科目1501: AJE借方 500000 + 200000 - AJE贷方 0 = +700000
    const acc1501 = summaries.find((s) => s.accountCode === '1501')!
    expect(acc1501.ajeNet).toBe(700000)
    expect(acc1501.rjeNet).toBe(0)

    // 科目6011: AJE借方 0 - AJE贷方 700000 = -700000
    const acc6011 = summaries.find((s) => s.accountCode === '6011')!
    expect(acc6011.ajeNet).toBe(-700000)
    expect(acc6011.rjeNet).toBe(0)
  })

  it('aggregateForWriteback 区分 AJE 与 RJE', () => {
    const entries = JSON.stringify([
      {
        id: 'e1', seq: 1, entryType: 'AJE', date: '2024-12-31',
        summary: 'AJE调整', accountCode: '1501', accountName: '债权投资',
        debitAmount: 300000, creditAmount: 0, preparedBy: '张三', remark: '',
      },
      {
        id: 'e2', seq: 2, entryType: 'RJE', date: '2024-12-31',
        summary: 'RJE重分类', accountCode: '1501', accountName: '债权投资',
        debitAmount: 0, creditAmount: 100000, preparedBy: '张三', remark: '',
      },
      {
        id: 'e3', seq: 3, entryType: 'AJE', date: '2024-12-31',
        summary: '对应', accountCode: '6011', accountName: '利息收入',
        debitAmount: 0, creditAmount: 300000, preparedBy: '张三', remark: '',
      },
      {
        id: 'e4', seq: 4, entryType: 'RJE', date: '2024-12-31',
        summary: '对应', accountCode: '6011', accountName: '利息收入',
        debitAmount: 100000, creditAmount: 0, preparedBy: '张三', remark: '',
      },
    ])
    const { adjustment } = setupAdjustment({ 'G4-3-rows': entries })

    const summaries = adjustment.aggregateForWriteback()
    const acc1501 = summaries.find((s) => s.accountCode === '1501')!
    // AJE: 300000 - 0 = 300000
    expect(acc1501.ajeNet).toBe(300000)
    // RJE: 0 - 100000 = -100000
    expect(acc1501.rjeNet).toBe(-100000)

    const acc6011 = summaries.find((s) => s.accountCode === '6011')!
    // AJE: 0 - 300000 = -300000
    expect(acc6011.ajeNet).toBe(-300000)
    // RJE: 100000 - 0 = 100000
    expect(acc6011.rjeNet).toBe(100000)
  })

  it('saveAndWriteback 调用 onWritebackG4_1 callback', () => {
    const entries = JSON.stringify([
      {
        id: 'e1', seq: 1, entryType: 'AJE', date: '2024-12-31',
        summary: '测试', accountCode: '1501', accountName: '债权投资',
        debitAmount: 1000000, creditAmount: 0, preparedBy: '测试', remark: '',
      },
      {
        id: 'e2', seq: 2, entryType: 'AJE', date: '2024-12-31',
        summary: '测试', accountCode: '6011', accountName: '利息收入',
        debitAmount: 0, creditAmount: 1000000, preparedBy: '测试', remark: '',
      },
    ])
    const writeback = vi.fn()
    const { adjustment } = setupAdjustment({ 'G4-3-rows': entries }, writeback)

    adjustment.saveAndWriteback()

    expect(writeback).toHaveBeenCalledTimes(1)
    const arg = writeback.mock.calls[0][0]
    expect(arg).toHaveLength(2)
    expect(arg.find((s: any) => s.accountCode === '1501').ajeNet).toBe(1000000)
    expect(arg.find((s: any) => s.accountCode === '6011').ajeNet).toBe(-1000000)
  })

  it('空金额行不参与汇总', () => {
    const entries = JSON.stringify([
      {
        id: 'e1', seq: 1, entryType: 'AJE', date: '',
        summary: '空行', accountCode: '1501', accountName: '债权投资',
        debitAmount: 0, creditAmount: 0, preparedBy: '', remark: '',
      },
      {
        id: 'e2', seq: 2, entryType: 'AJE', date: '2024-12-31',
        summary: '有值', accountCode: '1501', accountName: '债权投资',
        debitAmount: 200000, creditAmount: 0, preparedBy: '张三', remark: '',
      },
    ])
    const { adjustment } = setupAdjustment({ 'G4-3-rows': entries })

    const summaries = adjustment.aggregateForWriteback()
    // 仅 e2 参与汇总
    expect(summaries).toHaveLength(1)
    expect(summaries[0].accountCode).toBe('1501')
    expect(summaries[0].ajeNet).toBe(200000)
  })
})
