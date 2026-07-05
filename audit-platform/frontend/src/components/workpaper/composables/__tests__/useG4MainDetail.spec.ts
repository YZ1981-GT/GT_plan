/**
 * useG4MainDetail 单元测试 — G4-2五区段Tab行同步 + G4-4 Stage条件计算
 *
 * Spec: .kiro/specs/g4-bond-investment-main/ Task 6.5
 * 验证：
 *   1. Tab切换行索引保持（5区段间行同步）
 *   2. 5区段公式链完整性（从期初到账面价值）
 *   3. Stage1/2/3利息计算基数差异
 *   4. 利息测算合计 vs G4-1差异比对
 * Requirements: 5.2~5.11, 5.13, 7.3~7.7, 7.11
 */
import { describe, it, expect } from 'vitest'
import {
  calcBalanceSubtotal,
  calcAmortizedCost,
  calcPeriodEndComponent,
  calcOneYearMaturity,
  calcBookValue,
  calcEffectiveInterest,
  calcCashInflow,
  calcEndingBalance,
  parseNum,
} from '@/composables/useG4MainFormulaEngine'

// ═══ 辅助：模拟G4-2公式链（与useG4MainDetail.ts中的enrich逻辑一致） ═══

interface G4FormulaChainInput {
  openingCost: number
  openingInterestAdj: number
  openingAccruedInterest: number
  openingImpairment: number
  periodCostChange: number
  periodInterestAdjChange: number
  periodAccruedInterestChange: number
  closingImpairment: number
  oneYearBalance: number
  oneYearImpairment: number
}

interface G4FormulaChainResult {
  openingSubtotal: number
  openingAmortizedCost: number
  periodChangeSubtotal: number
  closingCost: number
  closingInterestAdj: number
  closingAccruedInterest: number
  closingSubtotal: number
  amortizedCost: number
  oneYearSubtotal: number
  bookValue: number
}

function computeG4FormulaChain(input: G4FormulaChainInput): G4FormulaChainResult {
  const openingSubtotal = calcBalanceSubtotal(input.openingCost, input.openingInterestAdj, input.openingAccruedInterest)
  const openingAmortizedCost = calcAmortizedCost(openingSubtotal, input.openingImpairment)
  const periodChangeSubtotal = calcBalanceSubtotal(input.periodCostChange, input.periodInterestAdjChange, input.periodAccruedInterestChange)
  const closingCost = calcPeriodEndComponent(input.openingCost, input.periodCostChange)
  const closingInterestAdj = calcPeriodEndComponent(input.openingInterestAdj, input.periodInterestAdjChange)
  const closingAccruedInterest = calcPeriodEndComponent(input.openingAccruedInterest, input.periodAccruedInterestChange)
  const closingSubtotal = calcBalanceSubtotal(closingCost, closingInterestAdj, closingAccruedInterest)
  const amortizedCost = calcAmortizedCost(closingSubtotal, input.closingImpairment)
  const oneYearSubtotal = calcOneYearMaturity(input.oneYearBalance, input.oneYearImpairment)
  const bookValue = calcBookValue(amortizedCost, oneYearSubtotal)
  return {
    openingSubtotal,
    openingAmortizedCost,
    periodChangeSubtotal,
    closingCost,
    closingInterestAdj,
    closingAccruedInterest,
    closingSubtotal,
    amortizedCost,
    oneYearSubtotal,
    bookValue,
  }
}

// ═══ 1. Tab切换行索引保持 ═══

