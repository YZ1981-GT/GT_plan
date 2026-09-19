/**
 * PBT — useA101GovernanceCommunication composable
 *
 * Property 1: item_id format — all saved item_ids match `a101-{section}-{field}` pattern
 * Property 2: service fee total correctness — totalFee = sum of non-null amounts
 *
 * **Validates: Requirements 11, 7**
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import * as fc from 'fast-check'
import { useA101GovernanceCommunication } from '../useA101GovernanceCommunication'
import type { A101RenderData } from '../useA101GovernanceCommunication'

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

function setup(data: A101RenderData | null = null) {
  const wpId = ref('wp-a101-test')
  const projectId = ref('proj-test')
  const htmlData = ref<A101RenderData | null>(data)
  return useA101GovernanceCommunication({ wpId, projectId, htmlData })
}

describe('useA101GovernanceCommunication PBT', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockPut.mockReset()
    mockPut.mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  // ─── Property 1: item_id format ──────────────────────────────────────

  it('Property 1: all saved item_ids match a101-{section} pattern', () => {
    fc.assert(
      fc.property(
        fc.record({
          recipientText: fc.string({ minLength: 1, maxLength: 30 }),
          chapterNum: fc.integer({ min: 1, max: 16 }),
          chapterContent: fc.string({ minLength: 1, maxLength: 100 }),
          feeIndex: fc.integer({ min: 0, max: 4 }),
          feeAmount: fc.oneof(fc.constant(null), fc.float({ min: 0, max: 1e6, noNaN: true })),
          signField: fc.constantFrom('firm_name', 'partner_name', 'date'),
          signValue: fc.string({ minLength: 1, maxLength: 20 }),
        }),
        (data) => {
          mockPut.mockReset()
          mockPut.mockResolvedValue({})
          const composable = setup()

          // Perform updates
          composable.updateRecipient(data.recipientText)
          composable.updateChapter(data.chapterNum, data.chapterContent)
          composable.updateFee(data.feeIndex, data.feeAmount)
          composable.updateSigning(data.signField, data.signValue)

          // Flush
          composable.flushPendingSaves()

          // Validate item_ids
          if (mockPut.mock.calls.length > 0) {
            const items = mockPut.mock.calls[0][1].items
            const validPattern = /^a101-(recipient|ch\d{1,2}-content|fee|sign-(firm_name|partner_name|date))$/
            for (const item of items) {
              expect(item.item_id).toMatch(validPattern)
            }
          }
        },
      ),
      { numRuns: 50 },
    )
  })

  // ─── Property 2: service fee total correctness ────────────────────────

  it('Property 2: totalFee equals sum of all non-null fee amounts', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.oneof(
            fc.constant(null),
            fc.float({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }),
          ),
          { minLength: 5, maxLength: 5 },
        ),
        (amounts) => {
          const fees = [
            { name: '审计服务', amount: amounts[0] },
            { name: '审阅服务', amount: amounts[1] },
            { name: '其他鉴证服务', amount: amounts[2] },
            { name: '税务服务', amount: amounts[3] },
            { name: '其他服务', amount: amounts[4] },
          ]
          const composable = setup({ service_fees: fees })

          const expectedTotal = amounts.reduce((sum: number, a) => sum + (a ?? 0), 0)
          expect(composable.totalFee.value).toBeCloseTo(expectedTotal, 2)
        },
      ),
      { numRuns: 50 },
    )
  })
})
