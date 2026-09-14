import { describe, it, expect } from 'vitest'
import {
  defaultOverheadMatrix,
  enrichOverheadMatrix,
  migrateToOverheadMatrix,
  sumOverheadAnnual,
} from '../useF2OverheadMatrixFormulas'

describe('useF2OverheadMatrixFormulas', () => {
  it('默认 13 项费用 + 合计行', () => {
    const m = enrichOverheadMatrix(defaultOverheadMatrix())
    expect(m.rows).toHaveLength(14)
    expect(m.rows[13].key).toBe('total')
    expect(m.rows[13].label).toBe('合计')
  })

  it('合计 = 各月分项之和', () => {
    const data = defaultOverheadMatrix()
    data.rows.find((r) => r.key === 'wages')!.months['01'] = 100
    data.rows.find((r) => r.key === 'welfare')!.months['01'] = 50
    const e = enrichOverheadMatrix(data)
    expect(e.rows.find((r) => r.key === 'total')!.months['01']).toBe(150)
    expect(sumOverheadAnnual(data)).toBe(150)
  })

  it('变动率基于合计与上年度', () => {
    const data = defaultOverheadMatrix()
    const wages = data.rows.find((r) => r.key === 'wages')!
    wages.months['01'] = 120
    wages.priorYear = 100
    const e = enrichOverheadMatrix(data)
    const row = e.rows.find((r) => r.key === 'wages')!
    expect(row.changeRate).toBe(0.2)
  })

  it('迁移旧预算/实际行', () => {
    const legacy = [{ rowId: '1', costItem: '折旧费', budgetAmt: 80, actualAmt: 100, allocatedAmt: 100, remark: '' }]
    const m = migrateToOverheadMatrix(legacy)
    expect(m).not.toBeNull()
    expect(m!.rows.find((r) => r.key === 'depreciation')!.months['12']).toBe(100)
  })
})
