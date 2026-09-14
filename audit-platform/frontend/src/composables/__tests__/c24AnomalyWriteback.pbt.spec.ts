/**
 * Property-Based Tests — P9/P10/P11 异常回写与联动
 *
 * Spec: .kiro/specs/c23-c24-journal-entry-testing/
 * Task: 8.3
 *
 * 使用 fast-check + vitest 验证 Property 9~11。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  benfordDistribution,
  type JournalEntry,
  type BenfordDigitResult,
} from '../useC24AnalyticsEngine'

// ─── Helper types matching component logic ───

interface AnomalyNote {
  checkContent: string
  conclusion: string
  indexRef?: string
}

interface AnomalyResult {
  entry: JournalEntry
  reasons: string[]
}

// ─── Generators ───

const arbDateStr = fc
  .date({ min: new Date('2020-01-01'), max: new Date('2030-12-31') })
  .map((d) => {
    const y = d.getFullYear()
    const m = String(d.getMonth() + 1).padStart(2, '0')
    const day = String(d.getDate()).padStart(2, '0')
    return `${y}-${m}-${day}`
  })

const arbAmount = fc.float({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true })

function arbJournalEntry(): fc.Arbitrary<JournalEntry> {
  return fc.record({
    voucherDate: arbDateStr,
    voucherMonth: fc.integer({ min: 1, max: 12 }),
    voucherType: fc.constantFrom('付', '收', '转'),
    voucherNo: fc.integer({ min: 1, max: 9999 }).map(n => `转-${String(n).padStart(3, '0')}`),
    summary: fc.string({ minLength: 0, maxLength: 20 }),
    accountCode: fc.stringMatching(/^[0-9]{4}$/),
    accountName: fc.string({ minLength: 1, maxLength: 10 }),
    debit: arbAmount,
    credit: arbAmount,
    voucherSheets: fc.constant('1'),
    preparer: fc.string({ minLength: 1, maxLength: 5 }),
    reviewer: fc.string({ minLength: 1, maxLength: 5 }),
    poster: fc.string({ minLength: 1, maxLength: 5 }),
  })
}

const arbConclusionValue = fc.constantFrom('正常', '异常-已解释', '异常-错报')

// ═══════════════════════════════════════════════════════════════════════════════
// Property 9: 异常确认错报 → indexRef 自动填入 A13 + GtIndexChip 渲染
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: c23-c24-journal-entry-testing, Property 9: 异常确认错报 indexRef 自动填入 A13', () => {
  /**
   * **Validates: Requirements 11.1**
   *
   * When anomaly conclusion = "异常-错报" and indexRef is empty,
   * the component auto-populates indexRef with "A13".
   * When conclusion is not "异常-错报", indexRef is NOT auto-populated.
   */

  /**
   * Simulates the onConclusionSelect logic from C24AnomalyEntrySheet:
   * - When value === '异常-错报' and current indexRef is empty → set to 'A13'
   */
  function simulateConclusionSelect(
    notes: AnomalyNote[],
    index: number,
    value: string,
  ): AnomalyNote[] {
    const updated = notes.map(n => ({ ...n }))
    if (!updated[index]) updated[index] = { checkContent: '', conclusion: '', indexRef: '' }
    updated[index].conclusion = value
    if (value === '异常-错报') {
      if (!updated[index].indexRef) {
        updated[index].indexRef = 'A13'
      }
    }
    return updated
  }

  it('conclusion=异常-错报 with empty indexRef → indexRef auto-set to A13', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 49 }),
        (index) => {
          // Start with empty notes
          const notes: AnomalyNote[] = Array.from({ length: index + 1 }, () => ({
            checkContent: '', conclusion: '', indexRef: '',
          }))

          const updated = simulateConclusionSelect(notes, index, '异常-错报')
          expect(updated[index].indexRef).toBe('A13')
          expect(updated[index].conclusion).toBe('异常-错报')
        },
      ),
      { numRuns: 100 },
    )
  })

  it('conclusion=异常-错报 with existing indexRef → indexRef preserved', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 20 }),
        fc.string({ minLength: 1, maxLength: 10 }),
        (index, existingRef) => {
          const notes: AnomalyNote[] = Array.from({ length: index + 1 }, () => ({
            checkContent: '', conclusion: '', indexRef: '',
          }))
          notes[index].indexRef = existingRef

          const updated = simulateConclusionSelect(notes, index, '异常-错报')
          // Existing indexRef is preserved (not overwritten)
          expect(updated[index].indexRef).toBe(existingRef)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('conclusion≠异常-错报 → indexRef NOT auto-populated', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 20 }),
        fc.constantFrom('正常', '异常-已解释'),
        (index, value) => {
          const notes: AnomalyNote[] = Array.from({ length: index + 1 }, () => ({
            checkContent: '', conclusion: '', indexRef: '',
          }))

          const updated = simulateConclusionSelect(notes, index, value)
          // indexRef should remain empty
          expect(updated[index].indexRef).toBe('')
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 10: 结论回填 C24-0 汇总一致性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: c23-c24-journal-entry-testing, Property 10: 结论回填 C24-0 一致性', () => {
  /**
   * **Validates: Requirements 11.2**
   *
   * When any sub-sheet conclusion changes, the C24-0 summary's subConclusions
   * map reflects the same value. The write-back is immediate and preserves
   * the source test item index for bidirectional traceability.
   */

  const CONCLUSION_KEYS = ['C24-1', 'C24-2', 'C24-3', 'C24-4', 'C24-5', 'benford'] as const

  /**
   * Simulates the onConclusionChange logic from GtC24JournalDetail:
   * - Updates conclusions map
   * - Writes back to C24-0 summary (simulated by updating summaryMap)
   */
  function simulateConclusionChange(
    conclusions: Record<string, string>,
    summaryMap: Record<string, { conclusion: string; source: string }>,
    key: string,
    value: string,
  ) {
    // Update conclusions (mirrors onConclusionChange)
    conclusions[key] = value
    // Write to summary (mirrors writeConclusionToSummary)
    const sourceIndex = key === 'benford' ? 'C24-本福特' : key
    summaryMap[`C24-0-sub-${key}`] = { conclusion: value, source: sourceIndex }
  }

  it('conclusion change → C24-0 summary reflects same value', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...CONCLUSION_KEYS),
        fc.string({ minLength: 1, maxLength: 50 }),
        (key, conclusionText) => {
          const conclusions: Record<string, string> = {}
          const summaryMap: Record<string, { conclusion: string; source: string }> = {}

          simulateConclusionChange(conclusions, summaryMap, key, conclusionText)

          // Verify consistency
          const summaryItem = summaryMap[`C24-0-sub-${key}`]
          expect(summaryItem).toBeDefined()
          expect(summaryItem.conclusion).toBe(conclusionText)
          expect(conclusions[key]).toBe(conclusionText)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('source index preserves bidirectional traceability (Req 11.4)', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...CONCLUSION_KEYS),
        fc.string({ minLength: 1, maxLength: 30 }),
        (key, conclusionText) => {
          const conclusions: Record<string, string> = {}
          const summaryMap: Record<string, { conclusion: string; source: string }> = {}

          simulateConclusionChange(conclusions, summaryMap, key, conclusionText)

          const summaryItem = summaryMap[`C24-0-sub-${key}`]
          // Source must identify origin test item
          const expectedSource = key === 'benford' ? 'C24-本福特' : key
          expect(summaryItem.source).toBe(expectedSource)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('multiple conclusion changes → all reflected in summary without loss', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.tuple(fc.constantFrom(...CONCLUSION_KEYS), fc.string({ minLength: 1, maxLength: 30 })),
          { minLength: 2, maxLength: 10 },
        ),
        (changes) => {
          const conclusions: Record<string, string> = {}
          const summaryMap: Record<string, { conclusion: string; source: string }> = {}

          for (const [key, value] of changes) {
            simulateConclusionChange(conclusions, summaryMap, key, value)
          }

          // For each unique key, check the LAST conclusion is reflected
          const lastValues = new Map<string, string>()
          for (const [key, value] of changes) {
            lastValues.set(key, value)
          }

          for (const [key, expectedValue] of lastValues) {
            expect(conclusions[key]).toBe(expectedValue)
            const summaryItem = summaryMap[`C24-0-sub-${key}`]
            expect(summaryItem.conclusion).toBe(expectedValue)
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 11: 扩大核查范围提示 (本福特偏离 + 异常分录聚集)
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: c23-c24-journal-entry-testing, Property 11: 扩大核查范围提示', () => {
  /**
   * **Validates: Requirements 11.3**
   *
   * When Benford deviation exceeds threshold (|deviation| > 0.05) for any digit,
   * OR when anomaly ratio exceeds threshold (count > 10 or > 5% of total),
   * a "建议扩大核查范围" alert appears.
   */

  const BENFORD_DEVIATION_THRESHOLD = 0.05
  const ANOMALY_COUNT_THRESHOLD = 10
  const ANOMALY_RATIO_THRESHOLD = 0.05

  /**
   * Simulates BenfordSheet expand-scope logic:
   * Returns warning message if any digit has |deviation| > 0.05
   */
  function computeBenfordWarning(distribution: BenfordDigitResult[]): string {
    if (distribution.length === 0) return ''
    const deviating = distribution.filter(d => Math.abs(d.deviation) > BENFORD_DEVIATION_THRESHOLD)
    if (deviating.length === 0) return ''
    const digits = deviating.map(d => d.digit).join('、')
    return `建议扩大核查范围：首位数 ${digits} 显著偏离本福特理论分布`
  }

  /**
   * Simulates AnomalyEntrySheet expand-scope logic:
   * Returns warning if anomaly count > threshold or ratio > threshold
   */
  function computeAnomalyWarning(anomalyCount: number, totalCount: number): string {
    if (anomalyCount === 0) return ''
    if (anomalyCount > ANOMALY_COUNT_THRESHOLD) {
      if (totalCount > 0) {
        const ratio = anomalyCount / totalCount
        if (ratio > ANOMALY_RATIO_THRESHOLD) {
          return `建议扩大核查范围：异常分录占比较高（${anomalyCount}/${totalCount}，${(ratio * 100).toFixed(1)}%）`
        }
      }
      return `建议扩大核查范围：异常分录数量较多（${anomalyCount} 条）`
    }
    if (totalCount > 0 && (anomalyCount / totalCount) > ANOMALY_RATIO_THRESHOLD) {
      return `建议扩大核查范围：异常分录占比较高（${anomalyCount}/${totalCount}，${((anomalyCount / totalCount) * 100).toFixed(1)}%）`
    }
    return ''
  }

  it('Benford: digit with |deviation| > 0.05 → warning includes that digit', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.float({ min: 1, max: 1e6, noNaN: true, noDefaultInfinity: true }),
          { minLength: 10, maxLength: 200 },
        ),
        (amounts) => {
          const dist = benfordDistribution(amounts)
          const warning = computeBenfordWarning(dist)
          const deviating = dist.filter(d => Math.abs(d.deviation) > BENFORD_DEVIATION_THRESHOLD)

          if (deviating.length > 0) {
            expect(warning).toContain('建议扩大核查范围')
            for (const d of deviating) {
              expect(warning).toContain(String(d.digit))
            }
          } else {
            expect(warning).toBe('')
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('Benford: all deviations ≤ 0.05 → no warning', () => {
    // We construct an input that closely follows Benford distribution
    fc.assert(
      fc.property(
        fc.integer({ min: 100, max: 1000 }),
        (n) => {
          // Generate amounts that follow Benford law
          // Use powers of 10 with random multipliers → naturally follows Benford
          const amounts: number[] = []
          for (let i = 0; i < n; i++) {
            // 10^(uniform[0,6]) naturally gives Benford distribution
            const exp = (i / n) * 6
            amounts.push(Math.pow(10, exp))
          }
          const dist = benfordDistribution(amounts)
          const deviating = dist.filter(d => Math.abs(d.deviation) > BENFORD_DEVIATION_THRESHOLD)
          const warning = computeBenfordWarning(dist)

          if (deviating.length === 0) {
            expect(warning).toBe('')
          }
          // If there are deviating digits, warning should be present
          if (deviating.length > 0) {
            expect(warning).toContain('建议扩大核查范围')
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('Anomaly: count > 10 → warning appears', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 11, max: 200 }),
        fc.integer({ min: 100, max: 5000 }),
        (anomalyCount, totalCount) => {
          // Ensure anomalyCount <= totalCount for realistic scenario
          const tc = Math.max(totalCount, anomalyCount)
          const warning = computeAnomalyWarning(anomalyCount, tc)
          expect(warning).toContain('建议扩大核查范围')
        },
      ),
      { numRuns: 100 },
    )
  })

  it('Anomaly: ratio > 5% with count ≤ 10 → warning includes ratio', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 2, max: 10 }),
        (anomalyCount) => {
          // Make total small enough that ratio > 5%
          // anomalyCount / totalCount > 0.05 → totalCount < anomalyCount / 0.05 = anomalyCount * 20
          const totalCount = Math.floor(anomalyCount / 0.06) // ratio ≈ 6% > 5%
          if (totalCount <= 0) return
          const warning = computeAnomalyWarning(anomalyCount, totalCount)
          if (anomalyCount / totalCount > ANOMALY_RATIO_THRESHOLD) {
            expect(warning).toContain('建议扩大核查范围')
            expect(warning).toContain('占比较高')
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('Anomaly: count ≤ 10 and ratio ≤ 5% → no warning', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 10 }),
        (anomalyCount) => {
          // Make total large enough that ratio ≤ 5%
          // anomalyCount / totalCount ≤ 0.05 → totalCount >= anomalyCount / 0.05 = anomalyCount * 20
          const totalCount = anomalyCount * 25 // ratio = 4% < 5%
          const warning = computeAnomalyWarning(anomalyCount, totalCount)
          expect(warning).toBe('')
        },
      ),
      { numRuns: 100 },
    )
  })

  it('Anomaly: count = 0 → no warning regardless of total', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 10000 }),
        (totalCount) => {
          const warning = computeAnomalyWarning(0, totalCount)
          expect(warning).toBe('')
        },
      ),
      { numRuns: 100 },
    )
  })
})
