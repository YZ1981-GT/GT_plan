/**
 * useConsolReportAddress — Property 25: Consolidation Address Resolution Additive + Numbers Unchanged
 *
 * **Validates: Requirements 20.1, 20.3, 20.5, 20.7, 20.9**
 *
 * ACNR consumer wiring, task 31.5 — P25. This file adds the fast-check property that
 * must hold for **any** random registry state (TB / REPORT address sets) and any random
 * account codes / report rows, driving the ACNR-backed `useAddressRegistry` store via
 * `store.addresses` and mocking `@/services/acnr/useAcnr`.
 *
 * The property has three limbs (design §"Correctness Properties (Expansion 5 — P25)"):
 *
 *   (a) Resolvable → addr / fallback: WHEN an account_code is registered in the TB domain,
 *       `accountIndexRef` returns the canonical `TB:{code}` index ns (resolvable → addr);
 *       WHEN it is NOT registered — or the TB registry is empty (not loaded) — it returns
 *       null so callers fall back to plain-text (Req 20.7, no blank render).
 *
 *   (b) Pure derivation: `accountForRow` is a pure read of the row's own
 *       standard_account_code / account_code / (row_code → REPORT account mapping); it never
 *       throws and returns null on empty / non-object input.
 *
 *   (c) Additive, numbers unchanged (Req 20.9): the presence/absence of registry data never
 *       mutates the input row objects, and the derived account for a row is identical whether
 *       or not the TB registry is loaded — ACNR routing is purely additive to chip/jump, it
 *       does not change the derivation. (`accountIndexRef` output, when non-null, is always the
 *       `TB:` index-ns form — never a bare addr_id containing `/`, the GtIndexChip contract.)
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import * as fc from 'fast-check'

// Mock the ACNR SDK — both this composable and the addressRegistry store import it.
// P25 (a)/(b)/(c) exercise pure derivation + chip gating only; resolve* are unused here
// but must exist so store creation + composable setup don't blow up.
vi.mock('@/services/acnr/useAcnr', () => {
  const resolveIndex = vi.fn().mockResolvedValue({ found: false })
  const resolveUri = vi.fn().mockResolvedValue({ found: false })
  return {
    useAcnr: () => ({
      resolveIndex,
      resolveUri,
      resolveFormula: vi.fn().mockResolvedValue({ found: false }),
      resolveAddr: vi.fn().mockResolvedValue({ found: false }),
      resolveInstance: vi.fn().mockResolvedValue({ found: false }),
      listSheets: vi.fn().mockResolvedValue([]),
      listCells: vi.fn().mockResolvedValue([]),
      buildAddressTree: vi.fn().mockResolvedValue([]),
      loadCellNodes: vi.fn().mockResolvedValue([]),
      clearCache: vi.fn(),
      loading: { value: false },
      sheets: { value: [] },
      cells: { value: [] },
    }),
  }
})

import { useAddressRegistry } from '@/stores/addressRegistry'
import { useConsolReportAddress } from '../composables/useConsolReportAddress'

// ─── helpers ────────────────────────────────────────────────────────────────

/** TB-domain address entry keyed by account_code (canonical TB coordinate). */
function tbEntry(code: string) {
  return {
    uri: `tb://${code}`,
    domain: 'tb',
    source: 'tb',
    path: '',
    cell: '',
    label: code,
    formula_ref: '',
    jump_route: '',
    account_code: code,
  }
}

/** REPORT-domain address entry (row_code → account_code mapping). */
function reportEntry(rowCode: string, accountCode: string) {
  return {
    uri: `report://${rowCode}`,
    domain: 'report',
    source: 'report',
    path: '',
    cell: '',
    label: rowCode,
    formula_ref: '',
    jump_route: '',
    row_code: rowCode,
    account_code: accountCode,
  }
}

/** Mirror of the composable's private `norm`. */
const norm = (s: unknown): string => (typeof s === 'string' ? s.trim() : '')

/** Reference implementation of accountForRow's pure derivation. */
function expectedAccount(
  row: Record<string, unknown> | null | undefined,
  reportMap: Record<string, string>,
): string | null {
  if (!row || typeof row !== 'object') return null
  const direct =
    norm((row as { standard_account_code?: unknown }).standard_account_code) ||
    norm((row as { account_code?: unknown }).account_code)
  if (direct) return direct
  const rc = norm((row as { row_code?: unknown }).row_code)
  if (rc && reportMap[rc]) return reportMap[rc]
  return null
}

/** Digit-only account code (real TB codes never contain '/'). */
const codeArb = fc.integer({ min: 1000, max: 9999 }).map(String)

