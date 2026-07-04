/**
 * useF2StocktakeOcr — sheet 类型与字段映射
 */
import { describe, it, expect } from 'vitest'
import type { F2StOcrSheet } from '../useF2StocktakeOcr'

const VALID: F2StOcrSheet[] = ['F2-24', 'F2-25', 'F2-26']

describe('F2StOcrSheet contract', () => {
  it('仅支持 F2-24/25/26 行级 OCR', () => {
    expect(VALID).toEqual(['F2-24', 'F2-25', 'F2-26'])
    expect(VALID).not.toContain('F2-21' as F2StOcrSheet)
  })
})
