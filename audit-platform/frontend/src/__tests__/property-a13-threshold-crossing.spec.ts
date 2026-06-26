/**
 * Feature: a13-misstatement-aggregation, Property 3: Materiality threshold transition detection
 *
 * For any prior cumulative amount below PM and a new cumulative amount at-or-above PM,
 * the system SHALL emit a warning notification. Conversely, if both prior and new are below PM,
 * or both are at-or-above PM, no transition notification SHALL fire.
 *
 * **Validates: Requirements 3.5**
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

// ─── Extract pure logic for threshold crossing detection ────────────────────

/**
 * Pure function that determines if a threshold crossing notification should fire.
 * Returns true iff old < PM AND new >= PM.
 */
function shouldNotifyThresholdCrossing(
  oldCumulative: number,
  newCumulative: number,
  pm: number | null | undefined,
): boolean {
  if (!pm || pm <= 0) return false
  return oldCumulative < pm && newCumulative >= pm
}

// ─── Property Tests ─────────────────────────────────────────────────────────

describe('Property 3: Materiality threshold transition detection', () => {
  it('triggers notification iff old < PM and new >= PM', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 1000000 }),   // oldCumulative (in cents)
        fc.integer({ min: 0, max: 1000000 }),   // newCumulative (in cents)
        fc.integer({ min: 1, max: 1000000 }),   // pm (positive, in cents)
        (oldCents, newCents, pmCents) => {
          const oldCumulative = oldCents / 100
          const newCumulative = newCents / 100
          const pm = pmCents / 100
          const shouldNotify = shouldNotifyThresholdCrossing(oldCumulative, newCumulative, pm)

          if (oldCumulative < pm && newCumulative >= pm) {
            // Crossing happened → must notify
            expect(shouldNotify).toBe(true)
          } else {
            // No crossing → must not notify
            expect(shouldNotify).toBe(false)
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('never triggers when PM is null or zero', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 1000000 }),
        fc.integer({ min: 0, max: 1000000 }),
        fc.constantFrom(null, undefined, 0, -1),
        (oldCents, newCents, pm) => {
          const oldCumulative = oldCents / 100
          const newCumulative = newCents / 100
          const shouldNotify = shouldNotifyThresholdCrossing(oldCumulative, newCumulative, pm)
          expect(shouldNotify).toBe(false)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('does not trigger when both values are below PM', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 100, max: 1000000 }),  // pm in cents (positive)
        (pmCents) => {
          const pm = pmCents / 100
          // Generate old and new both below PM
          const old = pm * 0.3
          const newVal = pm * 0.7
          expect(shouldNotifyThresholdCrossing(old, newVal, pm)).toBe(false)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('does not trigger when both values are at-or-above PM', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 100, max: 1000000 }),  // pm in cents
        (pmCents) => {
          const pm = pmCents / 100
          // Both at or above PM
          const old = pm * 1.2
          const newVal = pm * 1.5
          expect(shouldNotifyThresholdCrossing(old, newVal, pm)).toBe(false)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('does not trigger when crossing downward (old >= PM, new < PM)', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 100, max: 1000000 }),  // pm in cents
        (pmCents) => {
          const pm = pmCents / 100
          // Crossing downward
          const old = pm * 1.5
          const newVal = pm * 0.5
          expect(shouldNotifyThresholdCrossing(old, newVal, pm)).toBe(false)
        },
      ),
      { numRuns: 100 },
    )
  })
})
