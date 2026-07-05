/**
 * Property-Based Tests — P1 注册 / P6 人员核对 / P7 公式不可覆盖
 *
 * Spec: .kiro/specs/c23-c24-journal-entry-testing/
 * Task: 5.2
 *
 * 使用 fast-check + vitest 验证 Property 1, 6, 7。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  HTML_RENDERER_REGISTRY,
  HTML_COMPONENT_TYPE_SET,
  type HtmlRendererEntry,
} from '../../components/workpaper/htmlRendererRegistry'
import {
  checkPersonnel,
  type AuthorizedPerson,
  type JeControlSample,
} from '../useC23ControlData'
import {
  calcBalanceIntegrity,
  type JournalEntry,
} from '../useC24AnalyticsEngine'

// ═══════════════════════════════════════════════════════════════════════════════
// Property 1: 组件注册完整性 (P1 注册)
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: c23-c24-journal-entry-testing, Property 1: 组件注册完整性', () => {
  /**
   * **Validates: Requirements 1.1, 1.2**
   *
   * For any {c23-journal-entry-control, c24-journal-entry-detail}:
   * - Registry contains the component type
   * - Each resolves to a valid async component (non-null)
   * - The registry entry includes standard contextProps
   */

  const TARGET_TYPES = ['c23-journal-entry-control', 'c24-journal-entry-detail'] as const

  it('registry contains both c23 and c24 component types', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...TARGET_TYPES),
        (componentType) => {
          expect(HTML_COMPONENT_TYPE_SET.has(componentType)).toBe(true)
          expect(HTML_RENDERER_REGISTRY.has(componentType)).toBe(true)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('each entry resolves to a valid async component with standard contextProps', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...TARGET_TYPES),
        (componentType) => {
          const entry = HTML_RENDERER_REGISTRY.get(componentType) as HtmlRendererEntry
          expect(entry).toBeDefined()
          // component is a valid Vue component (defineAsyncComponent returns an object/function)
          expect(entry.component).toBeDefined()
          expect(entry.component).not.toBeNull()
          // contextProps must be 'standard'
          expect(entry.contextProps).toBe('standard')
          // icon is non-empty string
          expect(entry.icon.length).toBeGreaterThan(0)
          // label is non-empty string
          expect(entry.label.length).toBeGreaterThan(0)
          // emits is an array
          expect(Array.isArray(entry.emits)).toBe(true)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('registry entry componentType matches the lookup key', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...TARGET_TYPES),
        (componentType) => {
          const entry = HTML_RENDERER_REGISTRY.get(componentType)!
          expect(entry.componentType).toBe(componentType)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 6: C23 人员核对正确性 (P6 人员核对)
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: c23-c24-journal-entry-testing, Property 6: 人员核对正确性', () => {
  /**
   * **Validates: Requirements 2.4, 2.5**
   *
   * For any authorized persons list and sample entries:
   * - If all sample persons are in the authorized list → no deviations
   * - If a sample entry has a preparer NOT in the authorized list → deviation flagged
   * - Deviation count always equals number of entries with at least one unauthorized person
   */

  /** Generate a valid person name (non-empty, no leading/trailing spaces for clean comparison) */
  const arbName = fc.string({ minLength: 1, maxLength: 5 }).map(s => s.trim()).filter(s => s.length > 0)

  /** Generate an AuthorizedPerson */
  const arbAuthorizedPerson: fc.Arbitrary<AuthorizedPerson> = fc.record({
    name: arbName,
    role: fc.constantFrom('创建', '授权', '记录'),
  })

  /** Generate a JeControlSample given a pool of names for personnel fields */
  function arbSampleFromPool(namePool: string[]): fc.Arbitrary<JeControlSample> {
    const arbPoolName = fc.constantFrom(...namePool)
    return fc.record({
      seq: fc.integer({ min: 1, max: 25 }),
      voucherDate: fc.constant('2025-03-15'),
      voucherNo: fc.constant('转-001'),
      preparer: arbPoolName,
      poster: arbPoolName,
      reviewer: arbPoolName,
      supportDoc: fc.constant(''),
      approval: fc.constant(''),
    })
  }

  it('all persons in authorized list → no deviations', () => {
    fc.assert(
      fc.property(
        fc.array(arbAuthorizedPerson, { minLength: 1, maxLength: 10 }),
        fc.integer({ min: 1, max: 15 }),
        (authorized, sampleCount) => {
          // Create samples where all personnel are from the authorized list
          const names = authorized.map(a => a.name)
          const samples: JeControlSample[] = Array.from({ length: sampleCount }, (_, i) => ({
            seq: i + 1,
            voucherDate: '2025-03-15',
            voucherNo: `转-${String(i + 1).padStart(3, '0')}`,
            preparer: names[i % names.length],
            poster: names[(i + 1) % names.length],
            reviewer: names[(i + 2) % names.length],
            supportDoc: '',
            approval: '',
          }))

          const results = checkPersonnel(samples, authorized)
          // All should have deviation=false
          for (const r of results) {
            expect(r.deviation).toBe(false)
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('preparer NOT in authorized list → deviation flagged', () => {
    fc.assert(
      fc.property(
        fc.array(arbAuthorizedPerson, { minLength: 1, maxLength: 10 }),
        arbName,
        (authorized, outsiderName) => {
          // Ensure outsider is actually not in the authorized list
          const authorizedNames = new Set(authorized.map(a => a.name.trim()))
          if (authorizedNames.has(outsiderName.trim())) return // skip if collision

          const sample: JeControlSample = {
            seq: 1,
            voucherDate: '2025-03-15',
            voucherNo: '转-001',
            preparer: outsiderName,  // NOT authorized
            poster: authorized[0].name,  // authorized
            reviewer: authorized[0].name,  // authorized
            supportDoc: '',
            approval: '',
          }

          const results = checkPersonnel([sample], authorized)
          expect(results).toHaveLength(1)
          expect(results[0].deviation).toBe(true)
          expect(results[0].deviationDetails).toContain('编制人')
        },
      ),
      { numRuns: 100 },
    )
  })

  it('deviation count equals entries with at least one unauthorized person', () => {
    fc.assert(
      fc.property(
        fc.array(arbAuthorizedPerson, { minLength: 1, maxLength: 8 }),
        fc.array(arbName, { minLength: 1, maxLength: 15 }),
        (authorized, extraNames) => {
          const authorizedNames = new Set(authorized.map(a => a.name.trim()))
          // Build samples mixing authorized and potentially unauthorized names
          const allNames = [...authorized.map(a => a.name), ...extraNames]
          const samples: JeControlSample[] = extraNames.map((_, i) => ({
            seq: i + 1,
            voucherDate: '2025-03-15',
            voucherNo: `转-${String(i + 1).padStart(3, '0')}`,
            preparer: allNames[i % allNames.length],
            poster: allNames[(i + 3) % allNames.length],
            reviewer: allNames[(i + 5) % allNames.length],
            supportDoc: '',
            approval: '',
          }))

          const results = checkPersonnel(samples, authorized)

          // Count expected deviations manually
          let expectedDeviationCount = 0
          for (const sample of samples) {
            const prep = sample.preparer?.trim() || ''
            const post = sample.poster?.trim() || ''
            const rev = sample.reviewer?.trim() || ''
            const hasUnauthorized =
              (prep !== '' && !authorizedNames.has(prep)) ||
              (post !== '' && !authorizedNames.has(post)) ||
              (rev !== '' && !authorizedNames.has(rev))
            if (hasUnauthorized) expectedDeviationCount++
          }

          const actualDeviationCount = results.filter(r => r.deviation).length
          expect(actualDeviationCount).toBe(expectedDeviationCount)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('empty personnel fields do not trigger deviation', () => {
    fc.assert(
      fc.property(
        fc.array(arbAuthorizedPerson, { minLength: 1, maxLength: 5 }),
        (authorized) => {
          // All personnel fields are empty → no deviation
          const sample: JeControlSample = {
            seq: 1,
            voucherDate: '2025-03-15',
            voucherNo: '转-001',
            preparer: '',
            poster: '',
            reviewer: '',
            supportDoc: '',
            approval: '',
          }

          const results = checkPersonnel([sample], authorized)
          expect(results[0].deviation).toBe(false)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 7: 公式不可覆盖 (P7 公式不可覆盖)
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: c23-c24-journal-entry-testing, Property 7: 公式不可覆盖', () => {
  /**
   * **Validates: Requirements 3.4**
   *
   * For any input to calcBalanceIntegrity:
   * - The result is deterministic (same input → same output)
   * - Results are derived from input data only, not from any mutable external state
   * - Computed fields (debitTotal, creditTotal, balanced) cannot be set by the user
   *   (they are always recalculated from the input entries)
   */

  /** Generate a JournalEntry for formula immutability testing */
  const arbEntry: fc.Arbitrary<JournalEntry> = fc.record({
    voucherDate: fc.constant('2025-01-15'),
    voucherMonth: fc.integer({ min: 1, max: 12 }),
    voucherType: fc.constantFrom('付', '收', '转'),
    voucherNo: fc.integer({ min: 1, max: 999 }).map(n => `转-${String(n).padStart(3, '0')}`),
    summary: fc.string({ minLength: 0, maxLength: 10 }),
    accountCode: fc.stringMatching(/^[0-9]{4}$/),
    accountName: fc.string({ minLength: 1, maxLength: 5 }),
    debit: fc.float({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }),
    credit: fc.float({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }),
    voucherSheets: fc.constant('1'),
    preparer: fc.string({ minLength: 1, maxLength: 3 }),
    reviewer: fc.string({ minLength: 1, maxLength: 3 }),
    poster: fc.string({ minLength: 1, maxLength: 3 }),
  })

  it('determinism: same input always produces same output', () => {
    fc.assert(
      fc.property(
        fc.array(arbEntry, { minLength: 0, maxLength: 30 }),
        (entries) => {
          const result1 = calcBalanceIntegrity(entries)
          const result2 = calcBalanceIntegrity(entries)
          expect(result1.debitTotal).toBe(result2.debitTotal)
          expect(result1.creditTotal).toBe(result2.creditTotal)
          expect(result1.balanced).toBe(result2.balanced)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('results derived from input only — no external state dependency', () => {
    fc.assert(
      fc.property(
        fc.array(arbEntry, { minLength: 1, maxLength: 20 }),
        (entries) => {
          // Call at different "times" (simulating external state change)
          const result1 = calcBalanceIntegrity(entries)

          // Create a deep copy of entries and verify same result
          const entriesCopy = entries.map(e => ({ ...e }))
          const result2 = calcBalanceIntegrity(entriesCopy)

          expect(result1.debitTotal).toBe(result2.debitTotal)
          expect(result1.creditTotal).toBe(result2.creditTotal)
          expect(result1.balanced).toBe(result2.balanced)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('computed fields always equal recalculation from input entries', () => {
    fc.assert(
      fc.property(
        fc.array(arbEntry, { minLength: 0, maxLength: 30 }),
        (entries) => {
          const result = calcBalanceIntegrity(entries)

          // Manually compute expected values
          const expectedDebit = Math.round(
            entries.reduce((sum, e) => sum + (e.debit || 0), 0) * 100,
          ) / 100
          const expectedCredit = Math.round(
            entries.reduce((sum, e) => sum + (e.credit || 0), 0) * 100,
          ) / 100
          const expectedBalanced = Math.abs(expectedDebit - expectedCredit) < 0.01

          // Result must always equal recalculated value — user cannot override
          expect(result.debitTotal).toBeCloseTo(expectedDebit, 2)
          expect(result.creditTotal).toBeCloseTo(expectedCredit, 2)
          expect(result.balanced).toBe(expectedBalanced)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('modifying entries and recalculating reflects new data (not cached/stale)', () => {
    fc.assert(
      fc.property(
        fc.array(arbEntry, { minLength: 1, maxLength: 20 }),
        fc.float({ min: 1, max: 1e6, noNaN: true, noDefaultInfinity: true }),
        (entries, extraAmount) => {
          const result1 = calcBalanceIntegrity(entries)

          // Add a new entry and recalculate
          const extended = [...entries, {
            voucherDate: '2025-06-01', voucherMonth: 6, voucherType: '转',
            voucherNo: '转-999', summary: 'extra', accountCode: '1001',
            accountName: '新增', debit: extraAmount, credit: 0,
            voucherSheets: '1', preparer: 'X', reviewer: 'Y', poster: 'Z',
          }]
          const result2 = calcBalanceIntegrity(extended)

          // debitTotal must be greater than before (new debit added)
          // Use raw sum comparison to avoid floating-point accumulation mismatch
          const rawSum = entries.reduce((s, e) => s + (e.debit || 0), 0) + extraAmount
          const expectedNewDebit = Math.round(rawSum * 100) / 100
          expect(result2.debitTotal).toBeCloseTo(expectedNewDebit, 2)
          // creditTotal unchanged
          expect(result2.creditTotal).toBeCloseTo(result1.creditTotal, 2)
          // Key assertion: result is NOT stale/cached from previous call
          expect(result2.debitTotal).not.toBe(result1.debitTotal)
        },
      ),
      { numRuns: 100 },
    )
  })
})
