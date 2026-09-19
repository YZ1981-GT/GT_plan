/**
 * G7-11 / G7-12 披露解析：former subsidiaries
 */
import { describe, it, expect } from 'vitest'
import {
  parseG711FormerSubsidiaries,
  parseG712FormerSubsidiaries,
  applyFormerSubsidiaryBasicFromG712,
} from '../g7DisclosureCrossSheet'

describe('parseG711FormerSubsidiaries', () => {
  it('不用 disposalRatio 冒充持股比例', () => {
    const rows = parseG711FormerSubsidiaries([
      {
        investeeName: '甲公司',
        disposalDate: '2025-06-30',
        disposalRatio: 0.8,
        auditConclusion: '已核对',
      },
    ])
    expect(rows).toHaveLength(1)
    expect(rows[0].holdingRatio).toBeNull()
    expect(rows[0].reason).toContain('处置日 2025-06-30')
    expect(rows[0].reason).toContain('处置比例 80%')
    expect(rows[0].reason).toContain('已核对')
  })

  it('有 originalShareholdingRatio 时填持股', () => {
    const rows = parseG711FormerSubsidiaries([
      { investeeName: '乙', originalShareholdingRatio: 0.7, disposalRatio: 0.7 },
    ])
    expect(rows[0].holdingRatio).toBe(70)
  })
})

describe('parseG712FormerSubsidiaries', () => {
  it('优先 originalShareholdingRatio，不用 disposalRatio 兜底', () => {
    const rows = parseG712FormerSubsidiaries([
      {
        investeeName: '丙',
        originalShareholdingRatio: 0.6,
        disposalRatio: 0.4,
        registeredPlace: '上海',
      },
    ])
    expect(rows[0].holdingRatio).toBe(60)
    expect(rows[0].registeredPlace).toBe('上海')
  })
})

describe('applyFormerSubsidiaryBasicFromG712 sourceLabel', () => {
  it('可标注 G7-11 来源', () => {
    const table: any[] = []
    const ok = applyFormerSubsidiaryBasicFromG712(
      table,
      [{ investeeName: '丁', registeredPlace: '', businessNature: '', holdingRatio: null, votingRights: null, reason: '处置' }],
      true,
      '处置子公司测试表G7-11',
    )
    expect(ok).toBe(true)
    expect(table[0].source).toContain('G7-11')
    expect(table[0].label).toBe('丁')
  })
})
