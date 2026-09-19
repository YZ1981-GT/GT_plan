/**
 * Property-Based Tests — D2-7 方法学纯函数 (P11, P12, P16)
 *
 * Spec: .kiro/specs/d2-7-voucher-check-enhancement/
 * Task: 2.3
 *
 * 使用 fast-check + vitest，numRuns=100 验证：
 * - Property 11: 特定样本标记规则（markSpecificSamples）
 * - Property 12: 抽样总体算术不变量（computeSamplingPopulation）
 * - Property 16: 样本量偏离指示器（computeSampleSizeDeviation）
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  markSpecificSamples,
  computeSamplingPopulation,
  computeSampleSizeDeviation,
  isAbnormalDate,
  type TransactionItem,
  type PopulationDesc,
  type SpecificSampleItem,
} from '../useD2VcMethodology'

const RUNS = { numRuns: 100 }

// ─── Shared Generators ─────────────────────────────────────────────────────

/** Generate a valid YYYY-MM-DD date string */
const arbDateStr: fc.Arbitrary<string> = fc
  .tuple(
    fc.integer({ min: 2020, max: 2026 }),
    fc.integer({ min: 1, max: 12 }),
    fc.integer({ min: 1, max: 28 }), // stay safe with days
  )
  .map(([y, m, d]) => `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`)

/** Generate a weekend date (Saturday or Sunday) */
const arbWeekendDate: fc.Arbitrary<string> = fc
  .tuple(
    fc.integer({ min: 2020, max: 2026 }),
    fc.integer({ min: 1, max: 12 }),
  )
  .chain(([y, m]) => {
    // Find the first Saturday in this month
    const firstDay = new Date(y, m - 1, 1)
    const dayOfWeek = firstDay.getDay()
    // Saturday = 6, next Saturday from day 1
    const firstSat = dayOfWeek <= 6 ? 1 + (6 - dayOfWeek) : 1
    const maxDay = new Date(y, m, 0).getDate() // last day of month
    const satDays: number[] = []
    for (let d = firstSat; d <= maxDay; d += 7) satDays.push(d)
    // Sunday = Saturday + 1 (if within month)
    const sunDays: number[] = satDays.map(d => d + 1).filter(d => d <= maxDay)
    const allWeekendDays = [...satDays, ...sunDays]
    if (allWeekendDays.length === 0) return fc.constant(`${y}-${String(m).padStart(2, '0')}-01`)
    return fc.constantFrom(...allWeekendDays).map(
      d => `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`
    )
  })

/** Generate a date in the Dec 25-31 range (period-end cluster) */
const arbPeriodEndDate: fc.Arbitrary<string> = fc
  .tuple(
    fc.integer({ min: 2020, max: 2026 }),
    fc.integer({ min: 25, max: 31 }),
  )
  .map(([y, d]) => `${y}-12-${String(d).padStart(2, '0')}`)

/** Generate a normal business day date (weekday, not Dec 25+) */
const arbNormalDate: fc.Arbitrary<string> = fc
  .tuple(
    fc.integer({ min: 2020, max: 2026 }),
    fc.integer({ min: 1, max: 11 }), // exclude December to avoid period-end
    fc.integer({ min: 1, max: 28 }),
  )
  .filter(([y, m, d]) => {
    const date = new Date(y, m - 1, d)
    const dow = date.getDay()
    return dow !== 0 && dow !== 6 // must be weekday
  })
  .map(([y, m, d]) => `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`)

/** Generate a TransactionItem */
function arbTransaction(opts?: {
  amountRange?: [number, number]
  isRelatedParty?: boolean
  dateArb?: fc.Arbitrary<string>
}): fc.Arbitrary<TransactionItem> {
  const [minAmt, maxAmt] = opts?.amountRange ?? [0, 10000000]
  return fc.record({
    id: fc.uuid(),
    customerName: fc.string({ minLength: 1, maxLength: 10 }),
    amount: fc.integer({ min: minAmt, max: maxAmt }),
    isRelatedParty: opts?.isRelatedParty !== undefined
      ? fc.constant(opts.isRelatedParty)
      : fc.boolean(),
    transactionDate: opts?.dateArb ?? arbDateStr,
  })
}

// ═══════════════════════════════════════════════════════════════════════════
// Property 11: Specific sample marking rules
// ═══════════════════════════════════════════════════════════════════════════

