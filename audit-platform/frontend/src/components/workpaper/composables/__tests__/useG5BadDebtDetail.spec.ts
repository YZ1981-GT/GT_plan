import { describe, it, expect } from 'vitest'
import {
  computeMovement,
  migrateLegacyEclRows,
  normalizeStoredLeaves,
  buildDisplayRows,
} from '../useG5BadDebtDetail'
import { aggregateProvisionFromG53 } from '../g5CrossHelpers'
import { extractBadDebtForDisclosure } from '../g5ListedDisclosureRows'

describe('useG5BadDebtDetail movement', () => {
  it('滚动态公式：期初审定 / 期末未审 / 期末审定', () => {
    const d = computeMovement({
      openingUnadjusted: 100,
      openingAdjustment: 10,
      provisionIncrease: 20,
      otherIncrease: 5,
      reversal: 8,
      writeOff: 2,
      otherDecrease: 1,
      closingAdjustment: 3,
    })
    expect(d.openingAudited).toBe(110)
    expect(d.closingUnadjusted).toBe(124) // 110+20+5-8-2-1
    expect(d.closingAudited).toBe(127)
  })

  it('旧 ECL 行迁移后期末审定对齐 adjustedProvision', () => {
    const leaves = migrateLegacyEclRows([
      {
        debtorOrGroup: '甲公司',
        provisionMethod: 'individual',
        adjustedProvision: 50,
        priorYearProvision: 30,
        currentYearReversal: 0,
      },
    ])
    expect(leaves[0].item).toBe('甲公司')
    expect(leaves[0].category).toBe('individual')
    const d = computeMovement(leaves[0])
    expect(d.closingAudited).toBe(50)
  })

  it('展示行含单项/组合分区头与合计', () => {
    const leaves = normalizeStoredLeaves([
      {
        category: 'individual',
        item: 'A',
        openingUnadjusted: 10,
        provisionIncrease: 2,
      },
      {
        category: 'portfolio',
        item: '账龄组合',
        portfolioType: 'business',
        openingUnadjusted: 20,
        provisionIncrease: 1,
      },
    ])
    const rows = buildDisplayRows(leaves)
    expect(rows.some((r) => r.kind === 'section_header' && /单项/.test(r.item))).toBe(true)
    expect(rows.some((r) => r.kind === 'section_header' && /组合/.test(r.item))).toBe(true)
    expect(rows.find((r) => r.kind === 'total')!.closingAudited).toBe(33)
  })

  it('G5-1 汇总兼容滚动态与旧格式', () => {
    const movement = aggregateProvisionFromG53([
      { category: 'individual', item: 'X', closingAudited: 40 },
      { category: 'portfolio', item: '账龄', portfolioType: 'customer', closingAudited: 60 },
    ])
    expect(movement.individualClosing).toBe(40)
    expect(movement.customerClosing).toBe(60)

    const legacy = aggregateProvisionFromG53([
      { provisionMethod: 'individual', debtorOrGroup: 'Y', adjustedProvision: 15 },
      { provisionMethod: 'group', portfolioType: 'business', adjustedProvision: 25 },
    ])
    expect(legacy.individualClosing).toBe(15)
    expect(legacy.businessClosing).toBe(25)
  })

  it('附注取数兼容滚动态', () => {
    const raw = JSON.stringify([
      {
        category: 'individual',
        item: '债务人甲',
        closingAudited: 12,
        openingUnadjusted: 8,
        openingAdjustment: 0,
        reason: '违约',
      },
      { category: 'portfolio', item: '账龄组合', closingAudited: 30 },
    ])
    const bad = extractBadDebtForDisclosure(raw)
    expect(bad.individual[0].endProvision).toBe(12)
    expect(bad.groupNames).toContain('账龄组合')
    expect(bad.groupTotals.end.provision).toBe(30)
  })
})
