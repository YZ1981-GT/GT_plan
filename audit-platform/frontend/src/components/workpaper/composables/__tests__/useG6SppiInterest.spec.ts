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

function createMockGroup(overrides: Partial<InterestGroup> = {}): InterestGroup {
  return {
    id: `ig-test-${Date.now()}`,
    investProject: '测试债券A',
    faceValue: 100000,
    couponRate: 0.04,
    effectiveRate: 0.05,
    periods: [],
    ...overrides,
  }
}

function createMockPeriod(overrides: Partial<InterestPeriod> = {}): InterestPeriod {
  return {
    id: `ip-test-${Date.now()}`,
    periodEnd: '2024-06-30',
    openingAmortized: 100000,
    effectiveInterest: 0,
    cashInflow: 0,
    endingAmortized: 0,
    days: 180,
    remark: '',
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
  it('addPeriod 新增首期以faceValue为期初摊余', () => {
    const { groups, addPeriod } = useG6SppiInterest()
    groups.value = [createMockGroup({ id: 'g1', faceValue: 100000, effectiveRate: 0.05, couponRate: 0.04 })]
    addPeriod('g1')
    expect(groups.value[0].periods).toHaveLength(1)
    expect(groups.value[0].periods[0].openingAmortized).toBe(100000)
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

describe('useG6SppiInterest — 交叉验证', () => {
  it('差异 = totalInterest - auditedInterest', () => {
    const { groups, recalcAll, auditedInterest, crossValidationDiff, totalInterest } = useG6SppiInterest()
    groups.value = [createMockGroup({
      id: 'g1',
      faceValue: 100000,
      couponRate: 0.04,
      effectiveRate: 0.05,
      periods: [createMockPeriod({ id: 'p1', openingAmortized: 100000, days: 365 })],
    })]
    recalcAll()
    auditedInterest.value = 5000
    const expectedDiff = Math.round((totalInterest.value - 5000) * 100) / 100
    expect(crossValidationDiff.value).toBe(expectedDiff)
  })

  it('交叉验证通过(差异<0.01)', () => {
    const { auditedInterest, crossValidationPassed, totalInterest } = useG6SppiInterest()
    // totalInterest is 0 when no groups
    auditedInterest.value = 0
    expect(crossValidationPassed.value).toBe(true)
  })

  it('交叉验证不通过(差异≥0.01)', () => {
    const { groups, recalcAll, auditedInterest, crossValidationPassed } = useG6SppiInterest()
    groups.value = [createMockGroup({
      id: 'g1',
      faceValue: 100000,
      couponRate: 0.04,
      effectiveRate: 0.05,
      periods: [createMockPeriod({ id: 'p1', openingAmortized: 100000, days: 365 })],
    })]
    recalcAll()
    auditedInterest.value = 0 // big difference
    expect(crossValidationPassed.value).toBe(false)
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
    expect(json.crossValidation.totalInterest).toBeGreaterThan(0)
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