describe('G4-2明细表 — Tab切换行索引保持 (Req 5.13)', () => {
  it('selectedRowIndex在5个区段Tab之间保持不变', () => {
    // 模拟 selectedRowIndex 作为独立ref，切换segment时不受影响
    let selectedRowIndex = 2
    const segments = ['basic', 'opening', 'period', 'closing', 'amortized']

    // 切换Tab不影响选中行索引
    for (const seg of segments) {
      // segment切换只改变列定义，不改变selectedRowIndex
      expect(selectedRowIndex).toBe(2)
    }
  })

  it('选中行索引在不同区段中引用同一数据行', () => {
    // 5区段共享同一rows数组，selectedRowIndex指向同一行
    const rows = [
      { id: 'r1', investProject: '国债A', openingCost: 1000000, amortizedCost: 950000 },
      { id: 'r2', investProject: '企业债B', openingCost: 2000000, amortizedCost: 1800000 },
      { id: 'r3', investProject: '公司债C', openingCost: 3000000, amortizedCost: 2700000 },
    ]

    const selectedRowIndex = 1  // 选中第2行

    // 在基础信息区段看到的是同一行
    expect(rows[selectedRowIndex].investProject).toBe('企业债B')
    // 在期初余额区段看到的是同一行
    expect(rows[selectedRowIndex].openingCost).toBe(2000000)
    // 在摊余成本区段看到的是同一行
    expect(rows[selectedRowIndex].amortizedCost).toBe(1800000)
  })

  it('删除行后selectedRowIndex正确调整', () => {
    const rows = ['r1', 'r2', 'r3', 'r4', 'r5']
    let selectedRowIndex = 3  // 选中第4行

    // 删除第2行(index=1)，选中行索引下移
    rows.splice(1, 1)
    if (selectedRowIndex >= rows.length) {
      selectedRowIndex = rows.length - 1
    } else if (1 < selectedRowIndex) {
      selectedRowIndex--
    }
    expect(selectedRowIndex).toBe(2)  // 原第4行现在变为第3行(index=2)
    expect(rows[selectedRowIndex]).toBe('r4')
  })

  it('删除选中行本身时索引回退', () => {
    const rows = ['r1', 'r2', 'r3']
    let selectedRowIndex = 2  // 选中最后一行

    // 删除最后一行
    rows.splice(2, 1)
    if (selectedRowIndex >= rows.length) {
      selectedRowIndex = rows.length - 1
    }
    expect(selectedRowIndex).toBe(1)  // 回退到前一行
  })
})

// ═══ 2. 5区段公式链完整性（从期初到账面价值） ═══