describe('Feature: d2-7-voucher-check-enhancement, Property 11: Specific sample marking rules', () => {
  /**
   * **Validates: Requirements 8.1**
   *
   * For any transaction with amount A, party type (related/normal), and date
   * characteristics: given tolerable misstatement T, the transaction is marked
   * as specific sample if and only if (A >= T) OR (party == related) OR
   * (date is abnormal: weekend or Dec 25+).
   */

  it('transaction is marked iff (amount >= T) OR (isRelatedParty) OR (abnormal date)', () => {
    fc.assert(
      fc.property(
        fc.array(arbTransaction(), { minLength: 1, maxLength: 20 }),
        fc.integer({ min: 1, max: 5000000 }), // tolerableMisstatement > 0
        (transactions, T) => {
          const result = markSpecificSamples(transactions, T)
          const markedIds = new Set(result.map(r => r.id))

          for (const tx of transactions) {
            const shouldBeMarked =
              tx.amount >= T ||
              tx.isRelatedParty === true ||
              (tx.transactionDate ? isAbnormalDate(tx.transactionDate) : false)

            if (shouldBeMarked) {
              expect(markedIds.has(tx.id)).toBe(true)
            } else {
              expect(markedIds.has(tx.id)).toBe(false)
            }
          }
        },
      ),
      RUNS,
    )
  })

  it('amount >= T always produces a marking with reason containing "金额"', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 1000000 }), // T
        fc.integer({ min: 0, max: 1000000 }), // extra >= 0 so amount = T + extra >= T
        fc.string({ minLength: 1, maxLength: 5 }), // customerName
        (T, extra, name) => {
          const tx: TransactionItem = {
            id: 'test-1',
            customerName: name,
            amount: T + extra,
            isRelatedParty: false,
            transactionDate: '2024-03-05', // a Wednesday, not Dec
          }
          const result = markSpecificSamples([tx], T)
          expect(result.length).toBe(1)
          expect(result[0].reason).toContain('金额')
        },
      ),
      RUNS,
    )
  })

  it('related party always produces a marking with reason containing "关联方"', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1000000, max: 5000000 }), // T (very high so amount won't trigger)
        fc.integer({ min: 1, max: 100 }), // amount (small, below T)
        fc.string({ minLength: 1, maxLength: 5 }),
        (T, amount, name) => {
          const tx: TransactionItem = {
            id: 'test-2',
            customerName: name,
            amount,
            isRelatedParty: true,
            transactionDate: '2024-03-05', // normal date
          }
          const result = markSpecificSamples([tx], T)
          expect(result.length).toBe(1)
          expect(result[0].reason).toContain('关联方')
        },
      ),
      RUNS,
    )
  })

  it('abnormal date (weekend) always produces a marking with reason containing "异常日期"', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1000000, max: 5000000 }), // T (high)
        fc.integer({ min: 1, max: 100 }), // amount (small)
        arbWeekendDate,
        (T, amount, weekendDate) => {
          const tx: TransactionItem = {
            id: 'test-3',
            customerName: 'Client',
            amount,
            isRelatedParty: false,
            transactionDate: weekendDate,
          }
          const result = markSpecificSamples([tx], T)
          expect(result.length).toBe(1)
          expect(result[0].reason).toContain('异常日期')
        },
      ),
      RUNS,
    )
  })

  it('abnormal date (Dec 25+) always produces a marking with reason containing "异常日期"', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1000000, max: 5000000 }), // T (high)
        fc.integer({ min: 1, max: 100 }), // amount (small)
        arbPeriodEndDate,
        (T, amount, periodEndDate) => {
          const tx: TransactionItem = {
            id: 'test-4',
            customerName: 'Client',
            amount,
            isRelatedParty: false,
            transactionDate: periodEndDate,
          }
          const result = markSpecificSamples([tx], T)
          expect(result.length).toBe(1)
          expect(result[0].reason).toContain('异常日期')
        },
      ),
      RUNS,
    )
  })

  it('normal weekday + not related + amount < T → not marked', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 100, max: 5000000 }), // T
        arbNormalDate,
        fc.string({ minLength: 1, maxLength: 5 }),
        (T, normalDate, name) => {
          const tx: TransactionItem = {
            id: 'test-5',
            customerName: name,
            amount: T - 1, // strictly below T
            isRelatedParty: false,
            transactionDate: normalDate,
          }
          const result = markSpecificSamples([tx], T)
          expect(result.length).toBe(0)
        },
      ),
      RUNS,
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// Property 12: Sampling population arithmetic invariant
// ═══════════════════════════════════════════════════════════════════════════

