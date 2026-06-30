/**
 * useD7FormulaEngine Unit Tests
 *
 * 单元测试覆盖 D7 合同负债公式引擎全部纯函数。
 * 验证边界值、零值、负数、NaN/Infinity 等场景。
 *
 * Spec: .kiro/specs/d7-contract-liabilities/
 * Task: 2.1
 */
import { describe, it, expect } from 'vitest'
import {
  parseNum,
  calcCreditEndBalance,
  calcAuditedAmount,
  calcChangeAmount,
  calcChangeRate,
  isChangeRateExceeding,
  calcSubtotal,
  calcContractLiabilityTotal,
  aggregateByNature,
  aggregateByAging,
  topNByField,
} from '../composables/useD7FormulaEngine'
import type { DetailRow } from '../composables/useD7FormulaEngine'

// ─── parseNum ───────────────────────────────────────────────────────────────

describe('parseNum', () => {
  it('正常数字直接返回', () => {
    expect(parseNum(123)).toBe(123)
    expect(parseNum(-456.78)).toBe(-456.78)
    expect(parseNum(0)).toBe(0)
  })

  it('字符串数字转为数值', () => {
    expect(parseNum('123')).toBe(123)
    expect(parseNum('-456.78')).toBe(-456.78)
    expect(parseNum('0')).toBe(0)
  })

  it('null/undefined/空串 → 0', () => {
    expect(parseNum(null)).toBe(0)
    expect(parseNum(undefined)).toBe(0)
    expect(parseNum('')).toBe(0)
  })

  it('NaN/Infinity → 0', () => {
    expect(parseNum(NaN)).toBe(0)
    expect(parseNum(Infinity)).toBe(0)
    expect(parseNum(-Infinity)).toBe(0)
  })

  it('非数字字符串 → 0', () => {
    expect(parseNum('abc')).toBe(0)
    expect(parseNum('12abc')).toBe(0)
  })
})

// ─── calcCreditEndBalance ───────────────────────────────────────────────────

describe('calcCreditEndBalance', () => {
  it('贷方科目：期末 = 期初 + 贷方 - 借方', () => {
    expect(calcCreditEndBalance(1000, 500, 200)).toBe(1300)
    expect(calcCreditEndBalance(0, 100, 50)).toBe(50)
    expect(calcCreditEndBalance(1000, 0, 0)).toBe(1000)
  })

  it('借方发生>贷方发生时余额减少', () => {
    expect(calcCreditEndBalance(1000, 100, 800)).toBe(300)
  })

  it('可产生负数结果', () => {
    expect(calcCreditEndBalance(100, 50, 200)).toBe(-50)
  })

  it('全零输入返回零', () => {
    expect(calcCreditEndBalance(0, 0, 0)).toBe(0)
  })
})

// ─── calcAuditedAmount ──────────────────────────────────────────────────────

describe('calcAuditedAmount', () => {
  it('审定数 = 未审 + AJE + RJE', () => {
    expect(calcAuditedAmount(1000, 200, -50)).toBe(1150)
    expect(calcAuditedAmount(0, 0, 0)).toBe(0)
    expect(calcAuditedAmount(500, -100, -200)).toBe(200)
  })

  it('支持负数输入', () => {
    expect(calcAuditedAmount(-100, 50, 50)).toBe(0)
  })
})

// ─── calcChangeAmount ───────────────────────────────────────────────────────

describe('calcChangeAmount', () => {
  it('变动额 = 期末 - 期初', () => {
    expect(calcChangeAmount(800, 1200)).toBe(400)
    expect(calcChangeAmount(1000, 1000)).toBe(0)
    expect(calcChangeAmount(1200, 800)).toBe(-400)
  })

  it('期初为0时变动额=期末', () => {
    expect(calcChangeAmount(0, 500)).toBe(500)
  })
})

// ─── calcChangeRate ─────────────────────────────────────────────────────────

