import { describe, it, expect } from 'vitest'
import {
  normalizeCostRow,
  normalizeFairRow,
  normalizeChangeType,
  calcCostNetValue,
  calcCoverageRate,
  isIncreaseChangeType,
  getEvidenceHint,
  normalizeTraceRow,
} from '../h3AdditionCheckModel'

describe('h3AdditionCheckModel', () => {
  it('normalizes legacy change types', () => {
    expect(normalizeChangeType('购入')).toBe('外购')
    expect(normalizeChangeType('自建转入')).toBe('在建转入')
  })

  it('calculates cost net value with impairment', () => {
    const row = normalizeCostRow({ originalCost: 1000, accDep: 200, impairment: 50 })
    expect(row.netValue).toBe(750)
    expect(calcCostNetValue(row)).toBe(750)
  })

  it('calculates coverage rate capped at 100%', () => {
    expect(calcCoverageRate(500, 1000)).toBe(50)
    expect(calcCoverageRate(1500, 1000)).toBe(100)
    expect(calcCoverageRate(100, 0)).toBe(0)
  })

  it('identifies increase vs decrease change types', () => {
    expect(isIncreaseChangeType('外购')).toBe(true)
    expect(isIncreaseChangeType('处置')).toBe(false)
    expect(isIncreaseChangeType('转出')).toBe(false)
  })

  it('migrates legacy cost row fields', () => {
    const row = normalizeCostRow({
      assetName: '测试物业',
      changeType: '购入',
      originalCost: 100,
      accDep: 10,
      contract: true,
      conclusion: '有问题',
    })
    expect(row.changeType).toBe('外购')
    expect(row.contract).toBe(true)
    expect(row.isAbnormal).toBe('Y')
    expect(row.checks.check1).toBe(false)
  })

  it('normalizes fair row end balance', () => {
    const row = normalizeFairRow({ fairValue: 2000, fairValueChange: 100 })
    expect(row.endBalance).toBe(2000)
  })

  it('normalizes trace row and calculates diff', () => {
    const row = normalizeTraceRow({ sourceAmount: 1000, bookAmount: 900 })
    expect(row.amountDiff).toBe(100)
  })
})
