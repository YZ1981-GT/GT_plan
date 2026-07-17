import { describe, it, expect } from 'vitest'
import {
  emptyStdCostProject,
  enrichStdCostProject,
  calcStdCostProjectTotals,
  defaultThreeStdCostProjects,
  migrateToStdCostProjects,
} from '../useF2StdCostMonthlyFormulas'

describe('useF2StdCostMonthlyFormulas', () => {
  it('默认 3 个测试项目', () => {
    expect(defaultThreeStdCostProjects()).toHaveLength(3)
  })

  it('应结存滚动：期初 + 生产 − 发出', () => {
    const p = emptyStdCostProject(1, '甲')
    p.months[0].actEndQty = 100
    p.months[0].actEndStdCost = 1000
    p.months[0].actEndStdVariance = 50
    const jan = p.months[1]
    jan.prodQty = 20
    jan.stdUnitPrice = 10
    jan.prodStdVariance = 10
    jan.saleQty = 30
    jan.saleStdVariance = 5
    jan.actEndQty = 90
    jan.actEndStdCost = 900
    jan.actEndStdVariance = 55
    const e = enrichStdCostProject(p)
    const row = e.months[1]
    expect(row.prodStdCost).toBe(200)
    expect(row.saleStdCost).toBe(300)
    expect(row.expEndQty).toBe(90)
    expect(row.expEndStdCost).toBe(900)
    expect(row.expEndStdVariance).toBe(55)
    expect(row.diffStdCost).toBe(0)
  })

  it('差异 = 实际结存标准成本 − 应结存标准成本', () => {
    const p = emptyStdCostProject(1)
    p.months[0].actEndStdCost = 500
    p.months[1].actEndStdCost = 480
    const e = enrichStdCostProject(p)
    expect(e.months[1].diffStdCost).toBe(480 - e.months[1].expEndStdCost)
  })

  it('合计不含年初行', () => {
    const p = emptyStdCostProject(1)
    p.months[0].actEndStdCost = 100
    p.months[1].prodQty = 10
    p.months[1].stdUnitPrice = 5
    p.months[1].saleQty = 2
    const e = enrichStdCostProject(p)
    const t = calcStdCostProjectTotals(e.months)
    expect(t.prodQty).toBe(10)
    expect(t.saleQty).toBe(2)
  })

  it('迁移旧月度结构', () => {
    const legacy = [{
      itemName: '乙',
      months: [
        { key: 'opening', prodQty: 10, prodAmt: 100 },
        { key: '01', prodQty: 5, prodPrice: 10, saleQty: 2, saleAmt: 20 },
      ],
    }]
    const migrated = migrateToStdCostProjects(legacy)
    expect(migrated).toHaveLength(3)
    expect(migrated![0].itemName).toBe('乙')
  })
})
