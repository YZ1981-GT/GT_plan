import { describe, it, expect } from 'vitest'
import {
  buildD7SyncPayload,
  buildD7NoteTexts,
  resolveD7CurrentStandard,
  D7_NOTE_SECTION,
  D7_DISCLOSURE_SHEET_NAME,
  type D7DisclosureSnapshot,
} from '../d7NoteSectionMap'

const listedSnapshot = (): D7DisclosureSnapshot => ({
  mainRows: [
    { label: '预收货款', current: 100, prior: 80 },
    { label: '减：计入其他非流动负债的合同负债', current: 10, prior: 5 },
  ],
  mainTotal: { label: '合计', current: 90, prior: 75 },
  longTermRows: [{ label: 'XX客户', current: 30, prior: 0, reason: '项目未完工' }],
  longTermTotal: { label: '合计', current: 30, prior: 0 },
  changeRows: [{ label: '重大合同A', current: 50, prior: 20 }],
  notes: { 'D7-note-listed-text-1': '按性质说明', 'D7-note-listed-text-3': '' },
})

const soeSnapshot = (): D7DisclosureSnapshot => ({
  mainRows: [{ label: '预收账款', current: 200, prior: 150 }],
  mainTotal: { label: '合计', current: 200, prior: 150 },
  changeRows: [{ label: '变动项B', current: 60, prior: 40 }],
  notes: { 'D7-note-soe-text-1': 'SOE 说明' },
})

describe('d7NoteSectionMap', () => {
  it('章节号 + sheet 名（真实 tab 名，半角括号）', () => {
    expect(D7_NOTE_SECTION.listed).toBe('五、39')
    expect(D7_NOTE_SECTION.soe).toBe('八、39')
    expect(D7_DISCLOSURE_SHEET_NAME.listed).toBe('附注披露信息(上市公司)')
    expect(D7_DISCLOSURE_SHEET_NAME.soe).toBe('附注披露信息(国企)')
  })

  it('resolveD7CurrentStandard maps variant + applicable standards', () => {
    expect(resolveD7CurrentStandard('listed', null)).toBe('listed_standalone')
    expect(resolveD7CurrentStandard('listed', ['listed_consolidated'])).toBe('listed_consolidated')
    expect(resolveD7CurrentStandard('soe', ['soe_consolidated'])).toBe('soe_consolidated')
  })

  it('listed payload → 五、39 三表（合同负债 / 超1年 / 重大变动），子表键↔columns键一致', () => {
    const p = buildD7SyncPayload('listed', 'wp-1', null, listedSnapshot())
    expect(p.section_id).toBe('五、39')
    expect(p.sheet_name).toBe('附注披露信息(上市公司)')
    expect(p.current_standard).toBe('listed_standalone')
    expect(Object.keys(p.sub_table_data)).toEqual([
      '合同负债', '账龄超过1年的重要合同负债', '本期合同负债账面价值的重大变动', '_note_texts',
    ])
    // 🔴 各子表键 ↔ columns 键必须相同
    for (const k of ['合同负债', '账龄超过1年的重要合同负债', '本期合同负债账面价值的重大变动']) {
      expect(p.columns[k]).toBeDefined()
    }
    // 列头逐字取自模板
    expect(p.columns['合同负债'].map(c => c.label)).toEqual(['项目', '期末余额', '上年年末余额'])
    expect(p.columns['账龄超过1年的重要合同负债'].map(c => c.label)).toEqual(['项目', '期末余额', '未偿还或未结转的原因'])
    expect(p.columns['本期合同负债账面价值的重大变动'].map(c => c.label)).toEqual(['项目', '变动金额', '变动原因'])
    // 主表：current→期末 / prior→上年年末，合计标 is_total
    const mainRows = p.sub_table_data['合同负债'] as any[]
    expect(mainRows[0]).toEqual({ label: '预收货款', end_amount: 100, prior_amount: 80 })
    expect(mainRows[mainRows.length - 1]).toMatchObject({ label: '合计', end_amount: 90, prior_amount: 75, is_total: true })
    // 重大变动：变动金额 = 期末 − 期初
    const changeRows = p.sub_table_data['本期合同负债账面价值的重大变动'] as any[]
    expect(changeRows[0]).toEqual({ label: '重大合同A', change_amount: 30, reason: '' })
    expect(changeRows[1]).toMatchObject({ label: '合计', change_amount: 30, is_total: true })
  })

  it('soe payload → 八、39 两表（合同负债 / 表2重大变动），无超1年表', () => {
    const p = buildD7SyncPayload('soe', 'wp-2', ['soe_standalone'], soeSnapshot())
    expect(p.section_id).toBe('八、39')
    expect(p.sheet_name).toBe('附注披露信息(国企)')
    expect(Object.keys(p.sub_table_data)).toEqual(['合同负债', '合同负债（表2）', '_note_texts'])
    expect(p.columns['合同负债'].map(c => c.label)).toEqual(['项目', '期末余额', '期初余额'])
    expect(p.columns['合同负债（表2）'].map(c => c.label)).toEqual(['项目', '变动金额', '变动原因'])
    const change = p.sub_table_data['合同负债（表2）'] as any[]
    expect(change[0]).toEqual({ label: '变动项B', change_amount: 20, reason: '' })
  })

  it('buildD7NoteTexts: 非空文本→带标题条目；空→跳过', () => {
    expect(buildD7NoteTexts('listed', { 'D7-note-listed-text-1': '', 'D7-note-listed-text-2': '  ' })).toEqual([])
    expect(buildD7NoteTexts('listed', { 'D7-note-listed-text-1': '说明X' })).toEqual([
      { section: 'D7-note-listed-text-1', title: '按性质分类说明', text: '说明X' },
    ])
  })

  it('非法金额归零 (num guard)', () => {
    const snap: D7DisclosureSnapshot = {
      mainRows: [{ label: '预收', current: NaN as any, prior: undefined as any }],
      mainTotal: { label: '合计', current: NaN as any, prior: NaN as any },
      changeRows: [],
      notes: {},
    }
    const p = buildD7SyncPayload('soe', 'wp', null, snap)
    const rows = p.sub_table_data['合同负债'] as any[]
    expect(rows[0]).toEqual({ label: '预收', end_amount: 0, prior_amount: 0 })
    expect(p.sub_table_data['_note_texts']).toEqual([])
  })
})
