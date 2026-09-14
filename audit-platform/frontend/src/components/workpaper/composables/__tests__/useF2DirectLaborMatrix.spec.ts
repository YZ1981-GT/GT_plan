import { describe, it, expect } from 'vitest'
import {
  emptyLaborProductLine,
  enrichLaborProductLine,
  migrateToLaborMatrix,
  countAbnormalUnitVariance,
  sumLaborAnnual,
} from '../useF2DirectLaborMatrixFormulas'

describe('useF2DirectLaborMatrixFormulas', () => {
  it('单位人工成本 = 直接人工 ÷ 产量', () => {
    const line = emptyLaborProductLine('甲')
    line.laborMonths['01'] = 1000
    line.outputMonths['01'] = 200
    const e = enrichLaborProductLine(line)
    expect(e.unitMonths['01']).toBe(5)
    expect(e.unitAverage).toBe(5)
    expect(e.laborTotal).toBe(1000)
    expect(e.outputTotal).toBe(200)
  })

  it('变动率基于合计/平均值与上年度', () => {
    const line = emptyLaborProductLine()
    line.laborMonths['01'] = 120
    line.laborPriorYear = 100
    line.unitPriorYear = 10
    line.laborMonths['01'] = 120
    line.outputMonths['01'] = 10
    const e = enrichLaborProductLine(line)
    expect(e.laborChangeRate).toBe(0.2)
    expect(e.unitAverage).toBe(12)
    expect(e.unitChangeRate).toBe(0.2)
  })

  it('异常单位成本变动计数', () => {
    const a = enrichLaborProductLine(emptyLaborProductLine())
    a.unitPriorYear = 100
    a.laborMonths['01'] = 200
    a.outputMonths['01'] = 1
    const enriched = enrichLaborProductLine({
      ...emptyLaborProductLine(),
      unitPriorYear: 100,
      laborMonths: { ...emptyLaborProductLine().laborMonths, '01': 200 },
      outputMonths: { ...emptyLaborProductLine().outputMonths, '01': 1 },
    })
    expect(countAbnormalUnitVariance([enriched], 5)).toBeGreaterThanOrEqual(0)
  })

  it('迁移旧部门扁平行', () => {
    const legacy = [{
      rowId: '1', department: '车间A', jobType: '操作',
      headcount: 5, hours: 100, wageRate: 20, actualLabor: 2000, remark: '',
    }]
    const lines = migrateToLaborMatrix(legacy)
    expect(lines).toHaveLength(1)
    expect(lines![0].productName).toBe('车间A')
    expect(sumLaborAnnual(lines!)).toBe(2000)
  })
})
