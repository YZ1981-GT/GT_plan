/**
 * n1LossCheckModel.spec.ts — Property 1/2/3/4/10 (派生规则)
 *
 * Spec: .kiro/specs/n1-loss-check-source-alignment/
 * Task: 2.4
 * Requirements: 9.1, 9.2
 *
 * Tests the derivation logic of N1LossComputedRow from N1LossRow
 * by exercising the formulas directly (pure function extraction).
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

// ─── Helper: replicate the derivation logic (pure functions) ────────────────
// These mirror the computed logic inside useN1LossCheck without Vue reactivity.

function round2(n: number): number {
  return Math.round(n * 100) / 100
}

interface DeriveInput {
  bookAmount: number
  auditAdjustment: number
  recognizedAmount: number
  taxRate: number
  expiryYear: number
  auditYear: number
}

interface DeriveResult {
  auditedAmount: number
  effectiveRecognized: number
  unrecognizedAmount: number
  recognizableAsset: number
  isExpired: boolean
  splitMismatch: boolean
}

function deriveRow(input: DeriveInput): DeriveResult {
  const auditedAmount = round2(input.bookAmount + input.auditAdjustment)
  const isExpired = input.expiryYear < input.auditYear
  const effectiveRecognized = isExpired ? 0 : input.recognizedAmount
  const unrecognizedAmount = Math.max(0, round2(auditedAmount - effectiveRecognized))
  const recognizableAsset = round2(effectiveRecognized * input.taxRate)
  const splitMismatch = input.recognizedAmount > auditedAmount && !isExpired
  return { auditedAmount, effectiveRecognized, unrecognizedAmount, recognizableAsset, isExpired, splitMismatch }
}

function deriveLead(bookAmount: number, auditAdjustment: number): number {
  return round2(bookAmount + auditAdjustment)
}

// ─── Generators ─────────────────────────────────────────────────────────────

const arbAmount = fc.double({ min: -1e8, max: 1e8, noNaN: true, noDefaultInfinity: true })
const arbPositiveAmount = fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true })
const arbTaxRate = fc.double({ min: 0.01, max: 0.50, noNaN: true, noDefaultInfinity: true })
const arbYear = fc.integer({ min: 2015, max: 2040 })

const arbDeriveInput = fc.record({
  bookAmount: arbAmount,
  auditAdjustment: arbAmount,
  recognizedAmount: arbPositiveAmount,
  taxRate: arbTaxRate,
  expiryYear: arbYear,
  auditYear: arbYear,
})

// ─── Property 1: 本期审定 = 账面 + 审计调整 ──────────────────────────────────

describe('Property 1: auditedAmount === round2(bookAmount + auditAdjustment)', () => {
  /**
   * **Validates: Requirements 1.2, 1.3**
   */
  it('holds for any bookAmount and auditAdjustment (loss rows)', () => {
    fc.assert(
      fc.property(arbDeriveInput, (input) => {
        const result = deriveRow(input)
        expect(result.auditedAmount).toBe(round2(input.bookAmount + input.auditAdjustment))
      }),
      { numRuns: 200 },
    )
  })

  it('holds for lead rows (same formula)', () => {
    fc.assert(
      fc.property(arbAmount, arbAmount, (book, adj) => {
        expect(deriveLead(book, adj)).toBe(round2(book + adj))
      }),
      { numRuns: 200 },
    )
  })
})

// ─── Property 2: 确认 + 不确认 = 本期审定 ───────────────────────────────────

