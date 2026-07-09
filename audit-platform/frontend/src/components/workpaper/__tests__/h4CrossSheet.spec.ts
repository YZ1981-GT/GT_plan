/**
 * H4 跨sheet数据流 — 集成测试
 *
 * 验证 useH4CrossSheet composable 的跨sheet联动computed正确性：
 * 1. adjudicationVsDetail: H4-1审定合计 vs H4-2明细合计
 * 2. additionVsAdjudication: H4-4增加合计 vs H4-1借方发生合计
 * 3. disposalVsAdjudication: H4-5减少合计 vs H4-1贷方发生合计
 *
 * Spec: .kiro/specs/h4-engineering-materials/ Task 7.2
 * Requirements: 2.7, 3.5, 4.5
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useH4CrossSheet } from '../composables/useH4CrossSheet'

/**
 * 构建一个allResponses Map，模拟跨sheet数据
 */
function buildResponses(overrides: Record<string, any> = {}): Map<string, any> {
  const map = new Map<string, any>()
  for (const [key, value] of Object.entries(overrides)) {
    map.set(key, { remark: typeof value === 'string' ? value : String(value) })
  }
  return map
}

describe('useH4CrossSheet — 集成测试（跨sheet数据流）', () => {
  // ═══════════════════════════════════════════════════════════════════════════
  // 1. adjudicationVsDetail: H4-1审定合计 vs H4-2明细合计
  // ═══════════════════════════════════════════════════════════════════════════

  describe('adjudicationVsDetail: H4-1 ↔ H4-2 一致性', () => {
    it('H4-2明细行endAmount求和 = H4-1审定合计时，isMatch=true', () => {
      const detailRows = [
        { endAmount: 1000 },
        { endAmount: 2000 },
        { endAmount: 3000 },
      ]
      const responses = buildResponses({
        'H4-1-adjudicated-total': 6000,
        'H4-2-rows': JSON.stringify(detailRows),
      })
      const allResponses = ref(responses)
      const { adjudicationVsDetail } = useH4CrossSheet(allResponses)

      expect(adjudicationVsDetail.value.isMatch).toBe(true)
      expect(adjudicationVsDetail.value.diff).toBeCloseTo(0, 2)
    })

    it('H4-2明细行endAmount求和 ≠ H4-1审定合计时，isMatch=false', () => {
      const detailRows = [
        { endAmount: 1000 },
        { endAmount: 2000 },
      ]
      const responses = buildResponses({
        'H4-1-adjudicated-total': 5000,
        'H4-2-rows': JSON.stringify(detailRows),
      })
      const allResponses = ref(responses)
      const { adjudicationVsDetail } = useH4CrossSheet(allResponses)

      expect(adjudicationVsDetail.value.isMatch).toBe(false)
      expect(adjudicationVsDetail.value.diff).toBeCloseTo(2000, 2) // 5000 - 3000
    })

    it('使用H4-2-detail-total汇总item优先', () => {
      const responses = buildResponses({
        'H4-1-adjudicated-total': 8000,
        'H4-2-detail-total': 8000,
      })
      const allResponses = ref(responses)
      const { adjudicationVsDetail } = useH4CrossSheet(allResponses)

      expect(adjudicationVsDetail.value.isMatch).toBe(true)
      expect(adjudicationVsDetail.value.diff).toBeCloseTo(0, 2)
    })
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 2. additionVsAdjudication: H4-4增加合计 vs H4-1借方发生合计
  // ═══════════════════════════════════════════════════════════════════════════

  describe('additionVsAdjudication: H4-4 ↔ H4-1 借方一致性', () => {
    it('H4-4增加行amount合计 = H4-1借方合计时，isMatch=true', () => {
      const additionRows = [
        { amount: 500 },
        { amount: 1500 },
      ]
      const responses = buildResponses({
        'H4-1-debit-total': 2000,
        'H4-4-rows': JSON.stringify(additionRows),
      })
      const allResponses = ref(responses)
      const { additionVsAdjudication } = useH4CrossSheet(allResponses)

      expect(additionVsAdjudication.value.isMatch).toBe(true)
      expect(additionVsAdjudication.value.diff).toBeCloseTo(0, 2)
    })

    it('H4-4增加行合计 < H4-1借方合计时（抽样检查），isMatch=false', () => {
      const additionRows = [
        { amount: 300 },
      ]
      const responses = buildResponses({
        'H4-1-debit-total': 2000,
        'H4-4-rows': JSON.stringify(additionRows),
      })
      const allResponses = ref(responses)
      const { additionVsAdjudication } = useH4CrossSheet(allResponses)

      expect(additionVsAdjudication.value.isMatch).toBe(false)
      expect(additionVsAdjudication.value.diff).toBeCloseTo(-1700, 2) // 300 - 2000
    })

    it('使用H4-4-addition-total汇总item优先', () => {
      const responses = buildResponses({
        'H4-1-debit-total': 5000,
        'H4-4-addition-total': 5000,
      })
      const allResponses = ref(responses)
      const { additionVsAdjudication } = useH4CrossSheet(allResponses)

      expect(additionVsAdjudication.value.isMatch).toBe(true)
    })
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 3. disposalVsAdjudication: H4-5减少合计 vs H4-1贷方发生合计
  // ═══════════════════════════════════════════════════════════════════════════

  describe('disposalVsAdjudication: H4-5 ↔ H4-1 贷方一致性', () => {
    it('H4-5减少行amount合计 = H4-1贷方合计时，isMatch=true', () => {
      const disposalRows = [
        { amount: 800, reason: '领用出库' },
        { amount: 200, reason: '报废' },
      ]
      const responses = buildResponses({
        'H4-1-credit-total': 1000,
        'H4-5-rows': JSON.stringify(disposalRows),
      })
      const allResponses = ref(responses)
      const { disposalVsAdjudication } = useH4CrossSheet(allResponses)

      expect(disposalVsAdjudication.value.isMatch).toBe(true)
      expect(disposalVsAdjudication.value.diff).toBeCloseTo(0, 2)
    })

    it('H4-5减少合计 ≠ H4-1贷方合计时，isMatch=false', () => {
      const disposalRows = [
        { amount: 500 },
      ]
      const responses = buildResponses({
        'H4-1-credit-total': 1200,
        'H4-5-rows': JSON.stringify(disposalRows),
      })
      const allResponses = ref(responses)
      const { disposalVsAdjudication } = useH4CrossSheet(allResponses)

      expect(disposalVsAdjudication.value.isMatch).toBe(false)
      expect(disposalVsAdjudication.value.diff).toBeCloseTo(-700, 2) // 500 - 1200
    })

    it('使用H4-5-disposal-total汇总item优先', () => {
      const responses = buildResponses({
        'H4-1-credit-total': 3000,
        'H4-5-disposal-total': 3000,
      })
      const allResponses = ref(responses)
      const { disposalVsAdjudication } = useH4CrossSheet(allResponses)

      expect(disposalVsAdjudication.value.isMatch).toBe(true)
    })
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 4. 空数据场景：allResponses为空时所有检查返回isMatch=true
  // ═══════════════════════════════════════════════════════════════════════════

  describe('空数据场景', () => {
    it('allResponses为空Map时，所有检查返回isMatch=true（两侧均为0）', () => {
      const emptyMap = new Map<string, any>()
      const allResponses = ref(emptyMap)
      const { adjudicationVsDetail, additionVsAdjudication, disposalVsAdjudication } =
        useH4CrossSheet(allResponses)

      expect(adjudicationVsDetail.value.isMatch).toBe(true)
      expect(adjudicationVsDetail.value.diff).toBe(0)

      expect(additionVsAdjudication.value.isMatch).toBe(true)
      expect(additionVsAdjudication.value.diff).toBe(0)

      expect(disposalVsAdjudication.value.isMatch).toBe(true)
      expect(disposalVsAdjudication.value.diff).toBe(0)
    })

    it('H4-2-rows为无效JSON时，明细合计fallback为0', () => {
      const responses = new Map<string, any>()
      responses.set('H4-1-adjudicated-total', { remark: '0' })
      responses.set('H4-2-rows', { remark: 'invalid-json{{{' })
      const allResponses = ref(responses)
      const { adjudicationVsDetail } = useH4CrossSheet(allResponses)

      // 两侧均为0，匹配
      expect(adjudicationVsDetail.value.isMatch).toBe(true)
    })

    it('H4-4-rows为空数组JSON时，增加合计为0', () => {
      const responses = buildResponses({
        'H4-1-debit-total': 0,
        'H4-4-rows': '[]',
      })
      const allResponses = ref(responses)
      const { additionVsAdjudication } = useH4CrossSheet(allResponses)

      expect(additionVsAdjudication.value.isMatch).toBe(true)
      expect(additionVsAdjudication.value.diff).toBe(0)
    })
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 5. disclosureAutoFill 附注自动取数
  // ═══════════════════════════════════════════════════════════════════════════

  describe('disclosureAutoFill 附注自动取数', () => {
    it('正确聚合所有审定表+明细+增加+减少数据', () => {
      const responses = buildResponses({
        'H4-1-adjudicated-total': 10000,
        'H4-1-begin-total': 8000,
        'H4-1-end-total': 10000,
        'H4-1-debit-total': 3000,
        'H4-1-credit-total': 1000,
        'H4-2-detail-total': 10000,
        'H4-4-addition-total': 3000,
        'H4-5-disposal-total': 1000,
      })
      const allResponses = ref(responses)
      const { disclosureAutoFill } = useH4CrossSheet(allResponses)

      expect(disclosureAutoFill.value.disc_audited).toBe(10000)
      expect(disclosureAutoFill.value.disc_begin).toBe(8000)
      expect(disclosureAutoFill.value.disc_end).toBe(10000)
      expect(disclosureAutoFill.value.disc_debit).toBe(3000)
      expect(disclosureAutoFill.value.disc_credit).toBe(1000)
      expect(disclosureAutoFill.value.disc_detail_total).toBe(10000)
      expect(disclosureAutoFill.value.disc_addition_total).toBe(3000)
      expect(disclosureAutoFill.value.disc_disposal_total).toBe(1000)
    })
  })
})
