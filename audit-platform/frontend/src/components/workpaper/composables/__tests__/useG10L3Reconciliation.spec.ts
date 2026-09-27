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

  // 🔴 C-7（spec g-cycle-single-region-detail-lanes）：G10-2 按权威模板重构为 19 列 A..S。
  //    ①没有 `fairValueLevel`（层次权威源是 G10-5，Level3 名单由 G10-5 定）；
  //    ②没有 `currentDecrease`（模板 H 是净额列）⇒ `currentTerminated` 不再能从明细带入，
  //      由用户按凭证填（净额拆不出终止确认金额，猜一个会让 G10-6 的滚动表错）；
  //    ③期末读模板 O 列 `closingAdjusted`（=M+N），M 含利息（L=D+I+J）。
  it('G10-2 受管列可映射至 L3 调节行（终止确认金额不带入）', () => {
    const detail = enrichG10DetailRow({
      rowId: 'd1',
      liabilityName: '结构化负债',
      openingInitialAmount: 100,
      movementInitialAmount: 10,
      movementFvChange: 8,
      interestExpense: 2,
    }, 1)
    // K=100+10=110 · L=0+8+2=10 · M=120 · O=120
    expect(detail.closingFvAccum).toBe(10)
    expect(detail.closingAdjusted).toBe(120)
    expect(detail).not.toHaveProperty('fairValueLevel')
    expect(detail).not.toHaveProperty('currentDecrease')

    const l3 = enrichG10L3Row({
      rowId: 'l1',
      liabilityName: detail.liabilityName,
      openingBalance: detail.openingAdjusted,
      currentNew: detail.movementInitialAmount,
      fairValueChange: detail.movementFvChange,
      interestExpense: detail.interestExpense,
      reportedClosing: detail.closingAdjusted,
    })
    expect(l3.reportedClosing).toBe(detail.closingAdjusted)
    expect(l3.currentTerminated).toBe(0)
    expect(l3.fairValueChange).toBe(8)
  })
})
