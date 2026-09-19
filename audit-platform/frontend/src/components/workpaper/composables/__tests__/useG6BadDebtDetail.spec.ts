/**
 * G6-3 坏账准备明细 — 滚动态公式单测
 */
import { describe, it, expect } from 'vitest'
import {
  computeG6BadDebtMovement,
  sumG6BadDebtLeaves,
  buildG6BadDebtDisplayRows,
  migrateLegacyEclToMovement,
  buildG6BadDebtWritebackDetail,
  type G6BadDebtLeaf,
} from '../useG6BadDebtDetail'

function leaf(partial: Partial<G6BadDebtLeaf> & { category: 'individual' | 'portfolio'; item: string }): G6BadDebtLeaf {
  return {
    id: partial.id || 'x',
    seq: partial.seq || 1,
    category: partial.category,
    item: partial.item,
    openingUnadjusted: partial.openingUnadjusted ?? 0,
    openingAdjustment: partial.openingAdjustment ?? 0,
    provisionIncrease: partial.provisionIncrease ?? 0,
    otherIncrease: partial.otherIncrease ?? 0,
    reversal: partial.reversal ?? 0,
    writeOff: partial.writeOff ?? 0,
    otherDecrease: partial.otherDecrease ?? 0,
    closingAdjustment: partial.closingAdjustment ?? 0,
    reason: partial.reason ?? '',
  }
}

describe('computeG6BadDebtMovement（对齐 Excel）', () => {
  it('期初审定 = 未审 + 调整', () => {
    const m = computeG6BadDebtMovement({
      openingUnadjusted: 100,
      openingAdjustment: 20,
      provisionIncrease: 0,
      otherIncrease: 0,
      reversal: 0,
      writeOff: 0,
      otherDecrease: 0,
      closingAdjustment: 0,
    })
    expect(m.openingAudited).toBe(120)
  })

  it('期末未审 = 期初未审 + 增加 − 减少（不以期初审定起点）', () => {
    const m = computeG6BadDebtMovement({
      openingUnadjusted: 100,
      openingAdjustment: 50, // 不影响期末未审滚动起点
      provisionIncrease: 30,
      otherIncrease: 10,
      reversal: 5,
      writeOff: 2,
      otherDecrease: 3,
      closingAdjustment: 8,
    })
    // 100+30+10-5-2-3 = 130
    expect(m.closingUnadjusted).toBe(130)
    expect(m.closingAudited).toBe(138)
  })
})

describe('buildG6BadDebtDisplayRows', () => {
  it('含单项/组合分区与合计', () => {
    const rows = buildG6BadDebtDisplayRows([
      leaf({ category: 'individual', item: '甲', openingUnadjusted: 100, provisionIncrease: 20 }),
      leaf({ category: 'portfolio', item: '组合A', openingUnadjusted: 200, provisionIncrease: 10 }),
    ])
    expect(rows.some((r) => r.kind === 'section_header' && r.item.includes('单项'))).toBe(true)
    expect(rows.some((r) => r.kind === 'section_header' && r.item.includes('组合'))).toBe(true)
    expect(rows.some((r) => r.kind === 'total')).toBe(true)
    const total = rows.find((r) => r.kind === 'total')!
    expect(total.closingUnadjusted).toBe(330) // 100+20 + 200+10
  })
})

describe('migrateLegacyEclToMovement', () => {
  it('旧 ECL 字段迁移为滚动态', () => {
    const leaves = migrateLegacyEclToMovement([
      {
        investProject: '债A',
        stageGroup: '单项',
        priorProvision: 50,
        currentProvision: 10,
        currentReversal: 0,
        currentWriteOff: 0,
        adjustedProvision: 70,
      },
    ])
    expect(leaves[0].category).toBe('individual')
    expect(leaves[0].openingUnadjusted).toBe(50)
    expect(leaves[0].provisionIncrease).toBe(10)
    // 期末未审=60，审定70 → 调整10
    const m = computeG6BadDebtMovement(leaves[0])
    expect(m.closingAudited).toBe(70)
  })
})

describe('sumG6BadDebtLeaves', () => {
  it('汇总单项+组合', () => {
    const t = sumG6BadDebtLeaves([
      leaf({ category: 'individual', item: 'a', openingUnadjusted: 10, provisionIncrease: 5 }),
      leaf({ category: 'portfolio', item: 'b', openingUnadjusted: 20, provisionIncrease: 5 }),
    ])
    expect(t.openingUnadjusted).toBe(30)
    expect(t.closingUnadjusted).toBe(40)
  })
})

describe('buildG6BadDebtWritebackDetail（G6-3→G6-1 用未审）', () => {
  it('回写载荷取期末未审，忽略 closingAdjustment', () => {
    const detail = buildG6BadDebtWritebackDetail([
      leaf({
        category: 'individual',
        item: '甲',
        openingUnadjusted: 100,
        provisionIncrease: 20,
        closingAdjustment: 50, // 审定=170，未审=120
      }),
      leaf({
        category: 'portfolio',
        item: '乙',
        openingUnadjusted: 200,
        provisionIncrease: 10,
        closingAdjustment: 30, // 审定=240，未审=210
      }),
    ])
    expect(detail.individualClosing).toBe(120)
    expect(detail.portfolioClosing).toBe(210)
    expect(detail.totalClosing).toBe(330)
    // 若误用审定会得到 170/240/410
    expect(detail.individualClosing).not.toBe(170)
    expect(detail.portfolioClosing).not.toBe(240)
  })
})
