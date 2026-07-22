/**
 * i2OutsourceCheckModel — 单元测试
 */
import { describe, it, expect } from 'vitest'
import {
  normalizeI2OutsourceRow,
  summarizeI2Outsource,
  hasAmountMismatch,
  hasMissingAcceptance,
  suggestOutsourceAbnormal,
  extractI27OutsourceTotal,
  formatCoverageLabel,
  emptyI2OutsourceRow,
} from '../i2OutsourceCheckModel'

describe('i2OutsourceCheckModel', () => {
  it('兼容旧字段 supplier/deliverable/amount', () => {
    const row = normalizeI2OutsourceRow({
      supplier: '甲科研所',
      contractNo: 'HT-001',
      amount: 100000,
      deliverable: '技术方案',
      projectName: '项目A',
      conclusion: '验收通过',
    })
    expect(row.entrustedParty).toBe('甲科研所')
    expect(row.rdContent).toBe('技术方案')
    expect(row.acceptanceResult).toBe('技术方案')
    expect(row.amount).toBe(100000)
    expect(row.contractNo).toBe('HT-001')
  })

  it('检查比例：总体为 0 → N/A；有总体时计算百分比', () => {
    const rows = [
      emptyI2OutsourceRow({ amount: 30 }),
      emptyI2OutsourceRow({ amount: 70 }),
    ]
    const zero = summarizeI2Outsource(rows, 0)
    expect(zero.coverageRate).toBeNull()
    expect(formatCoverageLabel(zero.coverageRate)).toBe('N/A')
    expect(zero.checkedTotal).toBe(100)

    const ok = summarizeI2Outsource(rows, 200)
    expect(ok.coverageRate).toBe(50)
    expect(formatCoverageLabel(ok.coverageRate)).toBe('50.00%')
  })

  it('金额不符 / 缺验收 / 建议异常标记', () => {
    const mismatch = emptyI2OutsourceRow({ amount: 100, acceptanceAmount: 80 })
    expect(hasAmountMismatch(mismatch)).toBe(true)
    expect(suggestOutsourceAbnormal(mismatch)).toBe('金额不符')

    const missing = emptyI2OutsourceRow({ amount: 50 })
    expect(hasMissingAcceptance(missing)).toBe(true)
    expect(suggestOutsourceAbnormal(missing)).toBe('缺验收')

    const noQual = emptyI2OutsourceRow({
      amount: 50,
      acceptanceDate: '2025-12-01',
      acceptanceResult: '通过',
    })
    expect(suggestOutsourceAbnormal(noQual)).toBe('资质未核')
  })

  it('从 I2-7 提取委外发生额', () => {
    expect(extractI27OutsourceTotal([
      { outsourceAmount: 10 },
      { outsourceFee: 20 },
      { category: '委外研发费', amount: 30 },
      { materialSubtotal: 999 },
    ])).toBe(60)

    expect(extractI27OutsourceTotal(JSON.stringify([
      { outsourceSubtotal: 12.345 },
    ]))).toBe(12.35)
  })

  it('优先使用 increase.outsource 分期字段', () => {
    expect(extractI27OutsourceTotal([
      { increase: { outsource: 100.5 }, outsourceAmount: 1 },
      { increase: { outsource: 50 }, audited: { outsource: 999 } },
      { audited: { outsource: 20 } },
    ])).toBe(170.5)
  })
})
