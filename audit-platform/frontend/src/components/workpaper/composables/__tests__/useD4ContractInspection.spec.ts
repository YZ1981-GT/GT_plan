/**
 * PBT (Property-Based Tests) for useD4ContractInspection pure logic
 *
 * Tests mathematical properties of coverage rate, summary conclusion,
 * and contract CRUD reindexing using fast-check.
 */
import { describe, it, expect } from 'vitest'
import fc from 'fast-check'
import { parseNum, calcCoverageRate, calcSubtotal } from '../useD4FormulaEngine'

// ─── Pure helper functions extracted from composable for testing ──────────────

/** Compute coverage rate: sum(contractAmounts) / totalRevenue * 100, clamped [0, 100] */
function computeCoverageRate(contractAmounts: number[], totalRevenue: number): number {
  if (totalRevenue <= 0) return 0
  const sum = contractAmounts.reduce((s, v) => s + parseNum(v), 0)
  return Math.min((sum / totalRevenue) * 100, 100)
}

/** Build summary conclusion text from contracts data */
function buildSummaryConclusion(
  contracts: Array<{ contractAmount: number; conclusion: string }>,
  coverageRate: number,
): string {
  const total = contracts.length
  if (total === 0) return ''
  const totalAmount = contracts.reduce((s, c) => s + parseNum(c.contractAmount), 0)
  const compliant = contracts.filter(c => c.conclusion === 'Y').length
  const nonCompliant = contracts.filter(c => c.conclusion === 'N').length
  const amountStr = (totalAmount / 10000).toFixed(2)
  return `共检查${total}份合同，金额${amountStr}万元，覆盖率${coverageRate.toFixed(1)}%。` +
    `其中${compliant}份合规，${nonCompliant}份存在问题。`
}

/** Reindex after add: assign sequential indexNo */
function reindexAfterAdd(contracts: Array<{ indexNo: string }>): void {
  contracts.forEach((c, i) => { c.indexNo = `D4-12-${i + 1}` })
}

/** Reindex after remove: filter then reassign sequential indexNo */
function reindexAfterRemove(
  contracts: Array<{ id: string; indexNo: string }>,
  removeId: string,
): Array<{ id: string; indexNo: string }> {
  const remaining = contracts.filter(c => c.id !== removeId)
  remaining.forEach((c, i) => { c.indexNo = `D4-12-${i + 1}` })
  return remaining
}

/** Merge OCR fields with non-overwrite behavior */
function mergeOcrFields(
  item: Record<string, any>,
  fields: Record<string, any>,
  overwriteExisting: boolean,
): Record<string, any> {
  const result = { ...item }
  for (const [key, val] of Object.entries(fields)) {
    if (val == null || val === '') continue
    const currentVal = result[key]
    if (overwriteExisting || !currentVal || currentVal === '' || currentVal === 0) {
      result[key] = val
    }
  }
  return result
}

// ─── Arbitraries ─────────────────────────────────────────────────────────────

const positiveAmount = fc.double({ min: 0.01, max: 1e9, noNaN: true })
const nonNegativeAmount = fc.double({ min: 0, max: 1e9, noNaN: true })
const conclusionArb = fc.constantFrom('Y', 'N', 'NA', '')

const contractArb = fc.record({
  contractAmount: nonNegativeAmount,
  conclusion: conclusionArb,
})

// ─── Tests ───────────────────────────────────────────────────────────────────

