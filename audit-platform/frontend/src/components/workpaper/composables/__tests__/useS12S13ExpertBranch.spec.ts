import { describe, it, expect } from 'vitest'
import {
  resolveExpertSubSheet,
  EXPERT_DOMAINS,
  EXPERT_DOMAIN_LABELS,
  type ExpertDomain,
  type ExpertPrefix,
} from '../useS12S13ExpertBranch'

describe('useS12S13ExpertBranch', () => {
  describe('resolveExpertSubSheet — S12 映射', () => {
    it('general → S12-3-2 利用专家评价管理层的工作的适当性', () => {
      expect(resolveExpertSubSheet('S12', 'general'))
        .toBe('S12-3-2 利用专家评价管理层的工作的适当性')
    })

    it('share-based-payment → S12-3-3 利用专家评价管理层的工作(股份支付)', () => {
      expect(resolveExpertSubSheet('S12', 'share-based-payment'))
        .toBe('S12-3-3 利用专家评价管理层的工作(股份支付)')
    })

    it('financial-instrument-fair-value → S12-3-4 利用专家评价管理层的工作(金融工具公允价值）', () => {
      // 注意：S12-3-4 源模板使用全角右括号 ）
      expect(resolveExpertSubSheet('S12', 'financial-instrument-fair-value'))
        .toBe('S12-3-4 利用专家评价管理层的工作(金融工具公允价值）')
    })
  })

  describe('resolveExpertSubSheet — S13 映射', () => {
    it('general → S13-3-2 评价管理层专家工作的适当性', () => {
      expect(resolveExpertSubSheet('S13', 'general'))
        .toBe('S13-3-2 评价管理层专家工作的适当性')
    })

    it('share-based-payment → S13-3-3 评价管理层专家工作的适当性(股份支付)', () => {
      expect(resolveExpertSubSheet('S13', 'share-based-payment'))
        .toBe('S13-3-3 评价管理层专家工作的适当性(股份支付)')
    })

    it('financial-instrument-fair-value → S13-3-4 评价管理层专家工作的适当性(金融工具公允价值)', () => {
      expect(resolveExpertSubSheet('S13', 'financial-instrument-fair-value'))
        .toBe('S13-3-4 评价管理层专家工作的适当性(金融工具公允价值)')
    })
  })

  describe('resolveExpertSubSheet — 确定性', () => {
    it('同一 (prefix, domain) 对多次调用返回相同结果', () => {
      const prefixes: ExpertPrefix[] = ['S12', 'S13']
      for (const prefix of prefixes) {
        for (const domain of EXPERT_DOMAINS) {
          const first = resolveExpertSubSheet(prefix, domain)
          const second = resolveExpertSubSheet(prefix, domain)
          expect(first).toBe(second)
        }
      }
    })
  })

  describe('resolveExpertSubSheet — 降级处理', () => {
    it('domain 不可识别时降级为对应 prefix 的 general', () => {
      // 使用 as any 模拟非法 domain
      expect(resolveExpertSubSheet('S12', 'unknown-domain' as ExpertDomain))
        .toBe('S12-3-2 利用专家评价管理层的工作的适当性')
      expect(resolveExpertSubSheet('S13', 'something-else' as ExpertDomain))
        .toBe('S13-3-2 评价管理层专家工作的适当性')
    })

    it('prefix 非法时降级为 S12 general', () => {
      expect(resolveExpertSubSheet('S99' as ExpertPrefix, 'general'))
        .toBe('S12-3-2 利用专家评价管理层的工作的适当性')
    })
  })

  describe('EXPERT_DOMAINS', () => {
    it('包含 3 个合法 domain', () => {
      expect(EXPERT_DOMAINS).toHaveLength(3)
      expect(EXPERT_DOMAINS).toContain('general')
      expect(EXPERT_DOMAINS).toContain('share-based-payment')
      expect(EXPERT_DOMAINS).toContain('financial-instrument-fair-value')
    })
  })

  describe('EXPERT_DOMAIN_LABELS', () => {
    it('每个 domain 有对应中文标签', () => {
      expect(EXPERT_DOMAIN_LABELS['general']).toBe('通用')
      expect(EXPERT_DOMAIN_LABELS['share-based-payment']).toBe('股份支付')
      expect(EXPERT_DOMAIN_LABELS['financial-instrument-fair-value']).toBe('金融工具公允价值')
    })

    it('所有 EXPERT_DOMAINS 都有 label', () => {
      for (const domain of EXPERT_DOMAINS) {
        expect(EXPERT_DOMAIN_LABELS[domain]).toBeDefined()
        expect(typeof EXPERT_DOMAIN_LABELS[domain]).toBe('string')
        expect(EXPERT_DOMAIN_LABELS[domain].length).toBeGreaterThan(0)
      }
    })
  })

  describe('resolveExpertSubSheet — 返回值唯一性', () => {
    it('S12 各 domain 返回不同 sheetName', () => {
      const results = EXPERT_DOMAINS.map(d => resolveExpertSubSheet('S12', d))
      expect(new Set(results).size).toBe(3)
    })

    it('S13 各 domain 返回不同 sheetName', () => {
      const results = EXPERT_DOMAINS.map(d => resolveExpertSubSheet('S13', d))
      expect(new Set(results).size).toBe(3)
    })

    it('S12 和 S13 同 domain 返回不同 sheetName', () => {
      for (const domain of EXPERT_DOMAINS) {
        const s12 = resolveExpertSubSheet('S12', domain)
        const s13 = resolveExpertSubSheet('S13', domain)
        expect(s12).not.toBe(s13)
      }
    })
  })
})
