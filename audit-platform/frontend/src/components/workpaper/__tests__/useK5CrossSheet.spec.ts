/**
 * K5 跨sheet数据流 — 单元测试
 *
 * 验证 useK5CrossSheet composable 的跨sheet联动computed正确性：
 * 1. adjudicationVsDetail: K5-1审定合计 vs K5-2明细期末合计
 * 2. warrantyVsAdjudication: K5-1产品质量保证行 vs K5-4质保测算合计
 * 3. decommissionVsAdjudication: K5-1弃置义务行 vs K5-5弃置现值合计
 * 4. litigationVsAdjudication: K5-1未决诉讼行 vs K5-6诉讼预计损失合计
 *
 * Spec: .kiro/specs/k5-provisions/ Task 3.2
 * Requirements: 2.6, 3.4, 6.3, 7.4, 8.2
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useK5CrossSheet } from '../composables/useK5CrossSheet'

/**
 * 构建一个allResponses Map，模拟跨sheet数据
 */
function buildResponses(overrides: Record<string, number | string> = {}): Map<string, any> {
  const map = new Map<string, any>()
  for (const [key, value] of Object.entries(overrides)) {
    map.set(key, { remark: String(value) })
  }
  return map
}

describe('useK5CrossSheet — 单元测试', () => {
  // ═══════════════════════════════════════════════════════════════════════════
  // 1. adjudicationVsDetail: K5-1 审定合计 vs K5-2 明细期末合计
  // ═══════════════════════════════════════════════════════════════════════════

  describe('adjudicationVsDetail: K5-1 ↔ K5-2 一致性', () => {
    it('K5-1审定合计 = K5-2明细期末合计时，isMatch=true', () => {
      const responses = buildResponses({
        'K5-1-audited-total': 500000,
        'K5-2-detail-end-total': 500000,
      })
      const allResponses = ref(responses)
      const { adjudicationVsDetail } = useK5CrossSheet(allResponses)

      expect(adjudicationVsDetail.value.isMatch).toBe(true)
      expect(adjudicationVsDetail.value.diff).toBeCloseTo(0, 2)
    })

    it('K5-1审定合计 ≠ K5-2明细期末合计时，isMatch=false', () => {
      const responses = buildResponses({
        'K5-1-audited-total': 500000,
        'K5-2-detail-end-total': 480000,
      })
      const allResponses = ref(responses)
      const { adjudicationVsDetail } = useK5CrossSheet(allResponses)

      expect(adjudicationVsDetail.value.isMatch).toBe(false)
      expect(adjudicationVsDetail.value.diff).toBeCloseTo(20000, 2)
    })

    it('分以内差异视为匹配（rounding tolerance）', () => {
      const responses = buildResponses({
        'K5-1-audited-total': 100000.005,
        'K5-2-detail-end-total': 100000,
      })
      const allResponses = ref(responses)
      const { adjudicationVsDetail } = useK5CrossSheet(allResponses)

      expect(adjudicationVsDetail.value.isMatch).toBe(true)
    })
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 2. warrantyVsAdjudication: K5-1 产品质量保证 vs K5-4 质保测算
  // ═══════════════════════════════════════════════════════════════════════════

  describe('warrantyVsAdjudication: K5-1 产品质量保证 ↔ K5-4 质保测算', () => {
    it('K5-1质保行 = K5-4质保测算合计时，isMatch=true', () => {
      const responses = buildResponses({
        'K5-1-audited-warranty': 120000,
        'K5-4-warranty-end-total': 120000,
      })
      const allResponses = ref(responses)
      const { warrantyVsAdjudication } = useK5CrossSheet(allResponses)

      expect(warrantyVsAdjudication.value.isMatch).toBe(true)
      expect(warrantyVsAdjudication.value.diff).toBeCloseTo(0, 2)
    })

    it('K5-1质保行 > K5-4质保测算（企业多提），diff>0', () => {
      const responses = buildResponses({
        'K5-1-audited-warranty': 150000,
        'K5-4-warranty-end-total': 120000,
      })
      const allResponses = ref(responses)
      const { warrantyVsAdjudication } = useK5CrossSheet(allResponses)

      expect(warrantyVsAdjudication.value.isMatch).toBe(false)
      expect(warrantyVsAdjudication.value.diff).toBeCloseTo(30000, 2)
    })

    it('K5-1质保行 < K5-4质保测算（需补提），diff<0', () => {
      const responses = buildResponses({
        'K5-1-audited-warranty': 100000,
        'K5-4-warranty-end-total': 120000,
      })
      const allResponses = ref(responses)
      const { warrantyVsAdjudication } = useK5CrossSheet(allResponses)

      expect(warrantyVsAdjudication.value.isMatch).toBe(false)
      expect(warrantyVsAdjudication.value.diff).toBeCloseTo(-20000, 2)
    })
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 3. decommissionVsAdjudication: K5-1 弃置义务 vs K5-5 弃置现值
  // ═══════════════════════════════════════════════════════════════════════════

  describe('decommissionVsAdjudication: K5-1 弃置义务 ↔ K5-5 弃置现值', () => {
    it('K5-1弃置义务行 = K5-5弃置现值合计时，isMatch=true', () => {
      const responses = buildResponses({
        'K5-1-audited-decommission': 85000,
        'K5-5-decommission-end-total': 85000,
      })
      const allResponses = ref(responses)
      const { decommissionVsAdjudication } = useK5CrossSheet(allResponses)

      expect(decommissionVsAdjudication.value.isMatch).toBe(true)
      expect(decommissionVsAdjudication.value.diff).toBeCloseTo(0, 2)
    })

    it('K5-1弃置义务行 ≠ K5-5弃置现值合计时，isMatch=false', () => {
      const responses = buildResponses({
        'K5-1-audited-decommission': 90000,
        'K5-5-decommission-end-total': 85000,
      })
      const allResponses = ref(responses)
      const { decommissionVsAdjudication } = useK5CrossSheet(allResponses)

      expect(decommissionVsAdjudication.value.isMatch).toBe(false)
      expect(decommissionVsAdjudication.value.diff).toBeCloseTo(5000, 2)
    })
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 4. litigationVsAdjudication: K5-1 未决诉讼 vs K5-6 诉讼预计损失
  // ═══════════════════════════════════════════════════════════════════════════

  describe('litigationVsAdjudication: K5-1 未决诉讼 ↔ K5-6 诉讼预计损失', () => {
    it('K5-1未决诉讼行 = K5-6诉讼损失合计时，isMatch=true', () => {
      const responses = buildResponses({
        'K5-1-audited-litigation': 200000,
        'K5-6-litigation-loss-total': 200000,
      })
      const allResponses = ref(responses)
      const { litigationVsAdjudication } = useK5CrossSheet(allResponses)

      expect(litigationVsAdjudication.value.isMatch).toBe(true)
      expect(litigationVsAdjudication.value.diff).toBeCloseTo(0, 2)
    })

    it('K5-1未决诉讼行 ≠ K5-6诉讼损失合计时，isMatch=false', () => {
      const responses = buildResponses({
        'K5-1-audited-litigation': 250000,
        'K5-6-litigation-loss-total': 200000,
      })
      const allResponses = ref(responses)
      const { litigationVsAdjudication } = useK5CrossSheet(allResponses)

      expect(litigationVsAdjudication.value.isMatch).toBe(false)
      expect(litigationVsAdjudication.value.diff).toBeCloseTo(50000, 2)
    })

    it('仅"确认"类诉讼纳入：K5-6只聚合确认类金额', () => {
      // K5-6-litigation-loss-total 应只包含确认类（很可能败诉）的预计损失
      const responses = buildResponses({
        'K5-1-audited-litigation': 200000,
        'K5-6-litigation-loss-total': 200000,
      })
      const allResponses = ref(responses)
      const { litigationVsAdjudication } = useK5CrossSheet(allResponses)

      expect(litigationVsAdjudication.value.isMatch).toBe(true)
    })
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 5. 空数据场景：allResponses为空时所有检查返回isMatch=true
  // ═══════════════════════════════════════════════════════════════════════════

  describe('空数据场景', () => {
    it('allResponses为空Map时，所有检查返回isMatch=true（两侧均为0）', () => {
      const emptyMap = new Map<string, any>()
      const allResponses = ref(emptyMap)
      const {
        adjudicationVsDetail,
        warrantyVsAdjudication,
        decommissionVsAdjudication,
        litigationVsAdjudication,
      } = useK5CrossSheet(allResponses)

      expect(adjudicationVsDetail.value.isMatch).toBe(true)
      expect(adjudicationVsDetail.value.diff).toBe(0)

      expect(warrantyVsAdjudication.value.isMatch).toBe(true)
      expect(warrantyVsAdjudication.value.diff).toBe(0)

      expect(decommissionVsAdjudication.value.isMatch).toBe(true)
      expect(decommissionVsAdjudication.value.diff).toBe(0)

      expect(litigationVsAdjudication.value.isMatch).toBe(true)
      expect(litigationVsAdjudication.value.diff).toBe(0)
    })

    it('仅一侧有值时，diff = 该侧值', () => {
      const responses = buildResponses({
        'K5-1-audited-total': 300000,
        // K5-2-detail-end-total 缺失 → 0
      })
      const allResponses = ref(responses)
      const { adjudicationVsDetail } = useK5CrossSheet(allResponses)

      expect(adjudicationVsDetail.value.isMatch).toBe(false)
      expect(adjudicationVsDetail.value.diff).toBeCloseTo(300000, 2)
    })
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 6. 响应式更新
  // ═══════════════════════════════════════════════════════════════════════════

  describe('响应式更新', () => {
    it('allResponses变化时computed自动重算', () => {
      const responses = buildResponses({
        'K5-1-audited-warranty': 100000,
        'K5-4-warranty-end-total': 100000,
      })
      const allResponses = ref(responses)
      const { warrantyVsAdjudication } = useK5CrossSheet(allResponses)

      expect(warrantyVsAdjudication.value.isMatch).toBe(true)

      // 模拟 K5-4 数据变化
      const newMap = new Map(allResponses.value)
      newMap.set('K5-4-warranty-end-total', { remark: '80000' })
      allResponses.value = newMap

      expect(warrantyVsAdjudication.value.isMatch).toBe(false)
      expect(warrantyVsAdjudication.value.diff).toBeCloseTo(20000, 2)
    })
  })
})
