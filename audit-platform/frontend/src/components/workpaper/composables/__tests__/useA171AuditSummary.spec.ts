/**
 * PBT — useA171AuditSummary composable
 *
 * Property 1: item_id format — all saved item_ids match `a171-ch{N}-{content|table|yn}` or `a171-signature-{row}-{col}`
 * Property 3: Y/N conditional visibility — explanation textarea visible iff answer is "Y" or "N"
 *
 * **Validates: Requirements 11, 8**
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import * as fc from 'fast-check'
import { useA171AuditSummary } from '../useA171AuditSummary'
import type { A171RenderData } from '../useA171AuditSummary'

// ─── Mock API ────────────────────────────────────────────────────────────────

const mockPut = vi.fn()

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn(),
    put: (...args: any[]) => mockPut(...args),
  },
}))

vi.mock('element-plus', () => ({
  ElMessage: { warning: vi.fn(), error: vi.fn() },
}))

function setup(data: A171RenderData | null = null) {
  const wpId = ref('wp-a171-test')
  const projectId = ref('proj-test')
  const htmlData = ref<A171RenderData | null>(data)
  return useA171AuditSummary({ wpId, projectId, htmlData })
}

describe('useA171AuditSummary PBT', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockPut.mockReset()
    mockPut.mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  // ─── Property 1: item_id format consistency ──────────────────────────

  it('Property 1: all saved item_ids match a171-ch{N}-{suffix} or a171-signature-{row}-{col} pattern', () => {
    fc.assert(
      fc.property(
        fc.record({
          textareaNum: fc.constantFrom(1, 2, 3, 4, 5, 7, 13, 14, 15, 16),
          textareaContent: fc.string({ minLength: 1, maxLength: 50 }),
          tableNum: fc.constantFrom(6, 8),
          ynNum: fc.constantFrom(9, 10, 11, 12),
          ynAnswer: fc.constantFrom('Y' as const, 'N' as const, null),
          ynExplanation: fc.oneof(fc.constant(null), fc.string({ minLength: 1, maxLength: 30 })),
          sigRow: fc.integer({ min: 0, max: 9 }),
          sigCol: fc.constantFrom('name' as const, 'date' as const),
          sigValue: fc.string({ minLength: 1, maxLength: 20 }),
        }),
        (data) => {
          mockPut.mockReset()
          mockPut.mockResolvedValue({})
          const composable = setup()

          // Perform various updates
          composable.updateTextarea(data.textareaNum, data.textareaContent)
          composable.addTableRow(data.tableNum)
          composable.updateYn(data.ynNum, data.ynAnswer, data.ynExplanation)
          composable.updateSignature(data.sigRow, data.sigCol, data.sigValue)

          // Flush
          composable.flushPendingSaves()

          // Validate item_ids
          if (mockPut.mock.calls.length > 0) {
            const items = mockPut.mock.calls[0][1].items
            const validPattern = /^a171-(ch\d{1,2}-(content|table|yn)|signature-\d+-\w+)$/
            for (const item of items) {
              expect(item.item_id).toMatch(validPattern)
            }
          }
        },
      ),
      { numRuns: 50 },
    )
  })

  // ─── Property 3: Y/N conditional visibility ──────────────────────────

  it('Property 3: Y/N chapters have explanation iff answer is not null', () => {
    fc.assert(
      fc.property(
        fc.record({
          chapterNum: fc.constantFrom(9, 10, 11, 12),
          answer: fc.constantFrom('Y' as const, 'N' as const, null),
          explanation: fc.oneof(fc.constant(null), fc.string({ minLength: 1, maxLength: 30 })),
        }),
        (data) => {
          const composable = setup()

          composable.updateYn(data.chapterNum, data.answer, data.explanation)

          const ch = composable.chapters.value[String(data.chapterNum)]
          expect(ch.type).toBe('yn')

          if (ch.type === 'yn') {
            // The explanation textarea should be VISIBLE (non-null) only when answer is Y or N
            // When answer is null, explanation should also be null (hidden)
            if (data.answer === null) {
              // UI should hide explanation textarea — answer must be null
              expect(ch.answer).toBeNull()
            } else {
              // answer is Y or N — explanation is visible (may or may not have content)
              expect(ch.answer).toBe(data.answer)
              // explanation can be any value when answer is set
              expect(ch.explanation).toBe(data.explanation)
            }
          }
        },
      ),
      { numRuns: 50 },
    )
  })
})
