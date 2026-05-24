/**
 * Tests for useRangeMemory composable
 *
 * Feature: advanced-query-enhancements-p1p2
 * - Property 18: save/load round-trip
 * - Property 19: LRU 容量
 * - Property 20: 越界 clamp
 */

import { describe, it, expect, beforeEach } from 'vitest'
import fc from 'fast-check'
import {
  saveRangeMemory,
  loadRangeMemory,
  clearRangeMemory,
  clearAllRangeMemory,
  clampRange,
  colLetterToNumber,
  colNumberToLetter,
  MAX_ENTRIES,
  STORAGE_KEY,
} from '../useRangeMemory'

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {}
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value },
    removeItem: (key: string) => { delete store[key] },
    clear: () => { store = {} },
  }
})()

Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock })

beforeEach(() => {
  localStorageMock.clear()
})

// ---------------------------------------------------------------------------
// Property 18: save/load round-trip
// Feature: advanced-query-enhancements-p1p2, Property 18: Range memory save/load round-trip
// **Validates: Requirements 9.1, 9.2**
// ---------------------------------------------------------------------------

describe('Property 18: Range memory save/load round-trip', () => {
  it('save then load returns same expression', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 20 }).filter(s => !s.includes(':')),  // wpCode (no colon to avoid key collision)
        fc.string({ minLength: 1, maxLength: 50 }).filter(s => !s.includes(':')),  // sheetName
        fc.string({ minLength: 1, maxLength: 100 }),  // rangeExpr
        (wpCode, sheetName, rangeExpr) => {
          const userId = 'test-user-18'
          localStorageMock.clear()
          saveRangeMemory(userId, wpCode, sheetName, rangeExpr)
          const loaded = loadRangeMemory(userId, wpCode, sheetName)
          expect(loaded).toBe(rangeExpr)
        }
      ),
      { numRuns: 20 }
    )
  })

  it('load returns null for non-existent entry', () => {
    const result = loadRangeMemory('user1', 'D2', 'Sheet1')
    expect(result).toBeNull()
  })

  it('clear removes the entry', () => {
    saveRangeMemory('user1', 'D2', 'Sheet1', 'A1:B10')
    clearRangeMemory('user1', 'D2', 'Sheet1')
    expect(loadRangeMemory('user1', 'D2', 'Sheet1')).toBeNull()
  })

  it('clearAll removes all entries', () => {
    saveRangeMemory('user1', 'D2', 'Sheet1', 'A1:B10')
    saveRangeMemory('user1', 'D3', 'Sheet2', 'C1:D5')
    clearAllRangeMemory('user1')
    expect(loadRangeMemory('user1', 'D2', 'Sheet1')).toBeNull()
    expect(loadRangeMemory('user1', 'D3', 'Sheet2')).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Property 19: LRU 容量
// Feature: advanced-query-enhancements-p1p2, Property 19: Range memory LRU capacity
// **Validates: Requirements 9.3**
// ---------------------------------------------------------------------------

describe('Property 19: LRU capacity', () => {
  it('never exceeds MAX_ENTRIES after saving more than 50 entries', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: MAX_ENTRIES + 1, max: MAX_ENTRIES + 20 }),
        (totalEntries) => {
          localStorageMock.clear()
          const userId = 'test-user-19'

          // Save more than MAX_ENTRIES entries
          for (let i = 0; i < totalEntries; i++) {
            saveRangeMemory(userId, `wp_${i}`, `sheet_${i}`, `A1:B${i + 1}`)
          }

          // Check stored count
          const stored = JSON.parse(localStorageMock.getItem(STORAGE_KEY(userId)) || '{}')
          const count = Object.keys(stored).length
          expect(count).toBeLessThanOrEqual(MAX_ENTRIES)
        }
      ),
      { numRuns: 20 }
    )
  })

  it('evicts oldest entries when exceeding capacity', () => {
    localStorageMock.clear()
    const userId = 'test-user-evict'

    // Save MAX_ENTRIES + 1 entries with increasing timestamps
    // We need to mock Date.now to control timestamps
    let mockTime = 1000000
    const originalNow = Date.now
    Date.now = () => mockTime

    try {
      for (let i = 0; i < MAX_ENTRIES + 1; i++) {
        mockTime = 1000000 + i * 1000
        saveRangeMemory(userId, `wp_${i}`, 'sheet', `A1:B${i + 1}`)
      }

      // The first entry (oldest) should be evicted
      const loaded = loadRangeMemory(userId, 'wp_0', 'sheet')
      expect(loaded).toBeNull()

      // The last entry (newest) should still exist
      const lastLoaded = loadRangeMemory(userId, `wp_${MAX_ENTRIES}`, 'sheet')
      expect(lastLoaded).toBe(`A1:B${MAX_ENTRIES + 1}`)
    } finally {
      Date.now = originalNow
    }
  })
})

