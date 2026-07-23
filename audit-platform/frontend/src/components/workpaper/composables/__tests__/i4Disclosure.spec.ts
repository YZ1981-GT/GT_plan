/**
 * I4 附注披露模型 / 同步载荷 单测
 */
import { describe, it, expect } from 'vitest'
import {
  calcI4DisclosureEnd,
  aggregateI4DetailForDisclosure,
  calcI4CurrentPortion,
  summarizeI4Disclosure,
  resolveI4DisclosureLabel,
} from '../i4DisclosureModel'
import {
  buildI4ListedSubTableData,
  buildI4SoeSubTableData,
  buildI4ListedSyncPayloads,
  buildI4SoeSyncPayloads,
  buildI4ListedFootnote,
} from '../i4DisclosureSyncPayload'
import { I4_NOTE_SECTION, isI4DisclosureApplicable } from '../i4NoteSectionMap'

describe('i4DisclosureModel', () => {
  it('期末 = 期初 + 增加 − 摊销 − 其他减少', () => {
    expect(calcI4DisclosureEnd({
      beginBalance: 100,
      increase: 40,
      amortization: 30,
      otherDecrease: 10,
    })).toBe(100)
  })

  it('按费用类型/资产类型聚合明细', () => {
    const rows = aggregateI4DetailForDisclosure([
      {
        expenseType: '',
        assetType: '租入固定资产改良',
        auditedOpening: 100,
        auditedIncrease: 20,
        auditedAmortization: 15,
        auditedOtherDecrease: 0,
      },
      {
        expenseType: '开办费',
        auditedOpening: 50,
        auditedIncrease: 0,
        auditedAmortization: 10,
        auditedOtherDecrease: 5,
      },
    ])
    expect(rows).toHaveLength(2)
    const lease = rows.find((r) => r.item.includes('使用权') || r.item.includes('改良'))
    expect(lease?.endBalance).toBe(105)
    const kai = rows.find((r) => r.item === '开办费')
    expect(kai?.endBalance).toBe(35)
  })

  it('一年内到期：剩余月数≤12 的期末合计', () => {
    expect(calcI4CurrentPortion([
      { remainingMonths: 6, auditedEnding: 12 },
      { remainingMonths: 24, auditedEnding: 100 },
      { remainingMonths: 0, auditedEnding: 5 },
    ])).toBe(12)
  })

  it('resolve 标签：租入改良 → 使用权资产改良及维护支出', () => {
    expect(resolveI4DisclosureLabel({ assetType: '租入固定资产改良' })).toBe('使用权资产改良及维护支出')
  })
})

describe('i4DisclosureSyncPayload', () => {
  it('上市子表：本期减少 = 摊销 + 其他减少，含合计行', () => {
    const data = buildI4ListedSubTableData({
      rows: [{
        rowId: '1',
        item: '使用权资产改良及维护支出',
        beginBalance: 100,
        increase: 20,
        amortization: 15,
        otherDecrease: 5,
        endBalance: 100,
        otherDecreaseReason: '',
        isAutoFilled: true,
        remark: '',
      }],
      currentPortion: 8,
    })
    const mov = data['长期待摊费用']
    expect(mov).toHaveLength(2)
    expect(mov[0].本期减少).toBe(20)
    expect(mov[1].label).toBe('合计')
    expect(mov[1].is_total).toBe(true)
  })

  it('国企子表：摊销/其他减少分列 + 原因', () => {
    const data = buildI4SoeSubTableData({
      rows: [{
        rowId: '1',
        item: '使用权资产改良及维护支出',
        beginBalance: 100,
        increase: 0,
        amortization: 10,
        otherDecrease: 20,
        endBalance: 70,
        otherDecreaseReason: '转销',
        isAutoFilled: false,
        remark: '',
      }],
    })
    const mov = data['长期待摊费用']
    expect(mov[0].本期摊销额).toBe(10)
    expect(mov[0].其他减少额).toBe(20)
    expect(mov[0].其他减少的原因).toBe('转销')
  })

  it('同步载荷章节：上市五、29 / 国企八、30', () => {
    const listed = buildI4ListedSyncPayloads('wp', ['listed_standalone'], { rows: [] })
    expect(listed[0].section_id).toBe(I4_NOTE_SECTION.listed)
    const soe = buildI4SoeSyncPayloads('wp', ['soe_standalone'], { rows: [] })
    expect(soe[0].section_id).toBe(I4_NOTE_SECTION.soe)
  })

  it('准则过滤：仅上市准则时国企不同步', () => {
    expect(isI4DisclosureApplicable('soe', ['listed_standalone'])).toBe(false)
    expect(buildI4SoeSyncPayloads('wp', ['listed_standalone'], { rows: [] })).toHaveLength(0)
  })

  it('脚注含一年内到期金额', () => {
    expect(buildI4ListedFootnote(1234.5)).toContain('1,234.50')
  })

  it('合计汇总', () => {
    const t = summarizeI4Disclosure([
      {
        rowId: 'a', item: 'A', beginBalance: 10, increase: 1, amortization: 2,
        otherDecrease: 0, endBalance: 9, otherDecreaseReason: '', isAutoFilled: false, remark: '',
      },
      {
        rowId: 'b', item: 'B', beginBalance: 20, increase: 0, amortization: 5,
        otherDecrease: 1, endBalance: 14, otherDecreaseReason: '', isAutoFilled: false, remark: '',
      },
    ])
    expect(t.beginBalance).toBe(30)
    expect(t.endBalance).toBe(23)
  })
})
