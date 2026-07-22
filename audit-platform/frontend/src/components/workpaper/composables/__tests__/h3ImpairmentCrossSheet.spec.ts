import { describe, it, expect } from 'vitest'
import {
  bookValueFromH32Row,
  collectStocktakeImpairmentConcerns,
  mapH32TypeToH310Category,
  parseH32CostDetailRows,
  extractK11InvestmentPropertyAmount,
  K11_H3_ITEM_IDS,
} from '../h3ImpairmentCrossSheet'

describe('h3ImpairmentCrossSheet', () => {
  it('bookValueFromH32Row uses cost minus depreciation (ex impairment)', () => {
    expect(bookValueFromH32Row({
      costEnd: 1000,
      accDepEnd: 200,
      impairmentEnd: 50,
      netValue: 750,
    })).toBe(800)
  })

  it('mapH32TypeToH310Category maps land and CIP', () => {
    expect(mapH32TypeToH310Category('土地使用权')).toBe('土地使用权')
    expect(mapH32TypeToH310Category('在建工程')).toBe('在建工程')
    expect(mapH32TypeToH310Category('房屋')).toBe('房屋、建筑物')
  })

  it('parseH32CostDetailRows reads H3-2-cost-rows', () => {
    const seeds = parseH32CostDetailRows((id) => {
      if (id !== 'H3-2-cost-rows') return null
      return [{
        rowId: 'dc1',
        assetName: '写字楼A',
        assetType: '房屋',
        costEnd: 5000000,
        accDepEnd: 800000,
        impairmentEnd: 100000,
      }]
    })
    expect(seeds).toHaveLength(1)
    expect(seeds[0].bookValue).toBe(4200000)
    expect(seeds[0].alreadyProvided).toBe(100000)
  })

  it('collectStocktakeImpairmentConcerns flags vacant and deficit', () => {
    const concerns = collectStocktakeImpairmentConcerns([
      { rowId: 's1', assetName: '商铺', leaseStatus: '空置', bookAmount: 100 },
      { rowId: 's2', assetName: '仓库', result: '盘亏', bookAmount: 200 },
      { rowId: 's3', assetName: '正常', leaseStatus: '已出租', result: '账实相符' },
    ])
    expect(concerns).toHaveLength(2)
    expect(concerns[0].assetName).toBe('商铺')
    expect(concerns[1].assetName).toBe('仓库')
  })

  it('extractK11InvestmentPropertyAmount prefers K11-2 occurrence over source keys', () => {
    const list = [
      { item_id: K11_H3_ITEM_IDS.occurrence, remark: '50000' },
      { item_id: K11_H3_ITEM_IDS.sourceAmount, remark: '45000' },
      { item_id: K11_H3_ITEM_IDS.sourceWpAmount, remark: '40000' },
    ]
    const { amount, source } = extractK11InvestmentPropertyAmount(list)
    expect(amount).toBe(50000)
    expect(source).toBe(K11_H3_ITEM_IDS.occurrence)
  })

  it('extractK11InvestmentPropertyAmount reads K11-2-investment-property-source-amount', () => {
    const { amount, source } = extractK11InvestmentPropertyAmount([
      { item_id: K11_H3_ITEM_IDS.sourceAmount, remark: '12345.67' },
    ])
    expect(amount).toBe(12345.67)
    expect(source).toBe(K11_H3_ITEM_IDS.sourceAmount)
  })

  it('extractK11InvestmentPropertyAmount reads K11-source-H3-amount', () => {
    const { amount, source } = extractK11InvestmentPropertyAmount([
      { item_id: K11_H3_ITEM_IDS.sourceWpAmount, remark: '12345.67' },
    ])
    expect(amount).toBe(12345.67)
    expect(source).toBe(K11_H3_ITEM_IDS.sourceWpAmount)
  })

  it('extractK11InvestmentPropertyAmount sums H3 rows from K11-2-detail-rows', () => {
    const { amount, source } = extractK11InvestmentPropertyAmount([
      {
        item_id: K11_H3_ITEM_IDS.detailRows,
        remark: JSON.stringify([
          { assetCategory: '固定资产减值', sourceWp: 'H1', currentOccurrence: 1000 },
          { assetCategory: '投资性房地产减值准备', sourceWp: 'H3', currentOccurrence: 2000 },
          { assetCategory: '投资性房地产减值损失', currentProvision: 500 },
        ]),
      },
    ])
    expect(amount).toBe(2500)
    expect(source).toBe('K11-2 明细(投资性房地产行)')
  })
})