// ---------------------------------------------------------------------------
// Property 20: 越界 clamp
// Feature: advanced-query-enhancements-p1p2, Property 20: Range memory bounds clamping
// **Validates: Requirements 9.5**
// ---------------------------------------------------------------------------

describe('Property 20: Range memory bounds clamping', () => {
  it('clamps range to valid bounds for any exceeding range', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 100 }),   // sheetMaxRow
        fc.integer({ min: 1, max: 26 }),    // sheetMaxCol
        fc.integer({ min: 1, max: 200 }),   // rangeRow (may exceed)
        fc.integer({ min: 1, max: 50 }),    // rangeCol (may exceed)
        (sheetMaxRow, sheetMaxCol, rangeRow, rangeCol) => {
          const colLetter = colNumberToLetter(rangeCol)
          const rangeExpr = `A1:${colLetter}${rangeRow}`

          const { clampedExpr, wasClamped } = clampRange(rangeExpr, sheetMaxRow, sheetMaxCol)

          // Parse the clamped result to verify bounds
          const cellPattern = /([A-Z]{1,3})(\d{1,7})/g
          const matches = [...clampedExpr.matchAll(cellPattern)]

          for (const m of matches) {
            const col = colLetterToNumber(m[1])
            const row = parseInt(m[2], 10)
            expect(row).toBeGreaterThanOrEqual(1)
            expect(row).toBeLessThanOrEqual(sheetMaxRow)
            expect(col).toBeGreaterThanOrEqual(1)
            expect(col).toBeLessThanOrEqual(sheetMaxCol)
          }

          // If original exceeded bounds, wasClamped should be true
          if (rangeRow > sheetMaxRow || rangeCol > sheetMaxCol) {
            expect(wasClamped).toBe(true)
          }
        }
      ),
      { numRuns: 20 }
    )
  })

  it('does not clamp when range is within bounds', () => {
    const { clampedExpr, wasClamped } = clampRange('A1:C10', 100, 26)
    expect(clampedExpr).toBe('A1:C10')
    expect(wasClamped).toBe(false)
  })

  it('clamps multi-region expressions', () => {
    const { clampedExpr, wasClamped } = clampRange('A1:Z200,AA1:AA50', 100, 26)
    expect(wasClamped).toBe(true)
    // All cells should be within bounds
    const cellPattern = /([A-Z]{1,3})(\d{1,7})/g
    const matches = [...clampedExpr.matchAll(cellPattern)]
    for (const m of matches) {
      const col = colLetterToNumber(m[1])
      const row = parseInt(m[2], 10)
      expect(row).toBeLessThanOrEqual(100)
      expect(col).toBeLessThanOrEqual(26)
    }
  })
})

// ---------------------------------------------------------------------------
// Helper function tests
// ---------------------------------------------------------------------------

describe('colLetterToNumber / colNumberToLetter', () => {
  it('round-trips correctly', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 702 }),  // A to ZZ
        (num) => {
          const letter = colNumberToLetter(num)
          const back = colLetterToNumber(letter)
          expect(back).toBe(num)
        }
      ),
      { numRuns: 20 }
    )
  })

  it('known values', () => {
    expect(colLetterToNumber('A')).toBe(1)
    expect(colLetterToNumber('Z')).toBe(26)
    expect(colLetterToNumber('AA')).toBe(27)
    expect(colNumberToLetter(1)).toBe('A')
    expect(colNumberToLetter(26)).toBe('Z')
    expect(colNumberToLetter(27)).toBe('AA')
  })
})
