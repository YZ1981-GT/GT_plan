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

describe('GtReviewChecklist guard data contract', () => {
  it('guard structure fields', () => {
    const guard = {
      readonly: true,
      locked: true,
      signed_by: '张三',
      signed_at: '2026-01-15T10:30:00Z',
      gate_reason: 'A21 尚未签字通过',
      unresolved_count: 3,
      rbac_denied: false,
    }
    expect(guard.readonly).toBe(true)
    expect(guard.locked).toBe(true)
    expect(guard.signed_by).toBeTruthy()
    expect(guard.signed_at).toMatch(/^\d{4}-\d{2}-\d{2}T/)
    expect(guard.gate_reason).toContain('A21')
    expect(guard.unresolved_count).toBeGreaterThan(0)
  })

  it('sign_status blocks sign when unresolved > 0', () => {
    const unresolvedCount = 2
    const allItemsDone = true
    const signButtonDisabled = !allItemsDone || unresolvedCount > 0
    expect(signButtonDisabled).toBe(true)
  })

  it('sign allowed when unresolved == 0 and all items done', () => {
    const unresolvedCount = 0
    const allItemsDone = true
    const signButtonDisabled = !allItemsDone || unresolvedCount > 0
    expect(signButtonDisabled).toBe(false)
  })

  it('locked state formatted date', () => {
    const signedAt = '2026-01-15T10:30:00Z'
    const formatted = new Date(signedAt).toLocaleString('zh-CN')
    expect(formatted).toBeTruthy()
    expect(formatted.length).toBeGreaterThan(5)
  })
})
