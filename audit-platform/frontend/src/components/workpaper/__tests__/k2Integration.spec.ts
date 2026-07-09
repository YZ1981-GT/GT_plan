/**
 * K2 Integration Test — 合同成本→摊销测算→交叉验证 + 审定回写
 *
 * Spec: .kiro/specs/k2-other-current-assets/
 * Task: 7.2
 * Requirements: 4.4, 5.5, 2.5
 *
 * 验证 K2 多个 composable 联动：
 * 1. 合同成本K2-4 → 摊销测算K2-5 联动
 * 2. 交叉验证（adjudicationVsDetail / contractCostVsAmort）
 * 3. 审定表 subtotalRow + writebackTB(1231)
 * 4. Formula chain correctness（期初→借方→贷方→期末 + 未审→AJE→RJE→审定）
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, nextTick } from 'vue'

// ─── Mock eventBus ───────────────────────────────────────────────────────────

const emitSpy = vi.fn()
vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    emit: (...args: any[]) => emitSpy(...args),
    on: vi.fn(),
    off: vi.fn(),
  },
}))

// ─── Mock API ────────────────────────────────────────────────────────────────

const mockPut = vi.fn().mockResolvedValue({ data: { code: 200 } })
const mockGet = vi.fn().mockResolvedValue({ data: [] })

vi.mock('@/services/apiProxy', () => ({
  api: {
    put: (...args: any[]) => mockPut(...args),
    get: (...args: any[]) => mockGet(...args),
  },
}))

// ─── Mock element-plus ───────────────────────────────────────────────────────

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
  ElMessageBox: { confirm: vi.fn().mockResolvedValue(true) },
}))

// ─── Import composables under test ──────────────────────────────────────────

import { useK2Adjudication } from '../composables/useK2Adjudication'
import { useK2CrossSheet } from '../composables/useK2CrossSheet'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcTriangleReconciliation,
  calcSubtotal,
} from '../composables/useK2FormulaEngine'
import {
  calcStraightLineAmort,
  calcProgressAmort,
  calcAmortizedBalance,
  calcAmortVariance,
} from '../composables/useK2AmortizationEngine'

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** 构建 allResponses Map 辅助函数 */
function buildResponseMap(entries: Record<string, string | number>): Map<string, any> {
  const map = new Map<string, any>()
  for (const [key, val] of Object.entries(entries)) {
    map.set(key, { item_id: key, remark: String(val), conclusion: null })
  }
  return map
}

// ══════════════════════════════════════════════════════════════════════════════
// Test 1: 合同成本 → 摊销测算联动
// Requirements: 4.4, 5.5
// ══════════════════════════════════════════════════════════════════════════════

