/**
 * useF2StocktakeCrossSheet — 元数据种子与差异摘要
 */
import { describe, it, expect } from 'vitest'
import {
  applyMetaSeedToFields,
  extractDateToken,
  formatVarianceSummary,
} from '../useF2StocktakeCrossSheet'

describe('useF2StocktakeCrossSheet', () => {
  it('extractDateToken 解析中文日期', () => {
    expect(extractDateToken('2024年12月31日')).toBe('2024-12-31')
    expect(extractDateToken('2024-01-05')).toBe('2024-01-05')
  })

  it('applyMetaSeedToFields 仅填空', () => {
    const patch = applyMetaSeedToFields(
      { entityName: '甲公司', bsDate: '2024-12-31', countDate: '2025-01-10', source: 'F2-22' },
      { entityName: '已有', bsDate: '', countDate: '' },
      { entityName: 'entityName', bsDate: 'bsDate', countDate: 'countDate' },
    )
    expect(patch).toEqual({ bsDate: '2024-12-31', countDate: '2025-01-10' })
  })

  it('formatVarianceSummary 汇总差异行', () => {
    const s = formatVarianceSummary(
      [
        { itemName: 'A料', qtyDiff: 2, bookQty: 10, sampleQty: 12, hasVariance: true },
        { itemName: 'B料', qtyDiff: -1, hasVariance: true },
      ],
      { label: '抽盘差异', max: 1 },
    )
    expect(s).toContain('抽盘差异（1）')
    expect(s).toContain('A料')
    expect(s).toContain('另有 1 行未列示')
  })
})
