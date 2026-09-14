import { describe, it, expect } from 'vitest'
import {
  calcFvAllocationCheck,
  calcNetHedgePnl,
  summarizeG12NetHedgeDetailRows,
} from '../g12NetHedgeDetailCalc'

describe('g12NetHedgeDetailCalc', () => {
  it('calcFvAllocationCheck matches Excel sample', () => {
    expect(calcFvAllocationCheck(-200_000, 1_000_000, -1_200_000)).toBe(true)
    expect(calcFvAllocationCheck(-200_000, 1_000_000, -1_000_000)).toBe(false)
  })

  it('calcNetHedgePnl: FV row uses sales portion, amortization row uses adj', () => {
    expect(calcNetHedgePnl({
      rowKind: 'fv_allocation',
      instrumentFvCumulative: -200_000,
      salesPortion: 1_000_000,
      purchasePortion: -1_200_000,
      hedgeAdjAmortization: 0,
    })).toBe(1_000_000)

    expect(calcNetHedgePnl({
      rowKind: 'amortization',
      instrumentFvCumulative: 0,
      salesPortion: 0,
      purchasePortion: 0,
      hedgeAdjAmortization: -240_000,
    })).toBe(-240_000)
  })

  it('summarize totals match Excel sample 760,000', () => {
    const totals = summarizeG12NetHedgeDetailRows([
      {
        rowKind: 'fv_allocation',
        instrumentFvCumulative: -200_000,
        salesPortion: 1_000_000,
        purchasePortion: -1_200_000,
        hedgeAdjAmortization: 0,
      },
      {
        rowKind: 'amortization',
        instrumentFvCumulative: 0,
        salesPortion: 0,
        purchasePortion: 0,
        hedgeAdjAmortization: -240_000,
      },
    ])
    expect(totals.netHedgePnl).toBe(760_000)
    expect(totals.fvCheckFailCount).toBe(0)
  })
})