describe('K2 Integration: 合同成本K2-4 → 摊销测算K2-5 联动', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('3个合同的取得成本经直线法摊销后，摊余成本计算正确', () => {
    // Setup: 3个合同的取得成本明细
    const contracts = [
      { cost: 120000, totalPeriods: 24, currentPeriods: 6 },   // 合同A
      { cost: 360000, totalPeriods: 36, currentPeriods: 12 },  // 合同B
      { cost: 50000,  totalPeriods: 12, currentPeriods: 3 },   // 合同C
    ]

    // K2-5 摊销引擎计算
    const results = contracts.map(c => {
      const amort = calcStraightLineAmort(c.cost, c.totalPeriods, c.currentPeriods)
      const balance = calcAmortizedBalance(c.cost, amort)
      return { amort, balance }
    })

    // 合同A: 120000/24*6 = 30000, 摊余=120000-30000=90000
    expect(results[0].amort).toBeCloseTo(30000, 2)
    expect(results[0].balance).toBeCloseTo(90000, 2)

    // 合同B: 360000/36*12 = 120000, 摊余=360000-120000=240000
    expect(results[1].amort).toBeCloseTo(120000, 2)
    expect(results[1].balance).toBeCloseTo(240000, 2)

    // 合同C: 50000/12*3 = 12500, 摊余=50000-12500=37500
    expect(results[2].amort).toBeCloseTo(12500, 2)
    expect(results[2].balance).toBeCloseTo(37500, 2)
  })

  it('进度法摊销正确计算各合同', () => {
    const contracts = [
      { cost: 200000, currentProgress: 0.45, priorProgress: 0.30 },
      { cost: 150000, currentProgress: 0.80, priorProgress: 0.60 },
      { cost: 80000,  currentProgress: 0.25, priorProgress: 0.10 },
    ]

    const results = contracts.map(c => {
      const amort = calcProgressAmort(c.cost, c.currentProgress, c.priorProgress)
      return { amort }
    })

    // 合同A: 200000 × (0.45 - 0.30) = 30000
    expect(results[0].amort).toBeCloseTo(30000, 2)
    // 合同B: 150000 × (0.80 - 0.60) = 30000
    expect(results[1].amort).toBeCloseTo(30000, 2)
    // 合同C: 80000 × (0.25 - 0.10) = 12000
    expect(results[2].amort).toBeCloseTo(12000, 2)
  })

  it('交叉验证 contractCostVsAmort: K2-4企业摊销 vs K2-5测算摊销 一致', () => {
    // Setup: K2-4 企业摊销合计 = K2-5 测算摊销合计 → isMatch=true
    const responses = buildResponseMap({
      'K2-4-amort-total': 162500,       // 企业实际摊销合计
      'K2-5-calculated-amort-total': 162500,  // 测算摊销合计（一致）
    })

    const allResponses = ref(responses)
    const { contractCostVsAmort } = useK2CrossSheet(allResponses)

    expect(contractCostVsAmort.value.diff).toBeCloseTo(0, 2)
    expect(contractCostVsAmort.value.isMatch).toBe(true)
  })

  it('交叉验证 contractCostVsAmort: K2-4 vs K2-5 存在差异 → isMatch=false', () => {
    // Setup: 企业多摊销了500元
    const responses = buildResponseMap({
      'K2-4-amort-total': 163000,       // 企业实际摊销合计
      'K2-5-calculated-amort-total': 162500,  // 测算摊销合计
    })

    const allResponses = ref(responses)
    const { contractCostVsAmort } = useK2CrossSheet(allResponses)

    expect(contractCostVsAmort.value.diff).toBeCloseTo(500, 2)
    expect(contractCostVsAmort.value.isMatch).toBe(false)
  })

  it('摊销差异计算: calcAmortVariance(测算, 企业) 正值=企业少摊', () => {
    // 测算应摊销30000，企业实际只摊了28000
    const variance = calcAmortVariance(30000, 28000)
    expect(variance).toBe(2000)  // 正值→企业少摊

    // 企业多摊的情况
    const variance2 = calcAmortVariance(30000, 32000)
    expect(variance2).toBe(-2000)  // 负值→企业多摊
  })
})

// ══════════════════════════════════════════════════════════════════════════════
// Test 2: 交叉验证 (cross-sheet)
// Requirements: 2.5
// ══════════════════════════════════════════════════════════════════════════════

describe('K2 Integration: 交叉验证 adjudicationVsDetail', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('K2-1审定合计 = K2-2明细合计 → isMatch=true, diff≈0', () => {
    const responses = buildResponseMap({
      'K2-1-end-balance-total': 850000,
      'K2-2-end-total': 850000,
    })

    const allResponses = ref(responses)
    const { adjudicationVsDetail } = useK2CrossSheet(allResponses)

    expect(adjudicationVsDetail.value.diff).toBeCloseTo(0, 2)
    expect(adjudicationVsDetail.value.isMatch).toBe(true)
  })

  it('K2-1审定合计 ≠ K2-2明细合计 → isMatch=false, diff正确', () => {
    const responses = buildResponseMap({
      'K2-1-end-balance-total': 850000,
      'K2-2-end-total': 845000,  // 差5000
    })

    const allResponses = ref(responses)
    const { adjudicationVsDetail } = useK2CrossSheet(allResponses)

    expect(adjudicationVsDetail.value.diff).toBeCloseTo(5000, 2)
    expect(adjudicationVsDetail.value.isMatch).toBe(false)
  })

  it('微小差异 < 0.01 视为匹配（分以内精度）', () => {
    const responses = buildResponseMap({
      'K2-1-end-balance-total': 850000.005,
      'K2-2-end-total': 850000.001,
    })

    const allResponses = ref(responses)
    const { adjudicationVsDetail } = useK2CrossSheet(allResponses)

    expect(Math.abs(adjudicationVsDetail.value.diff)).toBeLessThan(0.01)
    expect(adjudicationVsDetail.value.isMatch).toBe(true)
  })

  it('allResponses为空时 → diff=0, isMatch=true（两边都是0）', () => {
    const responses = new Map<string, any>()
    const allResponses = ref(responses)
    const { adjudicationVsDetail } = useK2CrossSheet(allResponses)

    expect(adjudicationVsDetail.value.diff).toBe(0)
    expect(adjudicationVsDetail.value.isMatch).toBe(true)
  })
})

// ══════════════════════════════════════════════════════════════════════════════
// Test 3: 审定回写
// Requirements: 2.5, 2.6
// ══════════════════════════════════════════════════════════════════════════════

