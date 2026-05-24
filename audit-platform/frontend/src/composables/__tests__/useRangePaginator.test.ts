/**
 * Tests for useRangePaginator composable
 *
 * Feature: advanced-query-enhancements-p1p2
 * - Property 22: 分页阈值
 *
 * **Validates: Requirements 11.1, 11.5**
 */

import { describe, it, expect } from 'vitest'
import fc from 'fast-check'
import {
  getPaginationState,
  getPageSlice,
  PAGINATION_THRESHOLD,
  FORCE_PAGINATION_THRESHOLD,
  DEFAULT_PAGE_SIZE,
} from '../useRangePaginator'

// ---------------------------------------------------------------------------
// Property 22: Pagination threshold enforcement
// Feature: advanced-query-enhancements-p1p2, Property 22: Pagination threshold enforcement
// ---------------------------------------------------------------------------

describe('Property 22: Pagination threshold enforcement', () => {
  it('pagination enabled when rows > 100, expand disabled when rows > 5000', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 10000 }),
        (totalRows) => {
          const state = getPaginationState(totalRows)

          if (totalRows > PAGINATION_THRESHOLD) {
            expect(state.paginationEnabled).toBe(true)
          } else {
            expect(state.paginationEnabled).toBe(false)
          }

          if (totalRows > FORCE_PAGINATION_THRESHOLD) {
            expect(state.forcePagination).toBe(true)
            expect(state.expandAllDisabled).toBe(true)
          } else {
            expect(state.forcePagination).toBe(false)
            expect(state.expandAllDisabled).toBe(false)
          }
        }
      ),
      { numRuns: 20 }
    )
  })

  it('page slice returns correct subset', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 1000 }),  // totalRows
        fc.integer({ min: 1, max: 10 }),    // page
        fc.constantFrom(50, 100, 200, 500), // pageSize
        (totalRows, page, pageSize) => {
          const allRows = Array.from({ length: totalRows }, (_, i) => ({ id: i }))
          const maxPage = Math.ceil(totalRows / pageSize)
          const validPage = Math.min(page, maxPage)

          const slice = getPageSlice(allRows, validPage, pageSize)

          // Slice length should be at most pageSize
          expect(slice.length).toBeLessThanOrEqual(pageSize)

          // Slice should be a contiguous subset
          if (slice.length > 0) {
            const expectedStart = (validPage - 1) * pageSize
            expect(slice[0].id).toBe(expectedStart)
          }
        }
      ),
      { numRuns: 20 }
    )
  })

  it('boundary: exactly 100 rows does not enable pagination', () => {
    const state = getPaginationState(100)
    expect(state.paginationEnabled).toBe(false)
  })

  it('boundary: 101 rows enables pagination', () => {
    const state = getPaginationState(101)
    expect(state.paginationEnabled).toBe(true)
  })

  it('boundary: exactly 5000 rows does not force pagination', () => {
    const state = getPaginationState(5000)
    expect(state.forcePagination).toBe(false)
    expect(state.expandAllDisabled).toBe(false)
  })

  it('boundary: 5001 rows forces pagination', () => {
    const state = getPaginationState(5001)
    expect(state.forcePagination).toBe(true)
    expect(state.expandAllDisabled).toBe(true)
  })

  it('empty data does not enable pagination', () => {
    const state = getPaginationState(0)
    expect(state.paginationEnabled).toBe(false)
    expect(state.forcePagination).toBe(false)
  })

  it('getPageSlice returns empty for empty array', () => {
    const slice = getPageSlice([], 1, 100)
    expect(slice).toHaveLength(0)
  })

  it('getPageSlice handles last page with fewer items', () => {
    const allRows = Array.from({ length: 250 }, (_, i) => i)
    const slice = getPageSlice(allRows, 3, 100)
    expect(slice).toHaveLength(50)
    expect(slice[0]).toBe(200)
  })
})
