import { describe, it, expect } from 'vitest'
import { isSkipWorkpaperSheet } from '../workpaperSkipSheets'
import { resolveD1SheetCode } from '../useD1SheetRouting'
import { resolveD3SheetCode } from '../useD3SheetRouting'

describe('workpaperSkipSheets', () => {
  it('GT_Custom 应跳过', () => {
    expect(isSkipWorkpaperSheet('GT_Custom')).toBe(true)
    expect(resolveD1SheetCode('GT_Custom')).toBe('skip')
    expect(resolveD3SheetCode('GT_Custom')).toBe('skip')
  })
})
