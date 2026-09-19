import { describe, expect, it, vi } from 'vitest'
import {
  useK1BadDebtCalcSheet,
  parseK18Payload,
} from '../useK1BadDebtCalcSheet'
import { G5_AGING_FIVE_YEAR } from '../useG5ImpairmentCalc'

vi.mock('element-plus', () => ({
  ElMessage: { warning: vi.fn(), info: vi.fn(), success: vi.fn() },
}))

describe('useK1BadDebtCalcSheet', () => {
  it('默认：5 年账龄双标签 + 信用期 4 段 + 两个账龄组合', () => {
    const calc = useK1BadDebtCalcSheet()
    expect(calc.agingPreset.value).toBe('FIVE_YEAR')
    expect(calc.agingSegments.value).toHaveLength(G5_AGING_FIVE_YEAR.length)
    expect(calc.creditSegments.value).toHaveLength(4)
    expect(calc.agingGroups.value).toHaveLength(2)
    expect(calc.agingGroups.value[0].rows[0].label).toContain('未逾期')
  })

  it('应计提 = 余额 × 损失率；差异 = 应计提 − 账面', () => {
    const calc = useK1BadDebtCalcSheet()
    calc.addSingleRow('甲公司')
    const id = calc.singleRows.value[0].rowId
    calc.updateSingleCell(id, 'auditedBalance', 1000)
    calc.updateSingleCell(id, 'lossRate', 0.05)
    calc.updateSingleCell(id, 'bookProvision', 30)
    expect(calc.singleRows.value[0].expectedProvision).toBeCloseTo(50, 5)
    expect(calc.singleRows.value[0].difference).toBeCloseTo(20, 5)
  })

  it('切换 3 年段并保留同 key 已填数', () => {
    const calc = useK1BadDebtCalcSheet()
    const gid = calc.agingGroups.value[0].groupId
    const within = calc.agingGroups.value[0].rows.find((r) => r.segmentKey === 'within1')!
    calc.updateAgingCell(gid, within.rowId, 'auditedBalance', 500)
    calc.updateAgingCell(gid, within.rowId, 'lossRate', 0.01)
    expect(calc.setAgingPreset('THREE_YEAR')).toBe(true)
    expect(calc.agingPreset.value).toBe('THREE_YEAR')
    expect(calc.agingGroups.value[0].rows.filter((r) => !r.archived)).toHaveLength(4)
    expect(calc.agingGroups.value[0].rows[0].auditedBalance).toBe(500)
  })

  it('自定义账龄至少 2 段', () => {
    const calc = useK1BadDebtCalcSheet()
    expect(calc.setAgingPreset('CUSTOM', ['仅一段'])).toBe(false)
    expect(calc.setAgingPreset('CUSTOM', ['0-6月', '6-12月', '1年以上'])).toBe(true)
    expect(calc.agingPreset.value).toBe('CUSTOM')
    expect(calc.agingSegments.value).toHaveLength(3)
  })

  it('旧版 tables 结构可迁移为 V2', () => {
    const legacy = JSON.stringify({
      tables: {
        single: [{ id: 's1', name: 'A公司', balance: 100, rate: 0.1, bookProvision: 5 }],
        deposit: [{ id: 'd1', name: '合同期内', balance: 200, rate: 0, bookProvision: 0 }],
        aging: [{ id: 'a1', name: '1年以内/未逾期', balance: 300, rate: 0.02, bookProvision: 4 }],
      },
      auditNote: '说明',
      conclusion: '结论',
    })
    const parsed = parseK18Payload(legacy)
    expect(parsed.version).toBe(2)
    expect(parsed.singleRows).toHaveLength(1)
    expect(parsed.singleRows[0].label).toBe('A公司')
    expect(parsed.singleRows[0].expectedProvision).toBeCloseTo(10, 5)
    expect(parsed.agingGroups[0].rows.some((r) => r.auditedBalance === 300)).toBe(true)
    expect(parsed.auditNote).toBe('说明')
  })

  it('grandTotal 汇总三项区段', () => {
    const calc = useK1BadDebtCalcSheet()
    calc.addSingleRow('测试')
    const id = calc.singleRows.value[0].rowId
    calc.updateSingleCell(id, 'auditedBalance', 1000)
    calc.updateSingleCell(id, 'lossRate', 0.1)
    calc.updateSingleCell(id, 'bookProvision', 50)
    expect(calc.grandTotal.value.expected).toBeCloseTo(100, 5)
    expect(calc.grandTotal.value.diff).toBeCloseTo(50, 5)
  })
})
