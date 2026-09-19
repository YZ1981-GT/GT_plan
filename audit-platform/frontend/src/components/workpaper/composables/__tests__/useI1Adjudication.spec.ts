/**
 * useI1Adjudication — 审定表增强（净值变动/说明事项）单元测试
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useI1Adjudication, I1_DEFAULT_CATEGORIES, I1_CHANGE_RATE_THRESHOLD } from '../useI1Adjudication'

function makeMap(entries: Record<string, any>): Map<string, any> {
  const m = new Map<string, any>()
  for (const [k, v] of Object.entries(entries)) {
    m.set(k, typeof v === 'string' ? { remark: v } : { remark: JSON.stringify(v) })
  }
  return m
}

describe('useI1Adjudication enhancements', () => {
  it('默认分类对齐 Excel（含住房使用权/矿产权/数据资源）', () => {
    expect(I1_DEFAULT_CATEGORIES).toContain('土地使用权')
    expect(I1_DEFAULT_CATEGORIES).toContain('住房使用权')
    expect(I1_DEFAULT_CATEGORIES).toContain('矿产权')
    expect(I1_DEFAULT_CATEGORIES).toContain('数据资源')
  })

  it('净值按分类计算变动额/率，≥30% 标重大', () => {
    const map = ref(makeMap({
      'I1-adj-cost-rows': [
        { rowId: 'c1', category: '软件', beginBalance: 100, increase: 50, decrease: 0, endBalance: 150, unadjusted: 150, aje: 0, rje: 0, audited: 150 },
      ],
      'I1-adj-amort-rows': [
        { rowId: 'a1', category: '软件', beginBalance: 20, increase: 10, decrease: 0, endBalance: 30, unadjusted: 30, aje: 0, rje: 0, audited: 30 },
      ],
      'I1-adj-impair-rows': [
        { rowId: 'i1', category: '软件', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0, unadjusted: 0, aje: 0, rje: 0, audited: 0 },
      ],
    }))
    const api = useI1Adjudication(ref('wp'), ref('p'), map)
    const soft = api.netRows.value.find((r) => r.category === '软件')!
    // beginNet=80, endNet=120, rate=50%
    expect(soft.beginNet).toBe(80)
    expect(soft.endNet).toBe(120)
    expect(soft.changeAmount).toBe(40)
    expect(soft.changeRate).toBeCloseTo(50)
    expect(soft.isSignificant).toBe(true)
    expect(I1_CHANGE_RATE_THRESHOLD).toBe(30)
  })

  it('从 I1-2 按分类带入', () => {
    const map = ref(makeMap({
      'I1-2-rows': [
        { category: '专利权', costBegin: 1000, costIncrease: 100, costDecrease: 0, costEnd: 1100, accAmortBegin: 100, amortProvision: 50, amortTransferOut: 0, accAmortEnd: 150, impairmentBegin: 0, impairmentProvision: 0, impairmentReversal: 0, impairmentEnd: 0 },
      ],
    }))
    const api = useI1Adjudication(ref('wp'), ref('p'), map, {
      onSave: () => {},
    })
    const r = api.seedFromDetail()
    expect(r.ok).toBe(true)
    const cost = api.costRows.value.find((x) => x.category === '专利权')!
    expect(cost.beginBalance).toBe(1000)
    expect(cost.increase).toBe(100)
    expect(cost.unadjusted).toBe(1100)
  })

  it('fillFromDetail(book) 保留 AJE；fillFromDetail(full) 清零并用审定数', () => {
    const map = ref(makeMap({
      'I1-2-rows': [
        {
          category: '软件',
          costBegin: 100, costIncrease: 0, costDecrease: 0, costEnd: 100,
          auditedCostBegin: 120, auditedCostIncrease: 0, auditedCostDecrease: 0, auditedCostEnd: 120,
          accAmortBegin: 10, amortProvision: 0, amortTransferOut: 0, accAmortEnd: 10,
          auditedAccAmortBegin: 10, auditedAmortIncrease: 0, auditedAmortDecrease: 0, auditedAccAmortEnd: 10,
          impairmentBegin: 0, impairmentProvision: 0, impairmentReversal: 0, impairmentEnd: 0,
          auditedImpairmentBegin: 0, auditedImpairmentIncrease: 0, auditedImpairmentDecrease: 0, auditedImpairmentEnd: 0,
        },
      ],
      'I1-adj-cost-rows': [
        { rowId: 'c1', category: '软件', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0, unadjusted: 0, aje: 50, rje: 0, audited: 50 },
      ],
    }))
    const api = useI1Adjudication(ref('wp'), ref('p'), map, { onSave: () => {} })
    const book = api.fillFromDetail('book')
    expect(book.ok).toBe(true)
    let cost = api.costRows.value.find((x) => x.category === '软件')!
    expect(cost.unadjusted).toBe(100)
    expect(cost.aje).toBe(50)

    const full = api.fillFromDetail('full')
    expect(full.ok).toBe(true)
    cost = api.costRows.value.find((x) => x.category === '软件')!
    expect(cost.unadjusted).toBe(120)
    expect(cost.aje).toBe(0)
    expect(cost.rje).toBe(0)
    expect(cost.audited).toBe(120)
  })

  it('结论模板 A/B/C', () => {
    const saved: string[] = []
    const map = ref(makeMap({}))
    const api = useI1Adjudication(ref('wp'), ref('p'), map, {
      onSave: (id) => saved.push(id),
    })
    const text = api.applyConclusionTemplate('A')
    expect(text).toContain('公允反映')
    expect(saved).toContain('I1-adj-audit-conclusion')
  })

  it('draftIndefiniteLifeNote 从 I1-7 发布清单汇总', () => {
    const map = ref(makeMap({
      'I1-7-indefinite-list': {
        assets: [
          { name: '商标权', netBookValue: 1200, judgmentBasis: '无法预见使用期限' },
        ],
      },
    }))
    const api = useI1Adjudication(ref('wp'), ref('p'), map)
    const draft = api.draftIndefiniteLifeNote()
    expect(draft).toContain('商标权')
    expect(draft).toContain('无法预见使用期限')
  })
})
