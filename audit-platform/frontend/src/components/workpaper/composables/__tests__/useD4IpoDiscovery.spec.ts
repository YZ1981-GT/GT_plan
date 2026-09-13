/**
 * useD4IpoDiscovery — 行为守卫
 *
 * 验证：
 * 1. 四表候选收集正确性
 * 2. 人工确认三要件门控（direction + amount>0 + evidence）
 * 3. 推送幂等（已推不重推）
 * 4. 只读态不可写入
 * 5. 变异锚点
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

// Mock eventBus before importing the module
vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    emit: vi.fn(),
    on: vi.fn(),
    off: vi.fn(),
  },
}))

import { useD4IpoDiscovery, type IpoDiscoveryCandidate } from '../useD4IpoDiscovery'
import { eventBus } from '@/utils/eventBus'

function createHarness(readonly = false) {
  return useD4IpoDiscovery({
    projectId: ref('proj-1'),
    wpId: ref('wp-1'),
    isReadonly: ref(readonly),
  })
}

describe('useD4IpoDiscovery', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // ═══ 1. D4-29 风险收集 ═══

  describe('D4-29 risks', () => {
    it('收集关联方+供应商双标记客户', () => {
      const h = createHarness()
      h.collectD429Risks([
        { id: 'c1', name: '客户甲', fields: { isRelated: '是', isAlsoSupplier: '是' } },
        { id: 'c2', name: '客户乙', fields: { isRelated: '否' } },
      ])
      expect(h.totalCandidates.value).toBe(1)
      expect(h.candidates.value[0].sourceId).toBe('D4-29:c1')
      expect(h.candidates.value[0].description).toContain('关联方')
      expect(h.candidates.value[0].description).toContain('供应商')
    })

    it('无风险标记则无候选', () => {
      const h = createHarness()
      h.collectD429Risks([{ id: 'c1', name: '正常客户', fields: {} }])
      expect(h.totalCandidates.value).toBe(0)
    })

    it('失信+拖欠标记收集', () => {
      const h = createHarness()
      h.collectD429Risks([
        { id: 'c1', name: '问题客户', fields: { isBlacklisted: '是', hasOverdue: '是' } },
      ])
      expect(h.totalCandidates.value).toBe(1)
      expect(h.candidates.value[0].description).toContain('失信')
      expect(h.candidates.value[0].description).toContain('拖欠')
    })
  })

  // ═══ 2. D4-30 访谈发现 ═══

  describe('D4-30 findings', () => {
    it('结论含异常关键词时收集', () => {
      const h = createHarness()
      h.collectD430Findings([
        { id: 'iv1', name: '客户A', fields: { conclusion: '交易金额与规模不匹配' } },
      ])
      expect(h.totalCandidates.value).toBe(1)
      expect(h.candidates.value[0].source).toBe('D4-30-interview')
      expect(h.candidates.value[0].description).toContain('不匹配')
    })

    it('正常结论不收集', () => {
      const h = createHarness()
      h.collectD430Findings([
        { id: 'iv1', name: '客户A', fields: { conclusion: '经营正常' } },
      ])
      expect(h.totalCandidates.value).toBe(0)
    })
  })

  // ═══ 3. D4-31 红旗 ═══

  describe('D4-31 red flags', () => {
    it('q5_otherMatters 非空时收集', () => {
      const h = createHarness()
      h.collectD431RedFlags({
        target: 'ABC公司',
        q5_otherMatters: '发现资金异常往来',
        q4_otherFunds: '否',
      })
      expect(h.totalCandidates.value).toBe(1)
      expect(h.candidates.value[0].source).toBe('D4-31-redFlag')
      expect(h.candidates.value[0].description).toContain('其他重要事项')
    })

    it('q4_otherFunds=是时收集', () => {
      const h = createHarness()
      h.collectD431RedFlags({ target: 'DEF公司', q4_otherFunds: '是' })
      expect(h.totalCandidates.value).toBe(1)
      expect(h.candidates.value[0].description).toContain('其他资金往来')
    })

    it('无红旗则不收集', () => {
      const h = createHarness()
      h.collectD431RedFlags({ target: 'GHI', q5_otherMatters: '', q4_otherFunds: '否' })
      expect(h.totalCandidates.value).toBe(0)
    })
  })

  // ═══ 4. D4-32 异常流水 ═══

  describe('D4-32 anomalies', () => {
    it('hasAnomaly=是的行收集', () => {
      const h = createHarness()
      h.collectD432Anomalies([
        {
          key: 'customer',
          rows: [
            { id: 'r1', name: '客户B', amount: 200000, hasAnomaly: '是' },
            { id: 'r2', name: '客户C', amount: 100000, hasAnomaly: '否' },
          ],
        },
        { key: 'supplier', rows: [] },
      ])
      expect(h.totalCandidates.value).toBe(1)
      expect(h.candidates.value[0].source).toBe('D4-32-anomaly')
      expect(h.candidates.value[0].amount).toBe(200000)
    })
  })

  // ═══ 5. 人工确认门控 ═══

  describe('confirmation gate', () => {
    it('amount>0 + direction + evidence → 确认成功', () => {
      const h = createHarness()
      h.collectD432Anomalies([
        { key: 'customer', rows: [{ id: 'r1', name: '异常客户', amount: 50000, hasAnomaly: '是' }] },
      ])
      const ok = h.confirmCandidate('D4-32:customer:r1', 'debit', 50000, 'D4-32-ref')
      expect(ok).toBe(true)
      expect(h.confirmedCount.value).toBe(1)
    })

    it('amount<=0 → 确认失败', () => {
      const h = createHarness()
      h.collectD429Risks([{ id: 'c1', name: '客户', fields: { isRelated: '是' } }])
      const ok = h.confirmCandidate('D4-29:c1', 'credit', 0, 'evidence')
      expect(ok).toBe(false)
    })

    it('空证据 → 确认失败', () => {
      const h = createHarness()
      h.collectD432Anomalies([
        { key: 'supplier', rows: [{ id: 'r1', name: '供应商', amount: 10000, hasAnomaly: '是' }] },
      ])
      const ok = h.confirmCandidate('D4-32:supplier:r1', 'debit', 10000, '')
      expect(ok).toBe(false)
    })

    it('只读态不可确认', () => {
      const h = createHarness(true)
      h.collectD432Anomalies([
        { key: 'customer', rows: [{ id: 'r1', name: '客户', amount: 10000, hasAnomaly: '是' }] },
      ])
      const ok = h.confirmCandidate('D4-32:customer:r1', 'debit', 10000, 'evidence')
      expect(ok).toBe(false)
    })
  })

  // ═══ 6. A13 推送 ═══

  describe('push to A13', () => {
    it('确认后推送触发 a13:push-misstatement', () => {
      const h = createHarness()
      h.collectD432Anomalies([
        { key: 'customer', rows: [{ id: 'r1', name: '异常客户', amount: 80000, hasAnomaly: '是' }] },
      ])
      h.confirmCandidate('D4-32:customer:r1', 'debit', 80000, 'D4-32-idx')
      const count = h.pushToA13()
      expect(count).toBe(1)
      expect(eventBus.emit).toHaveBeenCalledWith(
        'a13:push-misstatement',
        expect.objectContaining({
          wpCode: 'D4-IPO',
          items: expect.arrayContaining([
            expect.objectContaining({ amount: 80000 }),
          ]),
        }),
      )
    })

    it('已推送不重推（幂等）', () => {
      const h = createHarness()
      h.collectD432Anomalies([
        { key: 'customer', rows: [{ id: 'r1', name: '客户', amount: 50000, hasAnomaly: '是' }] },
      ])
      h.confirmCandidate('D4-32:customer:r1', 'debit', 50000, 'ref')
      h.pushToA13()
      vi.clearAllMocks()
      const count2 = h.pushToA13()
      expect(count2).toBe(0)
      expect(eventBus.emit).not.toHaveBeenCalled()
    })

    it('只读态不可推送', () => {
      const h = createHarness(true)
      const count = h.pushToA13()
      expect(count).toBe(0)
    })
  })

  // ═══ 7. 替换（不累加）同来源候选 ═══

  describe('source replacement', () => {
    it('重复调用 collectD429Risks 替换而非累加', () => {
      const h = createHarness()
      h.collectD429Risks([{ id: 'c1', name: '客户A', fields: { isRelated: '是' } }])
      expect(h.totalCandidates.value).toBe(1)
      h.collectD429Risks([{ id: 'c2', name: '客户B', fields: { isBlacklisted: '是' } }])
      expect(h.totalCandidates.value).toBe(1) // 替换，不是2
      expect(h.candidates.value[0].sourceId).toBe('D4-29:c2')
    })
  })
})
