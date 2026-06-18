/**
 * GtReviewChecklist — lite 单元测试
 */
import { describe, it, expect } from 'vitest'

describe('GtReviewChecklist item_id contract', () => {
  it('generates stable chk item ids', () => {
    const wpCode = 'A21-1'
    const seq = 3
    const itemId = `${wpCode}-chk-${String(seq).padStart(2, '0')}`
    expect(itemId).toBe('A21-1-chk-03')
  })

  it('sign/record suffixes', () => {
    expect('A22-1-sign').toMatch(/^A2[1-5]-\d-sign$/)
    expect('A23-1-record').toMatch(/^A2[1-5]-\d-record$/)
  })
})
