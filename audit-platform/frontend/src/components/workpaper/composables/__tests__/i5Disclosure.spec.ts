/**
 * I5 附注披露模型 / 同步载荷 单测
 */
import { describe, it, expect } from 'vitest'
import {
  calcI5EndBookValue,
  calcI5PriorBookValue,
  aggregateI5DetailForDisclosure,
  summarizeI5Disclosure,
  normalizeI5DisclosureRow,
  resolveI5DisclosureLabel,
} from '../i5DisclosureModel'
import {
  buildI5ListedSubTableData,
  buildI5SoeSubTableData,
  buildI5ListedSyncPayloads,
  buildI5SoeSyncPayloads,
} from '../i5DisclosureSyncPayload'
import { I5_NOTE_SECTION, isI5DisclosureApplicable, isI5OtherNoncurrentNoteSection } from '../i5NoteSectionMap'

describe('i5DisclosureModel', () => {
  it('账面价值 = 账面余额 − 减值准备', () => {
    expect(calcI5EndBookValue({ endGross: 100, endImpairment: 15 })).toBe(85)
    expect(calcI5PriorBookValue({ priorGross: 80, priorImpairment: 5 })).toBe(75)
  })

  it('按分类聚合明细（含净值→减值）', () => {
    const rows = aggregateI5DetailForDisclosure([
      { name: '预付工程款A', category: '预付工程款', endBalance: 100, netValue: 90, beginBalance: 50 },
      { name: '预付工程款B', category: '预付工程款', endBalance: 40, netValue: 40, beginBalance: 10 },
      { name: '合同资产-XX', category: '合同资产', endBalance: 20, beginBalance: 5 },
    ])
    const eng = rows.find((r) => r.item === '预付工程款')
    expect(eng?.endGross).toBe(140)
    expect(eng?.endImpairment).toBe(10)
    expect(eng?.endBookValue).toBe(130)
    expect(eng?.priorBookValue).toBe(60)
    expect(rows.some((r) => r.item === '合同资产')).toBe(true)
  })

  it('旧变动矩阵行可迁移', () => {
    const row = normalizeI5DisclosureRow({
      item: '预付土地出让金',
      beginBalance: 10,
      increase: 5,
      decrease: 2,
      endBalance: 13,
    })
    expect(row.endBookValue).toBe(13)
    expect(row.priorBookValue).toBe(10)
    expect(row.endImpairment).toBe(0)
  })

  it('resolve 标签：别名映射', () => {
    expect(resolveI5DisclosureLabel({ name: '预付土地出让金款', category: '' })).toBe('预付土地出让金')
    expect(resolveI5DisclosureLabel({ category: '合同履约成本' })).toBe('合同履约成本')
  })
})

describe('i5DisclosureSyncPayload', () => {
  it('上市子表：期末/上年年末=账面价值，含合计行', () => {
    const data = buildI5ListedSubTableData({
      rows: [{
        rowId: '1',
        item: '预付工程款',
        endGross: 100,
        endImpairment: 10,
        endBookValue: 90,
        priorGross: 50,
        priorImpairment: 0,
        priorBookValue: 50,
        isAutoFilled: true,
        remark: '',
      }],
    })
    const main = data['其他非流动资产']
    expect(main).toHaveLength(2)
    expect(main[0].end_carrying).toBe(90)
    expect(main[0].prior_carrying).toBe(50)
    expect(main[1].label).toBe('合计')
    expect(main[1].is_total).toBe(true)
  })

  it('国企子表：期末/年初余额', () => {
    const data = buildI5SoeSubTableData({
      rows: [{
        rowId: '1',
        item: '合同资产',
        endGross: 30,
        endImpairment: 0,
        endBookValue: 30,
        priorGross: 12,
        priorImpairment: 0,
        priorBookValue: 12,
        isAutoFilled: false,
        remark: '',
      }],
    })
    const main = data['其他非流动资产']
    expect(main[0].期末余额).toBe(30)
    expect(main[0].年初余额).toBe(12)
  })

  it('同步载荷章节：上市五、31 / 国企八、32', () => {
    const listed = buildI5ListedSyncPayloads('wp', ['listed_standalone'], { rows: [] })
    expect(listed[0].section_id).toBe(I5_NOTE_SECTION.listed)
    const soe = buildI5SoeSyncPayloads('wp', ['soe_standalone'], { rows: [] })
    expect(soe[0].section_id).toBe(I5_NOTE_SECTION.soe)
  })

  it('准则过滤：仅上市准则时国企不同步', () => {
    expect(isI5DisclosureApplicable('soe', ['listed_standalone'])).toBe(false)
    expect(buildI5SoeSyncPayloads('wp', ['listed_standalone'], { rows: [] })).toHaveLength(0)
  })

  it('合计汇总', () => {
    const t = summarizeI5Disclosure([
      {
        rowId: 'a', item: 'A', endGross: 10, endImpairment: 1, endBookValue: 9,
        priorGross: 5, priorImpairment: 0, priorBookValue: 5, isAutoFilled: false, remark: '',
      },
      {
        rowId: 'b', item: 'B', endGross: 20, endImpairment: 2, endBookValue: 18,
        priorGross: 8, priorImpairment: 1, priorBookValue: 7, isAutoFilled: false, remark: '',
      },
    ])
    expect(t.endBookValue).toBe(27)
    expect(t.priorBookValue).toBe(12)
  })

  it('章节识别', () => {
    expect(isI5OtherNoncurrentNoteSection('五、31')).toBe(true)
    expect(isI5OtherNoncurrentNoteSection('八、32 其他非流动资产')).toBe(true)
    expect(isI5OtherNoncurrentNoteSection('五、29')).toBe(false)
  })
})
