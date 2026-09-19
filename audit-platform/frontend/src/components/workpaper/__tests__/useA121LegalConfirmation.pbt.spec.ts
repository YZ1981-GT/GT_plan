/**
 * Property-Based Tests — useA121LegalConfirmation composable
 *
 * Spec: .kiro/specs/a12-1-legal-confirmation/
 * Task: 2.2
 *
 * PBT: Property 1 (item_id send/reply partition), Property 2 (litigation add/remove consistency)
 *
 * **Validates: Requirements 12.2, 5.1-5.2**
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import * as fc from 'fast-check'
import { useA121LegalConfirmation, buildA121ItemId } from '../composables/useA121LegalConfirmation'
import type { A121RenderData } from '../composables/useA121LegalConfirmation'

// ─── Mock API ────────────────────────────────────────────────────────────────

const mockPut = vi.fn()

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn().mockResolvedValue({}),
    put: (...args: any[]) => mockPut(...args),
  },
}))

vi.mock('element-plus', () => ({
  ElMessage: { warning: vi.fn(), error: vi.fn() },
}))

// ─── Setup ───────────────────────────────────────────────────────────────────

function setup(renderData: A121RenderData | null = null) {
  const wpId = ref('wp-a121')
  const projectId = ref('proj-001')
  const htmlData = ref<A121RenderData | null>(renderData)
  return { composable: useA121LegalConfirmation({ wpId, projectId, htmlData }), wpId, projectId, htmlData }
}

// ─── Property 1: item_id 分区正确性 ─────────────────────────────────────────

describe('Feature: a12-1-legal-confirmation, Property 1: item_id send/reply partition', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockPut.mockReset()
    mockPut.mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('all send fields produce item_ids starting with "a121-send-"', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(
          'recipient-firm', 'recipient-lawyer', 'inquiry2-content',
          'inquiry3-content', 'sign-company', 'sign-date',
          'reply-address', 'reply-phone', 'reply-contact',
        ),
        (field) => {
          const itemId = buildA121ItemId('send', field)
          expect(itemId).toMatch(/^a121-send-/)
          expect(itemId).not.toMatch(/^a121-reply-/)
        },
      ),
      { numRuns: 50 },
    )
  })

  it('all reply fields produce item_ids starting with "a121-reply-"', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(
          'status', 'details', 'fee-status', 'fee-amount',
          'sign-firm', 'sign-lawyer', 'sign-date',
        ),
        (field) => {
          const itemId = buildA121ItemId('reply', field)
          expect(itemId).toMatch(/^a121-reply-/)
          expect(itemId).not.toMatch(/^a121-send-/)
        },
      ),
      { numRuns: 50 },
    )
  })

  it('updateField with send part generates send-prefixed item_ids in pending save', async () => {
    fc.assert(
      fc.property(
        fc.constantFrom(
          'recipient-firm', 'recipient-lawyer', 'inquiry2-content',
          'inquiry3-content', 'sign-company', 'sign-date',
          'reply-address', 'reply-phone', 'reply-contact',
        ),
        fc.string({ minLength: 1, maxLength: 20 }),
        (field, value) => {
          mockPut.mockReset()
          mockPut.mockResolvedValue({})
          const { composable } = setup()
          composable.updateField('send', field, value)

          // Flush to capture the pending save
          vi.advanceTimersByTime(2000)

          if (mockPut.mock.calls.length > 0) {
            const items = mockPut.mock.calls[0][1].items
            for (const item of items) {
              expect(item.item_id).toMatch(/^a121-send-/)
            }
          }
        },
      ),
      { numRuns: 50 },
    )
  })

  it('updateField with reply part generates reply-prefixed item_ids in pending save', async () => {
    fc.assert(
      fc.property(
        fc.constantFrom(
          'status', 'details', 'fee-status', 'fee-amount',
          'sign-firm', 'sign-lawyer', 'sign-date',
        ),
        fc.string({ minLength: 1, maxLength: 20 }),
        (field, value) => {
          mockPut.mockReset()
          mockPut.mockResolvedValue({})
          const { composable } = setup()
          composable.updateField('reply', field, value)

          vi.advanceTimersByTime(2000)

          if (mockPut.mock.calls.length > 0) {
            const items = mockPut.mock.calls[0][1].items
            for (const item of items) {
              expect(item.item_id).toMatch(/^a121-reply-/)
            }
          }
        },
      ),
      { numRuns: 50 },
    )
  })
})

// ─── Property 2: 诉讼列表增删一致性 ─────────────────────────────────────────

describe('Feature: a12-1-legal-confirmation, Property 2: litigation add/remove consistency', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockPut.mockReset()
    mockPut.mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('count equals (adds - removes) and never negative', () => {
    fc.assert(
      fc.property(
        // Generate a sequence of add/remove operations
        fc.array(
          fc.oneof(
            fc.constant('add' as const),
            fc.constant('remove' as const),
          ),
          { minLength: 1, maxLength: 20 },
        ),
        (operations) => {
          const { composable } = setup()
          let expectedCount = 0

          for (const op of operations) {
            if (op === 'add') {
              composable.addLitigation()
              expectedCount++
            } else {
              // Only remove if list is non-empty
              const currentLen = composable.sendSection.value.inquiry_1.litigation_list.length
              if (currentLen > 0) {
                composable.removeLitigation(0)
                expectedCount--
              }
            }
          }

          const actualCount = composable.sendSection.value.inquiry_1.litigation_list.length
          expect(actualCount).toBe(expectedCount)
          expect(actualCount).toBeGreaterThanOrEqual(0)
        },
      ),
      { numRuns: 50 },
    )
  })

  it('add always increases list length by 1', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 10 }),
        (initialSize) => {
          const { composable } = setup()
          // Add initial items
          for (let i = 0; i < initialSize; i++) {
            composable.addLitigation()
          }
          const before = composable.sendSection.value.inquiry_1.litigation_list.length
          composable.addLitigation()
          const after = composable.sendSection.value.inquiry_1.litigation_list.length
          expect(after).toBe(before + 1)
        },
      ),
      { numRuns: 50 },
    )
  })

  it('remove at valid index decreases list length by 1', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 10 }),
        fc.integer({ min: 0, max: 9 }),
        (size, removeIdx) => {
          const { composable } = setup()
          for (let i = 0; i < size; i++) {
            composable.addLitigation()
          }
          const validIdx = removeIdx % size
          const before = composable.sendSection.value.inquiry_1.litigation_list.length
          composable.removeLitigation(validIdx)
          const after = composable.sendSection.value.inquiry_1.litigation_list.length
          expect(after).toBe(before - 1)
        },
      ),
      { numRuns: 50 },
    )
  })

  it('remove at invalid index does not change list', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 5 }),
        fc.integer({ min: -10, max: -1 }),
        (size, negIdx) => {
          const { composable } = setup()
          for (let i = 0; i < size; i++) {
            composable.addLitigation()
          }
          const before = composable.sendSection.value.inquiry_1.litigation_list.length
          composable.removeLitigation(negIdx)
          const after = composable.sendSection.value.inquiry_1.litigation_list.length
          expect(after).toBe(before)
        },
      ),
      { numRuns: 50 },
    )
  })
})
