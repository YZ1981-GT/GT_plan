/**
 * G3 应收股利披露 — 章节映射 / 同步 payload 契约测试
 */
import { describe, it, expect } from 'vitest'
import {
  G3_COMBINED_DISCLOSURE_INDEX,
  G3_DISCLOSURE_SHEET_NAME,
  G3_NOTE_SECTION,
  isG3DisclosureApplicable,
  resolveG3NoteSectionTarget,
} from '../g3NoteSectionMap'
import {
  buildG3ListedSyncPayloads,
  buildG3SoeSyncPayloads,
  buildG3ListedSubTableData,
} from '../g3DisclosureSyncPayload'

describe('g3NoteSectionMap', () => {
  it('上市映射五、8，合计数 M1-1→K1-1', () => {
    expect(G3_NOTE_SECTION.listed).toBe('五、8')
    expect(G3_COMBINED_DISCLOSURE_INDEX.excelLegacy).toBe('M1-1')
    expect(G3_COMBINED_DISCLOSURE_INDEX.wpCode).toBe('K1-1')
    const t = resolveG3NoteSectionTarget('listed', ['listed_standalone'])
    expect(t?.sectionId).toBe('五、8')
    // sheetName = 源 xlsx 真实 tab 名（非 `G3-note-listed` 合成标识）
    expect(t?.sheetName).toBe(G3_DISCLOSURE_SHEET_NAME.listed)
    expect(t?.combinedWpChip).toBe('wp:K1-1')
  })

  it('国企映射八、9', () => {
    const t = resolveG3NoteSectionTarget('soe', ['soe_standalone'])
    expect(t?.sectionId).toBe('八、9')
    expect(t?.sheetName).toBe(G3_DISCLOSURE_SHEET_NAME.soe)
  })

  it('准则互斥', () => {
    expect(isG3DisclosureApplicable('listed', ['soe_standalone'])).toBe(false)
    expect(isG3DisclosureApplicable('soe', ['listed_standalone'])).toBe(false)
  })
})

describe('g3AdjudicationItems disclosure seed', () => {
  it('buildListedDisclosureFromAdj 映射期初/宣告/收回', async () => {
    const { buildListedDisclosureFromAdj, buildSoeDisclosureFromAdj, isG3DisclosurePlaceholder } =
      await import('../g3AdjudicationItems')
    const store = [{
      id: 'a1',
      investeeName: '甲公司',
      shareholdingRatio: 10,
      openingUnadjusted: 100,
      openingAJE: 10,
      openingRJE: 0,
      currentDeclared: 50,
      currentReceived: 20,
      closingAJE: 0,
      closingRJE: 0,
      remark: '',
      indexRef: '',
    }]
    const listed = buildListedDisclosureFromAdj(store)
    expect(listed).toHaveLength(1)
    expect(listed[0].openingBalance).toBe(110)
    expect(listed[0].currentIncrease).toBe(50)
    expect(listed[0].currentDecrease).toBe(20)
    const soe = buildSoeDisclosureFromAdj(store)
    expect(soe[0].currentChange).toBe(30)
    expect(isG3DisclosurePlaceholder([{ investeeName: '', openingBalance: 0 }])).toBe(true)
    expect(isG3DisclosurePlaceholder(listed)).toBe(false)
  })
})

describe('g3DisclosureSyncPayload', () => {
  it('上市同步 payload 含应收股利子表', () => {
    const payloads = buildG3ListedSyncPayloads(
      'wp-g3',
      ['listed_standalone'],
      [
        { investeeName: '甲公司', openingBalance: 100, currentIncrease: 20, currentDecrease: 10, remark: '' },
      ],
      '说明',
    )
    expect(payloads).toHaveLength(1)
    expect(payloads[0].section_id).toBe('五、8')
    expect(payloads[0].sheet_name).toBe(G3_DISCLOSURE_SHEET_NAME.listed)
    const sub = payloads[0].sub_table_data['应收股利']
    expect(sub?.some((r) => r.label === '甲公司' && r.end_balance === 110)).toBe(true)
    expect(sub?.some((r) => r.is_total && r.end_balance === 110)).toBe(true)
  })

  it('国企同步 payload', () => {
    const payloads = buildG3SoeSyncPayloads(
      'wp-g3',
      ['soe_standalone'],
      [{ investeeName: '乙公司', openingBalance: 50, currentChange: 5 }],
      '',
    )
    expect(payloads[0].section_id).toBe('八、9')
    expect(payloads[0].sub_table_data['应收股利']?.[0]).toMatchObject({
      label: '乙公司',
      end_balance: 55,
    })
  })

  it('空准则默认允许同步', () => {
    const sub = buildG3ListedSubTableData([], '')
    expect(sub['应收股利']?.some((r) => r.is_total)).toBe(true)
    const payloads = buildG3ListedSyncPayloads('wp', [], [], '')
    expect(payloads).toHaveLength(1)
  })
})
