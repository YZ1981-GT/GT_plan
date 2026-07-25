import { describe, it, expect } from 'vitest'
import {
  buildE1SyncPayload,
  buildNoteTexts,
  resolveE1CurrentStandard,
  E1_NOTE_SECTION,
  E1_DISCLOSURE_SHEET_NAME,
  type E1DisclosureSnapshot,
} from '../e1NoteSectionMap'

const listedSnapshot = (): E1DisclosureSnapshot => ({
  mainRows: [
    { key: 'cash', label: '库存现金', endingAmount: 100, openingAmount: 80 },
    { key: 'bank', label: '银行存款', endingAmount: 4703056.26, openingAmount: 400 },
    { key: 'other_mf', label: '其他货币资金', endingAmount: 12, openingAmount: 0 },
    { key: 'total', label: '合计', endingAmount: 4703168.26, openingAmount: 480 },
    { key: 'overseas', label: '其中：存放在境外的款项总额', endingAmount: 0, openingAmount: 0 },
  ],
  noteText: '期末货币资金较期初增加。',
})

const soeSnapshot = (): E1DisclosureSnapshot => ({
  mainRows: [
    { key: 'cash', label: '现金', endingAmount: 100, openingAmount: 80 },
    { key: 'total', label: '合计', endingAmount: 100, openingAmount: 80 },
  ],
  restrictedRows: [
    { item: '银行承兑汇票保证金', openingAmount: 5, endingAmount: 10, reason: '开立银行承兑汇票' },
    { item: '信用证保证金', openingAmount: 0, endingAmount: 3, reason: '' },
  ],
  noteText: '存在受限资金。',
})

describe('e1NoteSectionMap', () => {
  it('resolves note sections and sheet names (真实 tab 名，半角括号)', () => {
    expect(E1_NOTE_SECTION.listed).toBe('五、1')
    expect(E1_NOTE_SECTION.soe).toBe('八、1')
    expect(E1_DISCLOSURE_SHEET_NAME.listed).toBe('附注披露信息(上市公司)')
    expect(E1_DISCLOSURE_SHEET_NAME.soe).toBe('附注披露信息(国企)')
  })

  it('resolveE1CurrentStandard maps variant + applicable standards', () => {
    expect(resolveE1CurrentStandard('listed', null)).toBe('listed_standalone')
    expect(resolveE1CurrentStandard('listed', ['listed_consolidated'])).toBe('listed_consolidated')
    expect(resolveE1CurrentStandard('soe', null)).toBe('soe_standalone')
    expect(resolveE1CurrentStandard('soe', ['soe_consolidated'])).toBe('soe_consolidated')
  })

  it('listed payload → 五、1 单表「货币资金」(项目/期末余额/上年年末余额)', () => {
    const p = buildE1SyncPayload('listed', 'wp-1', null, listedSnapshot())
    expect(p.section_id).toBe('五、1')
    expect(p.sheet_name).toBe('附注披露信息(上市公司)')
    expect(p.current_standard).toBe('listed_standalone')
    // 单表 + _note_texts，无受限表
    expect(Object.keys(p.sub_table_data)).toEqual(['货币资金', '_note_texts'])
    const cols = p.columns['货币资金']
    expect(cols.map(c => c.label)).toEqual(['项目', '期末余额', '上年年末余额'])
    expect(cols[0].is_label).toBe(true)
    const rows = p.sub_table_data['货币资金'] as any[]
    expect(rows).toHaveLength(5)
    expect(rows[0]).toEqual({ label: '库存现金', end_amount: 100, prior_amount: 80 })
    // 合计行标 is_total
    const total = rows.find(r => r.label === '合计')
    expect(total.is_total).toBe(true)
    expect(total.end_amount).toBe(4703168.26)
  })

  it('soe payload → 八、1 主表 + 受限制的货币资金明细(含受限原因+合计)', () => {
    const p = buildE1SyncPayload('soe', 'wp-2', ['soe_standalone'], soeSnapshot())
    expect(p.section_id).toBe('八、1')
    expect(p.sheet_name).toBe('附注披露信息(国企)')
    expect(Object.keys(p.sub_table_data)).toEqual(['货币资金', '_note_texts', '受限制的货币资金明细'])
    // 主表列头（期初余额，非上年年末余额）
    expect(p.columns['货币资金'].map(c => c.label)).toEqual(['项目', '期末余额', '期初余额'])
    // 受限表列头（含受限原因）
    expect(p.columns['受限制的货币资金明细'].map(c => c.label)).toEqual(['项目', '期末余额', '期初余额', '受限原因'])
    const rst = p.sub_table_data['受限制的货币资金明细'] as any[]
    expect(rst).toHaveLength(3) // 2 明细 + 合计
    expect(rst[0]).toEqual({ label: '银行承兑汇票保证金', end_amount: 10, prior_amount: 5, reason: '开立银行承兑汇票' })
    const total = rst[2]
    expect(total).toEqual({ label: '合计', end_amount: 13, prior_amount: 5, reason: '', is_total: true })
  })

  it('buildNoteTexts: 非空文本→带标题条目；空→[]', () => {
    expect(buildNoteTexts('listed', '  ')).toEqual([])
    expect(buildNoteTexts('listed', '说明X')).toEqual([
      { section: 'listed-note', title: '货币资金说明', text: '说明X' },
    ])
  })

  it('非法金额归零 (num guard)', () => {
    const snap: E1DisclosureSnapshot = {
      mainRows: [{ key: 'cash', label: '库存现金', endingAmount: NaN as any, openingAmount: undefined as any }],
      noteText: '',
    }
    const p = buildE1SyncPayload('listed', 'wp', null, snap)
    const rows = p.sub_table_data['货币资金'] as any[]
    expect(rows[0]).toEqual({ label: '库存现金', end_amount: 0, prior_amount: 0 })
    // 空文本 → _note_texts 为空数组
    expect(p.sub_table_data['_note_texts']).toEqual([])
  })
})
