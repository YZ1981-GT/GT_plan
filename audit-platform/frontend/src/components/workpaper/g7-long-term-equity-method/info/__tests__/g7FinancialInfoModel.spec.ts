import { describe, expect, it } from 'vitest'
import {
  calcFinancialChangeAmount,
  calcFinancialChangeRate,
  computeFinancialGroupVirtualWindow,
  countUnauditedFinancialRows,
  createDefaultFinancialGroup,
  createFinancialInfoRow,
  estimateFinancialGroupHeight,
  isFinancialRateWarning,
  parseFinancialInfoGroups,
  recalcFinancialInfoRow,
  rollForwardFinancialPriorAmounts,
  serializeFinancialInfoPayload,
  shouldUseFinancialGroupVirtual,
  validateFinancialInfoGroups,
} from '../g7FinancialInfoModel'

describe('G7-5 financial info model', () => {
  it('calculates change amount and rate with zero guard', () => {
    expect(calcFinancialChangeAmount(120, 100)).toBe(20)
    expect(calcFinancialChangeRate(20, 100)).toBe(0.2)
    expect(calcFinancialChangeRate(20, 0)).toBeNull()
    expect(isFinancialRateWarning(0.5)).toBe(false)
    expect(isFinancialRateWarning(0.5001)).toBe(true)
    expect(isFinancialRateWarning(-0.6)).toBe(true)
    expect(isFinancialRateWarning(null)).toBe(false)
  })

  it('recalculates row formulas', () => {
    const row = createFinancialInfoRow('甲联营', 1, '净利润')
    row.priorAmount = 100
    row.currentAmount = 160
    recalcFinancialInfoRow(row)
    expect(row.changeAmount).toBe(60)
    expect(row.changeRate).toBe(0.6)
    expect(isFinancialRateWarning(row.changeRate)).toBe(true)
  })

  it('creates default group with key report items', () => {
    const group = createDefaultFinancialGroup('乙合营', 'id-1')
    expect(group.investeeId).toBe('id-1')
    expect(group.rows.length).toBe(10)
    expect(group.rows.some(r => r.reportItem.includes('净利润'))).toBe(true)
    expect(group.rows.some(r => r.reportItem.includes('所有者权益'))).toBe(true)
  })

  it('parses flat rows and nested groups payload', () => {
    const flat = parseFinancialInfoGroups({
      rows: [
        { investeeName: 'A', reportItem: '净利润', priorAmount: 10, currentAmount: 12 },
        { investeeName: 'A', reportItem: '总资产', priorAmount: 100, currentAmount: 110 },
        { investeeName: 'B', reportItem: '净利润', priorAmount: 1, currentAmount: 2 },
      ],
    })
    expect(flat).toHaveLength(2)
    expect(flat[0].rows).toHaveLength(2)

    const nested = parseFinancialInfoGroups({
      groups: [{
        investeeName: 'C',
        investeeId: 'c1',
        rows: [{ reportItem: '净利润', priorAmount: 5, currentAmount: 5 }],
      }],
    })
    expect(nested[0].investeeId).toBe('c1')
    expect(nested[0].rows[0].changeAmount).toBe(0)
  })

  it('validates high rate without analysis and missing key items', () => {
    const group = createDefaultFinancialGroup('丁公司')
    const profit = group.rows.find(r => r.reportItem === '净利润')!
    profit.priorAmount = 100
    profit.currentAmount = 200
    recalcFinancialInfoRow(profit)

    // remove net assets row to trigger completeness warning
    group.rows = group.rows.filter(r => !r.reportItem.includes('所有者权益'))

    const issues = validateFinancialInfoGroups([group])
    expect(issues.some(i => i.message.includes('超过50%') && i.message.includes('分析说明'))).toBe(true)
    expect(issues.some(i => i.message.includes('所有者权益/净资产'))).toBe(true)

    profit.analysisNote = '收入增长带动'
    const okRate = validateFinancialInfoGroups([{
      ...group,
      rows: [...group.rows, createFinancialInfoRow('丁公司', 99, '所有者权益（净资产）')],
    }])
    expect(okRate.some(i => i.message.includes('超过50%'))).toBe(false)
  })

  it('serializes payload with both rows and groups', () => {
    const group = createDefaultFinancialGroup('戊')
    const json = serializeFinancialInfoPayload([group])
    const parsed = JSON.parse(json)
    expect(parsed.rows.length).toBe(10)
    expect(parsed.groups).toHaveLength(1)
  })

  it('counts unaudited and pending rows', () => {
    const group = createDefaultFinancialGroup('己')
    for (const row of group.rows) row.auditStatus = '已审'
    group.rows[0].auditStatus = '未审'
    group.rows[1].auditStatus = '待确认'
    expect(countUnauditedFinancialRows([group])).toEqual({
      unaudited: 1,
      pending: 1,
      total: 2,
    })
  })

  it('rolls prior amounts from current amounts', () => {
    const group = createDefaultFinancialGroup('庚')
    const row = group.rows[0]
    row.priorAmount = 10
    row.currentAmount = 50
    recalcFinancialInfoRow(row)

    const n = rollForwardFinancialPriorAmounts([group], { clearCurrent: true })
    expect(n).toBe(group.rows.length)
    expect(row.priorAmount).toBe(50)
    expect(row.currentAmount).toBe(0)
    expect(row.changeAmount).toBe(-50)

    row.currentAmount = 80
    rollForwardFinancialPriorAmounts([group], { clearCurrent: false })
    expect(row.priorAmount).toBe(80)
    expect(row.currentAmount).toBe(80)
  })

  it('enables group virtual window for many groups', () => {
    expect(shouldUseFinancialGroupVirtual(6, 10)).toBe(true)
    expect(shouldUseFinancialGroupVirtual(3, 41)).toBe(true)
    expect(shouldUseFinancialGroupVirtual(3, 10)).toBe(false)

    const heights = [100, 100, 100, 100, 100]
    const win = computeFinancialGroupVirtualWindow(heights, 150, 120, 1)
    expect(win.totalHeight).toBe(500)
    expect(win.start).toBeLessThanOrEqual(1)
    expect(win.end).toBeGreaterThan(win.start)
    expect(win.offsetY).toBe(win.start * 100)

    const group = createDefaultFinancialGroup('辛')
    expect(estimateFinancialGroupHeight(group, false)).toBeLessThan(
      estimateFinancialGroupHeight(group, true),
    )
  })
})
