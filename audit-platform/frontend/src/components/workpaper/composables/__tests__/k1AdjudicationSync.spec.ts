import { describe, it, expect } from 'vitest'
import { aggregateK12ForK11 } from '../k1AdjudicationSync'
import { classifyK1Nature, classifyK1Portfolio } from '../k1AdjudicationModel'

describe('k1AdjudicationSync', () => {
  it('classifyK1Portfolio stage3 → individual', () => {
    expect(classifyK1Portfolio(3)).toBe('individual')
    expect(classifyK1Portfolio(1)).toBe('aging')
  })

  it('classifyK1Nature maps 保证金/押金', () => {
    expect(classifyK1Nature('保证金')).toBe('margin')
    expect(classifyK1Nature('员工备用金')).toBe('petty')
  })

  it('aggregateK12ForK11 sums portfolio and nature', () => {
    const agg = aggregateK12ForK11([
      {
        endBalance: 1000,
        badDebtProvision: 100,
        stage: 1,
        nature: '保证金',
        agingAudited: { within1: 600, y1to2: 400 },
      },
      {
        endBalance: 500,
        badDebtProvision: 50,
        stage: 3,
        nature: '往来款',
        agingAudited: { within1: 500 },
      },
    ])
    expect(agg.detailSubtotal).toBe(1500)
    expect(agg.portfolioGross[0]).toBe(500)
    expect(agg.portfolioGross[1]).toBe(1000)
    expect(agg.natureGross[0]).toBe(1000)
    expect(agg.agingGross[0]).toBe(1100)
  })
})
