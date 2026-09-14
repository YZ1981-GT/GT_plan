import { describe, it, expect } from 'vitest'
import {
  emptyProdCostBlock,
  enrichProdCostBlock,
  migrateToProdCostBlocks,
  readMatrixSourceTotals,
} from '../useF2ProductionCostMatrixFormulas'

describe('useF2ProductionCostMatrixFormulas', () => {
  it('月末余额 = 期初 + 增加合计 − 结转', () => {
    const b = emptyProdCostBlock('甲产品')
    const opening = b.rows.find((r) => r.key === 'opening')!
    opening.months['01'] = 1000
    const rm = b.rows.find((r) => r.key === 'rawMaterial')!
    rm.months['01'] = 500
    const fg = b.rows.find((r) => r.key === 'transferFG')!
    fg.months['01'] = 300
    const e = enrichProdCostBlock(b)
    const janEnd = e.rows.find((r) => r.key === 'monthEnd')!.months['01']
    expect(janEnd).toBe(1200)
    expect(e.rows.find((r) => r.key === 'increaseTotal')!.months['01']).toBe(500)
  })

  it('2月起期初 = 上月月末余额', () => {
    const b = emptyProdCostBlock()
    b.rows.find((r) => r.key === 'opening')!.months['01'] = 100
    b.rows.find((r) => r.key === 'rawMaterial')!.months['01'] = 50
    b.rows.find((r) => r.key === 'rawMaterial')!.months['02'] = 20
    const e = enrichProdCostBlock(b)
    expect(e.rows.find((r) => r.key === 'opening')!.months['02']).toBe(150)
    expect(e.rows.find((r) => r.key === 'monthEnd')!.months['02']).toBe(170)
  })

  it('合计：期初取1月，月末取12月，发生额累加', () => {
    const b = emptyProdCostBlock()
    b.rows.find((r) => r.key === 'opening')!.months['01'] = 100
    const rm = b.rows.find((r) => r.key === 'rawMaterial')!
    rm.months['01'] = 10
    rm.months['02'] = 20
    const e = enrichProdCostBlock(b)
    const rmRow = e.rows.find((r) => r.key === 'rawMaterial')!
    expect(rmRow.total).toBe(30)
    expect(e.rows.find((r) => r.key === 'opening')!.total).toBe(100)
  })

  it('迁移旧扁平行', () => {
    const legacy = [{
      productName: 'B',
      dmOpening: 100, dmInput: 200, dmTransfer: 50,
      dlOpening: 0, dlInput: 80, dlTransfer: 20,
      ohOpening: 0, ohInput: 30, ohTransfer: 10,
      remark: '',
      rowId: '1',
    }]
    const blocks = migrateToProdCostBlocks(legacy)
    expect(blocks).toHaveLength(1)
    expect(blocks![0].productName).toBe('B')
    const totals = readMatrixSourceTotals(blocks!)
    expect(totals.material).toBeGreaterThan(0)
  })
})
