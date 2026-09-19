import { describe, expect, it } from 'vitest'
import { ref } from 'vue'
import {
  defaultRelatedPartyInquirySheet,
  enrichInquiryGroup,
  enrichInquiryMonth,
  migrateRelatedPartyInquirySheet,
  applyInquiryOcrToSheet,
} from '../useF2RelatedPartyInquiryFormulas'
import { useF2RelatedPartyInquiry } from '../useF2RelatedPartyInquiry'
import type { ChecklistResponse } from '../useF2SpecialFormData'

describe('F2-65 询价公式层', () => {
  it('默认仅1个关联方产品组，每组固定12个月', () => {
    const sheet = defaultRelatedPartyInquirySheet()
    expect(sheet.groups).toHaveLength(1)
    expect(sheet.groups[0].rows).toHaveLength(12)
    expect(sheet.groups[0].comparableSuppliers).toHaveLength(4)
  })

  it('可比均价取有效正数报价，价差率超过10%标记异常', () => {
    const row = defaultRelatedPartyInquirySheet().groups[0].rows[0]
    const enriched = enrichInquiryMonth({
      ...row,
      relatedPrice: 120,
      comparablePrices: [100, 110, 90, 0],
    })
    expect(enriched.comparableAverage).toBe(100)
    expect(enriched.spreadRate).toBeCloseTo(0.2)
    expect(enriched.isAbnormal).toBe(true)
    expect(enriched.suggestedJudgment).toBe('待核实')
  })

  it('价差不超过10%自动建议合理', () => {
    const row = defaultRelatedPartyInquirySheet().groups[0].rows[0]
    const enriched = enrichInquiryMonth({
      ...row,
      relatedPrice: 102,
      comparablePrices: [100, 100, 0, 0],
    })
    expect(enriched.isAbnormal).toBe(false)
    expect(enriched.suggestedJudgment).toBe('合理')
  })

  it('分组汇总有效月份和异常月份', () => {
    const group = defaultRelatedPartyInquirySheet().groups[0]
    group.rows[0] = { ...group.rows[0], relatedPrice: 130, comparablePrices: [100, 0, 0, 0] }
    group.rows[1] = { ...group.rows[1], relatedPrice: 100, comparablePrices: [100, 0, 0, 0] }
    const enriched = enrichInquiryGroup(group)
    expect(enriched.filledMonthCount).toBe(2)
    expect(enriched.abnormalCount).toBe(1)
  })

  it('旧版扁平询价行按关联方+产品分组迁移', () => {
    const sheet = migrateRelatedPartyInquirySheet([
      { relatedParty: '关联方A', itemName: '产品甲', relatedPrice: 120, thirdPartyName: '供应商1', inquiryPrice: 100, conclusion: '待核实' },
      { relatedParty: '关联方A', itemName: '产品甲', relatedPrice: 105, thirdPartyName: '供应商1', inquiryPrice: 100, conclusion: '公允' },
      { relatedParty: '关联方B', itemName: '产品乙', relatedPrice: 50, thirdPartyName: '供应商2', inquiryPrice: 50 },
    ])
    expect(sheet.groups).toHaveLength(2)
    expect(sheet.groups[0].rows[0].month).toBe(1)
    expect(sheet.groups[0].rows[1].month).toBe(2)
    expect(sheet.groups[0].rows[0].judgment).toBe('待核实')
    expect(sheet.groups[1].comparableSuppliers[0]).toBe('供应商2')
  })

  it('OCR确认回写：匹配组并默认仅填空字段', () => {
    const sheet = defaultRelatedPartyInquirySheet()
    sheet.groups[0].relatedParty = '关联方A'
    sheet.groups[0].productName = '产品甲'
    sheet.groups[0].rows[0].relatedPrice = 120
    const next = applyInquiryOcrToSheet(sheet, {
      relatedParty: '关联方A',
      productName: '产品甲',
      month: 1,
      relatedPrice: 999,
      supplier1: '独立供应商X',
      price1: 100,
      judgment: '待核实',
      remark: 'OCR备注',
    })
    expect(next.groups).toHaveLength(1)
    expect(next.groups[0].rows[0].relatedPrice).toBe(120)
    expect(next.groups[0].comparableSuppliers[0]).toBe('独立供应商X')
    expect(next.groups[0].rows[0].comparablePrices[0]).toBe(100)
    expect(next.groups[0].rows[0].judgment).toBe('待核实')
    expect(next.groups[0].rows[0].remark).toBe('OCR备注')
  })

  it('OCR确认回写：overwrite 可覆盖并新建组别', () => {
    const sheet = defaultRelatedPartyInquirySheet()
    sheet.groups[0].relatedParty = 'A'
    sheet.groups[0].productName = '甲'
    sheet.groups[0].rows[2].relatedPrice = 10
    const next = applyInquiryOcrToSheet(sheet, {
      relatedParty: 'B',
      productName: '乙',
      month: 3,
      relatedPrice: 88,
      price1: 80,
    }, { overwrite: true })
    expect(next.groups).toHaveLength(2)
    expect(next.groups[1].relatedParty).toBe('B')
    expect(next.groups[1].rows[2].relatedPrice).toBe(88)
    expect(next.groups[1].rows[2].comparablePrices[0]).toBe(80)
  })
})

describe('F2-65 询价 composable', () => {
  function setup(initial?: unknown) {
    const map = new Map<string, ChecklistResponse>()
    if (initial !== undefined) {
      map.set('F2-65-rows', { item_id: 'F2-65-rows', conclusion: null, remark: JSON.stringify(initial) })
    }
    const allResponses = ref(map)
    return { inquiry: useF2RelatedPartyInquiry({ allResponses, isReadonly: ref(false) }), allResponses }
  }

  it('旧结构自动迁移并写回分组对象', () => {
    const { inquiry, allResponses } = setup([
      { relatedParty: 'A', itemName: '甲', relatedPrice: 120, inquiryPrice: 100 },
    ])
    expect(inquiry.groups.value[0].relatedParty).toBe('A')
    const saved = JSON.parse(allResponses.value.get('F2-65-rows')!.remark!)
    expect(saved.groups).toHaveLength(1)
  })

  it('新增分组及逐月报价更新实时生效且不被自回声裁剪', () => {
    const { inquiry } = setup()
    inquiry.addGroup()
    expect(inquiry.sheet.value.groups).toHaveLength(2)
    const group = inquiry.sheet.value.groups[0]
    const row = group.rows[0]
    inquiry.updateGroup(group.id, { relatedParty: 'A', productName: '产品甲' })
    inquiry.updateRow(group.id, row.id, { relatedPrice: 120 })
    inquiry.updateComparablePrice(group.id, row.id, 0, 100)
    expect(inquiry.groups.value[0].rows[0].spreadRate).toBeCloseTo(0.2)
    expect(inquiry.abnormalCount.value).toBe(1)
  })
})
