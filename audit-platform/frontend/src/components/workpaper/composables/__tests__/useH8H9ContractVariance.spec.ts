/**
 * buildH8H9ContractVariance — 按合同 CAS21 差额
 */
import { describe, it, expect } from 'vitest'
import { buildH8H9ContractVariance } from '../useH8CrossSheet'

describe('buildH8H9ContractVariance', () => {
  it('skips matching contracts within ±1', () => {
    const rows = buildH8H9ContractVariance([
      { contractNo: 'ZL-1', initialAmount: 101000, h9Initial: 100000, directCost: 1000, incentive: 0 },
    ])
    expect(rows).toHaveLength(0)
  })

  it('flags contract when H8 ≠ H9+direct−incentive', () => {
    const rows = buildH8H9ContractVariance([
      {
        contractNo: 'ZL-BAD',
        assetName: '办公楼',
        initialAmount: 120000,
        h9Initial: 100000,
        directCost: 1000,
        incentive: 0,
      },
    ])
    expect(rows).toHaveLength(1)
    expect(rows[0].contractNo).toBe('ZL-BAD')
    expect(rows[0].expected).toBe(101000)
    expect(rows[0].diff).toBe(19000)
  })

  it('prefers H9-2 join over row h9Initial', () => {
    const rows = buildH8H9ContractVariance(
      [{ contractNo: 'ZL-2', initialAmount: 50000, h9Initial: 1, directCost: 0, incentive: 0 }],
      [{ contractNo: 'ZL-2', auditedBegin: 50000 }],
    )
    expect(rows).toHaveLength(0)
  })
})
