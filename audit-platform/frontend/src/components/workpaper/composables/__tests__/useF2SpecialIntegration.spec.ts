/**
 * F2 特殊组 — 公式与数据集成测试
 */
import { describe, it, expect } from 'vitest'
import {
  calcImpairment,
  calcExpectedLoss,
  isLossContract,
  calcPriceDeviation,
  calcChecklistCompletion,
} from '../useF2SpecialFormulaEngine'
import { readSpeRowJson } from '../useF2SpecialFormData'
import type { ChecklistResponse } from '../useF2SpecialFormData'

describe('useF2SpecialIntegration', () => {
  it('合同履约减值 = max(0, 账面-可收回)', () => {
    expect(calcImpairment(100, 80)).toBe(20)
    expect(calcImpairment(80, 100)).toBe(0)
  })

  it('亏损合同判定：总成本>总收入', () => {
    expect(isLossContract(100, 120)).toBe(true)
    expect(calcExpectedLoss(100, 120, 0.5)).toBeGreaterThan(0)
    expect(isLossContract(120, 100)).toBe(false)
    expect(calcExpectedLoss(120, 100, 0.5)).toBe(0)
  })

  it('关联方定价偏离度', () => {
    const spread = calcPriceDeviation(110, 100)
    expect(typeof spread).toBe('number')
    if (typeof spread === 'number') expect(spread).toBeCloseTo(0.1, 3)
  })

  it('F2-57 行 JSON round-trip', () => {
    const rows = [{
      id: 'p1', projectName: '项目A', totalRevenue: 1000, totalCost: 800,
      recognizedRevenue: 600, incurredCost: 500, bookValue: 100, mgmtProvision: 0, remark: '',
    }]
    const map = new Map<string, ChecklistResponse>()
    map.set('F2-57-rows', { item_id: 'F2-57-rows', conclusion: null, remark: JSON.stringify(rows) })
    const raw = readSpeRowJson(map.get('F2-57-rows'))
    const parsed = JSON.parse(raw!)
    expect(parsed).toHaveLength(1)
    expect(parsed[0].projectName).toBe('项目A')
  })

  it('F2-69 核查清单完成度', () => {
    const pct = calcChecklistCompletion(8, 10, 0)
    expect(pct).toBeCloseTo(80, 1)
  })

  it('F2-70 实体 JSON round-trip', () => {
    const entities = [{
      id: 's1', supplierName: '供应商A', creditCode: '91110000',
      legalRepresentative: '张三', registeredCapital: '1000万',
      establishDate: '', businessScope: '', operatingAddress: '',
      employeeCount: 0, mainCustomers: '', financialStatus: '',
      cooperationYears: 2, transactionAmount: 100000,
      checkMethod: '实地', checkConclusion: '无异常',
    }]
    const map = new Map<string, ChecklistResponse>()
    map.set('F2-70-entities', { item_id: 'F2-70-entities', conclusion: null, remark: JSON.stringify(entities) })
    const raw = readSpeRowJson(map.get('F2-70-entities'))
    const parsed = JSON.parse(raw!)
    expect(parsed[0].supplierName).toBe('供应商A')
  })
})