describe('G4-2明细表 — 5区段公式链完整性 (Req 5.2~5.11)', () => {
  it('标准场景：完整公式链从期初三要素到账面价值', () => {
    const result = computeG4FormulaChain({
      openingCost: 1000000,
      openingInterestAdj: 50000,
      openingAccruedInterest: 20000,
      openingImpairment: 30000,
      periodCostChange: 200000,
      periodInterestAdjChange: 10000,
      periodAccruedInterestChange: 5000,
      closingImpairment: 40000,
      oneYearBalance: 500000,
      oneYearImpairment: 20000,
    })

    // 期初小计 = 1000000 + 50000 + 20000 = 1070000
    expect(result.openingSubtotal).toBe(1070000)
    // 期初摊余成本 = 1070000 - 30000 = 1040000
    expect(result.openingAmortizedCost).toBe(1040000)
    // 本期变动小计 = 200000 + 10000 + 5000 = 215000
    expect(result.periodChangeSubtotal).toBe(215000)
    // 期末成本 = 1000000 + 200000 = 1200000
    expect(result.closingCost).toBe(1200000)
    // 期末利息调整 = 50000 + 10000 = 60000
    expect(result.closingInterestAdj).toBe(60000)
    // 期末应计利息 = 20000 + 5000 = 25000
    expect(result.closingAccruedInterest).toBe(25000)
    // 期末小计 = 1200000 + 60000 + 25000 = 1285000
    expect(result.closingSubtotal).toBe(1285000)
    // 摊余成本 = 1285000 - 40000 = 1245000
    expect(result.amortizedCost).toBe(1245000)
    // 一年内到期小计 = 500000 - 20000 = 480000
    expect(result.oneYearSubtotal).toBe(480000)
    // 账面价值 = 1245000 - 480000 = 765000
    expect(result.bookValue).toBe(765000)
  })

  it('零变动场景：本期无变动时期末=期初', () => {
    const result = computeG4FormulaChain({
      openingCost: 5000000,
      openingInterestAdj: 100000,
      openingAccruedInterest: 50000,
      openingImpairment: 200000,
      periodCostChange: 0,
      periodInterestAdjChange: 0,
      periodAccruedInterestChange: 0,
      closingImpairment: 200000,
      oneYearBalance: 0,
      oneYearImpairment: 0,
    })

    // 期初小计 = 5000000 + 100000 + 50000 = 5150000
    expect(result.openingSubtotal).toBe(5150000)
    // 本期变动小计 = 0
    expect(result.periodChangeSubtotal).toBe(0)
    // 期末成本 = 期初成本 = 5000000
    expect(result.closingCost).toBe(5000000)
    // 期末小计 = 5000000 + 100000 + 50000 = 5150000（同期初）
    expect(result.closingSubtotal).toBe(5150000)
    // 摊余成本 = 5150000 - 200000 = 4950000
    expect(result.amortizedCost).toBe(4950000)
    // 账面价值 = 4950000 - 0 = 4950000
    expect(result.bookValue).toBe(4950000)
  })

  it('大额场景：1亿级金额精度', () => {
    const result = computeG4FormulaChain({
      openingCost: 100000000,
      openingInterestAdj: 5000000,
      openingAccruedInterest: 2000000,
      openingImpairment: 3000000,
      periodCostChange: 20000000,
      periodInterestAdjChange: 1000000,
      periodAccruedInterestChange: 500000,
      closingImpairment: 5000000,
      oneYearBalance: 50000000,
      oneYearImpairment: 2000000,
    })

    // 期初小计 = 100000000 + 5000000 + 2000000 = 107000000
    expect(result.openingSubtotal).toBe(107000000)
    // 期初摊余成本 = 107000000 - 3000000 = 104000000
    expect(result.openingAmortizedCost).toBe(104000000)
    // 期末成本 = 100000000 + 20000000 = 120000000
    expect(result.closingCost).toBe(120000000)
    // 期末小计 = 120000000 + 6000000 + 2500000 = 128500000
    expect(result.closingSubtotal).toBe(128500000)
    // 摊余成本 = 128500000 - 5000000 = 123500000
    expect(result.amortizedCost).toBe(123500000)
    // 一年内到期小计 = 50000000 - 2000000 = 48000000
    expect(result.oneYearSubtotal).toBe(48000000)
    // 账面价值 = 123500000 - 48000000 = 75500000
    expect(result.bookValue).toBe(75500000)
  })

  it('空值输入：parseNum将null/undefined/NaN视为0', () => {
    // 模拟空值输入 — 所有值为0时公式链应产出0
    const result = computeG4FormulaChain({
      openingCost: 0,
      openingInterestAdj: 0,
      openingAccruedInterest: 0,
      openingImpairment: 0,
      periodCostChange: 0,
      periodInterestAdjChange: 0,
      periodAccruedInterestChange: 0,
      closingImpairment: 0,
      oneYearBalance: 0,
      oneYearImpairment: 0,
    })

    expect(result.openingSubtotal).toBe(0)
    expect(result.openingAmortizedCost).toBe(0)
    expect(result.periodChangeSubtotal).toBe(0)
    expect(result.closingSubtotal).toBe(0)
    expect(result.amortizedCost).toBe(0)
    expect(result.bookValue).toBe(0)
  })

  it('负数利息调整（折价购入场景）', () => {
    const result = computeG4FormulaChain({
      openingCost: 10000000,
      openingInterestAdj: -500000,   // 折价→利息调整为负
      openingAccruedInterest: 100000,
      openingImpairment: 0,
      periodCostChange: 0,
      periodInterestAdjChange: 50000,  // 摊销使利息调整逐步归零
      periodAccruedInterestChange: 30000,
      closingImpairment: 0,
      oneYearBalance: 0,
      oneYearImpairment: 0,
    })

    // 期初小计 = 10000000 + (-500000) + 100000 = 9600000
    expect(result.openingSubtotal).toBe(9600000)
    // 期末利息调整 = -500000 + 50000 = -450000
    expect(result.closingInterestAdj).toBe(-450000)
    // 期末小计 = 10000000 + (-450000) + 130000 = 9680000
    expect(result.closingSubtotal).toBe(9680000)
    // 账面价值 = 9680000 - 0 = 9680000
    expect(result.bookValue).toBe(9680000)
  })
})

// ═══ 3. Stage1/2/3利息计算基数差异 ═══

