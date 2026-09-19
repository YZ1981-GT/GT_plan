/**
 * k1PostPaymentFromLedger / resolveK1BsDate 单测
 */
import { describe, it, expect } from 'vitest'
import { resolveK1BsDate } from '../k1PostPaymentFromLedger'

describe('resolveK1BsDate', () => {
  it('prefers explicit ISO date', () => {
    expect(resolveK1BsDate('2025-12-31', 2024)).toBe('2025-12-31')
  })

  it('falls back to year-12-31', () => {
    expect(resolveK1BsDate('', 2025)).toBe('2025-12-31')
    expect(resolveK1BsDate(null, '2024')).toBe('2024-12-31')
  })

  it('returns empty when neither valid', () => {
    expect(resolveK1BsDate('', undefined)).toBe('')
    expect(resolveK1BsDate('bad', 1990)).toBe('')
  })
})
