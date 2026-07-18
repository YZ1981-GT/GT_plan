import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  defaultRelatedPartyMarketSheet,
  emptyMarketGroup,
  enrichMarketGroup,
  enrichMarketMonth,
  migrateRelatedPartyMarketSheet,
  applyMarketOcrToSheet,
} from '../useF2RelatedPartyMarketFormulas'
import { useF2RelatedPartyMarket } from '../useF2RelatedPartyMarket'
import type { ChecklistResponse } from '../useF2SpecialFormData'

describe('F2-66 市场价核查公式层', () => {
  it('默认结构：1组×12个月', () => {
    const sheet = defaultRelatedPartyMarketSheet()
    expect(sheet.groups).toHaveLength(1)
    expect(sheet.groups[0].rows).toHaveLength(12)
    expect(sheet.groups[0].rows.map((r) => r.month)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])
  })

  it('区间/偏离率/是否处于区间自动计算', () => {
    const inRange = enrichMarketMonth({
      id: 'a', month: 1, purchaseAvgPrice: 105, marketPriceStart: 100, marketPriceEnd: 110, judgment: '', remark: '',
    })
    expect(inRange.marketLow).toBe(100)
    expect(inRange.marketHigh).toBe(110)
    expect(inRange.inRange).toBe(true)
    expect(inRange.isAbnormal).toBe(false)
    expect(inRange.suggestedJudgment).toBe('是')
    expect(inRange.deviationRate).toBeCloseTo(0, 5)

    const outOfRange = enrichMarketMonth({
      id: 'b', month: 2, purchaseAvgPrice: 130, marketPriceStart: 110, marketPriceEnd: 100, judgment: '', remark: '',
    })
    expect(outOfRange.marketLow).toBe(100)
    expect(outOfRange.marketHigh).toBe(110)
    expect(outOfRange.inRange).toBe(false)
    expect(outOfRange.isAbnormal).toBe(true)
    expect(outOfRange.suggestedJudgment).toBe('否')
    expect(outOfRange.deviationRate).toBeCloseTo((130 - 105) / 105, 5)
  })

  it('缺少市场价或采购价时不判断', () => {
    const row = enrichMarketMonth({
      id: 'c', month: 3, purchaseAvgPrice: 0, marketPriceStart: 100, marketPriceEnd: 110, judgment: '', remark: '',
    })
    expect(row.inRange).toBeNull()
    expect(row.isAbnormal).toBe(false)
    expect(row.suggestedJudgment).toBe('')
  })

  it('分组汇总：异常月数与已填月数', () => {
    const group = emptyMarketGroup()
    group.relatedParty = '关联方A'
    group.productName = '产品A'
    group.rows[0] = { ...group.rows[0], purchaseAvgPrice: 130, marketPriceStart: 100, marketPriceEnd: 110 }
    group.rows[1] = { ...group.rows[1], purchaseAvgPrice: 105, marketPriceStart: 100, marketPriceEnd: 110 }
    const enriched = enrichMarketGroup(group)
    expect(enriched.abnormalCount).toBe(1)
    expect(enriched.filledMonthCount).toBe(2)
  })

  it('旧版扁平行迁移为分组月度模型', () => {
    const legacy = [
      { id: '1', relatedParty: '关联方A', itemName: '产品A', relatedPrice: 120, marketPrice: 100, conclusion: '不公允', remark: 'x' },
      { id: '2', relatedParty: '关联方A', itemName: '产品A', relatedPrice: 100, marketPrice: 100, conclusion: '公允', remark: '' },
      { id: '3', relatedParty: '关联方B', itemName: '产品B', relatedPrice: 50, marketPrice: 52, conclusion: '', remark: '' },
    ]
    const sheet = migrateRelatedPartyMarketSheet(legacy)
    expect(sheet.groups).toHaveLength(2)
    const groupA = sheet.groups[0]
    expect(groupA.relatedParty).toBe('关联方A')
    expect(groupA.rows).toHaveLength(12)
    expect(groupA.rows[0].purchaseAvgPrice).toBe(120)
    expect(groupA.rows[0].marketPriceStart).toBe(100)
    expect(groupA.rows[0].judgment).toBe('否')
    expect(groupA.rows[1].judgment).toBe('是')
  })

  it('新版对象直接归一化并补齐12个月', () => {
    const sheet = migrateRelatedPartyMarketSheet({
      groups: [{
        id: 'g1', relatedParty: 'A', productName: 'P',
        rows: [{ id: 'r5', month: 5, purchaseAvgPrice: 88, marketPriceStart: 80, marketPriceEnd: 90, judgment: '是', remark: '' }],
      }],
    })
    expect(sheet.groups[0].rows).toHaveLength(12)
    expect(sheet.groups[0].rows[4].purchaseAvgPrice).toBe(88)
    expect(sheet.groups[0].rows[0].purchaseAvgPrice).toBe(0)
  })
})

