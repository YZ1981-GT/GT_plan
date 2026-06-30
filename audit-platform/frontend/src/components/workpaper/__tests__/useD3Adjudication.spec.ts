/**
 * useD3Adjudication PBT 测试
 *
 * Property-Based Tests 使用 fast-check，numRuns: 100。
 * 覆盖 D3-1 审定表 AJE/RJE EventBus 同步逻辑。
 *
 * 测试 onAdjustmentCreated 函数：adjustment:created 事件触发后，
 * 对应列值（AJE→currentAje / RJE→currentRje）正确累加。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { ref } from 'vue'
import { useD3Adjudication, type AdjustmentPayload } from '../composables/useD3Adjudication'
import type { ChecklistResponse } from '../composables/useD3FormData'

// ─── Test Helper: create minimal composable instance ─────────────────────────

function createTestInstance() {
  const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
  const wpId = ref('test-wp')
  const projectId = ref('test-project')
  const isReadonly = ref(false)

  const savedItems: Array<{ itemId: string; data: Partial<ChecklistResponse> }> = []

  const saveImmediate = async (itemId: string, data: Partial<ChecklistResponse>) => {
    savedItems.push({ itemId, data })
    const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    allResponses.value.set(itemId, { ...existing, ...data } as ChecklistResponse)
  }

  const debouncedSave = (itemId: string, data: Partial<ChecklistResponse>) => {
    const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    allResponses.value.set(itemId, { ...existing, ...data } as ChecklistResponse)
  }

  // Minimal crossSheet mock: empty aggregations
  const crossSheet = {
    natureAggregation: ref<Record<string, { prior: number; current: number }>>({}),
    agingAggregation: ref({
      within1: 0, y1to2: 0, y2to3: 0, over3: 0,
      prior_within1: 0, prior_y1to2: 0, prior_y2to3: 0, prior_over3: 0,
    }),
    longTermRows: ref([]),
    relatedPartyRows: ref([]),
    adjustmentTotals: ref({ ajeTotal: 0, rjeTotal: 0 }),
    adjudicationForDisclosure: ref({ natureAggregation: {}, agingAggregation: { within1: 0, y1to2: 0, y2to3: 0, over3: 0, prior_within1: 0, prior_y1to2: 0, prior_y2to3: 0, prior_over3: 0 }, longTermRows: [] }),
    postPeriodSettlementSync: ref({ byCustomer: {}, total: 0 }),
    crossSheetStatus: ref('loaded' as const),
  }

  const instance = useD3Adjudication({
    allResponses,
    wpId,
    projectId,
    saveImmediate,
    debouncedSave,
    crossSheet: crossSheet as any,
    isReadonly,
  })

  return { instance, allResponses, savedItems }
}

// ─── Property-Based Tests ───────────────────────────────────────────────────

describe('useD3Adjudication - Property-Based Tests', () => {
  /**
   * **Feature: d3-prepaid-accounts, Property 9: 调整分录EventBus同步正确性**
   *
   * For any adjustment:created事件payload（含entryType='AJE'|'RJE', amount），
   * 审定表D3-1对应列应累加该金额（AJE→currentAje，RJE→currentRje）。
   *
   * **Validates: Requirements 2.5, 7.4**
   */
  describe('Property 9: 调整分录EventBus同步正确性', () => {
    it('事件触发后对应列值正确累加', () => {
      fc.assert(
        fc.property(
          fc.array(
            fc.record({
              entryType: fc.constantFrom('AJE', 'RJE') as fc.Arbitrary<'AJE' | 'RJE'>,
              amount: fc.float({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
            }),
            { minLength: 1, maxLength: 20 }
          ),
          (events) => {
            const { instance } = createTestInstance()

            // Compute expected accumulations
            let expectedAje = 0
            let expectedRje = 0

            for (const event of events) {
              if (event.entryType === 'AJE') {
                expectedAje += event.amount
              } else {
                expectedRje += event.amount
              }

              // Fire event
              const payload: AdjustmentPayload = {
                wpCode: 'D3',
                entryType: event.entryType,
                amount: event.amount,
                accountCode: '2203',
              }
              instance.onAdjustmentCreated(payload)
            }

            // Assert accumulated values match
            const actualAje = instance._eventAjeAccum.value
            const actualRje = instance._eventRjeAccum.value

            // Use tolerance for floating point
            if (Math.abs(actualAje - expectedAje) > 1e-4) return false
            if (Math.abs(actualRje - expectedRje) > 1e-4) return false

            return true
          }
        ),
        { numRuns: 100 }
      )
    })

    it('仅D3事件触发累加，其他wpCode忽略', () => {
      fc.assert(
        fc.property(
          fc.constantFrom('AJE', 'RJE') as fc.Arbitrary<'AJE' | 'RJE'>,
          fc.float({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
          fc.constantFrom('D1', 'D2', 'D4', 'D5', 'D7'),
          (entryType, amount, otherWpCode) => {
            const { instance } = createTestInstance()

            // Fire event with non-D3 wpCode
            const payload: AdjustmentPayload = {
              wpCode: otherWpCode,
              entryType,
              amount,
              accountCode: '2203',
            }
            instance.onAdjustmentCreated(payload)

            // Should NOT accumulate
            return instance._eventAjeAccum.value === 0 && instance._eventRjeAccum.value === 0
          }
        ),
        { numRuns: 100 }
      )
    })

    it('AJE和RJE互相独立累加不干扰', () => {
      fc.assert(
        fc.property(
          fc.float({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
          fc.float({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
          (ajeAmount, rjeAmount) => {
            const { instance } = createTestInstance()

            // Fire AJE event
            instance.onAdjustmentCreated({ wpCode: 'D3', entryType: 'AJE', amount: ajeAmount })

            // RJE should still be 0
            if (Math.abs(instance._eventRjeAccum.value) > 1e-10) return false

            // Fire RJE event
            instance.onAdjustmentCreated({ wpCode: 'D3', entryType: 'RJE', amount: rjeAmount })

            // AJE should remain unchanged at ajeAmount
            if (Math.abs(instance._eventAjeAccum.value - ajeAmount) > 1e-4) return false
            // RJE should equal rjeAmount
            if (Math.abs(instance._eventRjeAccum.value - rjeAmount) > 1e-4) return false

            return true
          }
        ),
        { numRuns: 100 }
      )
    })
  })
})
