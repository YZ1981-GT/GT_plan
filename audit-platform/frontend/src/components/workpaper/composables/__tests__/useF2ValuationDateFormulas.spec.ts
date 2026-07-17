import { describe, it, expect } from 'vitest'
import {
  emptyDateProject,
  enrichDateProject,
  consumeFifoLayers,
  addFifoLayers,
  layersFromOpening,
  calcMovingWaIssue,
  migrateToDateProjects,
  defaultThreeDateProjects,
} from '../useF2ValuationDateFormulas'

describe('useF2ValuationDateFormulas', () => {
  it('默认 3 个测试项目', () => {
    const projects = defaultThreeDateProjects()
    expect(projects).toHaveLength(3)
    expect(projects[0].lines[0].dateLabel).toBe('年初数')
  })

  it('FIFO 层：先耗期初再耗购入', () => {
    let layers = layersFromOpening(100, 1000)
    layers = addFifoLayers(layers, 50, 12)
    const { cost, remaining } = consumeFifoLayers(layers, 120)
    expect(cost).toBe(100 * 10 + 20 * 12)
    expect(remaining.reduce((s, l) => s + l.qty, 0)).toBe(30)
  })

  it('按日期滚动 FIFO：差异 M=K−F', () => {
    const p = emptyDateProject(1, '甲')
    p.lines[0].prodQty = 100
    p.lines[0].prodAmt = 1000
    p.lines[1].dateLabel = '2024-01-15'
    p.lines[1].prodQty = 50
    p.lines[1].prodAmt = 600
    p.lines[1].saleQty = 80
    p.lines[1].saleAmt = 800
    const e = enrichDateProject(p, 'fifo')
    const row = e.lines[1]
    expect(row.shouldAmt).toBe(80 * 10)
    expect(row.variance).toBe(row.shouldAmt - 800)
  })

  it('移动加权平均：入库后加权再发出', () => {
    const wa = calcMovingWaIssue(100, 1000, 100, 1200, 50)
    expect(wa.shouldPrice).toBe(11)
    expect(wa.shouldAmt).toBe(550)
    expect(wa.endQty).toBe(150)
    expect(wa.endAmt).toBe(1650)
  })

  it('迁移月度结构到日期结构', () => {
    const monthly = [{
      itemName: '乙',
      months: [
        { key: 'opening', label: '年初数', prodQty: 10, prodAmt: 100 },
        { key: '01', label: '1月', prodQty: 5, prodAmt: 60, saleQty: 3, saleAmt: 30 },
      ],
    }]
    const migrated = migrateToDateProjects(monthly)
    expect(migrated).toHaveLength(3)
    expect(migrated![0].itemName).toBe('乙')
    expect(migrated![0].lines[1].dateLabel).toBe('1月')
  })
})
