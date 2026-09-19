/**
 * Unit Tests — K1-6 会计政策检查 composable
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  useK1PolicyCheck,
  K1_DEFAULT_COMBO_BASES,
  K1_POLICY_CONCLUSION_TEMPLATES,
} from '../../../composables/useK1PolicyCheck'

function create(opts: Record<string, any> = {}) {
  const map = new Map<string, any>(Object.entries(opts))
  const allResponses = ref(map)
  return { ...useK1PolicyCheck({ allResponses: allResponses as any }), allResponses }
}

describe('useK1PolicyCheck', () => {
  it('默认 seed 4 个组合', () => {
    const { combos, load } = create()
    load()
    expect(combos.value.length).toBe(4)
    expect(combos.value.map((c) => c.basis)).toEqual([...K1_DEFAULT_COMBO_BASES])
  })

  it('兼容旧版 K1-6-forward / K1-6-peer', () => {
    const { load, forwardLooking, peerComparison } = create({
      'K1-6-forward': { remark: '宏观预测下调损失率' },
      'K1-6-peer': { remark: '与同行业无重大差异' },
    })
    load()
    expect(forwardLooking.value).toBe('宏观预测下调损失率')
    expect(peerComparison.value).toBe('与同行业无重大差异')
  })

  it('applyListedExample 写入同业表与综合对比', () => {
    const { applyListedExample, peerRows, peerComparison } = create()
    applyListedExample('海螺水泥', '组合测试政策')
    expect(peerRows.value.some((r) => r.company === '海螺水泥')).toBe(true)
    expect(peerComparison.value).toContain('海螺水泥')
  })

  it('buildSaveItems 包含新增字段', () => {
    const { load, auditProcedures, historicalLoss, buildSaveItems } = create()
    load()
    auditProcedures.value = '程序1'
    historicalLoss.value = '历史损失说明'
    const ids = buildSaveItems().map((i) => i.item_id)
    expect(ids).toContain('K1-6-procedures')
    expect(ids).toContain('K1-6-historical')
    expect(ids).toContain('K1-6-audit-note')
  })

  it('buildSaveItems 包含 K2 损失率键', () => {
    const { load, buildSaveItems } = create()
    load()
    const ids = buildSaveItems().map((i) => i.item_id)
    expect(ids).toContain('K1-k2-aging-loss-rates')
  })

  it('K1-8 组合勾稽：名称匹配时一致', () => {
    const payload = JSON.stringify({
      version: 2,
      singleRows: [],
      creditGroups: [{ groupId: 'g1', groupName: '押金和保证金', rows: [] }],
      agingGroups: [],
      agingPreset: 'FIVE_YEAR',
      customAgingLabels: [],
      creditPreset: 'DEFAULT',
      customCreditLabels: [],
      conclusionOption: '',
    })
    const { load, k18ComboConsistency } = create({
      'K1-8-bad-debt-calc': { remark: payload },
    })
    load()
    expect(k18ComboConsistency.value.hasK18Data).toBe(true)
    expect(k18ComboConsistency.value.matched.some((m) => m.k16Basis === '押金和保证金')).toBe(true)
  })
})

describe('K1_POLICY_CONCLUSION_TEMPLATES', () => {
  it('A/B/C 模板非空', () => {
    expect(K1_POLICY_CONCLUSION_TEMPLATES.A).toContain('符合')
    expect(K1_POLICY_CONCLUSION_TEMPLATES.C).toContain('重大')
  })
})
