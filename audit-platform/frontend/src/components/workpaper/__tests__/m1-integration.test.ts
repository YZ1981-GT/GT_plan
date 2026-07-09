/**
 * 集成测试 — M1 应付股利（利润）
 *
 * 覆盖：
 * 1. declareVsM6: M6利润分配→M1股利核对一致性
 * 2. adjudicationVsDetail: M1-1审定表 vs M1-2明细表交叉验证
 * 3. 外币折算完整流程: FX conversion + 多币种汇总
 * 4. 负债类方向验证: 期末=期初+贷方(宣告)-借方(支付) + 多股东合计
 *
 * Spec: .kiro/specs/m1-dividends-payable/ Task 7.2
 * Requirements: 4.1-4.5, 5.1-5.6
 *
 * 科目：2232 应付股利（贷方/负债类！期末=期初+贷方-借方）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { useM1CrossSheet } from '../composables/useM1CrossSheet'
import type { ChecklistResponse } from '../composables/useM1FormData'
import {
  calcAuditedAmount,
  calcSubtotal,
  calcLiabilityEndBalance,
} from '../composables/useM1FormulaEngine'
import { calcFxConverted, calcFxDiff } from '../composables/useM1FxEngine'
import { calcDeclaredDividend, calcDeclareDiff } from '../composables/useM1DividendEngine'

// Mock eventBus
vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    emit: vi.fn(),
    on: vi.fn(),
    off: vi.fn(),
  },
}))

import { eventBus } from '@/utils/eventBus'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function createResponses(entries: [string, string | null][]) {
  const map = new Map<string, ChecklistResponse>()
  for (const [itemId, remark] of entries) {
    map.set(itemId, { item_id: itemId, conclusion: null, remark })
  }
  return ref(map)
}

// ═══════════════════════════════════════════════════════════════════════════════
// Section 1: M6→M1 股利核对 (declareVsM6)
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — M6→M1 股利核对 declareVsM6 (Req 5.1-5.6)', () => {
  it('M6 profit-distributed 事件触发后，declareVsM6 反映新数据', async () => {
    // 捕获EventBus订阅的handler
    let capturedHandler: Function | null = null
    ;(eventBus.on as any).mockImplementation((event: string, handler: Function) => {
      if (event === 'm6:profit-distributed') capturedHandler = handler
    })

    const responses = createResponses([
      ['M1-M1-5-declared-total', '500000'], // M1-5测算宣告合计=500000
    ])

    const { declareVsM6 } = useM1CrossSheet(responses)

    // 初始状态：M6数据为0（未收到事件），diff = 500000 - 0 = 500000
    expect(declareVsM6.value.diff).toBe(500000)
    expect(declareVsM6.value.isConsistent).toBe(false) // |500000| > 100

    // 模拟M6利润分配事件
    expect(capturedHandler).not.toBeNull()
    capturedHandler!({ distributedDividend: 500000, wpCode: 'M6' })
    await nextTick()

    // 事件触发后：diff = 500000 - 500000 = 0
    expect(declareVsM6.value.diff).toBe(0)
    expect(declareVsM6.value.isConsistent).toBe(true)
  })

  it('M1-5 declared total === M6 amount → isConsistent=true', () => {
    ;(eventBus.on as any).mockImplementation(() => {})

    const responses = createResponses([
      ['M1-M1-5-declared-total', '1000000'],
      ['M1-cross-m6-profit-distributed', '1000000'], // 持久化的M6数据
    ])

    const { declareVsM6 } = useM1CrossSheet(responses)
    // 从持久化恢复M6数据后: diff = 1000000 - 1000000 = 0
    expect(declareVsM6.value.diff).toBe(0)
    expect(declareVsM6.value.isConsistent).toBe(true)
  })

  it('显著差异(>100) → isConsistent=false', () => {
    ;(eventBus.on as any).mockImplementation(() => {})

    const responses = createResponses([
      ['M1-M1-5-declared-total', '800000'],
      ['M1-cross-m6-profit-distributed', '600000'], // M6=600000
    ])

    const { declareVsM6 } = useM1CrossSheet(responses)
    // diff = 800000 - 600000 = 200000
    expect(declareVsM6.value.diff).toBe(200000)
    expect(declareVsM6.value.isConsistent).toBe(false) // |200000| > 100
  })

  it('微小差异(≤100)允许四舍五入误差 → isConsistent=true', () => {
    ;(eventBus.on as any).mockImplementation(() => {})

    const responses = createResponses([
      ['M1-M1-5-declared-total', '1000050'], // 多50元
      ['M1-cross-m6-profit-distributed', '1000000'],
    ])

    const { declareVsM6 } = useM1CrossSheet(responses)
    // diff = 1000050 - 1000000 = 50，|50| < 100 → consistent
    expect(declareVsM6.value.diff).toBe(50)
    expect(declareVsM6.value.isConsistent).toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 2: 审定表 vs 明细表 交叉验证 (adjudicationVsDetail)
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — adjudicationVsDetail M1-1 vs M1-2 (Req 2.5, 3.5)', () => {
  beforeEach(() => {
    ;(eventBus.on as any).mockImplementation(() => {})
  })

  it('M1-1 total === M1-2 total → isMatch=true', () => {
    const responses = createResponses([
      ['M1-M1-1-total-end-balance', '5000000'], // 审定表合计
      ['M1-M1-2-total-end', '5000000'],          // 明细表合计
    ])

    const { adjudicationVsDetail } = useM1CrossSheet(responses)
    expect(adjudicationVsDetail.value.isMatch).toBe(true)
    expect(adjudicationVsDetail.value.diff).toBe(0)
  })

  it('差异>1 → isMatch=false', () => {
    const responses = createResponses([
      ['M1-M1-1-total-end-balance', '5000000'],
      ['M1-M1-2-total-end', '4998000'], // 差2000
    ])

    const { adjudicationVsDetail } = useM1CrossSheet(responses)
    expect(adjudicationVsDetail.value.isMatch).toBe(false)
    expect(adjudicationVsDetail.value.diff).toBe(2000)
  })

  it('差异<1(四舍五入容差) → isMatch=true', () => {
    const responses = createResponses([
      ['M1-M1-1-total-end-balance', '3000000.50'],
      ['M1-M1-2-total-end', '3000000.30'], // 差0.2 < 1
    ])

    const { adjudicationVsDetail } = useM1CrossSheet(responses)
    expect(adjudicationVsDetail.value.isMatch).toBe(true)
    expect(Math.abs(adjudicationVsDetail.value.diff)).toBeLessThan(1)
  })

  it('明细行累加降级: 无汇总行时遍历row*-end', () => {
    const responses = createResponses([
      ['M1-M1-1-total-end-balance', '3000000'],
      // 无 M1-M1-2-total-end，通过 row 累加
      ['M1-M1-2-row1-end', '1000000'],
      ['M1-M1-2-row2-end', '1200000'],
      ['M1-M1-2-row3-end', '800000'],
    ])

    const { adjudicationVsDetail } = useM1CrossSheet(responses)
    // row累加 = 1000000 + 1200000 + 800000 = 3000000
    expect(adjudicationVsDetail.value.isMatch).toBe(true)
    expect(adjudicationVsDetail.value.diff).toBe(0)
  })

  it('两侧都为空 → isMatch=true, diff=0', () => {
    const responses = createResponses([])
    const { adjudicationVsDetail } = useM1CrossSheet(responses)
    expect(adjudicationVsDetail.value.isMatch).toBe(true)
    expect(adjudicationVsDetail.value.diff).toBe(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 3: 外币折算完整流程
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — 外币折算完整流程 (Req 4.1-4.5)', () => {
  it('USD 10000 × 7.25 = 72500, booked 71000, diff = 1500', () => {
    const amount = 10000   // 原币金额 USD
    const rate = 7.25      // 期末汇率
    const booked = 71000   // 账面本位币

    // Step 1: 折算本位币
    const converted = calcFxConverted(amount, rate)
    expect(converted).toBe(72500)

    // Step 2: 汇兑差异
    const diff = calcFxDiff(converted, booked)
    expect(diff).toBe(1500)
  })

  it('多币种汇总正确求和', () => {
    // 多个外币股东应付股利
    const fxItems = [
      { amount: 10000, rate: 7.25, booked: 71000 },   // USD → 72500, diff=1500
      { amount: 5000, rate: 7.78, booked: 38500 },    // HKD → 38900, diff=400
      { amount: 20000, rate: 0.92, booked: 18000 },   // JPY → 18400, diff=400
    ]

    // Step 1: 逐行计算折算
    const convertedAmounts = fxItems.map(item => calcFxConverted(item.amount, item.rate))
    expect(convertedAmounts[0]).toBe(72500)
    expect(convertedAmounts[1]).toBe(38900)
    expect(convertedAmounts[2]).toBeCloseTo(18400, 2)

    // Step 2: 逐行汇兑差异
    const diffs = fxItems.map((item, i) => calcFxDiff(convertedAmounts[i], item.booked))
    expect(diffs[0]).toBe(1500)
    expect(diffs[1]).toBe(400)
    expect(diffs[2]).toBeCloseTo(400, 2)

    // Step 3: 合计汇兑差异
    const totalDiff = calcSubtotal(diffs)
    expect(totalDiff).toBeCloseTo(2300, 0)

    // Step 4: 合计折算本位币
    const totalConverted = calcSubtotal(convertedAmounts)
    expect(totalConverted).toBeCloseTo(129800, 0)
  })

  it('汇率为0 → 折算=0，差异=-booked', () => {
    const converted = calcFxConverted(10000, 0)
    expect(converted).toBe(0)

    const diff = calcFxDiff(converted, 50000)
    expect(diff).toBe(-50000)
  })

  it('原币为0 → 折算=0, 差异=0', () => {
    const converted = calcFxConverted(0, 7.25)
    expect(converted).toBe(0)

    const diff = calcFxDiff(converted, 0)
    expect(diff).toBe(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 4: 负债类方向验证
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — 负债类方向验证 (Req 2.4, 3.2)', () => {
  it('期末=期初+贷方(宣告)-借方(支付)', () => {
    // 某股东：期初欠100万，本期宣告分配200万(贷方增加)，本期支付150万(借方减少)
    const begin = 1_000_000
    const credit = 2_000_000  // 宣告分配（贷方增加）
    const debit = 1_500_000   // 实际支付（借方减少）

    const endBalance = calcLiabilityEndBalance(begin, credit, debit)
    // 期末 = 1000000 + 2000000 - 1500000 = 1500000
    expect(endBalance).toBe(1_500_000)
  })

  it('支付大于宣告+期初 → 期末为负(预付/多付)', () => {
    const begin = 500_000
    const credit = 100_000   // 少量宣告
    const debit = 800_000    // 多付

    const endBalance = calcLiabilityEndBalance(begin, credit, debit)
    // 期末 = 500000 + 100000 - 800000 = -200000 (多付，不常见但计算正确)
    expect(endBalance).toBe(-200_000)
  })

  it('多股东合计验证（多行calcLiabilityEndBalance → calcSubtotal）', () => {
    // 多个股东各自计算期末再汇总
    const shareholders = [
      { name: '股东A', begin: 1_000_000, credit: 500_000, debit: 300_000 },   // end = 1200000
      { name: '股东B', begin: 2_000_000, credit: 800_000, debit: 1_000_000 }, // end = 1800000
      { name: '股东C', begin: 500_000, credit: 200_000, debit: 100_000 },     // end = 600000
      { name: '股东D', begin: 300_000, credit: 0, debit: 300_000 },           // end = 0
    ]

    // 逐股东计算期末
    const endBalances = shareholders.map(s =>
      calcLiabilityEndBalance(s.begin, s.credit, s.debit),
    )
    expect(endBalances[0]).toBe(1_200_000)
    expect(endBalances[1]).toBe(1_800_000)
    expect(endBalances[2]).toBe(600_000)
    expect(endBalances[3]).toBe(0)

    // 合计
    const total = calcSubtotal(endBalances)
    expect(total).toBe(3_600_000)

    // 验证合计也可以先合计各列再计算
    const totalBegin = calcSubtotal(shareholders.map(s => s.begin))
    const totalCredit = calcSubtotal(shareholders.map(s => s.credit))
    const totalDebit = calcSubtotal(shareholders.map(s => s.debit))
    const totalEndFromColumns = calcLiabilityEndBalance(totalBegin, totalCredit, totalDebit)
    // 合计期末 = 3800000 + 1500000 - 1700000 = 3600000
    expect(totalEndFromColumns).toBe(3_600_000)
    expect(totalEndFromColumns).toBe(total) // 两种方式结果一致
  })

  it('仅有期初余额，无本期借贷发生 → 期末=期初', () => {
    const endBalance = calcLiabilityEndBalance(2_000_000, 0, 0)
    expect(endBalance).toBe(2_000_000)
  })

  it('全为0 → 期末=0', () => {
    const endBalance = calcLiabilityEndBalance(0, 0, 0)
    expect(endBalance).toBe(0)
  })

  it('审定数+负债类期末联合: 审定数作为期末再参与勾稽', () => {
    // 未审数通过AJE/RJE调整后得到审定数（期末余额）
    const unadj = 3_000_000
    const aje = 200_000
    const rje = -50_000
    const audited = calcAuditedAmount(unadj, aje, rje) // 3150000

    // 审定数即为期末余额，验证是否满足负债类公式
    const begin = 2_500_000
    const credit = 900_000
    const debit = 250_000
    const expectedEnd = calcLiabilityEndBalance(begin, credit, debit) // 3150000

    expect(audited).toBe(expectedEnd)
    expect(audited).toBe(3_150_000)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 5: 股利测算引擎 + M6联动完整流程
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — 股利测算引擎完整流程 (Req 5.3-5.4)', () => {
  it('可供分配利润×分配比例=应宣告股利, 与账面比较得差异', () => {
    const profit = 10_000_000  // M6来源的可供分配利润
    const ratio = 0.3          // 分配比例30%
    const booked = 2_800_000   // 账面宣告

    // Step 1: 计算应宣告
    const declared = calcDeclaredDividend(profit, ratio)
    expect(declared).toBe(3_000_000) // 10000000 × 0.3 = 3000000

    // Step 2: 宣告差异
    const diff = calcDeclareDiff(declared, booked)
    expect(diff).toBe(200_000) // 3000000 - 2800000 = 200000 (少分配20万)
  })

  it('多股东测算: 各股东分配比例不同, 合计与M6一致', () => {
    const distributableProfit = 5_000_000 // M6可供分配利润

    const shareholders = [
      { name: '股东A', ratio: 0.51, booked: 2_550_000 },
      { name: '股东B', ratio: 0.30, booked: 1_500_000 },
      { name: '股东C', ratio: 0.19, booked: 950_000 },
    ]

    // 逐股东计算应宣告
    const declaredAmounts = shareholders.map(s =>
      calcDeclaredDividend(distributableProfit, s.ratio),
    )
    expect(declaredAmounts[0]).toBe(2_550_000)
    expect(declaredAmounts[1]).toBe(1_500_000)
    expect(declaredAmounts[2]).toBe(950_000)

    // 合计应宣告
    const totalDeclared = calcSubtotal(declaredAmounts)
    expect(totalDeclared).toBe(5_000_000) // 比例合计100% → 合计=利润

    // 逐股东差异
    const diffs = shareholders.map((s, i) => calcDeclareDiff(declaredAmounts[i], s.booked))
    expect(diffs[0]).toBe(0)
    expect(diffs[1]).toBe(0)
    expect(diffs[2]).toBe(0)
  })

  it('分配比例为0 → 应宣告=0', () => {
    const declared = calcDeclaredDividend(10_000_000, 0)
    expect(declared).toBe(0)
  })
})