describe('K2 Integration: 审定表subtotalRow + writebackTB(1231)', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('subtotalRow 正确汇总8个明细行', () => {
    // Setup: 8个明细项（合同取得成本/预付款项/待摊费用/待抵扣税额/合同资产/押金/应收转让/其他）
    const entries: Record<string, number> = {
      'K2-1-contract-cost-begin': 100000,
      'K2-1-contract-cost-debit': 20000,
      'K2-1-contract-cost-credit': 5000,
      'K2-1-contract-cost-unadj': 115000,
      'K2-1-contract-cost-aje': 2000,
      'K2-1-contract-cost-rje': -1000,

      'K2-1-prepayment-begin': 50000,
      'K2-1-prepayment-debit': 10000,
      'K2-1-prepayment-credit': 8000,
      'K2-1-prepayment-unadj': 52000,
      'K2-1-prepayment-aje': 0,
      'K2-1-prepayment-rje': 0,

      'K2-1-deferred-expense-begin': 30000,
      'K2-1-deferred-expense-debit': 5000,
      'K2-1-deferred-expense-credit': 10000,
      'K2-1-deferred-expense-unadj': 25000,
      'K2-1-deferred-expense-aje': 0,
      'K2-1-deferred-expense-rje': 0,
    }

    const responses = buildResponseMap(entries)
    const allResponses = ref(responses)
    const saveFn = vi.fn()
    const { subtotalRow, rows } = useK2Adjudication(allResponses, { onSave: saveFn })

    // 3个有值，其余5个为0
    // subtotalRow.begin = 100000 + 50000 + 30000 = 180000
    expect(subtotalRow.value.begin).toBe(180000)
    // subtotalRow.debit = 20000 + 10000 + 5000 = 35000
    expect(subtotalRow.value.debit).toBe(35000)
    // subtotalRow.credit = 5000 + 8000 + 10000 = 23000
    expect(subtotalRow.value.credit).toBe(23000)
    // subtotalRow.end = calcAssetEndBalance(180000, 35000, 23000) = 192000
    expect(subtotalRow.value.end).toBe(192000)
    // subtotalRow.unadjusted = 115000 + 52000 + 25000 = 192000
    expect(subtotalRow.value.unadjusted).toBe(192000)
    // subtotalRow.aje = 2000 + 0 + 0 = 2000
    expect(subtotalRow.value.aje).toBe(2000)
    // subtotalRow.rje = -1000 + 0 + 0 = -1000
    expect(subtotalRow.value.rje).toBe(-1000)
    // subtotalRow.audited = calcAuditedAmount(192000, 2000, -1000) = 193000
    expect(subtotalRow.value.audited).toBe(193000)
  })

  it('writebackTB 调用正确端点并发布 EventBus', async () => {
    const { useK2FormData } = await import('../composables/useK2FormData')
    const formData = useK2FormData(ref('wp-k2-001'), ref('proj-001'))

    await formData.writebackTB(193000)

    // 验证 API 调用
    expect(mockPut).toHaveBeenCalledTimes(1)
    expect(mockPut).toHaveBeenCalledWith(
      '/api/projects/proj-001/trial-balance/writeback',
      { account_code: '1231', audited_amount: 193000 },
    )

    // 验证 EventBus 发布
    expect(emitSpy).toHaveBeenCalledTimes(1)
    expect(emitSpy).toHaveBeenCalledWith(
      'substantive:adjudicated',
      expect.objectContaining({
        accountCode: '1231',
        auditedAmount: 193000,
        wpCode: 'K2',
      }),
    )
  })

  it('writebackTB payload 包含 timestamp', async () => {
    const { useK2FormData } = await import('../composables/useK2FormData')
    const formData = useK2FormData(ref('wp-k2-002'), ref('proj-002'))

    const before = Date.now()
    await formData.writebackTB(500000)
    const after = Date.now()

    const payload = emitSpy.mock.calls[0][1]
    expect(payload.timestamp).toBeGreaterThanOrEqual(before)
    expect(payload.timestamp).toBeLessThanOrEqual(after)
  })

  it('writebackTB 失败时不发布 EventBus', async () => {
    mockPut.mockRejectedValueOnce(new Error('network error'))

    const { useK2FormData } = await import('../composables/useK2FormData')
    const formData = useK2FormData(ref('wp-k2-003'), ref('proj-003'))

    await formData.writebackTB(100000)

    expect(emitSpy).not.toHaveBeenCalled()
  })
})

// ══════════════════════════════════════════════════════════════════════════════
// Test 4: Formula chain correctness
// Requirements: 2.2-2.3, 8.1-8.2
// ══════════════════════════════════════════════════════════════════════════════

