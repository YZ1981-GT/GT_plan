/**
 * Unit tests for useK1CrossSheet composable
 *
 * Validates: Requirements 2.9, 3.3, 4.4-4.5, 6.5
 * - adjudicationVsDetail: K1-1 审定 vs K1-2 明细合计
 * - badDebtVsCalc: K1-3 坏账期末 vs K1-8 测算应计提
 * - agingVsBalance: K1-2 账龄合计 vs 期末余额
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useK1CrossSheet } from '../useK1CrossSheet'

function makeResponses(entries: Record<string, number>) {
  const map = new Map<string, any>()
  for (const [key, value] of Object.entries(entries)) {
    map.set(key, { item_id: key, conclusion: null, remark: String(value) })
  }
  return ref(map)
}

describe('useK1CrossSheet', () => {
  describe('adjudicationVsDetail', () => {
    it('should match when K1-1 total equals K1-2 subtotal', () => {
      const responses = makeResponses({
        'K1-1-audited-receivable': 100000,
        'K1-2-end-subtotal': 100000,
      })
      const { adjudicationVsDetail } = useK1CrossSheet(responses)
      expect(adjudicationVsDetail.value.diff).toBe(0)
      expect(adjudicationVsDetail.value.isMatch).toBe(true)
    })

    it('should detect diff when K1-1 total differs from K1-2 subtotal', () => {
      const responses = makeResponses({
        'K1-1-audited-receivable': 100000,
        'K1-2-end-subtotal': 99500,
      })
      const { adjudicationVsDetail } = useK1CrossSheet(responses)
      expect(adjudicationVsDetail.value.diff).toBe(500)
      expect(adjudicationVsDetail.value.isMatch).toBe(false)
    })

    it('should tolerate sub-cent difference as match', () => {
      const responses = makeResponses({
        'K1-1-audited-receivable': 100000.005,
        'K1-2-end-subtotal': 100000,
      })
      const { adjudicationVsDetail } = useK1CrossSheet(responses)
      expect(adjudicationVsDetail.value.isMatch).toBe(true)
    })

    it('should default to 0 when keys are missing', () => {
      const responses = ref(new Map<string, any>())
      const { adjudicationVsDetail } = useK1CrossSheet(responses)
      expect(adjudicationVsDetail.value.diff).toBe(0)
      expect(adjudicationVsDetail.value.isMatch).toBe(true)
    })
  })

  describe('badDebtVsCalc', () => {
    it('should match when K1-3 bad debt end equals K1-8 calculated provision', () => {
      const responses = makeResponses({
        'K1-3-bad-debt-end': 25000,
        'K1-8-calc-provision-total': 25000,
      })
      const { badDebtVsCalc } = useK1CrossSheet(responses)
      expect(badDebtVsCalc.value.diff).toBe(0)
      expect(badDebtVsCalc.value.isMatch).toBe(true)
    })

    it('should show positive diff when company over-provisioned', () => {
      const responses = makeResponses({
        'K1-3-bad-debt-end': 30000,
        'K1-8-calc-provision-total': 25000,
      })
      const { badDebtVsCalc } = useK1CrossSheet(responses)
      expect(badDebtVsCalc.value.diff).toBe(5000)
      expect(badDebtVsCalc.value.isMatch).toBe(false)
    })

    it('should show negative diff when company under-provisioned', () => {
      const responses = makeResponses({
        'K1-3-bad-debt-end': 20000,
        'K1-8-calc-provision-total': 25000,
      })
      const { badDebtVsCalc } = useK1CrossSheet(responses)
      expect(badDebtVsCalc.value.diff).toBe(-5000)
      expect(badDebtVsCalc.value.isMatch).toBe(false)
    })
  })

  describe('agingVsBalance', () => {
    it('should match when aging subtotal equals end balance', () => {
      const responses = makeResponses({
        'K1-2-aging-subtotal': 500000,
        'K1-2-end-subtotal': 500000,
      })
      const { agingVsBalance } = useK1CrossSheet(responses)
      expect(agingVsBalance.value.diff).toBe(0)
      expect(agingVsBalance.value.isMatch).toBe(true)
    })

    it('should detect discrepancy in aging vs balance', () => {
      const responses = makeResponses({
        'K1-2-aging-subtotal': 498000,
        'K1-2-end-subtotal': 500000,
      })
      const { agingVsBalance } = useK1CrossSheet(responses)
      expect(agingVsBalance.value.diff).toBe(-2000)
      expect(agingVsBalance.value.isMatch).toBe(false)
    })
  })

  describe('reactivity', () => {
    it('should reactively update when allResponses changes', () => {
      const map = new Map<string, any>()
      map.set('K1-1-audited-receivable', { item_id: 'K1-1-audited-receivable', conclusion: null, remark: '100000' })
      map.set('K1-2-end-subtotal', { item_id: 'K1-2-end-subtotal', conclusion: null, remark: '100000' })
      const responses = ref(map)

      const { adjudicationVsDetail } = useK1CrossSheet(responses)
      expect(adjudicationVsDetail.value.isMatch).toBe(true)

      // Mutate the map
      const newMap = new Map(responses.value)
      newMap.set('K1-2-end-subtotal', { item_id: 'K1-2-end-subtotal', conclusion: null, remark: '90000' })
      responses.value = newMap

      expect(adjudicationVsDetail.value.diff).toBe(10000)
      expect(adjudicationVsDetail.value.isMatch).toBe(false)
    })
  })
})
