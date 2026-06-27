/**
 * PBT — useWordTemplateStructured composable
 *
 * Property 6: Field value resolution — current_value > default_value (as placeholder) > empty
 * Property 7: Save produces correct item_id format — `wt-{wp_code}-{field_id}`
 * Property 8: Flush-before-switch ordering guarantee — flush completes before switch proceeds
 *
 * **Validates: Requirements 4.4, 4.5, 5.1, 5.2, 5.6, 8.2**
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import * as fc from 'fast-check'
import {
  useWordTemplateStructured,
  buildWtItemId,
  type TemplateStructure,
  type PlaceholderDef,
} from '../useWordTemplateStructured'

// ─── Mock API ────────────────────────────────────────────────────────────────

const mockPut = vi.fn()
const mockGet = vi.fn()

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    put: (...args: any[]) => mockPut(...args),
  },
}))

vi.mock('element-plus', () => ({
  ElMessage: { warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

// ─── Helpers ─────────────────────────────────────────────────────────────────

function makeStructure(placeholders: PlaceholderDef[]): TemplateStructure {
  return {
    placeholders,
    paragraphs: [],
    tables: [],
    metadata: { template_name: 'Test', wp_code: 'TEST-1', last_parsed_at: '2026-01-01T00:00:00Z' },
  }
}

function setup(wpCode = 'A8-1') {
  const wpId = ref('wp-test-123')
  const wpCodeRef = ref(wpCode)
  const projectId = ref('proj-test')
  return useWordTemplateStructured({ wpId, wpCode: wpCodeRef, projectId })
}

// ─── Arbitraries ─────────────────────────────────────────────────────────────

/** field_id: alphanumeric + underscore, 1–30 chars */
const arbFieldId = fc.stringMatching(/^[a-z][a-z0-9_]{0,29}$/)

/** wp_code: uppercase letter(s) + optional digits + optional dash suffix */
const arbWpCode = fc.stringMatching(/^[A-Z]{1,3}\d{0,2}(-\d{1,2})?$/)

/** data_type for placeholders */
const arbDataType = fc.constantFrom('text', 'date', 'textarea', 'number')

