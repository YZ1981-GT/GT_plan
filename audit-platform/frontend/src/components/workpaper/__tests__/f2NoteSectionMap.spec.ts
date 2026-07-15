/**
 * f2NoteSectionMap + sync payload 单测
 */
import { describe, it, expect } from 'vitest'
import {
  F2_NOTE_SECTION,
  isF2DisclosureApplicable,
  resolveF2CurrentStandard,
  resolveF2NoteSectionTarget,
} from '../composables/f2NoteSectionMap'
import {
  buildF2ListedSubTableData,
  buildF2SoeSubTableData,
  buildF2SyncPayload,
} from '../composables/f2DisclosureSyncPayload'

describe('f2NoteSectionMap', () => {
  it('listed → 五、9 / soe → 八、10', () => {
    expect(F2_NOTE_SECTION.listed).toBe('五、9')
    expect(F2_NOTE_SECTION.soe).toBe('八、10')
  })

  it('空准则时两侧均适用', () => {
    expect(isF2DisclosureApplicable('listed', [])).toBe(true)
    expect(isF2DisclosureApplicable('soe', [])).toBe(true)
  })

  it('上市准则不适用国企页，反之亦然', () => {
    expect(isF2DisclosureApplicable('listed', ['listed_standalone'])).toBe(true)
    expect(isF2DisclosureApplicable('soe', ['listed_standalone'])).toBe(false)
    expect(isF2DisclosureApplicable('soe', ['soe_standalone'])).toBe(true)
    expect(isF2DisclosureApplicable('listed', ['soe_standalone'])).toBe(false)
  })

  it('resolveF2NoteSectionTarget 按变体分流且不交叉', () => {
    const listed = resolveF2NoteSectionTarget('listed', ['listed_standalone'])!
    const soe = resolveF2NoteSectionTarget('soe', ['soe_standalone'])!
    expect(listed.sectionId).toBe('五、9')
    expect(listed.chipValue).toBe('Note:五、9')
    expect(listed.sheetName).toBe('F2-note-listed')
    expect(soe.sectionId).toBe('八、10')
    expect(soe.chipValue).toBe('Note:八、10')
    expect(soe.sheetName).toBe('F2-note-soe')
    expect(listed.sectionId).not.toBe(soe.sectionId)
  })

  it('不适用时返回 null', () => {
    expect(resolveF2NoteSectionTarget('listed', ['soe_standalone'])).toBeNull()
    expect(resolveF2NoteSectionTarget('soe', ['listed_consolidated'])).toBeNull()
  })

  it('current_standard 解析 consolidated / standalone', () => {
    expect(resolveF2CurrentStandard('listed', [])).toBe('listed_standalone')
    expect(resolveF2CurrentStandard('listed', ['listed_consolidated'])).toBe('listed_consolidated')
    expect(resolveF2CurrentStandard('soe', ['soe_consolidated'])).toBe('soe_consolidated')
  })
})

