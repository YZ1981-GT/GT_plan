/**
 * Unit + PBT Tests — useS35BundleState 完成进度纯函数（Task 3.2）
 *
 * Spec: .kiro/specs/s35-refinancing-bundle/
 * Task: 3.2 completionMap + progressSummary + refreshCompletion
 *
 * 测试 deriveProgramStatus / computeCompletionMap / computeProgressSummary 纯函数。
 * fast-check ≥ 100 次迭代。
 *
 * **Validates: Requirements 8.1**
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  deriveProgramStatus,
  computeCompletionMap,
  computeProgressSummary,
  type CompletionStatus,
  type ChecklistResponse,
  type ProgressSummary,
} from './useS35BundleState'

// ─── 生成器 ───

const conclusionArb = fc.oneof(
  fc.constant(null),
  fc.constant(undefined),
  fc.constant(''),
  fc.constant('   '), // whitespace-only should count as empty
  fc.string({ minLength: 1, maxLength: 50 }).filter(s => s.trim().length > 0),
)

const responseArb: fc.Arbitrary<ChecklistResponse> = fc.record({
  item_id: fc.string({ minLength: 1, maxLength: 20 }),
  conclusion: conclusionArb,
  remark: fc.option(fc.string(), { nil: null }),
})

const statusArb: fc.Arbitrary<CompletionStatus> = fc.constantFrom(
  'completed', 'in_progress', 'not_started',
)

// ─── deriveProgramStatus ───

describe('deriveProgramStatus', () => {
  it('empty array → not_started', () => {
    expect(deriveProgramStatus([])).toBe('not_started')
  })

  it('all conclusions filled → completed', () => {
    const responses: ChecklistResponse[] = [
      { item_id: '1', conclusion: '已完成' },
      { item_id: '2', conclusion: '无异常' },
    ]
    expect(deriveProgramStatus(responses)).toBe('completed')
  })

  it('no conclusions filled → not_started', () => {
    const responses: ChecklistResponse[] = [
      { item_id: '1', conclusion: null },
      { item_id: '2', conclusion: '' },
      { item_id: '3', conclusion: '   ' },
    ]
    expect(deriveProgramStatus(responses)).toBe('not_started')
  })

  it('partial conclusions → in_progress', () => {
    const responses: ChecklistResponse[] = [
      { item_id: '1', conclusion: '已完成' },
      { item_id: '2', conclusion: null },
    ]
    expect(deriveProgramStatus(responses)).toBe('in_progress')
  })

  it('[PBT] result is always a valid CompletionStatus', () => {
    fc.assert(
      fc.property(
        fc.array(responseArb, { minLength: 0, maxLength: 20 }),
        (responses) => {
          const status = deriveProgramStatus(responses)
          expect(['completed', 'in_progress', 'not_started']).toContain(status)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('[PBT] all filled → completed or empty → not_started', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            item_id: fc.string({ minLength: 1 }),
            conclusion: fc.string({ minLength: 1 }).filter(s => s.trim().length > 0),
          }),
          { minLength: 1, maxLength: 10 },
        ),
        (responses) => {
          expect(deriveProgramStatus(responses)).toBe('completed')
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── computeCompletionMap ───

describe('computeCompletionMap', () => {
  it('returns status for each visible wpCode', () => {
    const cache: Record<string, ChecklistResponse[]> = {
      'S35-1': [{ item_id: '1', conclusion: '已完成' }],
      'S35-2': [{ item_id: '1', conclusion: null }],
    }
    const map = computeCompletionMap(['S35-1', 'S35-2', 'S35-3'], cache)
    expect(map['S35-1']).toBe('completed')
    expect(map['S35-2']).toBe('not_started')
    expect(map['S35-3']).toBe('not_started') // no cache entry → empty → not_started
  })

  it('[PBT] keys of result match input wpCodes', () => {
    const wpCodeArb = fc.constantFrom('S35-1', 'S35-2', 'S35-3', 'S35-4', 'S35-5')
    fc.assert(
      fc.property(
        fc.uniqueArray(wpCodeArb, { minLength: 1, maxLength: 5 }),
        fc.dictionary(
          wpCodeArb,
          fc.array(responseArb, { maxLength: 5 }),
        ),
        (wpCodes, cache) => {
          const map = computeCompletionMap(wpCodes, cache)
          expect(Object.keys(map).sort()).toEqual([...wpCodes].sort())
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── computeProgressSummary ───

describe('computeProgressSummary', () => {
  it('empty map → all zeros', () => {
    const summary = computeProgressSummary({})
    expect(summary).toEqual({ completed: 0, inProgress: 0, notStarted: 0 })
  })

  it('counts match completionMap entries', () => {
    const map: Record<string, CompletionStatus> = {
      'S35-1': 'completed',
      'S35-2': 'in_progress',
      'S35-3': 'not_started',
      'S35-4': 'completed',
      'S35-5': 'not_started',
    }
    const summary = computeProgressSummary(map)
    expect(summary).toEqual({ completed: 2, inProgress: 1, notStarted: 2 })
  })

  it('[PBT] Property 6: sum of counts == number of entries', () => {
    fc.assert(
      fc.property(
        fc.dictionary(
          fc.constantFrom('S35-1', 'S35-2', 'S35-3', 'S35-4', 'S35-5'),
          statusArb,
        ),
        (completionMap) => {
          const summary = computeProgressSummary(completionMap)
          const total = summary.completed + summary.inProgress + summary.notStarted
          expect(total).toBe(Object.keys(completionMap).length)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('[PBT] Property 6: counts are non-negative', () => {
    fc.assert(
      fc.property(
        fc.dictionary(
          fc.constantFrom('S35-1', 'S35-2', 'S35-3', 'S35-4', 'S35-5'),
          statusArb,
        ),
        (completionMap) => {
          const summary = computeProgressSummary(completionMap)
          expect(summary.completed).toBeGreaterThanOrEqual(0)
          expect(summary.inProgress).toBeGreaterThanOrEqual(0)
          expect(summary.notStarted).toBeGreaterThanOrEqual(0)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('[PBT] Property 6: all completed → inProgress=0 & notStarted=0', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 5 }),
        (n) => {
          const map: Record<string, CompletionStatus> = {}
          for (let i = 1; i <= n; i++) map[`S35-${i}`] = 'completed'
          const summary = computeProgressSummary(map)
          expect(summary.completed).toBe(n)
          expect(summary.inProgress).toBe(0)
          expect(summary.notStarted).toBe(0)
        },
      ),
      { numRuns: 100 },
    )
  })
})
