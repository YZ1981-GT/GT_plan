/**
 * K8 跨sheet数据流 — 单元测试
 *
 * 验证 useK8CrossSheet composable 的跨sheet联动computed正确性：
 * 1. adjudicationVsDetail: K8-1审定表合计 vs K8-2明细表合计
 * 2. analysisVsDetail: K8-4实质性分析合计 vs K8-2明细表合计
 *
 * Spec: .kiro/specs/k8-selling-expenses/ Task 3.2
 * Requirements: 2.5, 3.2, 4.6
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useK8CrossSheet } from '../composables/useK8CrossSheet'

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

describe('useK8CrossSheet — 单元测试', () => {
  // ═══════════════════════════════════════════════════════════════════════════
  // 1. adjudicationVsDetail: K8-1 审定合计 vs K8-2 明细合计
  // ═══════════════════════════════════════════════════════════════════════════

  describe('adjudicationVsDetail: K8-1 ↔ K8-2 一致性', () => {
    it('K8-1审定合计 = K8-2明细合计时，isMatch=true', () => {
      const responses = buildResponses({
        'K8-1-audited-total': 1200000,
        'K8-2-total-audited': 1200000,
      })
      const allResponses = ref(responses)
      const { adjudicationVsDetail } = useK8CrossSheet(allResponses)

      expect(adjudicationVsDetail.value.isMatch).toBe(true)
      expect(adjudicationVsDetail.value.diff).toBeCloseTo(0, 2)
    })

    it('K8-1审定合计 ≠ K8-2明细合计时，isMatch=false', () => {
      const responses = buildResponses({
        'K8-1-audited-total': 1200000,
        'K8-2-total-audited': 1150000,
      })
      const allResponses = ref(responses)
      const { adjudicationVsDetail } = useK8CrossSheet(allResponses)

      expect(adjudicationVsDetail.value.isMatch).toBe(false)
      expect(adjudicationVsDetail.value.diff).toBeCloseTo(50000, 2)
    })

    it('分以内差异视为匹配（rounding tolerance）', () => {
      const responses = buildResponses({
        'K8-1-audited-total': 500000.005,
        'K8-2-total-audited': 500000,
      })
      const allResponses = ref(responses)
      const { adjudicationVsDetail } = useK8CrossSheet(allResponses)

      expect(adjudicationVsDetail.value.isMatch).toBe(true)
    })

    it('K8-1 < K8-2时diff为负（明细大于审定，可能漏列）', () => {
      const responses = buildResponses({
        'K8-1-audited-total': 800000,
        'K8-2-total-audited': 900000,
      })
      const allResponses = ref(responses)
      const { adjudicationVsDetail } = useK8CrossSheet(allResponses)

      expect(adjudicationVsDetail.value.isMatch).toBe(false)
      expect(adjudicationVsDetail.value.diff).toBeCloseTo(-100000, 2)
    })
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 2. analysisVsDetail: K8-4 实质性分析合计 vs K8-2 明细合计
  // ═══════════════════════════════════════════════════════════════════════════

  describe('analysisVsDetail: K8-4 ↔ K8-2 一致性', () => {
    it('K8-4分析合计 = K8-2明细合计时，isMatch=true', () => {
      const responses = buildResponses({
        'K8-4-analysis-total': 950000,
        'K8-2-total-audited': 950000,
      })
      const allResponses = ref(responses)
      const { analysisVsDetail } = useK8CrossSheet(allResponses)

      expect(analysisVsDetail.value.isMatch).toBe(true)
      expect(analysisVsDetail.value.diff).toBeCloseTo(0, 2)
    })

    it('K8-4分析合计 ≠ K8-2明细合计时，isMatch=false', () => {
      const responses = buildResponses({
        'K8-4-analysis-total': 950000,
        'K8-2-total-audited': 920000,
      })
      const allResponses = ref(responses)
      const { analysisVsDetail } = useK8CrossSheet(allResponses)

      expect(analysisVsDetail.value.isMatch).toBe(false)
      expect(analysisVsDetail.value.diff).toBeCloseTo(30000, 2)
    })

    it('K8-4 < K8-2时diff为负（分析表漏项）', () => {
      const responses = buildResponses({
        'K8-4-analysis-total': 800000,
        'K8-2-total-audited': 950000,
      })
      const allResponses = ref(responses)
      const { analysisVsDetail } = useK8CrossSheet(allResponses)

      expect(analysisVsDetail.value.isMatch).toBe(false)
      expect(analysisVsDetail.value.diff).toBeCloseTo(-150000, 2)
    })
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 3. 空数据场景
  // ═══════════════════════════════════════════════════════════════════════════

  describe('空数据场景', () => {
    it('allResponses为空Map时，所有检查返回isMatch=true（两侧均为0）', () => {
      const emptyMap = new Map<string, any>()
      const allResponses = ref(emptyMap)
      const { adjudicationVsDetail, analysisVsDetail } = useK8CrossSheet(allResponses)

      expect(adjudicationVsDetail.value.isMatch).toBe(true)
      expect(adjudicationVsDetail.value.diff).toBe(0)

      expect(analysisVsDetail.value.isMatch).toBe(true)
      expect(analysisVsDetail.value.diff).toBe(0)
    })

    it('仅一侧有值时，diff = 该侧值', () => {
      const responses = buildResponses({
        'K8-1-audited-total': 600000,
        // K8-2-total-audited 缺失 → 0
      })
      const allResponses = ref(responses)
      const { adjudicationVsDetail } = useK8CrossSheet(allResponses)

      expect(adjudicationVsDetail.value.isMatch).toBe(false)
      expect(adjudicationVsDetail.value.diff).toBeCloseTo(600000, 2)
    })
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 4. 响应式更新
  // ═══════════════════════════════════════════════════════════════════════════

  describe('响应式更新', () => {
    it('allResponses变化时computed自动重算', () => {
      const responses = buildResponses({
        'K8-1-audited-total': 1000000,
        'K8-2-total-audited': 1000000,
      })
      const allResponses = ref(responses)
      const { adjudicationVsDetail } = useK8CrossSheet(allResponses)

      expect(adjudicationVsDetail.value.isMatch).toBe(true)

      // 模拟 K8-2 数据变化
      const newMap = new Map(allResponses.value)
      newMap.set('K8-2-total-audited', { remark: '900000' })
      allResponses.value = newMap

      expect(adjudicationVsDetail.value.isMatch).toBe(false)
      expect(adjudicationVsDetail.value.diff).toBeCloseTo(100000, 2)
    })

    it('K8-4与K8-2同时更新时analysisVsDetail响应', () => {
      const responses = buildResponses({
        'K8-4-analysis-total': 500000,
        'K8-2-total-audited': 500000,
      })
      const allResponses = ref(responses)
      const { analysisVsDetail } = useK8CrossSheet(allResponses)

      expect(analysisVsDetail.value.isMatch).toBe(true)

      // 模拟 K8-4 更新
      const newMap = new Map(allResponses.value)
      newMap.set('K8-4-analysis-total', { remark: '520000' })
      allResponses.value = newMap

      expect(analysisVsDetail.value.isMatch).toBe(false)
      expect(analysisVsDetail.value.diff).toBeCloseTo(20000, 2)
    })
  })
})
