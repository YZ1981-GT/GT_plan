import { describe, it, expect } from 'vitest'
import { enrichG10L3Row } from '../useG10L3Reconciliation'
import { enrichG10DetailRow } from '../useG10Detail'

describe('useG10L3Reconciliation', () => {
  it('enrich 计算期末与差异', () => {
    const row = enrichG10L3Row({
      rowId: 'l1',
      openingBalance: 100,
      currentNew: 20,
      currentTerminated: 5,
      fairValueChange: 3,
      interestExpense: 1,
      reportedClosing: 120,
    })
    expect(row.closingBalance).toBe(119)
    expect(row.variance).toBe(1)
  })

  it('G10-2 Level3 字段可映射至 L3 调节行', () => {
    const detail = enrichG10DetailRow({
      rowId: 'd1',
      liabilityName: '结构化负债',
      fairValueLevel: 'Level3',
      openingInitialAmount: 100,
      movementInitialAmount: 10,
      currentDecrease: 5,
      movementFvChange: 8,
      interestExpense: 2,
    }, 1)
    const l3 = enrichG10L3Row({
      rowId: 'l1',
      liabilityName: detail.liabilityName,
      openingBalance: detail.openingAdjusted,
      currentNew: detail.movementInitialAmount,
      currentTerminated: detail.currentDecrease,
      fairValueChange: detail.movementFvChange,
      interestExpense: detail.interestExpense,
      reportedClosing: detail.closingAdjusted,
    })
    expect(l3.reportedClosing).toBe(detail.closingAdjusted)
    expect(detail.closingAdjusted).toBe(115)
    expect(l3.fairValueChange).toBe(8)
  })
})
