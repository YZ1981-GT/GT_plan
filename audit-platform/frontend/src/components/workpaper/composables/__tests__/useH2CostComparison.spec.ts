/**
 * useH2CostComparison — H2-7 单方造价/现金流勾稽公式单测
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useH2CostComparison, UNIT_DIFF_THRESHOLD } from '../useH2CostComparison'

function setup(rows?: any[]) {
  const map = new Map<string, any>()
  if (rows) {
    map.set('H2-7-rows', { remark: JSON.stringify(rows) })
  }
  const saved: Record<string, any> = {}
  const c = useH2CostComparison({
    wpId: ref('wp1'),
    projectId: ref('p1'),
    allResponses: ref(map),
    isReadonly: ref(false),
    onSave: (id, val) => { saved[id] = val },
  })
  return { c, saved, map }
}

describe('useH2CostComparison H2-7', () => {
  it('计算单方造价、可比价均值与差异率', () => {
    const { c } = setup([{
      name: '厂房A',
      totalCost: 10000000,
      buildingArea: 5000,
      comparable1: 1800,
      comparable2: 2000,
      comparable3: 2200,
      periodIncrease: 0,
      cashFlowAmount: 0,
    }])
    const row = c.rows.value[0]
    expect(row.unitCost).toBe(2000)
    expect(row.comparableAvg).toBe(2000)
    expect(row.unitCostDiff).toBe(0)
    expect(row.unitCostDiffRate).toBe(0)
  })

  it('面积为空时不计算单方造价（避免DIV/0）', () => {
    const { c } = setup([{ name: '装置', totalCost: 1000, buildingArea: null }])
    expect(c.rows.value[0].unitCost).toBeNull()
  })

  it('|差异率|>阈值时高亮', () => {
    const { c } = setup([{
      name: '超支工程',
      totalCost: 12000000,
      buildingArea: 5000, // unitCost=2400
      comparable1: 2000,
      periodIncrease: 100,
      cashFlowAmount: 80,
    }])
    const row = c.rows.value[0]
    expect(row.unitCost).toBe(2400)
    expect(row.unitCostDiffRate).toBe(20)
    expect(Math.abs(row.unitCostDiffRate!) > UNIT_DIFF_THRESHOLD).toBe(true)
    expect(c.rowHighlights.value.get(row.rowId)).toBe('red-unit-diff')
    expect(row.cashDiff).toBe(20)
  })

  it('合计行单方造价按加权平均', () => {
    const { c } = setup([
      { name: 'A', totalCost: 1000, buildingArea: 10 },
      { name: 'B', totalCost: 3000, buildingArea: 30 },
    ])
    expect(c.totalRow.value.totalCost).toBe(4000)
    expect(c.totalRow.value.buildingArea).toBe(40)
    expect(c.totalRow.value.unitCost).toBe(100)
  })

  it('主体层现金流勾稽差异', () => {
    const { c } = setup([
      { name: 'A', periodIncrease: 800, cashFlowAmount: 0 },
      { name: 'B', periodIncrease: 200, cashFlowAmount: 0 },
    ])
    c.updateRecon({ cfsCapexAmount: 900 })
    expect(c.entityCashDiff.value).toBe(100)
  })

  it('兼容旧版预算vs实际字段映射', () => {
    const { c } = setup([{
      name: '旧数据',
      contractBudget: 5000,
      adjustedBudget: 5500,
      actualMaterial: 1000,
      actualLabor: 500,
      actualMachinery: 200,
      actualOther: 300,
      deviationReason: '变更',
    }])
    const row = c.rows.value[0]
    expect(row.totalCost).toBe(5000)
    expect(row.periodIncrease).toBe(2000)
    expect(row.diffReason).toBe('变更')
  })

  it('从H2-2自动取数', () => {
    const map = new Map<string, any>()
    map.set('H2-2-rows', {
      remark: JSON.stringify([
        { name: '工程X', budget: 8000, area: 40, increaseTotal: 1200 },
      ]),
    })
    const c = useH2CostComparison({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: ref(map),
      isReadonly: ref(false),
    })
    expect(c.rows.value).toHaveLength(1)
    expect(c.rows.value[0].totalCost).toBe(8000)
    expect(c.rows.value[0].buildingArea).toBe(40)
    expect(c.rows.value[0].periodIncrease).toBe(1200)
    expect(c.rows.value[0].unitCost).toBe(200)
  })
})
