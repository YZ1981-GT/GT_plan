/**
 * Tests for SnapshotStalenessChip variant selection
 *
 * Feature: advanced-query-enhancements-p1p2
 * - Property 21: chip 变体选择
 *
 * **Validates: Requirements 10.1, 10.2, 10.4, 10.5**
 */

import { describe, it, expect } from 'vitest'
import fc from 'fast-check'
import { getChipVariant } from '../../components/custom-query/SnapshotStalenessChip.vue'

// ---------------------------------------------------------------------------
// Property 21: Staleness chip variant selection
// Feature: advanced-query-enhancements-p1p2, Property 21: Staleness chip variant selection
// ---------------------------------------------------------------------------

describe('Property 21: Staleness chip variant selection', () => {
  it('correctly selects chip variant for all (source, saved_at) combinations', () => {
    const now = Date.now()

    fc.assert(
      fc.property(
        fc.oneof(
          fc.constant('univer_snapshot'),
          fc.constant('xlsx_recomputed'),
          fc.constant('xlsx_cache')
        ),
        fc.oneof(
          fc.constant(null as string | null),
          // saved_at > 30 days ago
          fc.integer({ min: 31, max: 365 }).map(days =>
            new Date(now - days * 24 * 60 * 60 * 1000).toISOString()
          ),
          // saved_at ≤ 30 days ago
          fc.integer({ min: 0, max: 30 }).map(days =>
            new Date(now - days * 24 * 60 * 60 * 1000).toISOString()
          )
        ),
        (source, savedAt) => {
          const result = getChipVariant(source, savedAt)

          if (source === 'xlsx_recomputed') {
            // Always blue chip
            expect(result).not.toBeNull()
            expect(result!.type).toBe('primary')
            expect(result!.label).toContain('重算结果')
          } else if (source === 'xlsx_cache') {
            // Always gray chip
            expect(result).not.toBeNull()
            expect(result!.type).toBe('info')
            expect(result!.label).toContain('模板数据')
          } else if (source === 'univer_snapshot') {
            if (savedAt === null) {
              // Missing saved_at → gray "unknown" chip
              expect(result).not.toBeNull()
              expect(result!.type).toBe('info')
              expect(result!.label).toContain('数据时间未知')
            } else {
              const saved = new Date(savedAt)
              const daysDiff = Math.floor((now - saved.getTime()) / (1000 * 60 * 60 * 24))
              if (daysDiff > 30) {
                // Orange warning chip
                expect(result).not.toBeNull()
                expect(result!.type).toBe('warning')
                expect(result!.label).toContain('数据可能过时')
              } else {
                // No chip
                expect(result).toBeNull()
              }
            }
          }
        }
      ),
      { numRuns: 20 }
    )
  })

  it('xlsx_recomputed always returns blue chip regardless of saved_at', () => {
    const result1 = getChipVariant('xlsx_recomputed', null)
    expect(result1).not.toBeNull()
    expect(result1!.type).toBe('primary')

    const result2 = getChipVariant('xlsx_recomputed', '2020-01-01T00:00:00Z')
    expect(result2).not.toBeNull()
    expect(result2!.type).toBe('primary')
  })

  it('xlsx_cache always returns gray chip regardless of saved_at', () => {
    const result1 = getChipVariant('xlsx_cache', null)
    expect(result1).not.toBeNull()
    expect(result1!.type).toBe('info')
    expect(result1!.label).toContain('模板数据')

    const result2 = getChipVariant('xlsx_cache', new Date().toISOString())
    expect(result2).not.toBeNull()
    expect(result2!.type).toBe('info')
  })

  it('univer_snapshot with null saved_at returns unknown chip', () => {
    const result = getChipVariant('univer_snapshot', null)
    expect(result).not.toBeNull()
    expect(result!.label).toContain('数据时间未知')
  })

  it('univer_snapshot with recent saved_at returns null (no chip)', () => {
    const recent = new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString() // 5 days ago
    const result = getChipVariant('univer_snapshot', recent)
    expect(result).toBeNull()
  })

  it('univer_snapshot with old saved_at returns warning chip', () => {
    const old = new Date(Date.now() - 60 * 24 * 60 * 60 * 1000).toISOString() // 60 days ago
    const result = getChipVariant('univer_snapshot', old)
    expect(result).not.toBeNull()
    expect(result!.type).toBe('warning')
    expect(result!.label).toContain('数据可能过时')
  })
})
