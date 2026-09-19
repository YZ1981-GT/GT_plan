/**
 * Integration Tests — H5 油气资产跨Sheet数据流 + 行业守卫
 *
 * Spec: .kiro/specs/h5-oil-gas-assets/ Task 7.2
 * Requirements: 2.8, 7.6, 12.1-12.3
 *
 * 测试范围：
 * 1. useH5CrossSheet — H5-1↔H5-2 一致性 / 折耗↔审定表同步
 * 2. useH5IndustryGuard — 行业拦截逻辑
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import { useH5CrossSheet } from '../composables/useH5CrossSheet'
import {
  useH5IndustryGuard,
  APPLICABLE_INDUSTRIES,
  INDUSTRY_GUARD_MESSAGE,
} from '../composables/useH5IndustryGuard'

// ============================================================
// useH5CrossSheet — 跨Sheet数据流集成
// ============================================================

describe('useH5CrossSheet — 跨Sheet一致性检查', () => {
  // 辅助：构造 allResponses Map
  function buildResponses(entries: Record<string, number>): ReturnType<typeof ref> {
    const map = new Map<string, any>()
    for (const [key, val] of Object.entries(entries)) {
      map.set(key, { remark: String(val) })
    }
    return ref(map)
  }

  // ── adjudicationVsDetail: H5-1审定合计 vs H5-2明细合计 ──

  describe('adjudicationVsDetail (Req 2.8)', () => {
    it('匹配：审定合计 = 明细合计 → isMatch=true, diff=0', () => {
      const responses = buildResponses({
        'H5-1-cost-total': 1000000,
        'H5-2-cost-total': 1000000,
      })
      const { adjudicationVsDetail } = useH5CrossSheet(responses)
      expect(adjudicationVsDetail.value.isMatch).toBe(true)
      expect(adjudicationVsDetail.value.diff).toBe(0)
    })

    it('不匹配：审定合计 > 明细合计 → diff > 0', () => {
      const responses = buildResponses({
        'H5-1-cost-total': 1000000,
        'H5-2-cost-total': 950000,
      })
      const { adjudicationVsDetail } = useH5CrossSheet(responses)
      expect(adjudicationVsDetail.value.isMatch).toBe(false)
      expect(adjudicationVsDetail.value.diff).toBe(50000)
    })

    it('缺失数据：key不存在 → 视为0', () => {
      const responses = buildResponses({
        'H5-1-cost-total': 500000,
      })
      const { adjudicationVsDetail } = useH5CrossSheet(responses)
      expect(adjudicationVsDetail.value.diff).toBe(500000)
      expect(adjudicationVsDetail.value.isMatch).toBe(false)
    })

    it('容差内匹配：差 < 0.01', () => {
      const responses = buildResponses({
        'H5-1-cost-total': 1000000.005,
        'H5-2-cost-total': 1000000,
      })
      const { adjudicationVsDetail } = useH5CrossSheet(responses)
      expect(adjudicationVsDetail.value.isMatch).toBe(true)
    })
  })

  // ── depletionVsAdjudication: H5-12折耗计提 vs H5-1累计折耗本期贷方 ──

  describe('depletionVsAdjudication (Req 7.6)', () => {
    it('匹配：折耗计提 = 审定表贷方', () => {
      const responses = buildResponses({
        'H5-1-depletion-credit': 300000,
        'H5-12-depletion-total': 300000,
      })
      const { depletionVsAdjudication } = useH5CrossSheet(responses)
      expect(depletionVsAdjudication.value.isMatch).toBe(true)
      expect(depletionVsAdjudication.value.diff).toBe(0)
    })

    it('不匹配：审定表贷方 > 折耗测算', () => {
      const responses = buildResponses({
        'H5-1-depletion-credit': 350000,
        'H5-12-depletion-total': 300000,
      })
      const { depletionVsAdjudication } = useH5CrossSheet(responses)
      expect(depletionVsAdjudication.value.isMatch).toBe(false)
      expect(depletionVsAdjudication.value.diff).toBe(50000)
    })

    it('折耗测算 > 审定表贷方 → diff < 0', () => {
      const responses = buildResponses({
        'H5-1-depletion-credit': 280000,
        'H5-12-depletion-total': 300000,
      })
      const { depletionVsAdjudication } = useH5CrossSheet(responses)
      expect(depletionVsAdjudication.value.diff).toBe(-20000)
    })
  })

  // ── additionVsAdjudication: H5-7增加 vs H5-1原值借方 ──

  describe('additionVsAdjudication (Req 2.8)', () => {
    it('匹配：增加合计 = 原值借方', () => {
      const responses = buildResponses({
        'H5-1-cost-debit': 200000,
        'H5-7-addition-total': 200000,
      })
      const { additionVsAdjudication } = useH5CrossSheet(responses)
      expect(additionVsAdjudication.value.isMatch).toBe(true)
    })

    it('不匹配：借方 > 增加合计', () => {
      const responses = buildResponses({
        'H5-1-cost-debit': 250000,
        'H5-7-addition-total': 200000,
      })
      const { additionVsAdjudication } = useH5CrossSheet(responses)
      expect(additionVsAdjudication.value.diff).toBe(50000)
      expect(additionVsAdjudication.value.isMatch).toBe(false)
    })
  })

  // ── disposalVsAdjudication: H5-8减少 vs H5-1原值贷方 ──

  describe('disposalVsAdjudication (Req 2.8)', () => {
    it('匹配：减少合计 = 原值贷方', () => {
      const responses = buildResponses({
        'H5-1-cost-credit': 150000,
        'H5-8-disposal-total': 150000,
      })
      const { disposalVsAdjudication } = useH5CrossSheet(responses)
      expect(disposalVsAdjudication.value.isMatch).toBe(true)
    })

    it('不匹配', () => {
      const responses = buildResponses({
        'H5-1-cost-credit': 150000,
        'H5-8-disposal-total': 120000,
      })
      const { disposalVsAdjudication } = useH5CrossSheet(responses)
      expect(disposalVsAdjudication.value.diff).toBe(30000)
    })
  })

  // ── 响应式更新 ──

  describe('响应式联动', () => {
    it('allResponses变更后 computed 自动更新', () => {
      const map = new Map<string, any>()
      map.set('H5-1-cost-total', { remark: '1000' })
      map.set('H5-2-cost-total', { remark: '1000' })
      const responses = ref(map)

      const { adjudicationVsDetail } = useH5CrossSheet(responses)
      expect(adjudicationVsDetail.value.isMatch).toBe(true)

      // 修改明细合计 → 触发响应式更新
      const newMap = new Map(responses.value)
      newMap.set('H5-2-cost-total', { remark: '900' })
      responses.value = newMap

      expect(adjudicationVsDetail.value.isMatch).toBe(false)
      expect(adjudicationVsDetail.value.diff).toBe(100)
    })
  })
})

// ============================================================
// useH5IndustryGuard — 行业适用性拦截
// ============================================================

describe('useH5IndustryGuard — 行业拦截 (Req 12.1-12.3)', () => {
  // 注意：useH5IndustryGuard 使用 inject('projectContext')，
  // 在非组件环境下 inject 返回 fallback null → 默认放行。
  // 这里我们直接测试常量和核心逻辑。

  describe('APPLICABLE_INDUSTRIES 白名单', () => {
    it('包含 oil_gas', () => {
      expect(APPLICABLE_INDUSTRIES).toContain('oil_gas')
    })

    it('包含 mining', () => {
      expect(APPLICABLE_INDUSTRIES).toContain('mining')
    })

    it('不包含其他行业', () => {
      expect(APPLICABLE_INDUSTRIES).not.toContain('manufacturing')
      expect(APPLICABLE_INDUSTRIES).not.toContain('financial')
      expect(APPLICABLE_INDUSTRIES).not.toContain('retail')
    })

    it('只有2个适用行业', () => {
      expect(APPLICABLE_INDUSTRIES).toHaveLength(2)
    })
  })

  describe('INDUSTRY_GUARD_MESSAGE 提示信息', () => {
    it('包含关键信息', () => {
      expect(INDUSTRY_GUARD_MESSAGE).toContain('石油天然气')
      expect(INDUSTRY_GUARD_MESSAGE).toContain('采矿')
    })
  })

  describe('行业判断逻辑（无inject环境默认放行）', () => {
    it('无 projectContext → isApplicable = true', () => {
      // 在非组件环境中 inject 返回 null fallback，守卫默认放行
      const { isApplicable, message } = useH5IndustryGuard()
      expect(isApplicable.value).toBe(true)
      expect(message.value).toBe('')
    })
  })

  describe('行业白名单校验逻辑（直接测试判断）', () => {
    it('oil_gas 在白名单中 → 适用', () => {
      const industry = 'oil_gas'
      const applicable = (APPLICABLE_INDUSTRIES as readonly string[]).includes(industry)
      expect(applicable).toBe(true)
    })

    it('mining 在白名单中 → 适用', () => {
      const industry = 'mining'
      const applicable = (APPLICABLE_INDUSTRIES as readonly string[]).includes(industry)
      expect(applicable).toBe(true)
    })

    it('manufacturing 不在白名单中 → 不适用', () => {
      const industry = 'manufacturing'
      const applicable = (APPLICABLE_INDUSTRIES as readonly string[]).includes(industry)
      expect(applicable).toBe(false)
    })

    it('空字符串不在白名单 → 但守卫默认放行（未设置行业）', () => {
      const industry = ''
      const applicable = (APPLICABLE_INDUSTRIES as readonly string[]).includes(industry)
      expect(applicable).toBe(false)
      // 注意：实际 composable 中空 industry 默认放行（isApplicable=true）
    })

    it('financial_services 不适用', () => {
      const industry = 'financial_services'
      const applicable = (APPLICABLE_INDUSTRIES as readonly string[]).includes(industry)
      expect(applicable).toBe(false)
    })
  })
})
