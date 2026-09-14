/**
 * useH2Detail — 公式与勾稽单测（对齐致同 / H1 未审→调整→审定）
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useH2Detail } from '../useH2Detail'

function setup(seed?: any[]) {
  const map = new Map<string, any>()
  if (seed) {
    map.set('H2-2-rows', { remark: JSON.stringify(seed) })
  }
  const allResponses = ref(map)
  const saved: Record<string, any> = {}
  const api = useH2Detail({
    wpId: ref('wp1'),
    projectId: ref('p1'),
    allResponses,
    isReadonly: ref(false),
    onSave: (id, val) => { saved[id] = val },
  })
  return { api, saved, allResponses }
}

describe('useH2Detail formulas', () => {
  it('未审三角勾稽：期末=期初+增加−转固−其他减少', () => {
    const { api } = setup()
    api.addRow('厂房扩建')
    const id = api.rows.value[0].rowId
    api.updateCell(id, 'cipBegin', 1_000_000)
    api.updateCell(id, 'increaseMaterial', 200_000)
    api.updateCell(id, 'increaseInterest', 50_000)
    api.updateCell(id, 'transferAmount', 300_000)
    api.updateCell(id, 'decrease', 50_000)

    const row = api.rows.value[0]
    expect(row.increaseTotal).toBe(250_000)
    expect(row.cipEnd).toBe(900_000) // 1000+250-300-50
  })

  it('利息子列：期末资本化=期初+本期−转出', () => {
    const { api } = setup()
    api.addRow('专线工程')
    const id = api.rows.value[0].rowId
    api.updateCell(id, 'interestBegin', 80_000)
    api.updateCell(id, 'increaseInterest', 20_000)
    api.updateCell(id, 'interestDec', 30_000)

    expect(api.rows.value[0].interestEnd).toBe(70_000)
  })

  it('审定=未审+调整，净值=原值−减值', () => {
    const { api } = setup()
    api.addRow('码头')
    const id = api.rows.value[0].rowId
    api.updateCell(id, 'cipBegin', 500_000)
    api.updateCell(id, 'increaseOther', 100_000)
    api.updateCell(id, 'adjustBegin', 10_000)
    api.updateCell(id, 'increaseAdj', -5_000)
    api.updateCell(id, 'impairmentBegin', 20_000)
    api.updateCell(id, 'impairmentIncrease', 5_000)

    const row = api.rows.value[0]
    expect(row.beginAudited).toBe(510_000)
    expect(row.increaseAudited).toBe(95_000)
    expect(row.endAudited).toBe(605_000) // 510+95
    expect(row.cipEnd).toBe(600_000)
    expect(row.impairmentEnd).toBe(25_000)
    expect(row.netEndUnadj).toBe(575_000)
    expect(row.netEndAud).toBe(580_000) // 605-25（减值无调整时审定减值=未审期末）
    expect(row.netValue).toBe(580_000)
  })

  it('与 H2-1 勾稽使用审定期末', () => {
    const { api, allResponses } = setup([{
      rowId: 'r1', name: 'A', cipBegin: 100, increaseOther: 0, endAudited: 100,
    }])
    // 手动触发重算后 endAudited 会按公式覆盖
    api.updateCell('r1', 'cipBegin', 100)
    allResponses.value.set('H2-1-rows', {
      remark: JSON.stringify([{ endAudited: api.rows.value[0].endAudited }]),
    })
    // 触发 watch
    allResponses.value = new Map(allResponses.value)
    expect(api.crossValidationH1.value.isMatch).toBe(true)
  })

  it('结论模板 A/B/C', () => {
    const { api, saved } = setup()
    api.applyConclusionTemplate('A')
    expect(saved['H2-2-audit-conclusion']).toBe('未见异常。')
    api.applyConclusionTemplate('C')
    expect(api.auditConclusion.value).toContain('不可确认')
  })
})
