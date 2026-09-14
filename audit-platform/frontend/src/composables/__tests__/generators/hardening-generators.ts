/**
 * PBT generators for advanced-query-disclosure-integration-hardening.
 *
 * Feature: advanced-query-disclosure-integration-hardening
 *
 * Provides reusable fast-check arbitraries for properties P3, P5, P7, P10, P11, P12:
 * - DraftContext generator (project_id / year / section)
 * - DisclosureCell generator (with random manual/provenance/trace)
 * - Operation sequence generator (edit/save/refresh/pageChange/templateExec/reopen)
 *
 * Uses repo fast profile (numRuns defaults to project convention).
 */
import * as fc from 'fast-check'

// ---------------------------------------------------------------------------
// 1. DraftContext generator
// ---------------------------------------------------------------------------

export interface DraftContext {
  project_id: string
  year: number
  section: string
}

const PROJECT_IDS = [
  'proj-001', 'proj-002', 'proj-003', 'proj-004', 'proj-005',
  'proj-006', 'proj-007', 'proj-008',
]

const SECTIONS = [
  'revenue-recognition', 'trade-receivables', 'inventory',
  'fixed-assets', 'intangible-assets', 'investments',
  'cash-and-equivalents', 'provisions', 'equity',
]

export const arbProjectId = fc.constantFrom(...PROJECT_IDS)
export const arbYear = fc.integer({ min: 2020, max: 2030 })
export const arbSection = fc.constantFrom(...SECTIONS)

export const arbDraftContext: fc.Arbitrary<DraftContext> = fc.record({
  project_id: arbProjectId,
  year: arbYear,
  section: arbSection,
})

// ---------------------------------------------------------------------------
// 2. DisclosureCell generator
// ---------------------------------------------------------------------------

export interface DisclosureCell<T = unknown> {
  value: T
  manual: boolean
  provenance: Array<Record<string, unknown>>
  trace: Array<Record<string, unknown>>
  addr_id?: string
}

const arbProvenanceEntry = fc.record({
  source: fc.constantFrom('query', 'template', 'import', 'manual_edit'),
  timestamp: fc.integer({ min: 1700000000000, max: 1800000000000 }),
  query_id: fc.option(fc.uuid(), { nil: undefined }),
})

const arbTraceEntry = fc.record({
  step: fc.constantFrom('resolve', 'aggregate', 'merge', 'format'),
  addr_id: fc.option(
    fc.stringMatching(/^[A-Z]\d+-\d+\/[a-z_]+\/[A-Z]\d+$/),
    { nil: undefined },
  ),
  elapsed_ms: fc.integer({ min: 0, max: 5000 }),
})

export const arbDisclosureCell: fc.Arbitrary<DisclosureCell<number | string | null>> = fc.record({
  value: fc.oneof(
    fc.double({ min: -1e12, max: 1e12, noNaN: true }),
    fc.string({ minLength: 0, maxLength: 100 }),
    fc.constant(null),
  ),
  manual: fc.boolean(),
  provenance: fc.array(arbProvenanceEntry, { minLength: 0, maxLength: 3 }),
  trace: fc.array(arbTraceEntry, { minLength: 0, maxLength: 3 }),
  addr_id: fc.option(
    fc.stringMatching(/^[A-Z]\d+-\d+\/[a-z_]+\/[A-Z]\d+$/),
    { nil: undefined },
  ),
})

// ---------------------------------------------------------------------------
// 3. Operation sequence generator
// ---------------------------------------------------------------------------

export type OperationType =
  | 'edit'
  | 'save'
  | 'refresh'
  | 'pageChange'
  | 'templateExec'
  | 'reopen'

export interface Operation {
  type: OperationType
  /** For edit operations: cell index to edit */
  cellIndex?: number
  /** For pageChange: new page offset */
  newOffset?: number
  /** For edit: new value to set */
  newValue?: unknown
}

const arbEditOp: fc.Arbitrary<Operation> = fc.record({
  type: fc.constant('edit' as const),
  cellIndex: fc.integer({ min: 0, max: 99 }),
  newValue: fc.oneof(
    fc.double({ min: -1e9, max: 1e9, noNaN: true }),
    fc.string({ minLength: 1, maxLength: 50 }),
  ),
})

const arbSaveOp: fc.Arbitrary<Operation> = fc.constant({ type: 'save' as const })
const arbRefreshOp: fc.Arbitrary<Operation> = fc.constant({ type: 'refresh' as const })

const arbPageChangeOp: fc.Arbitrary<Operation> = fc.record({
  type: fc.constant('pageChange' as const),
  newOffset: fc.integer({ min: 0, max: 500 }),
})

const arbTemplateExecOp: fc.Arbitrary<Operation> = fc.constant({ type: 'templateExec' as const })
const arbReopenOp: fc.Arbitrary<Operation> = fc.constant({ type: 'reopen' as const })

export const arbOperation: fc.Arbitrary<Operation> = fc.oneof(
  { weight: 3, arbitrary: arbEditOp },
  { weight: 2, arbitrary: arbSaveOp },
  { weight: 2, arbitrary: arbRefreshOp },
  { weight: 1, arbitrary: arbPageChangeOp },
  { weight: 1, arbitrary: arbTemplateExecOp },
  { weight: 1, arbitrary: arbReopenOp },
)

export const arbOperationSequence: fc.Arbitrary<Operation[]> = fc.array(arbOperation, {
  minLength: 1,
  maxLength: 20,
})
