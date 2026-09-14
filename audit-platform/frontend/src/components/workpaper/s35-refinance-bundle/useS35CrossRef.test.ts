/**
 * useS35CrossRef.test.ts — S35 跨底稿引用纯函数测试
 *
 * Spec: .kiro/specs/s35-refinancing-bundle/
 * Task: 5.1
 * Requirements: 7.1, 7.2, 7.3, 7.4
 */
import { describe, it, expect } from 'vitest'
import { isS35InternalRef, getS35TabFromRef } from './useS35CrossRef'

describe('isS35InternalRef', () => {
  it('recognizes S35 Tab-level refs', () => {
    expect(isS35InternalRef('S35-1')).toBe(true)
    expect(isS35InternalRef('S35-2')).toBe(true)
    expect(isS35InternalRef('S35-3')).toBe(true)
    expect(isS35InternalRef('S35-4')).toBe(true)
    expect(isS35InternalRef('S35-5')).toBe(true)
  })

  it('recognizes S35 sub-sheet refs', () => {
    expect(isS35InternalRef('S35-1-1')).toBe(true)
    expect(isS35InternalRef('S35-2-1')).toBe(true)
    expect(isS35InternalRef('S35-3-1')).toBe(true)
  })

  it('rejects parent bundle code', () => {
    expect(isS35InternalRef('S35')).toBe(false)
  })

  it('rejects external workpaper codes', () => {
    expect(isS35InternalRef('D4-24')).toBe(false)
    expect(isS35InternalRef('B23-1')).toBe(false)
    expect(isS35InternalRef('S34-1')).toBe(false)
    expect(isS35InternalRef('A13')).toBe(false)
    expect(isS35InternalRef('')).toBe(false)
  })
})

describe('getS35TabFromRef', () => {
  it('extracts Tab ID from sub-sheet ref', () => {
    expect(getS35TabFromRef('S35-1-1')).toBe('S35-1')
    expect(getS35TabFromRef('S35-2-1')).toBe('S35-2')
    expect(getS35TabFromRef('S35-3-1')).toBe('S35-3')
  })

  it('returns Tab-level ref as-is', () => {
    expect(getS35TabFromRef('S35-1')).toBe('S35-1')
    expect(getS35TabFromRef('S35-4')).toBe('S35-4')
    expect(getS35TabFromRef('S35-5')).toBe('S35-5')
  })

  it('returns non-matching ref unchanged', () => {
    expect(getS35TabFromRef('D4-24')).toBe('D4-24')
    expect(getS35TabFromRef('B23')).toBe('B23')
  })
})
