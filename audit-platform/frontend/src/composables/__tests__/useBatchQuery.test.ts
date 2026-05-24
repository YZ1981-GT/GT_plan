/**
 * Tests for useBatchQuery composable
 *
 * Feature: advanced-query-enhancements-p1p2
 * - Property 1: 批量故障隔离 (frontend concurrency logic)
 * - Property 2: 并发限制 ≤ 5
 * - 空集合阻断 vitest
 * - 批量查询 e2e (integration)
 */

import { describe, it, expect, vi } from 'vitest'
import fc from 'fast-check'
import { executeWithConcurrencyLimit } from '../useBatchQuery'

// ---------------------------------------------------------------------------
// Property 1: 批量故障隔离
// Feature: advanced-query-enhancements-p1p2, Property 1: Batch fault isolation
// ---------------------------------------------------------------------------

describe('Property 1: Batch fault isolation', () => {
  it('failed tasks do not block successful ones', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.integer({ min: 1, max: 20 }),
        fc.integer({ min: 0, max: 20 }),
        async (nTotal, nFail) => {
          nFail = Math.min(nFail, nTotal)
          const nSuccess = nTotal - nFail

          const failIndices = new Set(
            Array.from({ length: nFail }, (_, i) => i)
          )

          const tasks = Array.from({ length: nTotal }, (_, i) => {
            return async () => {
              if (failIndices.has(i)) {
                throw new Error(`fail_${i}`)
              }
              return { wpCode: `D${i + 1}`, data: { rows: [{ x: 1 }], columns: ['x'], total: 1 } }
            }
          })

          const results = await executeWithConcurrencyLimit(tasks, 5)

          // All tasks should have a result
          expect(results.length).toBe(nTotal)

          // Count fulfilled vs rejected
          const fulfilled = results.filter(r => r.status === 'fulfilled')
          const rejected = results.filter(r => r.status === 'rejected')

          expect(fulfilled.length).toBe(nSuccess)
          expect(rejected.length).toBe(nFail)

          // Successful results have correct data
          for (const r of fulfilled) {
            if (r.status === 'fulfilled') {
              expect(r.value).toHaveProperty('wpCode')
              expect(r.value).toHaveProperty('data')
            }
          }
        }
      ),
      { numRuns: 20 }
    )
  })
})

// ---------------------------------------------------------------------------
// Property 2: 并发限制 ≤ 5
// Feature: advanced-query-enhancements-p1p2, Property 2: Batch concurrency limit
// ---------------------------------------------------------------------------

describe('Property 2: Batch concurrency limit ≤ 5', () => {
  it('never exceeds 5 concurrent tasks', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.integer({ min: 6, max: 20 }),
        async (nCodes) => {
          let maxConcurrent = 0
          let currentConcurrent = 0

          const tasks = Array.from({ length: nCodes }, (_, i) => {
            return async () => {
              currentConcurrent++
              if (currentConcurrent > maxConcurrent) {
                maxConcurrent = currentConcurrent
              }
              // Simulate async work
              await new Promise(resolve => setTimeout(resolve, 10))
              currentConcurrent--
              return { wpCode: `D${i + 1}`, data: {} }
            }
          })

          await executeWithConcurrencyLimit(tasks, 5)

          expect(maxConcurrent).toBeLessThanOrEqual(5)
        }
      ),
      { numRuns: 20 }
    )
  })

  it('uses fewer workers when tasks < 5', async () => {
    let maxConcurrent = 0
    let currentConcurrent = 0

    const tasks = Array.from({ length: 3 }, (_, i) => {
      return async () => {
        currentConcurrent++
        if (currentConcurrent > maxConcurrent) {
          maxConcurrent = currentConcurrent
        }
        await new Promise(resolve => setTimeout(resolve, 20))
        currentConcurrent--
        return { wpCode: `D${i + 1}` }
      }
    })

    await executeWithConcurrencyLimit(tasks, 5)

    expect(maxConcurrent).toBeLessThanOrEqual(3)
  })
})

// ---------------------------------------------------------------------------
// 空集合阻断 vitest
// ---------------------------------------------------------------------------

describe('Empty set blocking', () => {
  it('should not execute when wpCodes is empty', async () => {
    const tasks: (() => Promise<any>)[] = []
    const results = await executeWithConcurrencyLimit(tasks, 5)
    expect(results).toHaveLength(0)
  })

  it('executeWithConcurrencyLimit handles single item', async () => {
    const tasks = [async () => ({ wpCode: 'D1', data: { rows: [] } })]
    const results = await executeWithConcurrencyLimit(tasks, 5)
    expect(results).toHaveLength(1)
    expect(results[0].status).toBe('fulfilled')
  })
})

// ---------------------------------------------------------------------------
// 批量查询 e2e (integration test for the concurrency logic)
// ---------------------------------------------------------------------------

describe('Batch query e2e integration', () => {
  it('processes all items and returns correct structure', async () => {
    const wpCodes = ['D2', 'D3', 'D5', 'E1', 'F1', 'G1', 'H1']

    const tasks = wpCodes.map((code, i) => {
      return async () => {
        // Simulate varying response times
        await new Promise(resolve => setTimeout(resolve, Math.random() * 20))
        if (code === 'G1') {
          throw new Error('simulated network error')
        }
        return {
          wpCode: code,
          data: {
            rows: [{ wp_code: code, amount: (i + 1) * 100 }],
            columns: ['wp_code', 'amount'],
            total: 1,
            source: 'univer_snapshot',
          },
        }
      }
    })

    const results = await executeWithConcurrencyLimit(tasks, 5)

    expect(results).toHaveLength(7)

    // G1 should be rejected
    const g1Result = results[wpCodes.indexOf('G1')]
    expect(g1Result.status).toBe('rejected')

    // Others should be fulfilled
    const successResults = results.filter(r => r.status === 'fulfilled')
    expect(successResults).toHaveLength(6)

    // Each fulfilled result has correct structure
    for (const r of successResults) {
      if (r.status === 'fulfilled') {
        expect(r.value.data).toHaveProperty('rows')
        expect(r.value.data).toHaveProperty('columns')
        expect(r.value.data).toHaveProperty('total')
      }
    }
  })

  it('maintains order of results matching input order', async () => {
    const wpCodes = ['A1', 'B2', 'C3', 'D4', 'E5', 'F6']

    const tasks = wpCodes.map((code) => {
      return async () => {
        // Random delay to test ordering
        await new Promise(resolve => setTimeout(resolve, Math.random() * 30))
        return { wpCode: code }
      }
    })

    const results = await executeWithConcurrencyLimit(tasks, 5)

    // Results should be in same order as input
    for (let i = 0; i < wpCodes.length; i++) {
      const r = results[i]
      if (r.status === 'fulfilled') {
        expect(r.value.wpCode).toBe(wpCodes[i])
      }
    }
  })
})
