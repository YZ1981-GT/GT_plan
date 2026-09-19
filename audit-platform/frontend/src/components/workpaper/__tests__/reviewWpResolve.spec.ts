import { describe, it, expect } from 'vitest'
import { isReviewRoleRef, resolveReviewWpCode } from '../reviewWpResolve'

describe('reviewWpResolve', () => {
  const templates = {
    'A21-1': { applicable: true, mandatory: true },
    'A21-2': { applicable: false, mandatory: false },
    'A24-1': { applicable: false, mandatory: false },
  }

  it('detects review role refs', () => {
    expect(isReviewRoleRef('A21')).toBe(true)
    expect(isReviewRoleRef('A21-1')).toBe(true)
    expect(isReviewRoleRef('A17-3')).toBe(false)
  })

  it('resolves parent A21 to applicable subcode', () => {
    expect(resolveReviewWpCode('A21', templates)).toBe('A21-1')
  })

  it('falls back when only inapplicable subcodes exist', () => {
    expect(resolveReviewWpCode('A24', templates)).toBe('A24-1')
  })
})