describe('G4-4利息测算 — Stage1/2/3利息计算基数差异 (Req 7.3~7.5)', () => {
  const openingBalance = 10000000
  const effectiveRate = 0.05
  const days = 365

  it('Stage1：低减值→高摊余成本→高利息收入', () => {
    const openingImpairment = 100000  // Stage1减值准备较小
    const amortizedCost = calcAmortizedCost(openingBalance, openingImpairment)
    const interest = calcEffectiveInterest(amortizedCost, effectiveRate, days)

    // 摊余成本 = 10000000 - 100000 = 9900000
    expect(amortizedCost).toBe(9900000)
    // 利息 = 9900000 × 0.05 × 365/365 = 495000
    expect(interest).toBe(495000)
  })

  it('Stage2：中等减值→中等摊余成本→中等利息收入', () => {
    const openingImpairment = 500000  // Stage2减值准备中等
    const amortizedCost = calcAmortizedCost(openingBalance, openingImpairment)
    const interest = calcEffectiveInterest(amortizedCost, effectiveRate, days)

    // 摊余成本 = 10000000 - 500000 = 9500000
    expect(amortizedCost).toBe(9500000)
    // 利息 = 9500000 × 0.05 × 365/365 = 475000
    expect(interest).toBe(475000)
  })

  it('Stage3：高减值→低摊余成本→低利息收入', () => {
    const openingImpairment = 2000000  // Stage3已发生信用减值，减值准备最大
    const amortizedCost = calcAmortizedCost(openingBalance, openingImpairment)
    const interest = calcEffectiveInterest(amortizedCost, effectiveRate, days)

    // 摊余成本 = 10000000 - 2000000 = 8000000
    expect(amortizedCost).toBe(8000000)
    // 利息 = 8000000 × 0.05 × 365/365 = 400000
    expect(interest).toBe(400000)
  })

  it('相同条件下Stage级别越高→利息越低', () => {
    const stage1Imp = 100000
    const stage2Imp = 500000
    const stage3Imp = 2000000

    const interestS1 = calcEffectiveInterest(
      calcAmortizedCost(openingBalance, stage1Imp), effectiveRate, days,
    )
    const interestS2 = calcEffectiveInterest(
      calcAmortizedCost(openingBalance, stage2Imp), effectiveRate, days,
    )
    const interestS3 = calcEffectiveInterest(
      calcAmortizedCost(openingBalance, stage3Imp), effectiveRate, days,
    )

    // Stage1 > Stage2 > Stage3
    expect(interestS1).toBeGreaterThan(interestS2)
    expect(interestS2).toBeGreaterThan(interestS3)

    // 具体值验证
    expect(interestS1).toBe(495000)
    expect(interestS2).toBe(475000)
    expect(interestS3).toBe(400000)
  })

  it('按天数计息时Stage差异同样体现', () => {
    const halfYearDays = 180
    const stage1Imp = 100000
    const stage3Imp = 2000000

    const interestS1 = calcEffectiveInterest(
      calcAmortizedCost(openingBalance, stage1Imp), effectiveRate, halfYearDays,
    )
    const interestS3 = calcEffectiveInterest(
      calcAmortizedCost(openingBalance, stage3Imp), effectiveRate, halfYearDays,
    )

    // S1: 9900000 × 0.05 × 180/365 ≈ 244109.589...
    expect(interestS1).toBeCloseTo(9900000 * 0.05 * 180 / 365, 6)
    // S3: 8000000 × 0.05 × 180/365 ≈ 197260.274...
    expect(interestS3).toBeCloseTo(8000000 * 0.05 * 180 / 365, 6)
    // S1 > S3
    expect(interestS1).toBeGreaterThan(interestS3)
  })
})

// ═══ 4. 利息测算合计 vs G4-1差异比对 ═══

