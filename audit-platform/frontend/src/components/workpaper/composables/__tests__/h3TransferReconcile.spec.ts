import { describe, it, expect } from 'vitest'
import { buildH3TransferReconcile } from '../h3TransferReconcile'
import type { TransferSummary, H1TransferData, H2TransferData } from '../h3TransferReconcile'

describe('buildH3TransferReconcile', () => {
  // P1: fromH1 diff within tolerance → ok
  it('P1: fromH1 diff = h3.fromH1 - h1.disposalToInvest, within tolerance → ok', () => {
    const h3: TransferSummary = { fromH1: 100, toH1: 200, fromH2: 300 }
    const h1: H1TransferData = { disposalToInvest: 99.5, additionFromInvest: 200 }
    const h2: H2TransferData = { cipToInvest: 300 }

    const result = buildH3TransferReconcile(h3, h1, h2)

    expect(result.diffFromH1).toBeCloseTo(0.5)
    expect(result.status).toBe('ok')
  })

  // P2: fromH2 diff exceeds tolerance → warning
  it('P2: fromH2 diff = h3.fromH2 - h2.cipToInvest, exceeds tolerance → warning', () => {
    const h3: TransferSummary = { fromH1: 100, toH1: 200, fromH2: 305 }
    const h1: H1TransferData = { disposalToInvest: 100, additionFromInvest: 200 }
    const h2: H2TransferData = { cipToInvest: 300 }

    const result = buildH3TransferReconcile(h3, h1, h2)

    expect(result.diffFromH2).toBe(5)
    expect(result.status).toBe('warning')
  })

  // P3: toH1 diff exact match → ok
  it('P3: toH1 diff = h3.toH1 - h1.additionFromInvest, exact match → ok', () => {
    const h3: TransferSummary = { fromH1: 100, toH1: 200, fromH2: 300 }
    const h1: H1TransferData = { disposalToInvest: 100, additionFromInvest: 200 }
    const h2: H2TransferData = { cipToInvest: 300 }

    const result = buildH3TransferReconcile(h3, h1, h2)

    expect(result.diffToH1).toBe(0)
    expect(result.status).toBe('ok')
  })

  // P6: All H1/H2 data null → status = 'unavailable'
  it('P6: all H1/H2 data null → status unavailable', () => {
    const h3: TransferSummary = { fromH1: 100, toH1: 200, fromH2: 300 }
    const h1: H1TransferData = { disposalToInvest: null, additionFromInvest: null }
    const h2: H2TransferData = { cipToInvest: null }

    const result = buildH3TransferReconcile(h3, h1, h2)

    expect(result.status).toBe('unavailable')
    expect(result.diffFromH1).toBeNull()
    expect(result.diffToH1).toBeNull()
    expect(result.diffFromH2).toBeNull()
    expect(result.h3FromH1).toBe(100)
    expect(result.h3ToH1).toBe(200)
    expect(result.h3FromH2).toBe(300)
  })

  // P7: H1 data null + H2 has data → diff for H1 is null, status based only on H2
  it('P7: H1 null + H2 has data → H1 diffs null, status based on H2 only', () => {
    const h3: TransferSummary = { fromH1: 100, toH1: 200, fromH2: 300 }
    const h1: H1TransferData = { disposalToInvest: null, additionFromInvest: null }
    const h2: H2TransferData = { cipToInvest: 300 }

    const result = buildH3TransferReconcile(h3, h1, h2)

    expect(result.diffFromH1).toBeNull()
    expect(result.diffToH1).toBeNull()
    expect(result.diffFromH2).toBe(0)
    // H2 diff is 0 (within tolerance), so status should be ok
    expect(result.status).toBe('ok')
  })

  // Normal case: all match within tolerance → status 'ok'
  it('normal case: all diffs within tolerance → status ok', () => {
    const h3: TransferSummary = { fromH1: 1000, toH1: 2000, fromH2: 3000 }
    const h1: H1TransferData = { disposalToInvest: 1000.5, additionFromInvest: 1999.5 }
    const h2: H2TransferData = { cipToInvest: 2999.5 }

    const result = buildH3TransferReconcile(h3, h1, h2)

    expect(result.diffFromH1).toBeCloseTo(-0.5)
    expect(result.diffToH1).toBeCloseTo(0.5)
    expect(result.diffFromH2).toBeCloseTo(0.5)
    expect(result.status).toBe('ok')
  })

  // Warning case: one direction has diff > 1 → status 'warning'
  it('warning case: one direction has diff > TOLERANCE(1) → status warning', () => {
    const h3: TransferSummary = { fromH1: 100, toH1: 200, fromH2: 300 }
    const h1: H1TransferData = { disposalToInvest: 100, additionFromInvest: 197 }
    const h2: H2TransferData = { cipToInvest: 300 }

    const result = buildH3TransferReconcile(h3, h1, h2)

    // toH1 diff = 200 - 197 = 3, exceeds tolerance
    expect(result.diffToH1).toBe(3)
    expect(result.status).toBe('warning')
  })
})