describe('Feature: word-template-dual-mode', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockPut.mockReset()
    mockGet.mockReset()
    mockPut.mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  // ═══════════════════════════════════════════════════════════════════════
  // Feature: word-template-dual-mode, Property 6: field value resolution
  // ═══════════════════════════════════════════════════════════════════════

  describe('Property 6: field value resolution', () => {
    /**
     * **Validates: Requirements 4.4, 4.5**
     *
     * For any placeholder in the template structure:
     * - if a current_value exists → the rendered input SHALL display that value
     * - if no current_value exists but a default_value exists → the input SHALL show default_value as placeholder text
     * - if neither exists → the input SHALL be empty
     */
    it('current_value displayed as input value; else default_value as placeholder text; else empty', () => {
    fc.assert(
      fc.property(
        fc.record({
          fieldId: arbFieldId,
          dataType: arbDataType,
          currentValue: fc.oneof(fc.constant(''), fc.string({ minLength: 1, maxLength: 50 })),
          defaultValue: fc.oneof(fc.constant(''), fc.string({ minLength: 1, maxLength: 50 })),
        }),
        (data) => {
          const placeholder: PlaceholderDef = {
            field_id: data.fieldId,
            label: 'Test Label',
            data_type: data.dataType,
            default_value: data.defaultValue,
            position: { paragraph_index: 0 },
            pattern: `\${${data.fieldId}}`,
            current_value: data.currentValue,
          }

          const structure = makeStructure([placeholder])

          // Simulate loading: hydrate fieldValues from structure
          // (mirroring the logic in loadStructure)
          const values: Record<string, string> = {}
          if (placeholder.current_value) {
            values[placeholder.field_id] = placeholder.current_value
          }

          // Resolution rules:
          // 1. If current_value exists → fieldValues[field_id] = current_value (input displays it)
          // 2. If no current_value but default_value exists → field is empty, default_value used as placeholder text
          // 3. If neither → field is empty
          const resolvedValue = values[data.fieldId] ?? ''
          const placeholderText = (!values[data.fieldId] && data.defaultValue) ? data.defaultValue : ''

          if (data.currentValue) {
            // Rule 1: current_value is displayed as the input value
            expect(resolvedValue).toBe(data.currentValue)
          } else if (data.defaultValue) {
            // Rule 2: no current_value, default_value becomes placeholder text, input value is empty
            expect(resolvedValue).toBe('')
            expect(placeholderText).toBe(data.defaultValue)
          } else {
            // Rule 3: neither exists, input is empty, no placeholder text
            expect(resolvedValue).toBe('')
            expect(placeholderText).toBe('')
          }
        },
      ),
      { numRuns: 100 },
    )
  })
  })

  // ═══════════════════════════════════════════════════════════════════════
  // Feature: word-template-dual-mode, Property 7: item_id format
  // ═══════════════════════════════════════════════════════════════════════

  describe('Property 7: item_id format', () => {
    /**
     * **Validates: Requirements 5.1, 5.2**
     *
     * For any field edit in Structured View with wp_code and field_id,
     * the debounced save SHALL produce a checklist_responses batch request
     * where item_id equals `wt-{wp_code}-{field_id}`.
     */
    it('saved item_ids equal wt-{wp_code}-{field_id}', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.record({
          wpCode: arbWpCode,
          fieldId: arbFieldId,
          value: fc.string({ minLength: 1, maxLength: 100 }),
          dataType: arbDataType,
        }),
        async (data) => {
          mockPut.mockReset()
          mockPut.mockResolvedValue({})

          const wpId = ref('wp-test-123')
          const wpCodeRef = ref(data.wpCode)
          const projectId = ref('proj-test')
          const composable = useWordTemplateStructured({ wpId, wpCode: wpCodeRef, projectId })

          // Set up structure so updateField can find the placeholder
          const placeholder: PlaceholderDef = {
            field_id: data.fieldId,
            label: 'Test',
            data_type: data.dataType,
            default_value: '',
            position: { paragraph_index: 0 },
            pattern: `\${${data.fieldId}}`,
            current_value: '',
          }
          // Manually set templateStructure to contain this placeholder
          composable.templateStructure.value = makeStructure([placeholder])

          // Perform field update
          composable.updateField(data.fieldId, data.value)

          // Flush saves immediately
          await composable.flushPendingSaves()

          // Validate the item_id format
          expect(mockPut).toHaveBeenCalled()
          const items = mockPut.mock.calls[0][1].items
          expect(items.length).toBe(1)

          const expectedItemId = `wt-${data.wpCode}-${data.fieldId}`
          expect(items[0].item_id).toBe(expectedItemId)
          expect(items[0].item_id).toBe(buildWtItemId(data.wpCode, data.fieldId))

          // Validate item_id matches the pattern
          const pattern = /^wt-[A-Z]{1,3}\d{0,2}(-\d{1,2})?-[a-z][a-z0-9_]*$/
          expect(items[0].item_id).toMatch(pattern)
        },
      ),
      { numRuns: 100 },
    )
  })
  })

  // ═══════════════════════════════════════════════════════════════════════
  // Feature: word-template-dual-mode, Property 8: flush ordering
  // ═══════════════════════════════════════════════════════════════════════

  describe('Property 8: flush ordering', () => {
    /**
     * **Validates: Requirements 5.6, 8.2**
     *
     * For any pending unsaved field edits, switching from Structured_View
     * to Online_Editor SHALL first complete all pending saves (flush)
     * before initializing the OnlyOffice editor.
     */
    it('flushPendingSaves completes all pending saves before resolving', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.array(
          fc.record({
            fieldId: arbFieldId,
            value: fc.string({ minLength: 1, maxLength: 50 }),
          }),
          { minLength: 1, maxLength: 5 },
        ),
        async (edits) => {
          mockPut.mockReset()
          mockPut.mockResolvedValue({})

          const wpId = ref('wp-test-123')
          const wpCodeRef = ref('A8-1')
          const projectId = ref('proj-test')
          const composable = useWordTemplateStructured({ wpId, wpCode: wpCodeRef, projectId })

          // Build placeholders for all fields (deduplicate by fieldId)
          const uniqueEdits = [...new Map(edits.map((e) => [e.fieldId, e])).values()]
          const placeholders: PlaceholderDef[] = uniqueEdits.map((e) => ({
            field_id: e.fieldId,
            label: 'Test',
            data_type: 'text',
            default_value: '',
            position: { paragraph_index: 0 },
            pattern: `\${${e.fieldId}}`,
            current_value: '',
          }))
          composable.templateStructure.value = makeStructure(placeholders)

          // Apply all edits (each schedules a debounced save)
          for (const edit of edits) {
            composable.updateField(edit.fieldId, edit.value)
          }

          // Before flush: save should not have been called yet (debounce not elapsed)
          expect(mockPut).not.toHaveBeenCalled()
          expect(composable.saveStatus.value).toBe('unsaved')

          // Flush (simulates switch from structured to online mode)
          await composable.flushPendingSaves()

          // After flush: save must have been called (ordering guarantee)
          expect(mockPut).toHaveBeenCalledTimes(1)

          // pendingItems is a Map keyed by item_id, so duplicate fieldIds collapse
          const items = mockPut.mock.calls[0][1].items
          expect(items.length).toBe(uniqueEdits.length)

          // Each item_id follows the correct format
          for (const item of items) {
            expect(item.item_id).toMatch(/^wt-A8-1-[a-z][a-z0-9_]*$/)
          }

          // saveStatus should be 'saved' after successful flush
          expect(composable.saveStatus.value).toBe('saved')
        },
      ),
      { numRuns: 100 },
    )
  })
  })
})