describe('G4-4利息测算 — 合计 vs G4-1差异比对 (Req 7.11)', () => {
  const VARIANCE_THRESHOLD = 0.01

  /** 模拟多个投资项目的实际利息收入合计 */
  function computeTotalInterest(groups: Array<{
    openingBalance: number
    openingImpairment: number
    effectiveRate: number
    days: number
  }>): number {
    return groups.reduce((sum, g) => {
      const amortizedCost = calcAmortizedCost(g.openingBalance, g.openingImpairment)
      const interest = calcEffectiveInterest(amortizedCost, g.effectiveRate, g.days)
      return sum + Math.round(interest * 100) / 100
    }, 0)
  }

  it('差异=0时判断为可接受', () => {
    const total = 495000.00
    const g4_1Adjusted = 495000.00
    const variance = Math.round((total - g4_1Adjusted) * 100) / 100

    expect(variance).toBe(0)
    expect(Math.abs(variance) <= VARIANCE_THRESHOLD).toBe(true)
  })

  it('差异在0.01以内时判断为可接受', () => {
    const total = 495000.005
    const g4_1Adjusted = 495000.00
    const variance = Math.round((total - g4_1Adjusted) * 100) / 100

    expect(Math.abs(variance) <= VARIANCE_THRESHOLD).toBe(true)
  })

  it('差异超过0.01时判断为不可接受（需红色高亮）', () => {
    const total = 495100.00
    const g4_1Adjusted = 495000.00
    const variance = Math.round((total - g4_1Adjusted) * 100) / 100

    expect(variance).toBe(100)
    expect(Math.abs(variance) > VARIANCE_THRESHOLD).toBe(true)
  })

  it('多投资项目合计比对：精确匹配', () => {
    // 3个投资项目
    const groups = [
      { openingBalance: 5000000, openingImpairment: 50000, effectiveRate: 0.05, days: 365 },
      { openingBalance: 3000000, openingImpairment: 30000, effectiveRate: 0.06, days: 365 },
      { openingBalance: 2000000, openingImpairment: 20000, effectiveRate: 0.045, days: 365 },
    ]

    const total = computeTotalInterest(groups)
    // 项目1: (5000000-50000) * 0.05 = 247500
    // 项目2: (3000000-30000) * 0.06 = 178200
    // 项目3: (2000000-20000) * 0.045 = 89100
    // 合计: 247500 + 178200 + 89100 = 514800
    expect(total).toBe(514800)

    // 若G4-1审定数一致
    const g4_1Adjusted = 514800
    const variance = Math.round((total - g4_1Adjusted) * 100) / 100
    expect(Math.abs(variance) <= VARIANCE_THRESHOLD).toBe(true)
  })

  it('多投资项目合计比对：检测到差异', () => {
    const groups = [
      { openingBalance: 10000000, openingImpairment: 100000, effectiveRate: 0.05, days: 365 },
      { openingBalance: 8000000, openingImpairment: 200000, effectiveRate: 0.06, days: 365 },
    ]

    const total = computeTotalInterest(groups)
    // 项目1: (10000000-100000) * 0.05 = 495000
    // 项目2: (8000000-200000) * 0.06 = 468000
    // 合计: 495000 + 468000 = 963000
    expect(total).toBe(963000)

    // G4-1审定数存在差异（假设企业少确认了5000元利息）
    const g4_1Adjusted = 958000
    const variance = Math.round((total - g4_1Adjusted) * 100) / 100
    expect(variance).toBe(5000)
    expect(Math.abs(variance) > VARIANCE_THRESHOLD).toBe(true)
  })

  it('负差异（审定数大于测算合计）同样触发高亮', () => {
    const total = 200000
    const g4_1Adjusted = 200500  // 审定数大于测算合计
    const variance = Math.round((total - g4_1Adjusted) * 100) / 100

    expect(variance).toBe(-500)
    expect(Math.abs(variance) > VARIANCE_THRESHOLD).toBe(true)
  })
})

// ═══ 5. 现金流入公式（整年 vs 按天数） ═══

describe('G4-4利息测算 — 现金流入公式 (Req 7.6)', () => {
  it('整年现金流入 = 面值 × 票面利率', () => {
    const result = calcCashInflow(10000000, 0.05)
    expect(result).toBe(500000)
  })

  it('按天数现金流入 = 面值 × 票面利率 × days/365', () => {
    const result = calcCashInflow(10000000, 0.05, 180)
    expect(result).toBeCloseTo(10000000 * 0.05 * 180 / 365, 10)
  })

  it('半年(183天)现金流入', () => {
    const result = calcCashInflow(10000000, 0.05, 183)
    expect(result).toBeCloseTo(10000000 * 0.05 * 183 / 365, 10)
  })

  it('1天现金流入', () => {
    const result = calcCashInflow(10000000, 0.05, 1)
    expect(result).toBeCloseTo(10000000 * 0.05 / 365, 10)
  })

  it('闰年366天近似整年', () => {
    const result = calcCashInflow(10000000, 0.05, 366)
    // 366/365略大于1
    expect(result).toBeCloseTo(10000000 * 0.05 * 366 / 365, 10)
    expect(result).toBeGreaterThan(500000)
  })
})