describe('K2 Integration: Formula chain correctness', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('完整公式链：期初→借方→贷方→期末(资产类) + 未审→AJE→RJE→审定', () => {
    // 给定具体输入值
    const begin = 500000
    const debit = 80000
    const credit = 30000
    const unadj = 550000
    const aje = 5000
    const rje = -2000

    // Step 1: 期末 = 期初 + 借方 - 贷方（资产类1231）
    const end = calcAssetEndBalance(begin, debit, credit)
    expect(end).toBe(550000) // 500000 + 80000 - 30000

    // Step 2: 审定 = 未审 + AJE + RJE
    const audited = calcAuditedAmount(unadj, aje, rje)
    expect(audited).toBe(553000) // 550000 + 5000 + (-2000)

    // Step 3: 三角勾稽校验
    // 增加 = 借方, 减少 = 贷方 for 资产类
    const reconciliationDiff = calcTriangleReconciliation(begin, debit, credit, end)
    expect(reconciliationDiff).toBe(0) // 期末 - (期初 + 增加 - 减少) = 0 ✓
  })

  it('三角勾稽：end ≠ begin + inc - dec → diff ≠ 0', () => {
    const begin = 100000
    const inc = 20000
    const dec = 5000
    const wrongEnd = 120000 // 正确应为115000

    const diff = calcTriangleReconciliation(begin, inc, dec, wrongEnd)
    expect(diff).toBe(5000) // 120000 - (100000 + 20000 - 5000) = 5000 ≠ 0
  })

  it('合计行恒等：subtotal([a,b,c]) === a+b+c', () => {
    const values = [100000, 50000, 30000, 25000, 15000, 8000, 5000, 2000]
    const total = calcSubtotal(values)
    expect(total).toBe(235000)
  })

  it('审定表每行公式计算与合计一致性', () => {
    // 模拟3个明细行
    const rowsData = [
      { begin: 100000, debit: 20000, credit: 5000, unadj: 115000, aje: 2000, rje: -1000 },
      { begin: 50000, debit: 10000, credit: 8000, unadj: 52000, aje: 0, rje: 0 },
      { begin: 30000, debit: 5000, credit: 10000, unadj: 25000, aje: 500, rje: -500 },
    ]

    // 每行计算
    const computed = rowsData.map(r => ({
      end: calcAssetEndBalance(r.begin, r.debit, r.credit),
      audited: calcAuditedAmount(r.unadj, r.aje, r.rje),
    }))

    // 行级验证
    expect(computed[0].end).toBe(115000)   // 100000+20000-5000
    expect(computed[0].audited).toBe(116000) // 115000+2000-1000
    expect(computed[1].end).toBe(52000)    // 50000+10000-8000
    expect(computed[1].audited).toBe(52000)  // 52000+0+0
    expect(computed[2].end).toBe(25000)    // 30000+5000-10000
    expect(computed[2].audited).toBe(25000)  // 25000+500-500

    // 合计行验证
    const subtotalEnd = calcSubtotal(computed.map(r => r.end))
    const subtotalAudited = calcSubtotal(computed.map(r => r.audited))

    expect(subtotalEnd).toBe(192000)     // 115000+52000+25000
    expect(subtotalAudited).toBe(193000) // 116000+52000+25000

    // 三角勾稽：合计行level
    const totalBegin = calcSubtotal(rowsData.map(r => r.begin))
    const totalDebit = calcSubtotal(rowsData.map(r => r.debit))
    const totalCredit = calcSubtotal(rowsData.map(r => r.credit))
    const reconDiff = calcTriangleReconciliation(totalBegin, totalDebit, totalCredit, subtotalEnd)
    expect(reconDiff).toBe(0) // 三角勾稽平衡 ✓
  })

  it('摊销链完整性：合同成本→摊销→摊余→差异', () => {
    const cost = 240000
    const totalPeriods = 24
    const currentPeriods = 8
    const bookedAmort = 78000 // 企业账面已摊销（偏差）

    // Step 1: 测算摊销
    const calculatedAmort = calcStraightLineAmort(cost, totalPeriods, currentPeriods)
    expect(calculatedAmort).toBeCloseTo(80000, 2) // 240000/24*8

    // Step 2: 摊余成本
    const amortizedBalance = calcAmortizedBalance(cost, calculatedAmort)
    expect(amortizedBalance).toBeCloseTo(160000, 2) // 240000-80000

    // Step 3: 差异
    const variance = calcAmortVariance(calculatedAmort, bookedAmort)
    expect(variance).toBeCloseTo(2000, 2) // 80000-78000 (企业少摊2000)
  })
})