describe('F2-66 composable', () => {
  function setup(initialRows?: unknown) {
    const map = new Map<string, ChecklistResponse>()
    if (initialRows !== undefined) {
      map.set('F2-66-rows', { item_id: 'F2-66-rows', conclusion: null, remark: JSON.stringify(initialRows) })
    }
    const allResponses = ref(map)
    const market = useF2RelatedPartyMarket({ allResponses, isReadonly: ref(false) })
    return { allResponses, market }
  }

  it('旧数据迁移后立即回写新结构', () => {
    const { allResponses, market } = setup([
      { id: '1', relatedParty: 'A', itemName: 'P', relatedPrice: 120, marketPrice: 100, conclusion: '不公允', remark: '' },
    ])
    expect(market.groups.value).toHaveLength(1)
    expect(market.groups.value[0].rows[0].isAbnormal).toBe(true)
    const saved = JSON.parse(allResponses.value.get('F2-66-rows')!.remark!)
    expect(Array.isArray(saved.groups)).toBe(true)
  })

  it('addGroup 不被自回显裁剪', () => {
    const { market } = setup()
    market.addGroup()
    expect(market.sheet.value.groups).toHaveLength(2)
  })

  it('updateRow 后区间判断实时联动', () => {
    const { market } = setup()
    const group = market.sheet.value.groups[0]
    const row = group.rows[0]
    market.updateGroup(group.id, { relatedParty: '关联方A', productName: '产品A' })
    market.updateRow(group.id, row.id, { purchaseAvgPrice: 150, marketPriceStart: 100, marketPriceEnd: 110 })
    const enriched = market.groups.value[0].rows[0]
    expect(enriched.inRange).toBe(false)
    expect(enriched.suggestedJudgment).toBe('否')
    expect(market.abnormalCount.value).toBe(1)
    expect(market.filledGroupCount.value).toBe(1)
  })

  it('OCR确认回写：匹配组并默认仅填空字段', () => {
    const sheet = defaultRelatedPartyMarketSheet()
    sheet.groups[0].relatedParty = '关联方A'
    sheet.groups[0].productName = '产品甲'
    sheet.groups[0].rows[0].purchaseAvgPrice = 120
    const next = applyMarketOcrToSheet(sheet, {
      relatedParty: '关联方A',
      productName: '产品甲',
      month: 1,
      purchaseAvgPrice: 999,
      marketPriceStart: 100,
      marketPriceEnd: 110,
      remark: '挂牌价截图',
    })
    expect(next.groups).toHaveLength(1)
    expect(next.groups[0].rows[0].purchaseAvgPrice).toBe(120)
    expect(next.groups[0].rows[0].marketPriceStart).toBe(100)
    expect(next.groups[0].rows[0].marketPriceEnd).toBe(110)
    expect(next.groups[0].rows[0].remark).toBe('挂牌价截图')
  })
})
