/**
 * useG6SppiInterest — G6-6 利息测算 单元测试
 *
 * 覆盖：分组新增/删除逻辑、期间链式计算（上期末=下期初）、交叉验证、公式计算、loadData/toJSON
 * Spec: .kiro/specs/g6-other-bond-investment-sppi/ Task 5.3
 * Validates: Requirements 3.2, 3.3, 3.4, 3.5
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick } from 'vue'

// Mock element-plus
vi.mock('element-plus', () => ({
  ElMessageBox: {
    prompt: vi.fn(),
    confirm: vi.fn(),
  },
  ElMessage: {
    success: vi.fn(),
  },
}))

import { useG6SppiInterest, type InterestGroup, type InterestPeriod, type InterestCalculationData } from '../useG6SppiInterest'
import { ElMessageBox } from 'element-plus'
import {
  applyG66InterestToDetailRows,
  buildG66InterestVarianceAdjustmentDrafts,
  compareG66EndingToG62,
  closingAmortizedFromG62Row,
  mapG612RowsToInterestStageSeeds,
  mapG62RowsToInterestSeeds,
  mergeG64EntriesWithG66Drafts,
  normalizeG6Rate,
} from '../g6CrossHelpers'

function createMockGroup(overrides: Partial<InterestGroup> = {}): InterestGroup {
  return {
    id: `ig-test-${Date.now()}`,
    crossSheetInvestmentId: '',
    investProject: '测试债券A',
    faceValue: 100000,
    couponRate: 0.04,
    effectiveRate: 0.05,
    dayCountBasis: 'ACT/365',
    purchasePrice: 0,
    transactionCost: 0,
    initialDate: '',
    initialCarryingAmount: 0,
    periods: [],
    ...overrides,
  }
}

function createMockPeriod(overrides: Partial<InterestPeriod> = {}): InterestPeriod {
  return {
    id: `ip-test-${Date.now()}`,
    periodStart: '',
    periodEnd: '2024-06-30',
    openingAmortized: 100000,
    openingImpairment: 0,
    stage: 'Stage1',
    effectiveInterest: 0,
    cashInflow: 0,
    principalRecovered: 0,
    endingAmortized: 0,
    days: 180,
    daysManualOverride: true,
    openingManualOverride: true,
    remark: '',
    indexRef: '',
    ...overrides,
  }
}

describe('useG6SppiInterest — 分组新增/删除', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('addGroup 成功新增投资项目', async () => {
    vi.mocked(ElMessageBox.prompt).mockResolvedValue({ value: '国债A' } as any)
    const { groups, addGroup } = useG6SppiInterest()
    await addGroup()
    expect(groups.value).toHaveLength(1)
    expect(groups.value[0].investProject).toBe('国债A')
    expect(groups.value[0].faceValue).toBe(0)
    expect(groups.value[0].couponRate).toBe(0)
    expect(groups.value[0].effectiveRate).toBe(0)
    expect(groups.value[0].periods).toEqual([])
  })

  it('addGroup 用户取消不新增', async () => {
    vi.mocked(ElMessageBox.prompt).mockRejectedValue('cancel')
    const { groups, addGroup } = useG6SppiInterest()
    await addGroup()
    expect(groups.value).toHaveLength(0)
  })

  it('removeGroup 确认后删除', async () => {
    vi.mocked(ElMessageBox.confirm).mockResolvedValue('confirm' as any)
    const { groups, removeGroup } = useG6SppiInterest()
    groups.value = [
      createMockGroup({ id: 'g1', investProject: '债券A' }),
      createMockGroup({ id: 'g2', investProject: '债券B' }),
    ]
    await removeGroup('g1')
    expect(groups.value).toHaveLength(1)
    expect(groups.value[0].investProject).toBe('债券B')
  })

  it('removeGroup 用户取消不删除', async () => {
    vi.mocked(ElMessageBox.confirm).mockRejectedValue('cancel')
    const { groups, removeGroup } = useG6SppiInterest()
    groups.value = [createMockGroup({ id: 'g1' })]
    await removeGroup('g1')
    expect(groups.value).toHaveLength(1)
  })

  it('removeGroup 不存在的id无效', async () => {
    const { groups, removeGroup } = useG6SppiInterest()
    groups.value = [createMockGroup({ id: 'g1' })]
    await removeGroup('nonexistent')
    expect(groups.value).toHaveLength(1)
  })
})

describe('useG6SppiInterest — 期间新增/删除', () => {
  it('addPeriod 新增首期优先用初始入账价值，否则为 0', () => {
    const { groups, addPeriod } = useG6SppiInterest()
    groups.value = [createMockGroup({ id: 'g1', faceValue: 100000, effectiveRate: 0.05, couponRate: 0.04 })]
    addPeriod('g1')
    expect(groups.value[0].periods).toHaveLength(1)
    expect(groups.value[0].periods[0].openingAmortized).toBe(0)
    expect(groups.value[0].periods[0].days).toBe(180)
  })

  it('addPeriod 后续期继承上期末摊余', () => {
    const { groups, addPeriod, recalcGroup } = useG6SppiInterest()
    groups.value = [createMockGroup({
      id: 'g1',
      faceValue: 100000,
      effectiveRate: 0.05,
      couponRate: 0.04,
      periods: [createMockPeriod({ id: 'p1', openingAmortized: 100000, days: 180 })],
    })]
    // recalc first to compute endingAmortized for p1
    recalcGroup(groups.value[0])
    const firstPeriodEnding = groups.value[0].periods[0].endingAmortized
    expect(firstPeriodEnding).toBeGreaterThan(0)

    addPeriod('g1')
    expect(groups.value[0].periods).toHaveLength(2)
    expect(groups.value[0].periods[1].openingAmortized).toBe(firstPeriodEnding)
  })

  it('removePeriod 删除并重算链式', () => {
    const { groups, removePeriod, recalcGroup } = useG6SppiInterest()
    groups.value = [createMockGroup({
      id: 'g1',
      faceValue: 100000,
      effectiveRate: 0.05,
      couponRate: 0.04,
      periods: [
        createMockPeriod({ id: 'p1', openingAmortized: 100000, days: 180 }),
        createMockPeriod({ id: 'p2', openingAmortized: 0, days: 180 }),
        createMockPeriod({ id: 'p3', openingAmortized: 0, days: 180 }),
      ],
    })]
    recalcGroup(groups.value[0])
    removePeriod('g1', 'p2')
    expect(groups.value[0].periods).toHaveLength(2)
    expect(groups.value[0].periods[0].id).toBe('p1')
    expect(groups.value[0].periods[1].id).toBe('p3')
  })

  it('addPeriod 对不存在的groupId无效', () => {
    const { groups, addPeriod } = useG6SppiInterest()
    groups.value = [createMockGroup({ id: 'g1' })]
    addPeriod('nonexistent')
    expect(groups.value[0].periods).toHaveLength(0)
  })
})

describe('useG6SppiInterest — 期间链式计算（上期末=下期初）', () => {
  it('多期链式：第2期初 = 第1期末', () => {
    const { groups, recalcGroup } = useG6SppiInterest()
    groups.value = [createMockGroup({
      id: 'g1',
      faceValue: 100000,
      couponRate: 0.04,
      effectiveRate: 0.05,
      periods: [
        createMockPeriod({ id: 'p1', openingAmortized: 100000, days: 180 }),
        createMockPeriod({ id: 'p2', openingAmortized: 0, days: 185 }),
      ],
    })]
    recalcGroup(groups.value[0])

    const p1 = groups.value[0].periods[0]
    const p2 = groups.value[0].periods[1]
    // 链式断言：p2.openingAmortized === p1.endingAmortized
    expect(p2.openingAmortized).toBe(p1.endingAmortized)
  })

  it('三期链式传递', () => {
    const { groups, recalcGroup } = useG6SppiInterest()
    groups.value = [createMockGroup({
      id: 'g1',
      faceValue: 100000,
      couponRate: 0.04,
      effectiveRate: 0.05,
      periods: [
        createMockPeriod({ id: 'p1', openingAmortized: 100000, days: 180 }),
        createMockPeriod({ id: 'p2', openingAmortized: 0, days: 185 }),
        createMockPeriod({ id: 'p3', openingAmortized: 0, days: 180 }),
      ],
    })]
    recalcGroup(groups.value[0])

    const [p1, p2, p3] = groups.value[0].periods
    expect(p2.openingAmortized).toBe(p1.endingAmortized)
    expect(p3.openingAmortized).toBe(p2.endingAmortized)
  })

  it('第一期保持原始openingAmortized', () => {
    const { groups, recalcGroup } = useG6SppiInterest()
    groups.value = [createMockGroup({
      id: 'g1',
      faceValue: 100000,
      couponRate: 0.04,
      effectiveRate: 0.05,
      periods: [
        createMockPeriod({ id: 'p1', openingAmortized: 98000, days: 180 }),
      ],
    })]
    recalcGroup(groups.value[0])
    expect(groups.value[0].periods[0].openingAmortized).toBe(98000)
  })
})

describe('useG6SppiInterest — 公式计算', () => {
  it('effectiveInterest = openingAmortized × effectiveRate × days/365', () => {
    const { groups, recalcGroup } = useG6SppiInterest()
    groups.value = [createMockGroup({
      id: 'g1',
      faceValue: 100000,
      couponRate: 0.04,
      effectiveRate: 0.05,
      periods: [createMockPeriod({ id: 'p1', openingAmortized: 100000, days: 180 })],
    })]
    recalcGroup(groups.value[0])
    const p = groups.value[0].periods[0]
    // 100000 * 0.05 * 180/365 = 2465.75 (rounded to 2dp)
    const expected = Math.round(100000 * 0.05 * 180 / 365 * 100) / 100
    expect(p.effectiveInterest).toBe(expected)
  })

  it('cashInflow = faceValue × couponRate × days/365', () => {
    const { groups, recalcGroup } = useG6SppiInterest()
    groups.value = [createMockGroup({
      id: 'g1',
      faceValue: 100000,
      couponRate: 0.04,
      effectiveRate: 0.05,
      periods: [createMockPeriod({ id: 'p1', openingAmortized: 100000, days: 180 })],
    })]
    recalcGroup(groups.value[0])
    const p = groups.value[0].periods[0]
    // 100000 * 0.04 * 180/365 = 1972.60
    const expected = Math.round(100000 * 0.04 * 180 / 365 * 100) / 100
    expect(p.cashInflow).toBe(expected)
  })

  it('endingAmortized = opening + interest - cashInflow', () => {
    const { groups, recalcGroup } = useG6SppiInterest()
    groups.value = [createMockGroup({
      id: 'g1',
      faceValue: 100000,
      couponRate: 0.04,
      effectiveRate: 0.05,
      periods: [createMockPeriod({ id: 'p1', openingAmortized: 100000, days: 180 })],
    })]
    recalcGroup(groups.value[0])
    const p = groups.value[0].periods[0]
    const expectedEnding = Math.round((100000 + p.effectiveInterest - p.cashInflow) * 100) / 100
    expect(p.endingAmortized).toBe(expectedEnding)
  })

  it('effectiveRate > couponRate → 摊余成本递增（折价债券）', () => {
    const { groups, recalcGroup } = useG6SppiInterest()
    groups.value = [createMockGroup({
      id: 'g1',
      faceValue: 100000,
      couponRate: 0.03,
      effectiveRate: 0.05,
      periods: [createMockPeriod({ id: 'p1', openingAmortized: 95000, days: 365 })],
    })]
    recalcGroup(groups.value[0])
    const p = groups.value[0].periods[0]
    // interest > cashInflow → ending > opening
    expect(p.endingAmortized).toBeGreaterThan(p.openingAmortized)
  })

  it('effectiveRate < couponRate → 摊余成本递减（溢价债券）', () => {
    const { groups, recalcGroup } = useG6SppiInterest()
    groups.value = [createMockGroup({
      id: 'g1',
      faceValue: 100000,
      couponRate: 0.06,
      effectiveRate: 0.04,
      periods: [createMockPeriod({ id: 'p1', openingAmortized: 105000, days: 365 })],
    })]
    recalcGroup(groups.value[0])
    const p = groups.value[0].periods[0]
    // interest < cashInflow → ending < opening
    expect(p.endingAmortized).toBeLessThan(p.openingAmortized)
  })
})

describe('useG6SppiInterest — totalInterest 合计', () => {
  it('多组多期利息合计', () => {
    const { groups, recalcAll, totalInterest } = useG6SppiInterest()
    groups.value = [
      createMockGroup({
        id: 'g1',
        faceValue: 100000,
        couponRate: 0.04,
        effectiveRate: 0.05,
        periods: [
          createMockPeriod({ id: 'p1', openingAmortized: 100000, days: 180 }),
          createMockPeriod({ id: 'p2', openingAmortized: 0, days: 185 }),
        ],
      }),
      createMockGroup({
        id: 'g2',
        faceValue: 200000,
        couponRate: 0.03,
        effectiveRate: 0.04,
        periods: [
          createMockPeriod({ id: 'p3', openingAmortized: 200000, days: 180 }),
        ],
      }),
    ]
    recalcAll()

    // totalInterest should sum all periods' effectiveInterest
    let expectedSum = 0
    for (const g of groups.value) {
      for (const p of g.periods) {
        expectedSum += p.effectiveInterest
      }
    }
    expectedSum = Math.round(expectedSum * 100) / 100
    expect(totalInterest.value).toBe(expectedSum)
  })

  it('无组时合计为0', () => {
    const { totalInterest } = useG6SppiInterest()
    expect(totalInterest.value).toBe(0)
  })

  it('getGroupInterestTotal 单组利息小计', () => {
    const { groups, recalcAll, getGroupInterestTotal } = useG6SppiInterest()
    groups.value = [createMockGroup({
      id: 'g1',
      faceValue: 100000,
      couponRate: 0.04,
      effectiveRate: 0.05,
      periods: [
        createMockPeriod({ id: 'p1', openingAmortized: 100000, days: 180 }),
        createMockPeriod({ id: 'p2', openingAmortized: 0, days: 185 }),
      ],
    })]
    recalcAll()

    const groupTotal = getGroupInterestTotal('g1')
    let expected = 0
    for (const p of groups.value[0].periods) {
      expected += p.effectiveInterest
    }
    expected = Math.round(expected * 100) / 100
    expect(groupTotal).toBe(expected)
  })
})

describe('useG6SppiInterest — 三层勾稽', () => {
  it('摊销差异 = (实际利息−票息) − G6-1利息调整本期变动', () => {
    const {
      groups, recalcAll, interestAdjPeriodChange,
      amortizationDiff, totalAmortization, totalInterest, totalCashInflow,
    } = useG6SppiInterest()
    groups.value = [createMockGroup({
      id: 'g1',
      faceValue: 100000,
      couponRate: 0.04,
      effectiveRate: 0.05,
      periods: [createMockPeriod({ id: 'p1', openingAmortized: 100000, days: 365 })],
    })]
    recalcAll()
    interestAdjPeriodChange.value = 500
    const expectedAmort = Math.round((totalInterest.value - totalCashInflow.value) * 100) / 100
    expect(totalAmortization.value).toBe(expectedAmort)
    expect(amortizationDiff.value).toBe(Math.round((expectedAmort - 500) * 100) / 100)
  })

  it('损益层未填账面利息时不强制失败', () => {
    const { bookInterestIncome, incomeLayerActive, incomePassed, interestAdjPeriodChange, amortizationPassed, crossValidationPassed } = useG6SppiInterest()
    bookInterestIncome.value = 0
    interestAdjPeriodChange.value = 0
    expect(incomeLayerActive.value).toBe(false)
    expect(incomePassed.value).toBe(true)
    expect(amortizationPassed.value).toBe(true)
    expect(crossValidationPassed.value).toBe(true)
  })

  it('摊销层差异≥0.01 时交叉验证不通过', () => {
    const { groups, recalcAll, interestAdjPeriodChange, crossValidationPassed, amortizationPassed } = useG6SppiInterest()
    groups.value = [createMockGroup({
      id: 'g1',
      faceValue: 100000,
      couponRate: 0.04,
      effectiveRate: 0.05,
      periods: [createMockPeriod({ id: 'p1', openingAmortized: 100000, days: 365 })],
    })]
    recalcAll()
    interestAdjPeriodChange.value = 0
    expect(amortizationPassed.value).toBe(false)
    expect(crossValidationPassed.value).toBe(false)
  })

  it('损益层填基准后校验 incomeDiff', () => {
    const { groups, recalcAll, setBookInterestIncome, incomeDiff, incomePassed, incomeLayerActive, totalInterest } = useG6SppiInterest()
    groups.value = [createMockGroup({
      id: 'g1',
      faceValue: 100000,
      couponRate: 0.04,
      effectiveRate: 0.05,
      periods: [createMockPeriod({ id: 'p1', openingAmortized: 100000, days: 365 })],
    })]
    recalcAll()
    setBookInterestIncome(totalInterest.value)
    expect(incomeLayerActive.value).toBe(true)
    expect(incomeDiff.value).toBe(0)
    expect(incomePassed.value).toBe(true)
  })

  it('auditedInterest 兼容别名指向 interestAdjPeriodChange', () => {
    const { auditedInterest, interestAdjPeriodChange } = useG6SppiInterest()
    interestAdjPeriodChange.value = 1234.56
    expect(auditedInterest.value).toBe(1234.56)
    auditedInterest.value = 99
    expect(interestAdjPeriodChange.value).toBe(99)
  })
})

describe('useG6SppiInterest — 扁平行与 G6-2 种子合并', () => {
  it('nestFlatRows 按投资项目聚合多期', () => {
    const { nestFlatRows, recalcAll, groups } = useG6SppiInterest()
    const nested = nestFlatRows([
      { investProject: '债A', faceValue: 100, couponRate: 0.04, effectiveRate: 0.05, cutoffDate: '2024-06-30', openingAmortized: 100, days: 180 },
      { investProject: '债A', cutoffDate: '2024-12-31', openingAmortized: 0, days: 184 },
      { investProject: '债B', faceValue: 200, couponRate: 0.03, effectiveRate: 0.04, cutoffDate: '2024-12-31', openingAmortized: 200, days: 365 },
    ])
    groups.value = nested
    recalcAll()
    expect(groups.value).toHaveLength(2)
    expect(groups.value[0].periods).toHaveLength(2)
    expect(groups.value[0].periods[1].openingAmortized).toBe(groups.value[0].periods[0].endingAmortized)
  })

  it('flattenGroups ↔ nestFlatRows round-trip 保留项目与期间数', () => {
    const { groups, addPeriod, flattenGroups, nestFlatRows, loadData, toJSON } = useG6SppiInterest()
    groups.value = [{
      id: 'g1',
      investProject: '国债',
      faceValue: 100000,
      couponRate: 0.035,
      effectiveRate: 0.04,
      periods: [],
    }]
    addPeriod('g1')
    addPeriod('g1')
    const periodIds = groups.value[0].periods.map((p) => p.id)
    const flat = flattenGroups()
    expect(flat.length).toBe(2)
    expect(flat[0].periodId).toBe(periodIds[0])
    expect(flat[1].periodId).toBe(periodIds[1])
    loadData(flat)
    expect(toJSON().groups).toHaveLength(1)
    expect(toJSON().groups[0].periods).toHaveLength(2)
    expect(toJSON().groups[0].periods.map((p) => p.id)).toEqual(periodIds)
  })

  it('mergeSeedsFromDetail 新增并补全空参数', () => {
    const { groups, mergeSeedsFromDetail } = useG6SppiInterest()
    groups.value = [{
      id: 'g1',
      investProject: '已有债',
      faceValue: 0,
      couponRate: 0,
      effectiveRate: 0,
      periods: [],
    }]
    const result = mergeSeedsFromDetail([
      { id: 's1', investProject: '已有债', faceValue: 1000, couponRate: 0.05, effectiveRate: 0.06, openingAmortized: 980 },
      { id: 's2', investProject: '新债', faceValue: 2000, couponRate: 0.04, effectiveRate: 0.045, openingAmortized: 2000 },
    ])
    expect(result.added).toBe(1)
    expect(result.updated).toBe(1)
    expect(groups.value).toHaveLength(2)
    expect(groups.value[0].faceValue).toBe(1000)
    expect(groups.value[0].id).toBe('s1')
    expect(groups.value[0].periods[0].openingAmortized).toBe(980)
  })

  it('mergeSeedsFromDetail 优先按稳定 id 匹配', () => {
    const { groups, mergeSeedsFromDetail } = useG6SppiInterest()
    groups.value = [{
      id: 'stable-1',
      investProject: '旧名称',
      faceValue: 100,
      couponRate: 0.03,
      effectiveRate: 0.04,
      periods: [createMockPeriod({ id: 'p1', openingAmortized: 100, days: 180 })],
    }]
    const result = mergeSeedsFromDetail([
      { id: 'stable-1', investProject: '新名称', faceValue: 0, couponRate: 0, effectiveRate: 0, openingAmortized: 999 },
    ])
    expect(result.updated).toBe(1)
    expect(result.added).toBe(0)
    expect(groups.value).toHaveLength(1)
    expect(groups.value[0].periods[0].openingAmortized).toBe(100) // 已有期间不覆盖
  })
})

describe('useG6SppiInterest — loadData/toJSON round-trip', () => {
  it('loadData 加载数据并重算公式', () => {
    const { groups, conclusion, auditedInterest, loadData } = useG6SppiInterest()
    const data: InterestCalculationData = {
      groups: [
        {
          id: 'g1',
          investProject: '公司债券X',
          faceValue: 200000,
          couponRate: 0.05,
          effectiveRate: 0.06,
          periods: [
            { id: 'p1', periodEnd: '2024-06-30', openingAmortized: 195000, effectiveInterest: 0, cashInflow: 0, endingAmortized: 0, days: 180, remark: '首期' },
          ],
        },
      ],
      conclusion: '利息确认合理',
      crossValidation: { totalInterest: 0, auditedInterest: 5500, difference: 0 },
    }
    loadData(data)
    expect(groups.value).toHaveLength(1)
    expect(groups.value[0].investProject).toBe('公司债券X')
    expect(groups.value[0].faceValue).toBe(200000)
    expect(groups.value[0].periods[0].openingAmortized).toBe(195000)
    // effectiveInterest should be recalculated
    expect(groups.value[0].periods[0].effectiveInterest).toBeGreaterThan(0)
    expect(conclusion.value).toBe('利息确认合理')
    expect(auditedInterest.value).toBe(5500)
  })

  it('loadData 识别新版 crossValidation 字段', () => {
    const { bookInterestIncome, interestAdjPeriodChange, loadData } = useG6SppiInterest()
    loadData({
      groups: [],
      conclusion: '',
      crossValidation: {
        totalInterest: 0,
        totalCashInflow: 0,
        totalAmortization: 0,
        bookInterestIncome: 1200,
        interestAdjPeriodChange: 80,
        incomeDiff: 0,
        amortizationDiff: 0,
      },
    })
    expect(bookInterestIncome.value).toBe(1200)
    expect(interestAdjPeriodChange.value).toBe(80)
  })

  it('loadData null 清空数据', () => {
    const { groups, loadData } = useG6SppiInterest()
    groups.value = [createMockGroup()]
    loadData(null)
    expect(groups.value).toHaveLength(0)
  })

  it('toJSON 输出正确结构含crossValidation', () => {
    const { groups, conclusion, auditedInterest, recalcAll, toJSON } = useG6SppiInterest()
    groups.value = [createMockGroup({
      id: 'g1',
      investProject: '测试X',
      faceValue: 100000,
      couponRate: 0.04,
      effectiveRate: 0.05,
      periods: [createMockPeriod({ id: 'p1', openingAmortized: 100000, days: 180 })],
    })]
    recalcAll()
    conclusion.value = '结论文本'
    auditedInterest.value = 2000

    const json = toJSON()
    expect(json.groups).toHaveLength(1)
    expect(json.groups[0].investProject).toBe('测试X')
    expect(json.groups[0].periods[0].effectiveInterest).toBeGreaterThan(0)
    expect(json.conclusion).toBe('结论文本')
    expect(json.crossValidation.auditedInterest).toBe(2000)
    expect(json.crossValidation.interestAdjPeriodChange).toBe(2000)
    expect(json.crossValidation.totalInterest).toBeGreaterThan(0)
    expect(typeof json.crossValidation.amortizationDiff).toBe('number')
    expect(typeof json.crossValidation.difference).toBe('number')
  })

  it('loadData → toJSON round-trip 数据一致', () => {
    const { loadData, toJSON } = useG6SppiInterest()
    const original: InterestCalculationData = {
      groups: [
        {
          id: 'g1',
          investProject: '国债round-trip',
          faceValue: 500000,
          couponRate: 0.035,
          effectiveRate: 0.04,
          periods: [
            { id: 'p1', periodEnd: '2024-06-30', openingAmortized: 490000, effectiveInterest: 0, cashInflow: 0, endingAmortized: 0, days: 180, remark: '' },
            { id: 'p2', periodEnd: '2024-12-31', openingAmortized: 0, effectiveInterest: 0, cashInflow: 0, endingAmortized: 0, days: 184, remark: '' },
          ],
        },
      ],
      conclusion: 'round-trip结论',
      crossValidation: { totalInterest: 0, auditedInterest: 19000, difference: 0 },
    }
    loadData(original)
    const result = toJSON()
    expect(result.groups[0].investProject).toBe('国债round-trip')
    expect(result.groups[0].faceValue).toBe(500000)
    expect(result.groups[0].periods).toHaveLength(2)
    // chain: p2.openingAmortized === p1.endingAmortized
    expect(result.groups[0].periods[1].openingAmortized).toBe(result.groups[0].periods[0].endingAmortized)
    expect(result.conclusion).toBe('round-trip结论')
    expect(result.crossValidation.auditedInterest).toBe(19000)
  })
})

describe('mapG62RowsToInterestSeeds — 期初摊余口径', () => {
  it('期初摊余 = 成本 + 利息调整（不含应计利息）', () => {
    const seeds = mapG62RowsToInterestSeeds([
      {
        id: 'r1',
        investProject: '债X',
        faceValue: 1000,
        couponRate: 0.04,
        effectiveRate: 0.05,
        openingCost: 980,
        openingInterestAdj: -20,
        openingAccruedInterest: 15,
        openingSubtotal: 975,
      },
    ])
    expect(seeds).toHaveLength(1)
    expect(seeds[0].openingAmortized).toBe(960)
  })

  it('normalizeG6Rate 将百分数启发式转为小数', () => {
    expect(normalizeG6Rate(5)).toBe(0.05)
    expect(normalizeG6Rate(0.05)).toBe(0.05)
    expect(normalizeG6Rate(0)).toBe(0)
  })

  it('种子映射时归一化百分数利率', () => {
    const seeds = mapG62RowsToInterestSeeds([
      { id: 'r1', investProject: '债Y', couponRate: 4.5, effectiveRate: 5, openingCost: 100, openingInterestAdj: 0 },
    ])
    expect(seeds[0].couponRate).toBe(0.045)
    expect(seeds[0].effectiveRate).toBe(0.05)
  })
})

describe('applyG66InterestToDetailRows — G6-6→G6-2 回写', () => {
  it('按 id 匹配并回写 periodInterestAdjChange = 实际利息−票息', () => {
    const result = applyG66InterestToDetailRows(
      [{
        id: 'g1',
        investProject: '债A',
        openingCost: 100,
        openingInterestAdj: -2,
        openingAccruedInterest: 1,
        periodCostChange: 0,
        periodAccruedInterestChange: 0,
        periodInterestAdjChange: 999,
      }],
      [{
        id: 'g1',
        investProject: '债A',
        periods: [
          { effectiveInterest: 12, cashInflow: 10 },
          { effectiveInterest: 11, cashInflow: 10 },
        ],
      }],
    )
    expect(result.matched).toEqual(['债A'])
    expect(result.unmatched).toHaveLength(0)
    expect(result.matchedAdjustmentTotal).toBe(3)
    expect(result.rows[0].periodInterestAdjChange).toBe(3)
    expect(result.rows[0].closingInterestAdj).toBe(1)
    expect(result.rows[0].closingCost).toBeUndefined()
    expect(result.rows[0].interestWritebackSource).toBe('G6-6')
  })

  it('预览合计仅含匹配行调整额', () => {
    const result = applyG66InterestToDetailRows(
      [
        {
          id: 'g1',
          investProject: '债A',
          openingInterestAdj: 0,
          periodCostChange: 0,
          periodAccruedInterestChange: 0,
          closingCost: 100,
          closingAccruedInterest: 2,
          periodInterestAdjChange: 0,
        },
        {
          id: 'other',
          investProject: '债B',
          periodInterestAdjChange: 50,
          closingCost: 200,
        },
      ],
      [{ id: 'g1', investProject: '债A', periods: [{ effectiveInterest: 5, cashInflow: 2 }] }],
    )
    expect(result.matchedAdjustmentTotal).toBe(3)
    expect(result.rows[1].periodInterestAdjChange).toBe(50)
    expect(result.rows[0].closingCost).toBe(100)
    expect(result.rows[0].closingAccruedInterest).toBe(2)
    expect(result.rows[0].closingSubtotal).toBe(105) // 100 + 3 + 2
  })

  it('未匹配项目进入 unmatched', () => {
    const result = applyG66InterestToDetailRows(
      [{ id: 'other', investProject: '债B', periodInterestAdjChange: 0 }],
      [{ id: 'g1', investProject: '债A', periods: [{ effectiveInterest: 1, cashInflow: 0 }] }],
    )
    expect(result.matched).toHaveLength(0)
    expect(result.unmatched).toEqual(['债A'])
  })
})

describe('useG6SppiInterest — 日期天数与收回本金', () => {
  it('填写起息日/截止日后自动推算天数', () => {
    const { groups, updatePeriod, recalcAll } = useG6SppiInterest()
    groups.value = [createMockGroup({
      id: 'g1',
      periods: [createMockPeriod({
        id: 'p1',
        periodStart: '',
        periodEnd: '',
        days: 180,
        daysManualOverride: false,
        openingAmortized: 100000,
      })],
    })]
    updatePeriod('g1', 'p1', 'periodStart', '2024-01-01')
    updatePeriod('g1', 'p1', 'periodEnd', '2024-01-31')
    expect(groups.value[0].periods[0].days).toBe(30)
    expect(groups.value[0].periods[0].daysManualOverride).toBe(false)
  })

  it('手工改天数后标记 override，改日期不再覆盖', () => {
    const { groups, updatePeriod } = useG6SppiInterest()
    groups.value = [createMockGroup({
      id: 'g1',
      periods: [createMockPeriod({
        id: 'p1',
        periodStart: '2024-01-01',
        periodEnd: '2024-01-31',
        days: 30,
        daysManualOverride: false,
      })],
    })]
    updatePeriod('g1', 'p1', 'days', 28)
    expect(groups.value[0].periods[0].daysManualOverride).toBe(true)
    updatePeriod('g1', 'p1', 'periodEnd', '2024-02-29')
    expect(groups.value[0].periods[0].days).toBe(28)
  })

  it('期末摊余扣减收回本金', () => {
    const { groups, recalcAll } = useG6SppiInterest()
    groups.value = [createMockGroup({
      id: 'g1',
      faceValue: 100000,
      couponRate: 0,
      effectiveRate: 0,
      periods: [createMockPeriod({
        id: 'p1',
        openingAmortized: 100000,
        principalRecovered: 10000,
        days: 365,
        daysManualOverride: true,
      })],
    })]
    recalcAll()
    expect(groups.value[0].periods[0].endingAmortized).toBe(90000)
  })

  it('收回本金后后续期间票息按剩余面值计算', () => {
    const { groups, recalcAll } = useG6SppiInterest()
    groups.value = [createMockGroup({
      id: 'g1',
      faceValue: 100000,
      couponRate: 0.04,
      effectiveRate: 0,
      periods: [
        createMockPeriod({
          id: 'p1',
          openingAmortized: 100000,
          principalRecovered: 20000,
          days: 365,
          daysManualOverride: true,
        }),
        createMockPeriod({
          id: 'p2',
          openingAmortized: 0,
          principalRecovered: 0,
          days: 365,
          daysManualOverride: true,
        }),
      ],
    })]
    recalcAll()
    // 第1期票息仍按全额面值 100000×4%=4000
    expect(groups.value[0].periods[0].cashInflow).toBe(4000)
    // 第2期票息按剩余面值 80000×4%=3200
    expect(groups.value[0].periods[1].cashInflow).toBe(3200)
  })

  it('累计收回本金超过面值产生告警', () => {
    const { groups, principalWarnings, hasPrincipalWarnings } = useG6SppiInterest()
    groups.value = [createMockGroup({
      id: 'g1',
      faceValue: 100,
      couponRate: 0,
      effectiveRate: 0,
      periods: [createMockPeriod({
        id: 'p1',
        openingAmortized: 100,
        principalRecovered: 120,
        days: 365,
        daysManualOverride: true,
      })],
    })]
    expect(hasPrincipalWarnings.value).toBe(true)
    expect(principalWarnings.value[0].message).toContain('超过面值')
  })

  it('期末摊余为负产生告警', () => {
    const { groups, principalWarnings, recalcAll } = useG6SppiInterest()
    groups.value = [createMockGroup({
      id: 'g1',
      faceValue: 100,
      couponRate: 0,
      effectiveRate: 0,
      periods: [createMockPeriod({
        id: 'p1',
        openingAmortized: 50,
        principalRecovered: 80,
        days: 365,
        daysManualOverride: true,
      })],
    })]
    recalcAll()
    expect(groups.value[0].periods[0].endingAmortized).toBe(-30)
    expect(principalWarnings.value.some((w) => w.message.includes('期末摊余成本为负'))).toBe(true)
  })

  it('ACT/360 计息基准按 360 年天数计算', () => {
    const { groups, updateGroupHeader, recalcAll } = useG6SppiInterest()
    groups.value = [createMockGroup({
      id: 'g1',
      faceValue: 360000,
      couponRate: 0.04,
      effectiveRate: 0.05,
      dayCountBasis: 'ACT/365',
      periods: [createMockPeriod({
        id: 'p1',
        openingAmortized: 360000,
        days: 360,
        daysManualOverride: true,
      })],
    })]
    recalcAll()
    // ACT/365: 360000×5%×360/365
    expect(groups.value[0].periods[0].effectiveInterest).toBe(
      Math.round(360000 * 0.05 * 360 / 365 * 100) / 100,
    )
    updateGroupHeader('g1', 'dayCountBasis', 'ACT/360')
    // ACT/360: 360000×5%×360/360 = 18000
    expect(groups.value[0].periods[0].effectiveInterest).toBe(18000)
    expect(groups.value[0].periods[0].cashInflow).toBe(14400)
  })

  it('利率差异超过200bp 产生告警', () => {
    const { groups, rateWarnings, hasRateWarnings } = useG6SppiInterest()
    groups.value = [createMockGroup({
      id: 'g1',
      couponRate: 0.03,
      effectiveRate: 0.06,
      periods: [],
    })]
    expect(hasRateWarnings.value).toBe(true)
    expect(rateWarnings.value[0].message).toContain('200bp')
  })

  it('初始入账价值 = 对价+费用，并可填充首期开口', () => {
    const { groups, addPeriod, recalcAll } = useG6SppiInterest()
    groups.value = [createMockGroup({
      id: 'g1',
      purchasePrice: 98000,
      transactionCost: 200,
      periods: [],
    })]
    recalcAll()
    expect(groups.value[0].initialCarryingAmount).toBe(98200)
    addPeriod('g1')
    expect(groups.value[0].periods[0].openingAmortized).toBe(98200)
  })

  it('openingManualOverride 时合法 0 期初不被初始入账覆盖', () => {
    const { groups, updatePeriod, recalcAll } = useG6SppiInterest()
    groups.value = [createMockGroup({
      id: 'g1',
      purchasePrice: 98000,
      transactionCost: 200,
      periods: [createMockPeriod({
        id: 'p1',
        openingAmortized: 0,
        openingManualOverride: true,
        days: 180,
        daysManualOverride: true,
      })],
    })]
    recalcAll()
    expect(groups.value[0].periods[0].openingAmortized).toBe(0)
    updatePeriod('g1', 'p1', 'openingAmortized', 0)
    expect(groups.value[0].periods[0].openingManualOverride).toBe(true)
    expect(groups.value[0].periods[0].openingAmortized).toBe(0)
  })

  it('Stage3 按净额（摊余−减值）计息', () => {
    const { groups, recalcAll } = useG6SppiInterest()
    groups.value = [createMockGroup({
      id: 'g1',
      faceValue: 100000,
      couponRate: 0,
      effectiveRate: 0.10,
      periods: [createMockPeriod({
        id: 'p1',
        openingAmortized: 100000,
        openingImpairment: 20000,
        stage: 'Stage3',
        days: 365,
        daysManualOverride: true,
      })],
    })]
    recalcAll()
    // 净额 80000 × 10% × 365/365 = 8000
    expect(groups.value[0].periods[0].effectiveInterest).toBe(8000)
  })

  it('超 B15 重要性标记 materialVariance，并要求差异说明', () => {
    const {
      groups, recalcAll, interestAdjPeriodChange, setPerformanceMateriality,
      materialVariance, needsVarianceReason, varianceReasonMissing, varianceReason,
    } = useG6SppiInterest()
    groups.value = [createMockGroup({
      id: 'g1',
      faceValue: 100000,
      couponRate: 0.04,
      effectiveRate: 0.05,
      periods: [createMockPeriod({ id: 'p1', openingAmortized: 100000, days: 365 })],
    })]
    recalcAll()
    interestAdjPeriodChange.value = 0
    setPerformanceMateriality(1)
    expect(needsVarianceReason.value).toBe(true)
    expect(materialVariance.value).toBe(true)
    expect(varianceReasonMissing.value).toBe(true)
    varianceReason.value = '尾差待调整'
    expect(varianceReasonMissing.value).toBe(false)
  })

  it('mergeEclStageSeeds 仅写入末期 Stage3 与减值', () => {
    const { groups, mergeEclStageSeeds, recalcAll } = useG6SppiInterest()
    groups.value = [createMockGroup({
      id: 'g1',
      crossSheetInvestmentId: 'ecl-1',
      investProject: '债A',
      faceValue: 100000,
      couponRate: 0,
      effectiveRate: 0.1,
      periods: [
        createMockPeriod({
          id: 'p1',
          openingAmortized: 100000,
          stage: 'Stage1',
          openingImpairment: 0,
          days: 365,
          daysManualOverride: true,
        }),
        createMockPeriod({
          id: 'p2',
          openingAmortized: 100000,
          stage: 'Stage1',
          openingImpairment: 0,
          days: 365,
          daysManualOverride: true,
        }),
      ],
    })]
    const result = mergeEclStageSeeds([
      { id: 'ecl-1', investProject: '债A', stage: 'Stage3', openingImpairment: 25000 },
    ])
    expect(result.updated).toBe(1)
    expect(groups.value[0].periods[0].stage).toBe('Stage1')
    expect(groups.value[0].periods[0].openingImpairment).toBe(0)
    expect(groups.value[0].periods[1].stage).toBe('Stage3')
    expect(groups.value[0].periods[1].openingImpairment).toBe(25000)
    recalcAll()
    // 第1期仍按总额计息 → 期末 110000；第2期 Stage3 净额 (110000−25000)×10%=8500
    expect(groups.value[0].periods[1].effectiveInterest).toBe(8500)
  })
})

describe('mapG612RowsToInterestStageSeeds', () => {
  it('优先审定减值并归一化阶段', () => {
    const seeds = mapG612RowsToInterestStageSeeds([
      { id: '1', investProject: '债A', stageGroup: 'Stage3', adjImpairment: 12, impairmentProvision: 9 },
      { id: '2', investProject: '债A', stage: 'Stage1', impairmentProvision: 1 }, // 去重
    ])
    expect(seeds).toHaveLength(1)
    expect(seeds[0].stage).toBe('Stage3')
    expect(seeds[0].openingImpairment).toBe(12)
  })
})

describe('compareG66EndingToG62 — 第三层期末摊余勾稽', () => {
  it('closingAmortizedFromG62Row = 成本 + 利息调整', () => {
    expect(closingAmortizedFromG62Row({
      closingCost: 100,
      closingInterestAdj: -3,
      closingAccruedInterest: 5,
      closingSubtotal: 102,
    })).toBe(97)
  })

  it('按 id 匹配并计算差异', () => {
    const result = compareG66EndingToG62(
      [{
        id: 'g1',
        investProject: '债A',
        periods: [
          { endingAmortized: 90 },
          { endingAmortized: 95 },
        ],
      }],
      [{
        id: 'g1',
        investProject: '债A',
        closingCost: 100,
        closingInterestAdj: -5,
      }],
    )
    expect(result).toHaveLength(1)
    expect(result[0].g66Ending).toBe(95)
    expect(result[0].g62Ending).toBe(95)
    expect(result[0].diff).toBe(0)
    expect(result[0].matched).toBe(true)
  })

  it('未匹配明细标记 matched=false', () => {
    const result = compareG66EndingToG62(
      [{ id: 'g1', investProject: '债A', periods: [{ endingAmortized: 10 }] }],
      [{ id: 'other', investProject: '债B', closingCost: 10, closingInterestAdj: 0 }],
    )
    expect(result[0].matched).toBe(false)
    expect(result[0].g62Ending).toBeNull()
  })
})

describe('buildG66InterestVarianceAdjustmentDrafts — G6-6→G6-4', () => {
  it('摊销层 diff>0 生成借利息调整贷投资收益', () => {
    const { pairs, skipped } = buildG66InterestVarianceAdjustmentDrafts({
      amortizationDiff: 120,
      incomeDiff: 0,
      incomeLayerActive: false,
      performanceMateriality: 50,
      varianceReason: '漏记摊销',
    })
    expect(skipped.some((s) => s.layer.includes('损益'))).toBe(true)
    expect(pairs).toHaveLength(1)
    expect(pairs[0].layer).toBe('amortization')
    expect(pairs[0].amount).toBe(120)
    const [dr, cr] = pairs[0].entries
    expect(dr.accountCode).toBe('150302')
    expect(dr.debitAmount).toBe(120)
    expect(cr.accountCode).toBe('6111')
    expect(cr.creditAmount).toBe(120)
  })

  it('diff<0 借贷方向相反；merge 替换同层旧草稿', () => {
    const { pairs } = buildG66InterestVarianceAdjustmentDrafts({
      amortizationDiff: -80,
      incomeDiff: 0,
      incomeLayerActive: false,
      performanceMateriality: 10,
    })
    expect(pairs[0].entries[0].creditAmount).toBe(80)
    expect(pairs[0].entries[1].debitAmount).toBe(80)

    const existing = [
      {
        id: 'g66-amortization-dr',
        rowId: 'g66-amortization-dr',
        seq: 1,
        description: 'old',
        category: '账项调整',
        reportItem: '',
        accountCode: '150302',
        accountName: '',
        noteItem: '',
        debitAmount: 1,
        creditAmount: 0,
        indexRef: 'G6-6',
        remark: 'source=G6-6;layer=amortization;diff=1',
        entryType: 'AJE' as const,
        date: '',
        summary: 'old',
        preparedBy: '',
      },
      {
        id: 'keep-me',
        rowId: 'keep-me',
        seq: 2,
        description: 'other',
        category: '账项调整',
        reportItem: '',
        accountCode: '150301',
        accountName: '',
        noteItem: '',
        debitAmount: 5,
        creditAmount: 0,
        indexRef: 'G6-9',
        remark: '',
        entryType: 'AJE' as const,
        date: '',
        summary: 'other',
        preparedBy: '',
      },
    ]
    const merged = mergeG64EntriesWithG66Drafts(existing, pairs)
    expect(merged.some((e) => e.id === 'keep-me')).toBe(true)
    expect(merged.filter((e) => String(e.remark).includes('layer=amortization'))).toHaveLength(2)
    expect(merged.find((e) => e.id === 'g66-amortization-dr' && e.debitAmount === 1)).toBeUndefined()
  })

  it('仅 material 时跳过低于 B15 的差异', () => {
    const { pairs, skipped } = buildG66InterestVarianceAdjustmentDrafts({
      amortizationDiff: 5,
      incomeDiff: 0,
      incomeLayerActive: false,
      performanceMateriality: 100,
      onlyMaterial: true,
    })
    expect(pairs).toHaveLength(0)
    expect(skipped[0].reason).toContain('未超过阈值')
  })
})

describe('30/360 计息基准', () => {
  it('30/360 按欧洲规则推算天数并用 360 年天数计息', () => {
    const { groups, updatePeriod, recalcAll } = useG6SppiInterest()
    groups.value = [createMockGroup({
      id: 'g1',
      faceValue: 360000,
      couponRate: 0,
      effectiveRate: 0.05,
      dayCountBasis: '30/360',
      periods: [createMockPeriod({
        id: 'p1',
        periodStart: '2024-01-31',
        periodEnd: '2024-02-29',
        openingAmortized: 360000,
        days: 180,
        daysManualOverride: false,
      })],
    })]
    // 强制走日期推算
    updatePeriod('g1', 'p1', 'periodEnd', '2024-02-29')
    // 30E/360: Jan31→Feb29 → D1=30,D2=29 → 29 days? 
    // Actually: y same, m: 2-1=1, d: 29-30 = -1 → 30*1 + (-1) = 29
    expect(groups.value[0].periods[0].days).toBe(29)
    recalcAll()
    expect(groups.value[0].periods[0].effectiveInterest).toBe(
      Math.round(360000 * 0.05 * 29 / 360 * 100) / 100,
    )
  })
})