describe('Feature: d2-7-voucher-check-enhancement, Property 12: Sampling population arithmetic invariant', () => {
  /**
   * **Validates: Requirements 8.3, 8.4**
   *
   * For any test population (amount_t, count_t) and confirmed specific samples
   * subset (amount_s, count_s) where amount_s <= amount_t and count_s <= count_t:
   * sampling_population_amount == max(0, amount_t - amount_s)
   * AND sampling_population_count == max(0, count_t - count_s)
   */

  it('samplingPopulation = testPopulation - confirmed specific samples (amount & count)', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 100000000 }), // test population amount
        fc.integer({ min: 0, max: 10000 }), // test population count
        fc.array(
          fc.record({
            id: fc.uuid(),
            customerName: fc.string({ minLength: 1, maxLength: 5 }),
            amount: fc.integer({ min: 0, max: 5000000 }),
            reason: fc.constant('测试原因'),
            confirmed: fc.boolean(),
          }),
          { minLength: 0, maxLength: 10 },
        ),
        (testAmount, testCount, samples) => {
          const testPopulation: PopulationDesc = {
            amount: testAmount,
            count: testCount,
            description: '测试总体',
          }

          const specificSamples: SpecificSampleItem[] = samples

          const result = computeSamplingPopulation(testPopulation, specificSamples)

          // Only confirmed samples should be subtracted
          const confirmedSamples = specificSamples.filter(s => s.confirmed)
          const confirmedAmount = confirmedSamples.reduce((sum, s) => sum + s.amount, 0)
          const confirmedCount = confirmedSamples.length

          const expectedAmount = Math.max(0, testAmount - confirmedAmount)
          const expectedCount = Math.max(0, testCount - confirmedCount)

          expect(result.amount).toBe(expectedAmount)
          expect(result.count).toBe(expectedCount)
        },
      ),
      RUNS,
    )
  })

  it('no confirmed samples → samplingPopulation equals testPopulation', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 100000000 }),
        fc.integer({ min: 0, max: 10000 }),
        fc.array(
          fc.record({
            id: fc.uuid(),
            customerName: fc.string({ minLength: 1, maxLength: 5 }),
            amount: fc.integer({ min: 0, max: 5000000 }),
            reason: fc.constant('原因'),
            confirmed: fc.constant(false), // none confirmed
          }),
          { minLength: 0, maxLength: 10 },
        ),
        (testAmount, testCount, samples) => {
          const testPopulation: PopulationDesc = {
            amount: testAmount,
            count: testCount,
            description: '测试',
          }

          const result = computeSamplingPopulation(testPopulation, samples)
          expect(result.amount).toBe(testAmount)
          expect(result.count).toBe(testCount)
        },
      ),
      RUNS,
    )
  })

  it('samplingPopulation amount and count are always >= 0 (floor at zero)', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 1000 }), // small test amount
        fc.integer({ min: 0, max: 10 }), // small test count
        fc.array(
          fc.record({
            id: fc.uuid(),
            customerName: fc.constant('X'),
            amount: fc.integer({ min: 0, max: 10000 }), // may exceed testAmount
            reason: fc.constant('r'),
            confirmed: fc.constant(true),
          }),
          { minLength: 0, maxLength: 20 }, // more samples than count to trigger floor
        ),
        (testAmount, testCount, samples) => {
          const testPopulation: PopulationDesc = {
            amount: testAmount,
            count: testCount,
            description: '测试',
          }

          const result = computeSamplingPopulation(testPopulation, samples)
          expect(result.amount).toBeGreaterThanOrEqual(0)
          expect(result.count).toBeGreaterThanOrEqual(0)
        },
      ),
      RUNS,
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// Property 16: Sample size deviation indicator
// ═══════════════════════════════════════════════════════════════════════════

describe('Feature: d2-7-voucher-check-enhancement, Property 16: Sample size deviation indicator', () => {
  /**
   * **Validates: Requirements 11.5**
   *
   * For any user-entered sample size U > 0 and recommended sample size R > 0:
   * if U < R then deviation == 'below';
   * if U >= R then deviation == 'ok'.
   */

  it('U < R → "below"; U >= R → "ok"', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 10000 }), // userSize > 0
        fc.integer({ min: 1, max: 10000 }), // recommendedSize > 0
        (userSize, recommendedSize) => {
          const result = computeSampleSizeDeviation(userSize, recommendedSize)
          if (userSize < recommendedSize) {
            expect(result).toBe('below')
          } else {
            expect(result).toBe('ok')
          }
        },
      ),
      RUNS,
    )
  })

  it('U == R → "ok" (boundary case)', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 10000 }), // same value for both
        (size) => {
          const result = computeSampleSizeDeviation(size, size)
          expect(result).toBe('ok')
        },
      ),
      RUNS,
    )
  })

  it('recommendedSize <= 0 → null (guard)', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 10000 }),
        fc.integer({ min: -1000, max: 0 }),
        (userSize, recommendedSize) => {
          const result = computeSampleSizeDeviation(userSize, recommendedSize)
          expect(result).toBeNull()
        },
      ),
      RUNS,
    )
  })

  it('userSize <= 0 → null (guard)', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: -1000, max: 0 }),
        fc.integer({ min: 1, max: 10000 }),
        (userSize, recommendedSize) => {
          const result = computeSampleSizeDeviation(userSize, recommendedSize)
          expect(result).toBeNull()
        },
      ),
      RUNS,
    )
  })
})
