import { describe, it, expect } from 'vitest'
import { normalizeH3Category, inferH3CategoryFromAdjustment, isStandardH3Category } from '../h3CategoryMap'
import {
  aggregateH32CostByCategory,
  allocateTransferByWeight,
  previewCostFillDiff,
} from '../h3FillFromDetail'
import { applyAdjToRows, buildCategoryBuckets } from '../useH3Adjustment'

describe('h3CategoryMap', () => {
  it('归一化房屋/土地/其他', () => {
    expect(normalizeH3Category('厂房')).toBe('房屋及建筑物')
    expect(normalizeH3Category('土地使用权')).toBe('土地使用权')
    expect(normalizeH3Category('地块A')).toBe('土地使用权')
    expect(normalizeH3Category('设备')).toBe('其他')
    expect(normalizeH3Category('')).toBe('其他')
  })

  it('isStandardH3Category 仅认标准三类', () => {
    expect(isStandardH3Category('房屋及建筑物')).toBe(true)
    expect(isStandardH3Category('厂房')).toBe(false)
  })

  it('从调整分录推断分类', () => {
    expect(inferH3CategoryFromAdjustment({ summary: '调整写字楼原值' })).toBe('房屋及建筑物')
    expect(inferH3CategoryFromAdjustment({ category: '土地使用权' })).toBe('土地使用权')
  })
})

describe('aggregateH32CostByCategory', () => {
  it('按类别汇总原值/折旧/减值', () => {
    const { map, unmatchedCount } = aggregateH32CostByCategory([
      {
        assetType: '房屋及建筑物',
        costBegin: 100, costIncrease: 20, costDecrease: 0, transferIn: 0, transferOut: 0, costEnd: 120,
        accDepBegin: 10, depProvision: 5, depReversal: 0, accDepEnd: 15,
        impairmentBegin: 0, impairmentProvision: 2, impairmentReversal: 0, impairmentEnd: 2,
      },
      {
        assetType: '土地使用权',
        costBegin: 50, costIncrease: 0, costDecrease: 0, transferIn: 10, transferOut: 0, costEnd: 60,
        accDepBegin: 0, depProvision: 0, depReversal: 0, accDepEnd: 0,
        impairmentBegin: 0, impairmentProvision: 0, impairmentReversal: 0, impairmentEnd: 0,
      },
      {
        assetType: '厂房', // 非标准 → 房屋及建筑物，计未匹配
        costBegin: 0, costIncrease: 0, costDecrease: 0, transferIn: 0, transferOut: 0, costEnd: 30,
        accDepBegin: 0, depProvision: 0, depReversal: 0, accDepEnd: 0,
        impairmentBegin: 0, impairmentProvision: 0, impairmentReversal: 0, impairmentEnd: 0,
      },
    ])
    expect(map['房屋及建筑物'].end).toBe(150)
    expect(map['土地使用权'].end).toBe(60)
    expect(map['房屋及建筑物'].depEnd).toBe(15)
    expect(map['房屋及建筑物'].impEnd).toBe(2)
    expect(unmatchedCount).toBe(1)
  })
})

describe('applyAdjToRows / buildCategoryBuckets', () => {
  it('按分类写入 AJE/RJE，孤儿并入其他', () => {
    const rows = [
      { category: '房屋及建筑物', unadjusted: 100, aje: 0, rje: 0 },
      { category: '其他', unadjusted: 10, aje: 0, rje: 0 },
    ]
    const next = applyAdjToRows(
      rows,
      { '房屋及建筑物': 5, '土地使用权': 3, '其他': 1 },
      { '房屋及建筑物': 0, '土地使用权': 2, '其他': 0 },
    )
    expect(next[0].aje).toBe(5)
    expect(next[0].audited).toBe(105)
    // 土地使用权无行 → 并入其他
    expect(next[1].aje).toBe(1 + 3)
    expect(next[1].rje).toBe(2)
  })

  it('1503/1504/1505 分桶', () => {
    const b = buildCategoryBuckets([
      {
        rowId: '1', seq: 1, description: '', entryType: 'AJE', category: '房屋及建筑物',
        accountCode: '1503', accountName: '投资性房地产', summary: '', debitAmount: 100, creditAmount: 0, indexRef: '', remark: '',
      },
      {
        rowId: '2', seq: 2, description: '', entryType: 'AJE', category: '房屋及建筑物',
        accountCode: '1504', accountName: '累计折旧', summary: '', debitAmount: 0, creditAmount: 20, indexRef: '', remark: '',
      },
      {
        rowId: '3', seq: 3, description: '', entryType: 'RJE', category: '土地使用权',
        accountCode: '1505', accountName: '减值准备', summary: '', debitAmount: 8, creditAmount: 0, indexRef: '', remark: '',
      },
    ])
    expect(b.aje1503['房屋及建筑物']).toBe(100)
    expect(b.aje1504['房屋及建筑物']).toBe(-20)
    expect(b.rje1505['土地使用权']).toBe(8)
  })
})

describe('fill preview / transfer allocate', () => {
  it('book 模式预览不改 AJE', () => {
    const map = aggregateH32CostByCategory([{
      assetType: '房屋及建筑物',
      costBegin: 100, costIncrease: 0, costDecrease: 0, transferIn: 0, transferOut: 0, costEnd: 100,
      costAje: 9, costRje: 0,
      accDepBegin: 0, depProvision: 0, depReversal: 0, accDepEnd: 0,
      impairmentBegin: 0, impairmentProvision: 0, impairmentReversal: 0, impairmentEnd: 0,
    }]).map
    const diffs = previewCostFillDiff({
      originalRows: [{ category: '房屋及建筑物', beginBalance: 80, increase: 0, decrease: 0, transfer: 0, endBalance: 80, unadjusted: 80, aje: 1, rje: 0, audited: 81 }],
      depRows: [{ category: '房屋及建筑物', beginBalance: 0, provision: 0, reversal: 0, endBalance: 0, unadjusted: 0, aje: 0, rje: 0, audited: 0 }],
      impairRows: [{ category: '房屋及建筑物', beginBalance: 0, provision: 0, reversal: 0, endBalance: 0, unadjusted: 0, aje: 0, rje: 0, audited: 0 }],
      map,
      mode: 'book',
    })
    expect(diffs.some((d) => d.field === 'AJE')).toBe(false)
    expect(diffs.some((d) => d.field === '期初' && d.after === 100)).toBe(true)
  })

  it('转换按权重分摊，合计等于净额', () => {
    const alloc = allocateTransferByWeight([
      { category: '房屋及建筑物', weight: 70 },
      { category: '土地使用权', weight: 30 },
      { category: '其他', weight: 0 },
    ], 100)
    const sum = alloc['房屋及建筑物'] + alloc['土地使用权'] + alloc['其他']
    expect(sum).toBeCloseTo(100, 2)
  })
})