describe('useConsolReportAddress — P25 additive resolution + numbers unchanged (property)', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('(a) TB registered → TB:{code}; unregistered / empty registry → null fallback (Req 20.1/20.7)', () => {
    fc.assert(
      fc.property(fc.uniqueArray(codeArb, { maxLength: 10 }), codeArb, (registered, query) => {
        setActivePinia(createPinia())
        const store = useAddressRegistry()
        store.addresses = registered.map(tbEntry) as never

        const { accountIndexRef } = useConsolReportAddress()
        const ref = accountIndexRef(query)

        if (registered.length === 0) {
          // TB registry not loaded → no fake chip (degrade to plain text)
          expect(ref).toBeNull()
        } else if (registered.includes(query)) {
          // resolvable → canonical TB index ns
          expect(ref).toBe(`TB:${query}`)
        } else {
          // registered but this code missing → fallback plain text
          expect(ref).toBeNull()
        }

        // GtIndexChip contract: non-null output is always the `TB:` index-ns form,
        // never a bare addr_id containing `/`.
        if (ref !== null) {
          expect(ref.startsWith('TB:')).toBe(true)
          expect(ref.includes('/')).toBe(false)
        }
      }),
      { numRuns: 60 },
    )
  })

  it('(b) accountForRow is a pure derivation — never throws, null on empty (Req 20.9)', () => {
    const reportMap: Record<string, string> = { 'BS-001': '1601', 'IS-019': '6001' }

    const fieldArb = fc.oneof(
      fc.constant(undefined),
      fc.constant(''),
      fc.constant('   '),
      fc.integer({ min: 1000, max: 9999 }).map(String),
      fc.integer({ min: 1000, max: 9999 }), // non-string → norm() = ''
    )
    const rowArb = fc.record(
      {
        standard_account_code: fieldArb,
        account_code: fieldArb,
        row_code: fc.oneof(
          fc.constant(undefined),
          fc.constantFrom('BS-001', 'IS-019', 'ZZZ-999'),
        ),
        amount: fc.double({ noNaN: true }), // extra numeric payload — must never change
      },
      { requiredKeys: [] },
    )

    fc.assert(
      fc.property(fc.uniqueArray(codeArb, { maxLength: 6 }), rowArb, (tbCodes, row) => {
        setActivePinia(createPinia())
        const store = useAddressRegistry()
        store.addresses = [
          ...tbCodes.map(tbEntry),
          ...Object.entries(reportMap).map(([rc, ac]) => reportEntry(rc, ac)),
        ] as never

        const { accountForRow } = useConsolReportAddress()

        // never throws on empty / non-object
        expect(accountForRow(null)).toBeNull()
        expect(accountForRow(undefined)).toBeNull()
        expect(accountForRow({} as Record<string, unknown>)).toBeNull()

        // matches the pure reference derivation
        const got = accountForRow(row as Record<string, unknown>)
        expect(got).toBe(expectedAccount(row as Record<string, unknown>, reportMap))
      }),
      { numRuns: 80 },
    )
  })

  it('(c) additive: registry presence never mutates the row, derivation is registry-independent (Req 20.9)', () => {
    const reportMap: Record<string, string> = { 'BS-001': '1601' }

    const rowArb = fc.record(
      {
        standard_account_code: fc.oneof(fc.constant(undefined), codeArb),
        account_code: fc.oneof(fc.constant(undefined), codeArb),
        row_code: fc.oneof(fc.constant(undefined), fc.constantFrom('BS-001', 'ZZZ-000')),
        balance: fc.double({ noNaN: true }),
        name: fc.string({ maxLength: 8 }),
      },
      { requiredKeys: [] },
    )

    fc.assert(
      fc.property(fc.uniqueArray(codeArb, { maxLength: 6 }), rowArb, (tbCodes, row) => {
        const snapshot = JSON.parse(JSON.stringify(row))

        // (1) full registry (TB + REPORT) loaded
        setActivePinia(createPinia())
        const storeFull = useAddressRegistry()
        storeFull.addresses = [
          ...tbCodes.map(tbEntry),
          ...Object.entries(reportMap).map(([rc, ac]) => reportEntry(rc, ac)),
        ] as never
        const apiFull = useConsolReportAddress()
        const withRegistry = apiFull.accountForRow(row as Record<string, unknown>)
        apiFull.accountIndexRef((row as { account_code?: string }).account_code)
        apiFull.isReportRowRegistered(String((row as { row_code?: string }).row_code ?? ''))

        // input row is never mutated by any read
        expect(JSON.parse(JSON.stringify(row))).toEqual(snapshot)

        // (2) TB registry absent (only REPORT map) → same derived account (additive)
        setActivePinia(createPinia())
        const storeNoTb = useAddressRegistry()
        storeNoTb.addresses = Object.entries(reportMap).map(([rc, ac]) =>
          reportEntry(rc, ac),
        ) as never
        const withoutTb = useConsolReportAddress().accountForRow(row as Record<string, unknown>)

        expect(withoutTb).toBe(withRegistry)
        // still identical to the pure reference derivation
        expect(withRegistry).toBe(expectedAccount(row as Record<string, unknown>, reportMap))
      }),
      { numRuns: 60 },
    )
  })
})
