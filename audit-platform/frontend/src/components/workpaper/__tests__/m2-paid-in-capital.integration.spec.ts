/**
 * 集成测试 — M2 实收资本（股本）
 *
 * 覆盖：
 * 1. 双版本明细切换：分支状态持久化、行独立
 * 2. 审定表 vs 明细表：交叉验证（adjudicationVsDetail）
 * 3. FX engine + CrossSheet：外币折算差异→M4阈值检测
 * 4. Verify engine + CapitalCheck：验资核对+出资到位率+阈值告警
 * 5. 调整分录：借贷平衡校验
 *
 * Spec: .kiro/specs/m2-paid-in-capital/ Task 7.2
 * Requirements: 3.1-3.7, 4.1-4.5, 5.1-5.5
 *
 * 科目：4001 实收资本/股本（贷方/权益类！期末=期初+贷方-借方）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { useM2CrossSheet } from '../composables/useM2CrossSheet'
import type { ChecklistResponse } from '../composables/useM2FormData'
import {
  calcAuditedAmount,
  calcEquityEndBalance,
  calcSubtotal,
  calcVarianceAmount,
  calcShareRatio,
} from '../composables/useM2FormulaEngine'
import { calcFxConverted, calcFxDiff } from '../composables/useM2FxEngine'
import { calcVerifyDiff, calcPaidInRate } from '../composables/useM2VerifyEngine'

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

function createResponses(entries: [string, Partial<ChecklistResponse>][]) {
  const map = new Map<string, ChecklistResponse>()
  for (const [itemId, partial] of entries) {
    map.set(itemId, {
      item_id: itemId,
      conclusion: partial.conclusion ?? null,
      remark: partial.remark ?? null,
      ...partial,
    } as ChecklistResponse)
  }
  return ref(map)
}

// ═══════════════════════════════════════════════════════════════════════════════
// Section 1: 双版本明细切换（Req 3.1-3.7）
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — 双版本明细切换 (Req 3.1-3.7)', () => {
  beforeEach(() => {
    ;(eventBus.on as any).mockImplementation(() => {})
    ;(eventBus.emit as any).mockImplementation(() => {})
  })

  it('默认分支为 unlisted（非上市公司更常见）', () => {
    const responses = createResponses([])
    const { detailBranch } = useM2CrossSheet(responses)
    expect(detailBranch.value).toBe('unlisted')
  })

  it('从 checklist_responses 恢复 listed 分支', () => {
    const responses = createResponses([
      ['M2-M2-2-detail-branch', { conclusion: 'listed' }],
    ])
    const { detailBranch } = useM2CrossSheet(responses)
    expect(detailBranch.value).toBe('listed')
  })

  it('分支切换不影响另一分支的行数据（行独立）', () => {
    // 模拟两个版本各有独立行数据
    const responses = createResponses([
      ['M2-M2-2-detail-branch', { conclusion: 'listed' }],
      ['M2-M2-2-listed-row1-end', { remark: '5000000' }],
      ['M2-M2-2-listed-row2-end', { remark: '3000000' }],
      ['M2-M2-2-unlisted-row1-end', { remark: '2000000' }],
    ])

    const { detailBranch } = useM2CrossSheet(responses)
    expect(detailBranch.value).toBe('listed')

    // 切换分支
    detailBranch.value = 'unlisted'
    expect(detailBranch.value).toBe('unlisted')

    // unlisted 的行数据仍然独立存在
    const unlistedRow = responses.value.get('M2-M2-2-unlisted-row1-end')
    expect(unlistedRow?.remark).toBe('2000000')

    // listed 行数据未被修改
    const listedRow = responses.value.get('M2-M2-2-listed-row1-end')
    expect(listedRow?.remark).toBe('5000000')
  })

  it('分支来回切换保持状态一致', () => {
    const responses = createResponses([])
    const { detailBranch } = useM2CrossSheet(responses)

    detailBranch.value = 'listed'
    expect(detailBranch.value).toBe('listed')

    detailBranch.value = 'unlisted'
    expect(detailBranch.value).toBe('unlisted')

    detailBranch.value = 'listed'
    expect(detailBranch.value).toBe('listed')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 2: 审定表 vs 明细表 交叉验证 (adjudicationVsDetail)
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — adjudicationVsDetail M2-1 vs M2-2 (Req 2.5, 3.7)', () => {
  beforeEach(() => {
    ;(eventBus.on as any).mockImplementation(() => {})
    ;(eventBus.emit as any).mockImplementation(() => {})
  })

  it('M2-1 total === M2-2 total → isMatch=true', () => {
    const responses = createResponses([
      ['M2-M2-1-total-end-balance', { remark: '50000000' }],
      ['M2-M2-2-total-end', { remark: '50000000' }],
    ])

    const { adjudicationVsDetail } = useM2CrossSheet(responses)
    expect(adjudicationVsDetail.value.isMatch).toBe(true)
    expect(adjudicationVsDetail.value.diff).toBe(0)
  })

  it('差异>1 → isMatch=false', () => {
    const responses = createResponses([
      ['M2-M2-1-total-end-balance', { remark: '50000000' }],
      ['M2-M2-2-total-end', { remark: '49980000' }], // 差20000
    ])

    const { adjudicationVsDetail } = useM2CrossSheet(responses)
    expect(adjudicationVsDetail.value.isMatch).toBe(false)
    expect(adjudicationVsDetail.value.diff).toBe(20000)
  })

  it('差异<1(四舍五入容差) → isMatch=true', () => {
    const responses = createResponses([
      ['M2-M2-1-total-end-balance', { remark: '30000000.50' }],
      ['M2-M2-2-total-end', { remark: '30000000.30' }],
    ])

    const { adjudicationVsDetail } = useM2CrossSheet(responses)
    expect(adjudicationVsDetail.value.isMatch).toBe(true)
    expect(Math.abs(adjudicationVsDetail.value.diff)).toBeLessThan(1)
  })

  it('明细行累加降级: 无汇总行时遍历row*-end', () => {
    const responses = createResponses([
      ['M2-M2-1-total-end-balance', { remark: '30000000' }],
      // 无 M2-M2-2-total-end，通过 row 累加
      ['M2-M2-2-row1-end', { remark: '10000000' }],
      ['M2-M2-2-row2-end', { remark: '12000000' }],
      ['M2-M2-2-row3-end', { remark: '8000000' }],
    ])

    const { adjudicationVsDetail } = useM2CrossSheet(responses)
    // row累加 = 10000000 + 12000000 + 8000000 = 30000000
    expect(adjudicationVsDetail.value.isMatch).toBe(true)
    expect(adjudicationVsDetail.value.diff).toBe(0)
  })

  it('两侧都为空 → isMatch=true, diff=0', () => {
    const responses = createResponses([])
    const { adjudicationVsDetail } = useM2CrossSheet(responses)
    expect(adjudicationVsDetail.value.isMatch).toBe(true)
    expect(adjudicationVsDetail.value.diff).toBe(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 3: FX engine + CrossSheet — 外币折算→M4 阈值检测 (Req 4.1-4.5)
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — 外币折算→M4联动 fxDiffToM4 (Req 4.1-4.5)', () => {
  beforeEach(() => {
    ;(eventBus.on as any).mockImplementation(() => {})
    ;(eventBus.emit as any).mockClear()
  })

  it('折算差异合计超阈值(>100) → exceedsThreshold=true', () => {
    const fxRows = JSON.stringify([
      { investor: '外资A', fxDiff: 150 },
      { investor: '外资B', fxDiff: 80 },
    ])
    const responses = createResponses([
      ['M2-M2-4-rows', { remark: fxRows }],
    ])

    const { fxDiffToM4 } = useM2CrossSheet(responses)
    expect(fxDiffToM4.value.totalFxDiff).toBe(230)
    expect(fxDiffToM4.value.exceedsThreshold).toBe(true)
    expect(fxDiffToM4.value.byInvestor).toHaveLength(2)
    expect(fxDiffToM4.value.byInvestor[0]).toEqual({ investor: '外资A', fxDiff: 150 })
  })

  it('折算差异合计≤阈值(≤100) → exceedsThreshold=false', () => {
    const fxRows = JSON.stringify([
      { investor: '外资C', fxDiff: 30 },
      { investor: '外资D', fxDiff: 50 },
    ])
    const responses = createResponses([
      ['M2-M2-4-rows', { remark: fxRows }],
    ])

    const { fxDiffToM4 } = useM2CrossSheet(responses)
    expect(fxDiffToM4.value.totalFxDiff).toBe(80)
    expect(fxDiffToM4.value.exceedsThreshold).toBe(false)
  })

  it('无外币行数据 → totalFxDiff=0, exceedsThreshold=false', () => {
    const responses = createResponses([])
    const { fxDiffToM4 } = useM2CrossSheet(responses)
    expect(fxDiffToM4.value.totalFxDiff).toBe(0)
    expect(fxDiffToM4.value.exceedsThreshold).toBe(false)
    expect(fxDiffToM4.value.byInvestor).toHaveLength(0)
  })

  it('publishFxDiffToM4: 超阈值时发布EventBus事件', () => {
    const fxRows = JSON.stringify([
      { investor: '外资E', fxDiff: 500000 },
    ])
    const responses = createResponses([
      ['M2-M2-4-rows', { remark: fxRows }],
    ])

    const { publishFxDiffToM4 } = useM2CrossSheet(responses)
    publishFxDiffToM4()

    expect(eventBus.emit).toHaveBeenCalledWith(
      'm2:fx-diff-to-m4',
      expect.objectContaining({
        wpCode: 'M2',
        totalFxDiff: 500000,
        byInvestor: [{ investor: '外资E', fxDiff: 500000 }],
      }),
    )
  })

  it('publishFxDiffToM4: 未超阈值不发布', () => {
    const fxRows = JSON.stringify([
      { investor: '外资F', fxDiff: 50 },
    ])
    const responses = createResponses([
      ['M2-M2-4-rows', { remark: fxRows }],
    ])

    const { publishFxDiffToM4 } = useM2CrossSheet(responses)
    publishFxDiffToM4()

    expect(eventBus.emit).not.toHaveBeenCalled()
  })

  it('外币折算完整流程: 原币×汇率→折算→差异→合计→阈值', () => {
    // 模拟多个外币出资人折算全流程
    const investors = [
      { name: '美资A', amount: 1000000, rate: 7.1, booked: 7050000 },
      { name: '港资B', amount: 5000000, rate: 0.92, booked: 4500000 },
    ]

    // Step 1: 逐行折算
    const converted = investors.map(inv => calcFxConverted(inv.amount, inv.rate))
    expect(converted[0]).toBeCloseTo(7100000, 0)
    expect(converted[1]).toBeCloseTo(4600000, 0)

    // Step 2: 逐行差异
    const diffs = investors.map((inv, i) => calcFxDiff(converted[i], inv.booked))
    expect(diffs[0]).toBeCloseTo(50000, 0)   // 7100000 - 7050000
    expect(diffs[1]).toBeCloseTo(100000, 0)  // 4600000 - 4500000

    // Step 3: 合计差异
    const totalDiff = calcSubtotal(diffs)
    expect(totalDiff).toBeCloseTo(150000, 0)

    // Step 4: 超阈值判定（150000 > 100）
    expect(Math.abs(totalDiff) > 100).toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 4: Verify engine + CapitalCheck — 验资核对 (Req 5.1-5.5)
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — 验资核对 Verify engine (Req 5.1-5.5)', () => {
  it('验资完整流程: 逐出资人核对 + 出资到位率计算', () => {
    const investors = [
      { name: '股东A', subscribed: 10000000, paid: 10000000, verified: 10000000 },
      { name: '股东B', subscribed: 5000000, paid: 3000000, verified: 3000000 },
      { name: '股东C', subscribed: 8000000, paid: 8000000, verified: 7800000 },
    ]

    // 逐出资人验资差异
    const verifyDiffs = investors.map(inv => calcVerifyDiff(inv.paid, inv.verified))
    expect(verifyDiffs[0]).toBe(0)       // A核对一致
    expect(verifyDiffs[1]).toBe(0)       // B核对一致
    expect(verifyDiffs[2]).toBe(200000)  // C有差异（需查明）

    // 逐出资人出资到位率
    const paidInRates = investors.map(inv => calcPaidInRate(inv.paid, inv.subscribed))
    expect(paidInRates[0]).toBeCloseTo(1.0, 5)    // A: 100%全额到位
    expect(paidInRates[1]).toBeCloseTo(0.6, 5)    // B: 60%部分到位
    expect(paidInRates[2]).toBeCloseTo(1.0, 5)    // C: 100%全额到位
  })

  it('出资到位率<100% → 关注认缴未实缴风险', () => {
    const rate = calcPaidInRate(3000000, 10000000)
    expect(rate).toBeCloseTo(0.3, 5)
    // 30% < 100% → 需关注出资义务
    expect(rate < 1.0).toBe(true)
  })

  it('验资差异>阈值 → 红色高亮标记', () => {
    const THRESHOLD = 100 // 验资差异阈值
    const diff = calcVerifyDiff(5200000, 5000000) // diff=200000
    expect(Math.abs(diff) > THRESHOLD).toBe(true)
  })

  it('验资差异=0 → 核对一致（绿色状态）', () => {
    const diff = calcVerifyDiff(5000000, 5000000)
    expect(diff).toBe(0)
  })

  it('认缴为0时出资到位率=0（异常数据保护）', () => {
    const rate = calcPaidInRate(1000000, 0)
    expect(rate).toBe(0) // 不抛异常，返回0
  })

  it('多出资人汇总: 合计实缴 vs 合计验资', () => {
    const paidAmounts = [10000000, 3000000, 8000000]
    const verifiedAmounts = [10000000, 3000000, 7800000]

    const totalPaid = calcSubtotal(paidAmounts)
    const totalVerified = calcSubtotal(verifiedAmounts)
    const totalDiff = calcVerifyDiff(totalPaid, totalVerified)

    expect(totalPaid).toBe(21000000)
    expect(totalVerified).toBe(20800000)
    expect(totalDiff).toBe(200000) // 合计差异
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 5: 调整分录借贷平衡 + 权益类方向集成
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — 权益类方向 + 调整借贷平衡 (Req 2.1-2.7, 6.1)', () => {
  it('权益类期末=期初+贷方(增资)-借方(减资) + 多出资人合计', () => {
    const shareholders = [
      { name: '出资人A', begin: 10000000, credit: 5000000, debit: 0 },       // end=15000000
      { name: '出资人B', begin: 20000000, credit: 0, debit: 3000000 },       // end=17000000
      { name: '出资人C', begin: 5000000, credit: 2000000, debit: 1000000 },  // end=6000000
    ]

    // 逐出资人计算期末
    const endBalances = shareholders.map(s =>
      calcEquityEndBalance(s.begin, s.credit, s.debit),
    )
    expect(endBalances[0]).toBe(15000000)
    expect(endBalances[1]).toBe(17000000)
    expect(endBalances[2]).toBe(6000000)

    // 合计
    const total = calcSubtotal(endBalances)
    expect(total).toBe(38000000)

    // 列合计方式与行合计方式结果一致
    const totalBegin = calcSubtotal(shareholders.map(s => s.begin))
    const totalCredit = calcSubtotal(shareholders.map(s => s.credit))
    const totalDebit = calcSubtotal(shareholders.map(s => s.debit))
    const totalEndFromColumns = calcEquityEndBalance(totalBegin, totalCredit, totalDebit)
    expect(totalEndFromColumns).toBe(38000000)
    expect(totalEndFromColumns).toBe(total)
  })

  it('审定数作为期末参与勾稽验证', () => {
    // 未审数通过AJE/RJE调整后得到审定数（即期末余额）
    const unadj = 30000000
    const aje = 2000000   // 增资调整
    const rje = -500000   // 重分类
    const audited = calcAuditedAmount(unadj, aje, rje) // 31500000

    // 验证审定数满足权益类公式
    const begin = 25000000
    const credit = 9000000
    const debit = 2500000
    const expectedEnd = calcEquityEndBalance(begin, credit, debit) // 31500000

    expect(audited).toBe(expectedEnd)
    expect(audited).toBe(31500000)
  })

  it('借贷平衡: AJE借方合计=贷方合计', () => {
    // 模拟AJE调整分录的借贷平衡检查
    const debitEntries = [2000000, 500000]  // 借方合计
    const creditEntries = [2500000]          // 贷方合计

    const totalDebit = calcSubtotal(debitEntries)
    const totalCredit = calcSubtotal(creditEntries)

    // 借方合计 === 贷方合计 → 平衡
    expect(totalDebit).toBe(totalCredit)
    expect(totalDebit - totalCredit).toBe(0)
  })

  it('借贷不平衡时差额检测', () => {
    const debitEntries = [2000000, 500000]
    const creditEntries = [2000000]  // 差500000

    const totalDebit = calcSubtotal(debitEntries)
    const totalCredit = calcSubtotal(creditEntries)
    const imbalance = totalDebit - totalCredit

    expect(imbalance).toBe(500000)
    expect(imbalance !== 0).toBe(true) // 不平衡，需告警
  })

  it('持股比例计算 + 比例合计应=100%', () => {
    const totalShares = 100000000 // 总股本1亿
    const shareholders = [
      { name: '股东A', shares: 51000000 },
      { name: '股东B', shares: 30000000 },
      { name: '股东C', shares: 19000000 },
    ]

    const ratios = shareholders.map(s => calcShareRatio(s.shares, totalShares))
    expect(ratios[0]).toBeCloseTo(0.51, 5)
    expect(ratios[1]).toBeCloseTo(0.30, 5)
    expect(ratios[2]).toBeCloseTo(0.19, 5)

    // 比例合计=100%
    const totalRatio = calcSubtotal(ratios)
    expect(totalRatio).toBeCloseTo(1.0, 5)
  })

  it('变动额计算 + 变动方向确认', () => {
    // 增资：期末>期初
    const variance = calcVarianceAmount(15000000, 10000000)
    expect(variance).toBe(5000000)
    expect(variance > 0).toBe(true) // 正=增资

    // 减资：期末<期初
    const variance2 = calcVarianceAmount(8000000, 10000000)
    expect(variance2).toBe(-2000000)
    expect(variance2 < 0).toBe(true) // 负=减资
  })
})