describe('f2DisclosureSyncPayload', () => {
  const listedSnap = {
    section1Rows: [{
      rowKey: 'raw-materials',
      label: '原材料',
      endGross: 100,
      endImpairment: 10,
      endNet: 90,
      priorGross: 80,
      priorImpairment: 5,
      priorNet: 75,
    }],
    section1Total: {
      label: '合计',
      endGross: 100,
      endImpairment: 10,
      endNet: 90,
      priorGross: 80,
      priorImpairment: 5,
      priorNet: 75,
    },
    section2Rows: [{
      rowKey: 'raw-materials',
      label: '原材料',
      opening: 5,
      incProvision: 5,
      incOther: 0,
      decReversal: 0,
      decOther: 0,
      ending: 10,
    }],
    section2Total: {
      label: '合计',
      opening: 5,
      incProvision: 5,
      incOther: 0,
      decReversal: 0,
      decOther: 0,
      ending: 10,
    },
    section2QualRows: [{
      rowKey: 'raw-materials',
      label: '原材料',
      nrvBasis: '市价',
      reversalReason: '',
    }],
    s3EndRows: [],
    s3PriorRows: [],
    s4BorrowText: '借款资本化说明',
    s5Rows: [],
    s6Rows: [],
    s7Rows: [],
    noteCategory: '分类说明',
    noteNrv: 'NRV',
    noteProvision: '计提依据',
    noteRe: '房企说明',
  }

  it('上市 sub_table_data 含同名子表与 note texts', () => {
    const sub = buildF2ListedSubTableData(listedSnap)
    expect(sub['存货分类']).toHaveLength(2)
    expect(sub['存货分类'][0].label).toBe('原材料')
    expect(sub['存货分类'][0].end_gross).toBe(100)
    expect(sub['存货跌价准备及合同履约成本减值准备'][0].ending).toBe(10)
    expect(sub['_note_texts'].some((r) => r.section === 'listed-note-category')).toBe(true)
  })

  it('上市 sync payload 只指向 五、9', () => {
    const payload = buildF2SyncPayload(
      'listed',
      'wp-1',
      ['listed_standalone'],
      buildF2ListedSubTableData(listedSnap),
    )!
    expect(payload.section_id).toBe('五、9')
    expect(payload.sheet_name).toBe('F2-note-listed')
    expect(payload.current_standard).toBe('listed_standalone')
    expect(payload.wp_id).toBe('wp-1')
    expect(payload.section_id).not.toBe('八、10')
  })

  it('国企 sync payload 只指向 八、10', () => {
    const soeSnap = {
      section1Rows: [{
        rowKey: 'raw-combined',
        label: '原材料',
        kind: 'normal',
        endGross: 50,
        endImpairment: 0,
        endNet: 50,
        priorGross: 40,
        priorImpairment: 0,
        priorNet: 40,
      }],
      section1Total: {
        label: '合计',
        endGross: 50,
        endImpairment: 0,
        endNet: 50,
        priorGross: 40,
        priorImpairment: 0,
        priorNet: 40,
      },
      section2Rows: [{
        rowKey: 'raw-combined',
        label: '原材料',
        opening: 0,
        incProvision: 0,
        incOther: 0,
        decReversal: 0,
        decWriteOff: 0,
        decOther: 0,
        ending: 0,
      }],
      section2Total: {
        label: '合计',
        opening: 0,
        incProvision: 0,
        incOther: 0,
        decReversal: 0,
        decWriteOff: 0,
        decOther: 0,
        ending: 0,
      },
      noteCategory: '国企分类',
      s3BorrowText: '借款',
      s4AmortText: '摊销',
      noteText: '其他',
    }
    const payload = buildF2SyncPayload(
      'soe',
      'wp-2',
      ['soe_standalone'],
      buildF2SoeSubTableData(soeSnap),
    )!
    expect(payload.section_id).toBe('八、10')
    expect(payload.sheet_name).toBe('F2-note-soe')
    expect(payload.current_standard).toBe('soe_standalone')
    expect(payload.sub_table_data['存货分类'][0].end_gross).toBe(50)
    expect(payload.section_id).not.toBe('五、9')
  })

  it('不适用准则时 buildF2SyncPayload 返回 null', () => {
    expect(buildF2SyncPayload('listed', 'wp', ['soe_standalone'], {})).toBeNull()
    expect(buildF2SyncPayload('soe', 'wp', ['listed_standalone'], {})).toBeNull()
  })
})

describe('disclosure:note-text-updated 约定', () => {
  it('detail 含 wpCode/section/text', () => {
    const received: unknown[] = []
    const handler = (e: Event) => received.push((e as CustomEvent).detail)
    window.addEventListener('disclosure:note-text-updated', handler)
    window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
      detail: { wpCode: 'F2', section: 'soe-note-borrow', text: '借款说明' },
    }))
    window.removeEventListener('disclosure:note-text-updated', handler)
    expect(received).toEqual([{ wpCode: 'F2', section: 'soe-note-borrow', text: '借款说明' }])
  })
})