describe('calcChangeRate', () => {
  it('正常计算：(期末-期初)/期初', () => {
    expect(calcChangeRate(100, 150)).toBe(0.5)
    expect(calcChangeRate(200, 100)).toBe(-0.5)
    expect(calcChangeRate(100, 100)).toBe(0)
  })

  it('期初=0且期末=0 → 空串', () => {
    expect(calcChangeRate(0, 0)).toBe('')
  })

  it('期初=0且期末≠0 → N/A', () => {
    expect(calcChangeRate(0, 100)).toBe('N/A')
    expect(calcChangeRate(0, -50)).toBe('N/A')
  })

  it('期初<0的正常除法', () => {
    // (current - prior) / prior = (-50 - (-100)) / (-100) = 50 / -100 = -0.5
    const rate = calcChangeRate(-100, -50)
    expect(rate).toBe(-0.5)
  })
})

// ─── isChangeRateExceeding ──────────────────────────────────────────────────

describe('isChangeRateExceeding', () => {
  it('数值型超过阈值返回true', () => {
    expect(isChangeRateExceeding(0.5, 0.3)).toBe(true)
    expect(isChangeRateExceeding(-0.5, 0.3)).toBe(true)
  })

  it('数值型未超过阈值返回false', () => {
    expect(isChangeRateExceeding(0.2, 0.3)).toBe(false)
    expect(isChangeRateExceeding(-0.1, 0.3)).toBe(false)
    expect(isChangeRateExceeding(0, 0.3)).toBe(false)
  })

  it('恰好等于阈值返回false（不超过）', () => {
    expect(isChangeRateExceeding(0.3, 0.3)).toBe(false)
    expect(isChangeRateExceeding(-0.3, 0.3)).toBe(false)
  })

  it('空串返回false', () => {
    expect(isChangeRateExceeding('', 0.3)).toBe(false)
  })

  it('N/A返回false', () => {
    expect(isChangeRateExceeding('N/A', 0.3)).toBe(false)
  })
})

// ─── calcSubtotal ───────────────────────────────────────────────────────────

describe('calcSubtotal', () => {
  it('正常数组求和', () => {
    expect(calcSubtotal([100, 200, 300])).toBe(600)
    expect(calcSubtotal([1.1, 2.2, 3.3])).toBeCloseTo(6.6)
  })

  it('空数组返回0', () => {
    expect(calcSubtotal([])).toBe(0)
  })

  it('单元素数组返回该元素', () => {
    expect(calcSubtotal([42])).toBe(42)
  })

  it('含负数正确求和', () => {
    expect(calcSubtotal([100, -50, 200, -30])).toBe(220)
  })
})

// ─── calcContractLiabilityTotal ─────────────────────────────────────────────

describe('calcContractLiabilityTotal', () => {
  it('合同负债合计 = 小计 - 非流动负债扣减', () => {
    expect(calcContractLiabilityTotal(10000, 2000)).toBe(8000)
    expect(calcContractLiabilityTotal(5000, 0)).toBe(5000)
    expect(calcContractLiabilityTotal(0, 0)).toBe(0)
  })

  it('扣减额可以大于小计（产生负数）', () => {
    expect(calcContractLiabilityTotal(1000, 3000)).toBe(-2000)
  })
})

// ─── aggregateByNature ──────────────────────────────────────────────────────