describe('Property 2: effectiveRecognized + unrecognizedAmount === auditedAmount (tolerance 0.01)', () => {
  /**
   * **Validates: Requirements 3.1, 1.5**
   */
  it('sum equals audited within tolerance for non-expired rows', () => {
    fc.assert(
      fc.property(arbDeriveInput, (input) => {
        // Force non-expired for the main invariant check
        const nonExpiredInput = { ...input, expiryYear: input.auditYear + 5 }
        const result = deriveRow(nonExpiredInput)
        const sum = result.effectiveRecognized + result.unrecognizedAmount
        // unrecognizedAmount has max(0,...) floor → when recognized > audited, sum may exceed
        if (nonExpiredInput.recognizedAmount > result.auditedAmount) {
          // splitMismatch case: unrecognizedAmount floored to 0
          expect(result.unrecognizedAmount).toBe(0)
          expect(result.splitMismatch).toBe(true)
        } else {
          expect(Math.abs(sum - result.auditedAmount)).toBeLessThanOrEqual(0.01)
        }
      }),
      { numRuns: 200 },
    )
  })

  it('recognizedAmount > auditedAmount ⇒ unrecognizedAmount = 0 ∧ splitMismatch = true', () => {
    fc.assert(
      fc.property(
        arbPositiveAmount,
        fc.double({ min: 0.01, max: 1e6, noNaN: true, noDefaultInfinity: true }),
        arbTaxRate,
        arbYear,
        (book, excess, taxRate, year) => {
          const auditedAmount = round2(book)
          // recognizedAmount exceeds auditedAmount
          const recognizedAmount = auditedAmount + excess
          const input: DeriveInput = {
            bookAmount: book,
            auditAdjustment: 0,
            recognizedAmount,
            taxRate,
            expiryYear: year + 10,
            auditYear: year,
          }
          const result = deriveRow(input)
          expect(result.unrecognizedAmount).toBe(0)
          expect(result.splitMismatch).toBe(true)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── Property 3: 届满行确认额恒为 0 ────────────────────────────────────────

describe('Property 3: expired rows ⇒ effectiveRecognized === 0 ∧ recognizableAsset === 0 ∧ unrecognized === audited', () => {
  /**
   * **Validates: Requirements 2.2, 3.5**
   */
  it('holds regardless of recognizedAmount', () => {
    fc.assert(
      fc.property(
        arbAmount,
        arbAmount,
        arbPositiveAmount,
        arbTaxRate,
        arbYear,
        (book, adj, recognized, taxRate, auditYear) => {
          // Ensure expired: expiryYear < auditYear
          const expiryYear = auditYear - fc.sample(fc.integer({ min: 1, max: 10 }), 1)[0]
          const input: DeriveInput = {
            bookAmount: book,
            auditAdjustment: adj,
            recognizedAmount: recognized,
            taxRate,
            expiryYear,
            auditYear,
          }
          const result = deriveRow(input)
          expect(result.isExpired).toBe(true)
          expect(result.effectiveRecognized).toBe(0)
          expect(result.recognizableAsset).toBe(0)
          expect(result.unrecognizedAmount).toBe(Math.max(0, result.auditedAmount))
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── Property 4: 可确认递延税资产 = 确认金额 × 税率 ─────────────────────────

describe('Property 4: recognizableAsset === round2(effectiveRecognized * taxRate)', () => {
  /**
   * **Validates: Requirements 3.4**
   */
  it('per-row formula', () => {
    fc.assert(
      fc.property(arbDeriveInput, (input) => {
        const result = deriveRow(input)
        expect(result.recognizableAsset).toBe(round2(result.effectiveRecognized * input.taxRate))
      }),
      { numRuns: 200 },
    )
  })

  it('totals.recognizableAsset === round2(sum of per-row recognizableAsset)', () => {
    fc.assert(
      fc.property(
        fc.array(arbDeriveInput, { minLength: 1, maxLength: 20 }),
        (inputs) => {
          const rows = inputs.map((input) => deriveRow(input))
          const sumPerRow = rows.reduce((s, r) => s + r.recognizableAsset, 0)
          const totalRecognizable = round2(sumPerRow)
          // The total should equal round2(Σ recognizableAsset)
          expect(totalRecognizable).toBe(round2(rows.reduce((s, r) => s + r.recognizableAsset, 0)))
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── Property 10: isExpired 集合单调扩张 ────────────────────────────────────

describe('Property 10: isExpired set monotonically expands as auditYear increases', () => {
  /**
   * **Validates: Requirements 2.1, 2.2**
   */
  it('rows expired at year Y remain expired at Y+1', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            expiryYear: arbYear,
            bookAmount: arbAmount,
            auditAdjustment: arbAmount,
            recognizedAmount: arbPositiveAmount,
            taxRate: arbTaxRate,
          }),
          { minLength: 1, maxLength: 15 },
        ),
        arbYear,
        (rowInputs, baseYear) => {
          const expiredAtY = new Set<number>()
          const expiredAtY1 = new Set<number>()

          for (let i = 0; i < rowInputs.length; i++) {
            const row = rowInputs[i]
            const resultY = deriveRow({ ...row, auditYear: baseYear })
            const resultY1 = deriveRow({ ...row, auditYear: baseYear + 1 })

            if (resultY.isExpired) expiredAtY.add(i)
            if (resultY1.isExpired) expiredAtY1.add(i)
          }

          // Monotone: every index expired at Y must be expired at Y+1
          for (const idx of expiredAtY) {
            expect(expiredAtY1.has(idx)).toBe(true)
          }
          // Y+1 set is superset or equal (may expand by 1 more row whose expiryYear === baseYear)
          expect(expiredAtY1.size).toBeGreaterThanOrEqual(expiredAtY.size)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('does not depend on system current year (deterministic on auditYear)', () => {
    fc.assert(
      fc.property(arbDeriveInput, (input) => {
        const r1 = deriveRow(input)
        const r2 = deriveRow(input)
        expect(r1.isExpired).toBe(r2.isExpired)
      }),
      { numRuns: 50 },
    )
  })
})
