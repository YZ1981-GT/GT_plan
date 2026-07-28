import { describe, it, expect } from 'vitest'
import {
  buildD4SyncPayload,
  buildD4NoteTexts,
  resolveD4CurrentStandard,
  D4_NOTE_SECTION,
  D4_DISCLOSURE_SHEET_NAME,
  type D4DisclosureSnapshot,
} from '../d4NoteSectionMap'

const snapshot = (): D4DisclosureSnapshot => ({
  revenueRows: [
    { label: '主营业务', currentRevenue: 1000, currentCost: 600, priorRevenue: 900, priorCost: 550 },
    { label: '其他业务', currentRevenue: 100, currentCost: 40, priorRevenue: 80, priorCost: 30 },
  ],
  revenueTotal: { label: '合计', currentRevenue: 1100, currentCost: 640, priorRevenue: 980, priorCost: 580 },
  industryRows: [{ label: '消费品', currentRevenue: 700, currentCost: 400 }],
  regionRows: [{ label: '华东', currentRevenue: 500, currentCost: 300 }],
  timingRows: [{ label: '在某一时点确认', currentRevenue: 800, currentCost: 480 }],
  notes: { 'note-1': '收入说明', 'note-2': '', 'note-8': '试运行说明' },
})

describe('d4NoteSectionMap', () => {
  it('章节号 + sheet 名（真实 tab 名，全角括号）', () => {
    expect(D4_NOTE_SECTION.listed).toBe('五、62')
    expect(D4_NOTE_SECTION.soe).toBe('八、64')
    // 🔴 D4 为全角括号（与 D7 半角不同）
    expect(D4_DISCLOSURE_SHEET_NAME.listed).toBe('附注披露信息（上市公司）')
    expect(D4_DISCLOSURE_SHEET_NAME.soe).toBe('附注披露信息（国企）')
  })

  it('resolveD4CurrentStandard maps variant + applicable standards', () => {
    expect(resolveD4CurrentStandard('listed', null)).toBe('listed_standalone')
    expect(resolveD4CurrentStandard('listed', ['listed_consolidated'])).toBe('listed_consolidated')
    expect(resolveD4CurrentStandard('soe', ['soe_consolidated'])).toBe('soe_consolidated')
  })

  it('listed payload → 五、62 四表，子表键↔columns键一致，主表 5 列', () => {
    const p = buildD4SyncPayload('listed', 'wp-1', null, snapshot())
    expect(p.section_id).toBe('五、62')
    expect(p.sheet_name).toBe('附注披露信息（上市公司）')
    expect(p.current_standard).toBe('listed_standalone')
    expect(Object.keys(p.sub_table_data)).toEqual([
      '营业收入和营业成本',
      '营业收入、营业成本按行业（或产品类型）划分',
      '营业收入、营业成本按地区划分',
      '营业收入、营业成本按商品转让时间划分',
      '_note_texts',
    ])
    // 🔴 各子表键 ↔ columns 键必须相同
    for (const k of Object.keys(p.sub_table_data)) {
      if (k === '_note_texts') continue
      expect(p.columns[k]).toBeDefined()
    }
    // 主表拍平为 5 列（本期收入/本期成本/上期收入/上期成本）
    expect(p.columns['营业收入和营业成本'].map(c => c.label)).toEqual(['项目', '本期收入', '本期成本', '上期收入', '上期成本'])
    const mainRows = p.sub_table_data['营业收入和营业成本'] as any[]
    expect(mainRows[0]).toEqual({ label: '主营业务', current_revenue: 1000, current_cost: 600, prior_revenue: 900, prior_cost: 550 })
    expect(mainRows[mainRows.length - 1]).toMatchObject({ label: '合计', current_revenue: 1100, is_total: true })
    // 两列表列头 + 合计
    expect(p.columns['营业收入、营业成本按行业（或产品类型）划分'].map(c => c.label)).toEqual(['主要产品类型（或行业）', '本期收入', '本期成本'])
    const ind = p.sub_table_data['营业收入、营业成本按行业（或产品类型）划分'] as any[]
    expect(ind[0]).toEqual({ label: '消费品', current_revenue: 700, current_cost: 400 })
    expect(ind[1]).toMatchObject({ label: '合计', current_revenue: 700, current_cost: 400, is_total: true })
  })

  it('soe payload → 八、64 四表，主表名/时段表首列头不同', () => {
    const p = buildD4SyncPayload('soe', 'wp-2', ['soe_standalone'], snapshot())
    expect(p.section_id).toBe('八、64')
    expect(p.sheet_name).toBe('附注披露信息（国企）')
    expect(Object.keys(p.sub_table_data)).toEqual([
      '营业收入、营业成本',
      '按行业（或产品类型）划分',
      '营业收入、营业成本按地区划分',
      '营业收入、营业成本按商品转让时间划分',
      '_note_texts',
    ])
    // 时段表 soe 首列头 = 合同分类/报告分部
    expect(p.columns['营业收入、营业成本按商品转让时间划分'][0].label).toBe('合同分类/报告分部')
  })

  it('sumNullable：两列表空行 → 合计 null（不塌 0）', () => {
    const snap: D4DisclosureSnapshot = {
      revenueRows: [],
      revenueTotal: { label: '合计', currentRevenue: 0, currentCost: 0, priorRevenue: 0, priorCost: 0 },
      industryRows: [],
      regionRows: [],
      timingRows: [],
      notes: {},
    }
    const p = buildD4SyncPayload('listed', 'wp', null, snap)
    const ind = p.sub_table_data['营业收入、营业成本按行业（或产品类型）划分'] as any[]
    expect(ind).toHaveLength(1) // 仅合计行
    expect(ind[0]).toEqual({ label: '合计', current_revenue: null, current_cost: null, is_total: true })
    expect(p.sub_table_data['_note_texts']).toEqual([])
  })

  it('buildD4NoteTexts: section 前缀带 variant，空文本跳过', () => {
    expect(buildD4NoteTexts('listed', { 'note-1': '收入说明', 'note-2': '' })).toEqual([
      { section: 'listed-note-1', title: '营业收入和营业成本说明', text: '收入说明' },
    ])
    // soe 无 note-8
    expect(buildD4NoteTexts('soe', { 'note-8': '试运行' })).toEqual([])
  })
})
