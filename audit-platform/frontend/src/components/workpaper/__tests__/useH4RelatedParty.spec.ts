/**
 * useH4RelatedParty — 公式 / 迁移 / 带入 单元测试
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import {
  recalcRelatedPartyRow,
  emptyRelatedPartyRow,
  needsEntryDiffRemark,
  isMarkedRelatedParty,
  applyH44SourceToRow,
  applyH45SourceToRow,
  useH4RelatedParty,
} from '../composables/useH4RelatedParty'

describe('recalcRelatedPartyRow', () => {
  it('购入：入账差异 = 入账价值 − 购买价款', () => {
    const row = emptyRelatedPartyRow(1, '购入')
    row.transAmount = 100
    row.bookValue = 108
    row.appraisedValue = 100
    recalcRelatedPartyRow(row)
    expect(row.entryDiff).toBe(8)
    expect(row.priceDiffRate).toBe(0)
    expect(row.netValue).toBe(0)
  })

  it('出售：净值 = 原值 − 减值；处置损益 = 售价 − 净值', () => {
    const row = emptyRelatedPartyRow(1, '出售')
    row.originalCost = 200
    row.impairment = 20
    row.transAmount = 150
    row.appraisedValue = 160
    recalcRelatedPartyRow(row)
    expect(row.netValue).toBe(180)
    expect(row.disposalGain).toBe(-30)
    expect(row.priceDiffRate).toBeCloseTo((150 - 160) / 160 * 100, 5)
  })

  it('占同类% 按 categoryTotal 计算', () => {
    const row = emptyRelatedPartyRow(1, '购入')
    row.transAmount = 25
    row.categoryTotal = 100
    recalcRelatedPartyRow(row)
    expect(row.similarRatio).toBe(25)
  })
})

describe('needsEntryDiffRemark', () => {
  it('超阈且无备注时需要备注', () => {
    const row = emptyRelatedPartyRow(1, '购入')
    row.transAmount = 100
    row.bookValue = 120
    recalcRelatedPartyRow(row)
    expect(needsEntryDiffRemark(row, 10)).toBe(true)
    row.remark = '运杂费'
    expect(needsEntryDiffRemark(row, 10)).toBe(false)
  })
})

describe('isMarkedRelatedParty / apply source', () => {
  it('识别关联方标记', () => {
    expect(isMarkedRelatedParty({ isRelatedParty: '是' })).toBe(true)
    expect(isMarkedRelatedParty({ relatedPartyName: '甲公司' })).toBe(true)
    expect(isMarkedRelatedParty({ isRelatedParty: '否' })).toBe(false)
  })

  it('H4-4 带入为购入', () => {
    const row = emptyRelatedPartyRow(1, '出售')
    applyH44SourceToRow(row, {
      rowId: 'a1',
      name: '钢材',
      amount: 5000,
      supplier: '乙供应商',
      relatedPartyName: '乙关联方',
      relationship: '联营企业',
      inboundDate: '2025-06-01',
      contractNo: 'C-1',
      refIndex: 'H4-4-1',
    })
    expect(row.transType).toBe('购入')
    expect(row.counterparty).toBe('乙关联方')
    expect(row.transAmount).toBe(5000)
    expect(row.sourceWp).toBe('H4-4')
  })

  it('H4-5 带入为出售', () => {
    const row = emptyRelatedPartyRow(1, '购入')
    applyH45SourceToRow(row, {
      rowId: 'd1',
      name: '电缆',
      amount: 3000,
      relatedPartyName: '丙公司',
      relationship: '合营企业',
      disposalDate: '2025-07-01',
      reason: '退货',
    })
    expect(row.transType).toBe('出售')
    expect(row.originalCost).toBe(3000)
    expect(row.sourceWp).toBe('H4-5')
  })
})

describe('useH4RelatedParty', () => {
  it('旧版单表数据迁移为购入行，并支持无交易标记', () => {
    const map = new Map<string, any>()
    map.set('H4-9-rows', {
      item_id: 'H4-9-rows',
      remark: JSON.stringify([{
        name: '旧物资',
        counterparty: '旧对手',
        transAmount: 1000,
        marketPrice: 900,
        pricingBasis: '市场价',
        isFair: '否',
      }]),
    })
    const saved: Record<string, any> = {}
    const c = useH4RelatedParty({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: ref(map),
      isReadonly: ref(false),
      onSave: (id, val) => { saved[id] = val },
    })
    expect(c.rows.value).toHaveLength(1)
    expect(c.rows.value[0].transType).toBe('购入')
    expect(c.rows.value[0].appraisedValue).toBe(900)
    expect(c.rows.value[0].hasAnomaly).toBe('是')

    c.applyNoTransaction()
    expect(c.rows.value).toHaveLength(0)
    expect(c.settings.value.noTransaction).toBe(true)
    expect(saved['H4-9-note']).toContain('未发生')
  })

  it('从 H4-4 带入已标记关联方行', () => {
    const map = new Map<string, any>()
    map.set('H4-4-rows', {
      item_id: 'H4-4-rows',
      remark: JSON.stringify([{
        rowId: 'r1',
        name: '水泥',
        amount: 800,
        isRelatedParty: '是',
        relatedPartyName: '丁公司',
        relationship: '其他关联方',
        inboundDate: '2025-01-01',
      }]),
    })
    const c = useH4RelatedParty({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: ref(map),
      isReadonly: ref(false),
      onSave: vi.fn(),
    })
    const result = c.importFromH4H5()
    expect(result.added).toBe(1)
    expect(c.purchaseRows.value).toHaveLength(1)
    expect(c.purchaseRows.value[0].counterparty).toBe('丁公司')
  })
})
