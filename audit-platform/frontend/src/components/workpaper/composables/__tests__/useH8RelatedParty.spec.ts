/**
 * useH8RelatedParty — 公式 / 迁移 / 带入 / 配对 单元测试
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  calcRouNetValue,
  calcPriceDiffRate,
  suggestIsAbnormal,
  emptyRouRow,
  emptyLiabRow,
  recalcRouRow,
  recalcLiabRow,
  useH8RelatedParty,
} from '../useH8RelatedParty'

describe('calcRouNetValue / calcPriceDiffRate', () => {
  it('净值 = 原值 − 累计折旧 − 减值', () => {
    expect(calcRouNetValue(1000, 300, 50)).toBe(650)
    expect(calcRouNetValue(0, 0, 0)).toBe(0)
  })

  it('价差率 = (年租金 − 市场租金) / 市场租金 × 100%', () => {
    expect(calcPriceDiffRate(110, 100)).toBeCloseTo(10)
    expect(calcPriceDiffRate(90, 100)).toBeCloseTo(-10)
    expect(calcPriceDiffRate(100, 0)).toBe(0)
  })

  it('suggestIsAbnormal 按阈值建议', () => {
    expect(suggestIsAbnormal(12, 100)).toBe('是')
    expect(suggestIsAbnormal(7, 100)).toBe('待核实')
    expect(suggestIsAbnormal(2, 100)).toBe('否')
    expect(suggestIsAbnormal(50, 0)).toBe('')
  })
})

describe('recalcRouRow / recalcLiabRow', () => {
  it('重算使用权资产净值与价差率', () => {
    const row = emptyRouRow(1)
    row.costEnding = 1000
    row.accumDepEnding = 200
    row.impairmentEnding = 50
    row.annualRent = 120
    row.marketRent = 100
    recalcRouRow(row)
    expect(row.netValue).toBe(750)
    expect(row.priceDiffRate).toBeCloseTo(20)
  })

  it('重算租赁负债价差率', () => {
    const row = emptyLiabRow(1)
    row.annualRent = 80
    row.marketRent = 100
    recalcLiabRow(row)
    expect(row.priceDiffRate).toBeCloseTo(-20)
  })
})

describe('useH8RelatedParty', () => {
  function makeMap(entries: Record<string, any> = {}) {
    const m = new Map<string, any>()
    for (const [k, v] of Object.entries(entries)) {
      m.set(k, {
        item_id: k,
        conclusion: null,
        remark: typeof v === 'string' ? v : JSON.stringify(v),
      })
    }
    return ref(m)
  }

  it('兼容旧版单表字段迁移', () => {
    const allResponses = makeMap({
      'H8-14-rows': [
        {
          contractNo: 'L-001',
          relatedParty: '甲母公司',
          relationship: '母公司',
          assetName: '办公楼',
          relatedRental: 110,
          marketRental: 100,
          fairnessAssessment: '存在异常',
        },
      ],
    })
    const saved: Array<{ id: string; value: any }> = []
    const c = useH8RelatedParty({
      allResponses,
      onSave: (id, value) => saved.push({ id, value }),
    })
    expect(c.rouRows.value).toHaveLength(1)
    const row = c.rouRows.value[0]
    expect(row.relatedPartyName).toBe('甲母公司')
    expect(row.leaseItem).toBe('办公楼')
    expect(row.indexNo).toBe('L-001')
    expect(row.annualRent).toBe(110)
    expect(row.marketRent).toBe(100)
    expect(row.priceDiffRate).toBeCloseTo(10)
    expect(row.isAbnormal).toBe('是')
  })

  it('配对负债行复制关联方信息', () => {
    const allResponses = makeMap()
    const c = useH8RelatedParty({ allResponses, onSave: () => {} })
    const rou = c.addRouRow()
    c.updateRouCell(rou.rowId, 'relatedPartyName', '乙联营')
    c.updateRouCell(rou.rowId, 'relationship', '联营企业')
    c.updateRouCell(rou.rowId, 'leaseItem', '厂房')
    c.updateRouCell(rou.rowId, 'annualRent', 200)
    c.updateRouCell(rou.rowId, 'marketRent', 200)

    const liab = c.pairLiabilityFromRou(rou.rowId)
    expect(liab).not.toBeNull()
    expect(c.liabRows.value).toHaveLength(1)
    expect(liab!.relatedPartyName).toBe('乙联营')
    expect(liab!.leaseItem).toBe('厂房')
    expect(liab!.pairedRouRowId).toBe(rou.rowId)

    // 再次配对不重复
    expect(c.pairLiabilityFromRou(rou.rowId)?.rowId).toBe(liab!.rowId)
    expect(c.liabRows.value).toHaveLength(1)
  })

  it('从 H8-2 带入并去重', () => {
    const allResponses = makeMap({
      'H8-2-rows': [
        {
          rowId: 'd1',
          contractNo: 'C-1',
          assetName: '车辆',
          lessor: '丙公司',
          startDate: '2024-01-01',
          endDate: '2026-12-31',
          leaseType: '运输工具',
          initialAmount: 500000,
          accDepEnd: 100000,
          depCurrentPeriod: 50000,
        },
        {
          rowId: 'd2',
          contractNo: 'C-2',
          assetName: '设备',
          lessor: '丁公司',
          initialAmount: 200000,
          accDepEnd: 0,
          depCurrentPeriod: 0,
        },
      ],
    })
    const c = useH8RelatedParty({ allResponses, onSave: () => {} })
    const r1 = c.importFromH82()
    expect(r1.added).toBe(2)
    expect(c.rouRows.value[0].relatedPartyName).toBe('丙公司')
    expect(c.rouRows.value[0].leasePeriod).toContain('2024-01-01')
    expect(c.rouRows.value[0].netValue).toBe(400000)

    const r2 = c.importFromH82()
    expect(r2.added).toBe(0)
    expect(r2.skipped).toBe(2)
  })

  it('summary 汇总异常与价差', () => {
    const allResponses = makeMap()
    const c = useH8RelatedParty({ allResponses, onSave: () => {} })
    const rou = c.addRouRow()
    c.updateRouCell(rou.rowId, 'costEnding', 100)
    c.updateRouCell(rou.rowId, 'annualRent', 130)
    c.updateRouCell(rou.rowId, 'marketRent', 100)
    // marketRent 变更会自动建议 isAbnormal=是
    expect(c.summary.value.rouCount).toBe(1)
    expect(c.summary.value.highDiffCount).toBe(1)
    expect(c.summary.value.abnormalCount).toBeGreaterThanOrEqual(1)
    expect(c.summary.value.rouNetTotal).toBe(100)
  })

  it('draftAuditNote 含识别范围与公允性段落', () => {
    const allResponses = makeMap()
    const c = useH8RelatedParty({ allResponses, onSave: () => {} })
    const rou = c.addRouRow()
    c.updateRouCell(rou.rowId, 'relatedPartyName', '测试方')
    c.updateRouCell(rou.rowId, 'annualRent', 150)
    c.updateRouCell(rou.rowId, 'marketRent', 100)
    const note = c.draftAuditNote()
    expect(note).toContain('关联方租赁识别')
    expect(note).toContain('定价公允性核查')
    expect(note).toContain('测试方')
  })
})
