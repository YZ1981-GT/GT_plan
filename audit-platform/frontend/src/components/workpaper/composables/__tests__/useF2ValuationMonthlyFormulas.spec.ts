import { describe, it, expect } from 'vitest'
import {
  emptyProductProject,
  enrichProductProject,
  calcFifoIssueAmt,
  calcProductTotals,
  migrateLegacyValuationRows,
} from '../useF2ValuationMonthlyFormulas'

describe('useF2ValuationMonthlyFormulas', () => {
  it('加权平均：J=(期初+购入)/(数量)，K=D×J，M=K−F', () => {
    const p = emptyProductProject(1, '甲产品')
    p.months[0].prodQty = 100
    p.months[0].prodAmt = 1000
    p.months[1].prodQty = 100
    p.months[1].prodAmt = 1200
    p.months[1].saleQty = 50
    p.months[1].saleAmt = 500

    const e = enrichProductProject(p, 'weighted-avg')
    const jan = e.months[1]
    // J = (1000+1200)/(100+100) = 11
    expect(jan.shouldPrice).toBe(11)
    expect(jan.shouldAmt).toBe(550)
    expect(jan.variance).toBe(50)
    expect(jan.endQty).toBe(150)
    expect(jan.endAmt).toBe(1650)
    // 结余 L = 期初+购入−账面发出
    expect(jan.remainder).toBe(1700)
  })

  it('先进先出月内：先耗期初再耗购入', () => {
    const fifo = calcFifoIssueAmt(100, 1000, 100, 1200, 120)
    // 100×10 + 20×12 = 1240
    expect(fifo.shouldAmt).toBe(1240)
    expect(fifo.shouldPrice).toBeCloseTo(1240 / 120, 6)

    const p = emptyProductProject(1)
    p.months[0].prodQty = 100
    p.months[0].prodAmt = 1000
    p.months[1].prodQty = 100
    p.months[1].prodAmt = 1200
    p.months[1].saleQty = 120
    p.months[1].saleAmt = 1200
    const e = enrichProductProject(p, 'fifo')
    expect(e.months[1].shouldAmt).toBe(1240)
    expect(e.months[1].variance).toBe(40)
  })

  it('标准成本：K=发出数量×标准单价', () => {
    const p = emptyProductProject(1)
    p.stdPrice = 10
    p.months[0].prodQty = 50
    p.months[0].prodAmt = 500
    p.months[1].saleQty = 20
    p.months[1].saleAmt = 180
    const e = enrichProductProject(p, 'standard-cost')
    expect(e.months[1].shouldPrice).toBe(10)
    expect(e.months[1].shouldAmt).toBe(200)
    expect(e.months[1].variance).toBe(20)
  })

  it('合计不含年初行', () => {
    const p = emptyProductProject(1)
    p.months[0].prodQty = 10
    p.months[0].prodAmt = 100
    p.months[1].prodQty = 5
    p.months[1].prodAmt = 50
    p.months[1].saleQty = 2
    p.months[1].saleAmt = 20
    const e = enrichProductProject(p, 'weighted-avg')
    const t = calcProductTotals(e.months)
    expect(t.prodQty).toBe(5)
    expect(t.saleQty).toBe(2)
  })

  it('迁移旧扁平行到 4 产品结构', () => {
    const legacy = [
      {
        rowId: '1',
        itemName: 'A',
        openingQty: 10,
        openingAmt: 100,
        inboundQty: 5,
        inboundAmt: 60,
        issueQty: 3,
        bookIssueAmt: 30,
        stdPrice: 0,
      },
    ]
    const migrated = migrateLegacyValuationRows(legacy)
    expect(migrated).toHaveLength(1)
    expect(migrated![0].itemName).toBe('A')
    expect(migrated![0].months[0].prodQty).toBe(10)
    expect(migrated![0].months[12].saleQty).toBe(3)
  })
})
