/**
 * H3-14 跨底稿联动单测
 */
import { describe, it, expect } from 'vitest'
import {
  mapH32AssetTypeToCategory,
  isRentalRelatedD43Item,
  aggregateD43RentalRows,
  matchD43ItemToContract,
  extractH32Assets,
} from '../composables/useH3RentalCrossSheet'

describe('H3-14 mapH32AssetTypeToCategory', () => {
  it('土地/使用权 → land', () => {
    expect(mapH32AssetTypeToCategory('土地使用权')).toBe('land')
    expect(mapH32AssetTypeToCategory('土地')).toBe('land')
  })

  it('房屋/建筑物 → building', () => {
    expect(mapH32AssetTypeToCategory('房屋')).toBe('building')
    expect(mapH32AssetTypeToCategory('')).toBe('building')
  })
})

describe('H3-14 D4-3 租金分项识别', () => {
  it('含租金/租赁关键词的项目被识别', () => {
    expect(isRentalRelatedD43Item('投资性房地产租金收入')).toBe(true)
    expect(isRentalRelatedD43Item('咨询服务')).toBe(false)
  })

  it('aggregateD43RentalRows 汇总租金分项', () => {
    const agg = aggregateD43RentalRows([
      { rowId: '1', item: '投资性房地产租金', currentUnadjusted: 100, currentAdjustment: 20 },
      { rowId: '2', item: '材料销售', currentUnadjusted: 50, currentAdjustment: 0 },
      { rowId: '3', item: '出租收入', currentAudited: 30 },
    ])
    expect(agg.items).toHaveLength(2)
    expect(agg.totalCurrent).toBe(150) // 120 + 30
  })

  it('matchD43ItemToContract 模糊匹配', () => {
    const items = [{ rowId: 'a', item: 'XX大厦租金收入', currentAudited: 100, priorAudited: 0 }]
    const hit = matchD43ItemToContract('XX大厦', items)
    expect(hit?.currentAudited).toBe(100)
  })
})

describe('H3-14 extractH32Assets', () => {
  it('从 H3-2-cost-rows 解析资产种子', () => {
    const seeds = extractH32Assets((id) => {
      if (id === 'H3-2-cost-rows') {
        return [
          { rowId: 'dc-1', assetName: 'A大厦', assetType: '房屋', area: 1000 },
          { rowId: 'dc-2', assetName: 'B地块', assetType: '土地使用权', area: 500 },
        ]
      }
      return undefined
    }, 'cost')
    expect(seeds).toHaveLength(2)
    expect(seeds[0].category).toBe('building')
    expect(seeds[1].category).toBe('land')
    expect(seeds[1].area).toBe(500)
  })
})
