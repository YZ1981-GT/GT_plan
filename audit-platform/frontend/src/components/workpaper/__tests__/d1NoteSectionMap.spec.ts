import { describe, expect, it } from 'vitest'
import {
  D1_NOTE_SECTION,
  D1_DISCLOSURE_SHEET_NAME,
  resolveD1CurrentStandard,
  buildD1SyncPayload,
  buildNoteTexts,
  type D1DisclosureSnapshot,
} from '../composables/d1NoteSectionMap'

function snap(overrides: Partial<D1DisclosureSnapshot> = {}): D1DisclosureSnapshot {
  const zeroSummary = {
    category: '', endBalance: 0, endProvision: 0, endBookValue: 0,
    priorBalance: 0, priorProvision: 0, priorBookValue: 0,
  }
  return {
    summaryRows: [
      { ...zeroSummary, category: '银行承兑汇票', endBalance: 1000, endProvision: 10, endBookValue: 990, priorBalance: 800, priorProvision: 8, priorBookValue: 792 },
      { ...zeroSummary, category: '商业承兑汇票', endBalance: 500, endProvision: 5, endBookValue: 495 },
    ],
    summaryTotal: { ...zeroSummary, category: '合计', endBalance: 1500, endProvision: 15, endBookValue: 1485, priorBalance: 800, priorProvision: 8, priorBookValue: 792 },
    pledgedRows: [{ category: '银行承兑票据', pledgedAmount: 200 }],
    pledgedTotal: { category: '合计', pledgedAmount: 200 },
    endorsedRows: [{ category: '银行承兑票据', derecognizedAmount: 300, notDerecognizedAmount: 0 }],
    endorsedTotal: { category: '合计', derecognizedAmount: 300, notDerecognizedAmount: 0 },
    transferRows: [{ category: '商业承兑票据', transferAmount: 50 }],
    transferTotal: { category: '合计', transferAmount: 50 },
    classEndRows: [
      { label: '按单项计提坏账准备', balance: 0, ratio: 0, provision: 0, lossRate: 0, bookValue: 0 },
      { label: '合计', balance: 1500, ratio: 1, provision: 15, lossRate: 0.01, bookValue: 1485 },
    ],
    classPriorRows: [{ label: '合计', balance: 800, ratio: 1, provision: 8, lossRate: 0.01, bookValue: 792 }],
    writeOffAmount: 0,
    writeOffDetailRows: [],
    notes: { top: '应收票据说明文本', pledged: '', endorsed: '背书说明', badDebtClass: '', writeOff: '' },
    ...overrides,
  }
}

describe('d1NoteSectionMap', () => {
  it('章节号冻结映射 五、4 / 八、4', () => {
    expect(D1_NOTE_SECTION.listed).toBe('五、4')
    expect(D1_NOTE_SECTION.soe).toBe('八、4')
  })

  it('resolveD1CurrentStandard 默认 standalone，含 consolidated 时升级', () => {
    expect(resolveD1CurrentStandard('listed', null)).toBe('listed_standalone')
    expect(resolveD1CurrentStandard('soe', [])).toBe('soe_standalone')
    expect(resolveD1CurrentStandard('listed', ['listed_consolidated'])).toBe('listed_consolidated')
  })

  it('listed sync payload 指向 五、4 + 主表名 应收票据 + 6 值列', () => {
    const p = buildD1SyncPayload('listed', 'wp-1', null, snap())
    expect(p.section_id).toBe('五、4')
    expect(p.sheet_name).toBe(D1_DISCLOSURE_SHEET_NAME.listed)
    const main = (p.sub_table_data['应收票据'] as any[])
    expect(main).toHaveLength(3) // 银承+商承+合计
    expect(main[0]).toMatchObject({ label: '银行承兑汇票', end_balance: 1000, end_provision: 10, end_book_value: 990 })
    expect(main[2]).toMatchObject({ label: '合计', is_total: true })
    // 列头 6 值列 + 标签列
    expect(p.columns['应收票据']).toHaveLength(7)
    expect(p.columns['应收票据'][0].is_label).toBe(true)
  })

  it('soe 主表名 应收票据分类，section 八、4', () => {
    const p = buildD1SyncPayload('soe', 'wp-2', null, snap())
    expect(p.section_id).toBe('八、4')
    expect(p.sub_table_data['应收票据分类']).toBeDefined()
    expect(p.sub_table_data['应收票据']).toBeUndefined()
  })

  it('_note_texts 只收非空说明，文本框内容与披露表一致', () => {
    const p = buildD1SyncPayload('listed', 'wp-1', null, snap())
    const texts = (p.sub_table_data._note_texts as any[])
    expect(texts.map(t => t.section)).toEqual(['note-top', 'note-endorsed'])
    expect(texts[0]).toMatchObject({ text: '应收票据说明文本' })
  })

  it('buildNoteTexts 跳过空白，保持子节顺序', () => {
    const texts = buildNoteTexts({ writeOff: '核销', top: '主表', badDebtClass: '  ' })
    expect(texts.map(t => t.section)).toEqual(['note-top', 'note-writeOff'])
  })

  it('质押/背书/转应收账款/坏账分类/核销 表格与列头齐备', () => {
    const p = buildD1SyncPayload('listed', 'wp-1', null, snap())
    expect(p.sub_table_data['期末已质押的应收票据']).toBeDefined()
    expect(p.sub_table_data['期末已背书或贴现但尚未到期的应收票据']).toBeDefined()
    expect(p.sub_table_data['期末因出票人未履约而将其转应收账款的票据']).toBeDefined()
    expect(p.sub_table_data['按坏账计提方法分类（期末余额）']).toBeDefined()
    expect(p.sub_table_data['按坏账计提方法分类（上年年末余额）']).toBeDefined()
    expect(p.sub_table_data['本期实际核销的应收票据情况']).toBeDefined()
    // 每张表都有对应列头
    for (const key of Object.keys(p.sub_table_data)) {
      if (key.startsWith('_')) continue
      expect(p.columns[key], `${key} 缺列头`).toBeDefined()
    }
  })
})