describe('aggregateByNature', () => {
  const rows: DetailRow[] = [
    { natureType: '预收货款', endAudited: 100, endAging1: 50, endAging2: 30, endAging3: 10, endAging4: 10 },
    { natureType: '预收货款', endAudited: 200, endAging1: 100, endAging2: 50, endAging3: 30, endAging4: 20 },
    { natureType: '预收工程款', endAudited: 300, endAging1: 200, endAging2: 50, endAging3: 30, endAging4: 20 },
    { natureType: '其他', endAudited: 50, endAging1: 30, endAging2: 10, endAging3: 5, endAging4: 5 },
  ]

  it('按性质分组SUM endAudited', () => {
    const result = aggregateByNature(rows, 'endAudited')
    expect(result['预收货款']).toBe(300)
    expect(result['预收工程款']).toBe(300)
    expect(result['其他']).toBe(50)
  })

  it('按性质分组SUM endAging1', () => {
    const result = aggregateByNature(rows, 'endAging1')
    expect(result['预收货款']).toBe(150)
    expect(result['预收工程款']).toBe(200)
    expect(result['其他']).toBe(30)
  })

  it('空数组返回空对象', () => {
    const result = aggregateByNature([], 'endAudited')
    expect(result).toEqual({})
  })

  it('natureType为空时归入"其他"', () => {
    const rowsWithEmpty: DetailRow[] = [
      { natureType: '', endAudited: 100, endAging1: 0, endAging2: 0, endAging3: 0, endAging4: 0 },
    ]
    const result = aggregateByNature(rowsWithEmpty, 'endAudited')
    expect(result['其他']).toBe(100)
  })
})

// ─── aggregateByAging ───────────────────────────────────────────────────────

describe('aggregateByAging', () => {
  const rows: DetailRow[] = [
    { natureType: '预收货款', endAudited: 100, endAging1: 50, endAging2: 30, endAging3: 10, endAging4: 10 },
    { natureType: '预收货款', endAudited: 200, endAging1: 100, endAging2: 50, endAging3: 30, endAging4: 20 },
    { natureType: '预收工程款', endAudited: 300, endAging1: 200, endAging2: 50, endAging3: 30, endAging4: 20 },
  ]

  it('按账龄4段列SUM', () => {
    const result = aggregateByAging(rows)
    expect(result.within1Year).toBe(350)
    expect(result.year1to2).toBe(130)
    expect(result.year2to3).toBe(70)
    expect(result.over3Years).toBe(50)
  })

  it('空数组返回全零', () => {
    const result = aggregateByAging([])
    expect(result.within1Year).toBe(0)
    expect(result.year1to2).toBe(0)
    expect(result.year2to3).toBe(0)
    expect(result.over3Years).toBe(0)
  })

  it('含0值字段正常处理', () => {
    const rowsZero: DetailRow[] = [
      { natureType: '其他', endAudited: 100, endAging1: 100, endAging2: 0, endAging3: 0, endAging4: 0 },
    ]
    const result = aggregateByAging(rowsZero)
    expect(result.within1Year).toBe(100)
    expect(result.year1to2).toBe(0)
    expect(result.year2to3).toBe(0)
    expect(result.over3Years).toBe(0)
  })
})

// ─── topNByField ────────────────────────────────────────────────────────────

describe('topNByField', () => {
  const rows = [
    { name: 'A', endAudited: 100 },
    { name: 'B', endAudited: 500 },
    { name: 'C', endAudited: 300 },
    { name: 'D', endAudited: 200 },
    { name: 'E', endAudited: 400 },
  ]

  it('取Top3降序排列', () => {
    const result = topNByField(rows, 'endAudited', 3)
    expect(result.length).toBe(3)
    expect(result[0].name).toBe('B')
    expect(result[1].name).toBe('E')
    expect(result[2].name).toBe('C')
  })

  it('N大于数组长度时返回全部（降序）', () => {
    const result = topNByField(rows, 'endAudited', 10)
    expect(result.length).toBe(5)
    expect(result[0].endAudited).toBe(500)
    expect(result[4].endAudited).toBe(100)
  })

  it('不修改原数组', () => {
    const original = [...rows]
    topNByField(rows, 'endAudited', 3)
    expect(rows).toEqual(original)
  })

  it('空数组返回空数组', () => {
    const result = topNByField([], 'endAudited' as never, 5)
    expect(result).toEqual([])
  })

  it('N=0返回空数组', () => {
    const result = topNByField(rows, 'endAudited', 0)
    expect(result).toEqual([])
  })
})