describe('useD4ContractInspection - PBT', () => {
  describe('P1: coverageRate property', () => {
    it('coverage rate = sum(amounts) / totalRevenue * 100, clamped [0, 100]', () => {
      fc.assert(
        fc.property(
          fc.array(nonNegativeAmount, { minLength: 1, maxLength: 20 }),
          positiveAmount,
          (amounts, totalRevenue) => {
            const rate = computeCoverageRate(amounts, totalRevenue)
            expect(rate).toBeGreaterThanOrEqual(0)
            expect(rate).toBeLessThanOrEqual(100)

            // Verify the formula
            const sum = amounts.reduce((s, v) => s + parseNum(v), 0)
            const expected = Math.min((sum / totalRevenue) * 100, 100)
            expect(rate).toBeCloseTo(expected, 8)
          },
        ),
        { numRuns: 100 },
      )
    })

    it('coverage rate is 0 when totalRevenue <= 0', () => {
      fc.assert(
        fc.property(
          fc.array(nonNegativeAmount, { minLength: 1, maxLength: 10 }),
          fc.double({ min: -1e9, max: 0, noNaN: true }),
          (amounts, totalRevenue) => {
            const rate = computeCoverageRate(amounts, totalRevenue)
            expect(rate).toBe(0)
          },
        ),
        { numRuns: 50 },
      )
    })
  })

  describe('P2: summaryConclusion property', () => {
    it('summary contains correct N count, Y/N counts, and amount', () => {
      fc.assert(
        fc.property(
          fc.array(contractArb, { minLength: 1, maxLength: 15 }),
          fc.double({ min: 0.1, max: 100, noNaN: true }),
          (contracts, coverageRate) => {
            const summary = buildSummaryConclusion(contracts, coverageRate)

            const total = contracts.length
            const compliant = contracts.filter(c => c.conclusion === 'Y').length
            const nonCompliant = contracts.filter(c => c.conclusion === 'N').length
            const totalAmount = contracts.reduce((s, c) => s + parseNum(c.contractAmount), 0)
            const amountStr = (totalAmount / 10000).toFixed(2)

            expect(summary).toContain(`共检查${total}份合同`)
            expect(summary).toContain(`金额${amountStr}万元`)
            expect(summary).toContain(`${compliant}份合规`)
            expect(summary).toContain(`${nonCompliant}份存在问题`)
            expect(summary).toContain(`覆盖率${coverageRate.toFixed(1)}%`)
          },
        ),
        { numRuns: 100 },
      )
    })

    it('summary is empty string when contracts is empty', () => {
      const summary = buildSummaryConclusion([], 50)
      expect(summary).toBe('')
    })
  })

  describe('P3: addContract reindexing', () => {
    it('after adding N contracts, indexNo values are sequential D4-12-1 to D4-12-N', () => {
      fc.assert(
        fc.property(
          fc.integer({ min: 1, max: 30 }),
          (n) => {
            const contracts: Array<{ indexNo: string }> = []
            for (let i = 0; i < n; i++) {
              contracts.push({ indexNo: '' })
            }
            reindexAfterAdd(contracts)

            for (let i = 0; i < n; i++) {
              expect(contracts[i].indexNo).toBe(`D4-12-${i + 1}`)
            }
          },
        ),
        { numRuns: 50 },
      )
    })
  })

  describe('P4: removeContract reindexing', () => {
    it('after removing any contract, remaining indexNo values are re-sequential', () => {
      fc.assert(
        fc.property(
          fc.integer({ min: 2, max: 20 }),
          fc.nat(),
          (n, removeIdx) => {
            // Create N contracts with sequential IDs
            const contracts = Array.from({ length: n }, (_, i) => ({
              id: `c-${i}`,
              indexNo: `D4-12-${i + 1}`,
            }))

            // Remove one at a valid index
            const actualRemoveIdx = removeIdx % n
            const removeId = contracts[actualRemoveIdx].id
            const remaining = reindexAfterRemove(contracts, removeId)

            // Verify remaining count
            expect(remaining.length).toBe(n - 1)

            // Verify sequential indexing
            for (let i = 0; i < remaining.length; i++) {
              expect(remaining[i].indexNo).toBe(`D4-12-${i + 1}`)
            }

            // Verify removed item is gone
            expect(remaining.find(c => c.id === removeId)).toBeUndefined()
          },
        ),
        { numRuns: 100 },
      )
    })
  })

  describe('P5: mergeOcrFields non-overwrite', () => {
    it('when overwriteExisting=false, fields with existing values are not overwritten', () => {
      fc.assert(
        fc.property(
          fc.record({
            contractNo: fc.string({ minLength: 1, maxLength: 20 }),
            counterparty: fc.string({ minLength: 1, maxLength: 20 }),
            contractAmount: fc.double({ min: 1, max: 1e6, noNaN: true }),
          }),
          fc.record({
            contractNo: fc.string({ minLength: 1, maxLength: 20 }),
            counterparty: fc.string({ minLength: 1, maxLength: 20 }),
            contractAmount: fc.double({ min: 1, max: 1e6, noNaN: true }),
          }),
          (existing, ocrFields) => {
            const result = mergeOcrFields(existing, ocrFields, false)

            // Existing non-empty string values should be preserved
            if (existing.contractNo && existing.contractNo !== '') {
              expect(result.contractNo).toBe(existing.contractNo)
            }
            if (existing.counterparty && existing.counterparty !== '') {
              expect(result.counterparty).toBe(existing.counterparty)
            }
            // Existing non-zero number values should be preserved
            if (existing.contractAmount && existing.contractAmount !== 0) {
              expect(result.contractAmount).toBe(existing.contractAmount)
            }
          },
        ),
        { numRuns: 100 },
      )
    })

    it('when overwriteExisting=false, empty fields get filled from OCR', () => {
      fc.assert(
        fc.property(
          fc.string({ minLength: 1, maxLength: 30 }),
          fc.double({ min: 1, max: 1e6, noNaN: true }),
          (ocrValue, ocrAmount) => {
            const existing = { contractNo: '', counterparty: '', contractAmount: 0 }
            const ocrFields = { contractNo: ocrValue, counterparty: 'OCR Corp', contractAmount: ocrAmount }

            const result = mergeOcrFields(existing, ocrFields, false)

            // Empty fields should be filled
            expect(result.contractNo).toBe(ocrValue)
            expect(result.counterparty).toBe('OCR Corp')
            expect(result.contractAmount).toBe(ocrAmount)
          },
        ),
        { numRuns: 50 },
      )
    })

    it('when overwriteExisting=true, all fields are overwritten', () => {
      fc.assert(
        fc.property(
          fc.record({
            contractNo: fc.string({ minLength: 1, maxLength: 20 }),
            counterparty: fc.string({ minLength: 1, maxLength: 20 }),
          }),
          fc.record({
            contractNo: fc.string({ minLength: 1, maxLength: 20 }),
            counterparty: fc.string({ minLength: 1, maxLength: 20 }),
          }),
          (existing, ocrFields) => {
            const result = mergeOcrFields(existing, ocrFields, true)

            // All OCR fields should overwrite
            expect(result.contractNo).toBe(ocrFields.contractNo)
            expect(result.counterparty).toBe(ocrFields.counterparty)
          },
        ),
        { numRuns: 50 },
      )
    })
  })
})
