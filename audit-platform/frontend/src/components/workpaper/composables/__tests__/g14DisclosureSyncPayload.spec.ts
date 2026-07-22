/**
 * G14 附注同步 payload / 空项省略 / 章节映射
 */
import { describe, it, expect } from 'vitest'
import {
  buildG14SyncPayloads,
  buildG14MainSubTableRows,
  resolveG14NoteTemplateLabel,
} from '../g14DisclosureSyncPayload'
import {
  G14_MAIN_SUBTABLE,
  G14_NOTE_SECTION,
  isG14CreditImpairmentNoteSection,
} from '../g14NoteSectionMap'
import {
  G14_DISCLOSURE_LISTED_ROWS,
  G14_DISCLOSURE_SOE_ROWS,
  G14_SOE_BAD_DEBT_SOURCES,
  G14_SOE_OTHER_EXTRA_SOURCES,
} from '../g14Constants'
import {
  filterG14DisclosureRows,
  g14DisclosureHasAnyAmount,
} from '../g14DisclosureVisibility'
import { buildG14NoteTextFromRows } from '../g14NoteText'
import { resolveNoteDisclosureJumpTarget } from '@/views/composables/noteDisclosureJump'

function listedSnap(partial: Record<string, { current?: number; prior?: number }> = {}) {
  return {
    rows: G14_DISCLOSURE_LISTED_ROWS.map((d) => ({
      rowKey: d.rowKey,
      label: d.label,
      currentAmount: partial[d.rowKey]?.current ?? 0,
      priorAmount: partial[d.rowKey]?.prior ?? 0,
      remark: '',
    })),
    noteText: '测试叙述',
    adjudicatedAmount: 100,
  }
}

describe('G14_NOTE_SECTION', () => {
  it('上市/国企章节对齐模板', () => {
    expect(G14_NOTE_SECTION.listed).toBe('三、信用减值损失')
    expect(G14_NOTE_SECTION.soe).toBe('八、73')
    expect(isG14CreditImpairmentNoteSection('三、信用减值损失')).toBe(true)
    expect(isG14CreditImpairmentNoteSection('八、73')).toBe(true)
  })
})

describe('G14 SOE aggregation sources', () => {
  it('坏账不含担保；含合同资产；担保并入其他', () => {
    expect([...G14_SOE_BAD_DEBT_SOURCES]).toEqual(['notes', 'ar', 'rfin', 'othar', 'ltar', 'ca'])
    expect([...G14_SOE_OTHER_EXTRA_SOURCES]).toContain('guarantee')
  })
})

describe('buildG14SyncPayloads', () => {
  it('上市：仅非空行 + 合计；标签对齐 note_template', () => {
    const payloads = buildG14SyncPayloads('wp-1', 'listed', ['listed_standalone'], listedSnap({
      ar: { current: 100, prior: 80 },
      guarantee: { current: 25 },
      notes: { current: 0 },
    }))
    expect(payloads).toHaveLength(1)
    expect(payloads[0].section_id).toBe(G14_NOTE_SECTION.listed)
    expect(payloads[0].sheet_name).toContain('上市公司')
    const main = payloads[0].sub_table_data[G14_MAIN_SUBTABLE.listed]
    expect(main.map((r) => r.label)).toEqual([
      '应收账款坏账损失',
      '财务担保预计损失',
      '合计',
    ])
    expect(main.find((r) => r.is_total)?.current_amount).toBe(125)
    expect(payloads[0].sub_table_data._note_texts?.[0]).toMatchObject({
      section: 'disclosure-note',
      text: '测试叙述',
    })
  })

  it('国企准则不适用上市 payload', () => {
    expect(buildG14SyncPayloads('wp-1', 'listed', ['soe_standalone'], listedSnap({
      ar: { current: 1 },
    }))).toHaveLength(0)
  })

  it('国企 4 行模板空项省略', () => {
    const rows = G14_DISCLOSURE_SOE_ROWS.map((d) => ({
      rowKey: d.rowKey,
      label: d.label,
      currentAmount: d.rowKey === 'bad_debt' ? 50 : 0,
      priorAmount: 0,
      remark: '',
    }))
    const payloads = buildG14SyncPayloads('wp-1', 'soe', ['soe_standalone'], {
      rows,
      noteText: '',
      adjudicatedAmount: 50,
    })
    expect(payloads[0].section_id).toBe('八、73')
    const main = buildG14MainSubTableRows(rows, 'soe')
    expect(main.map((r) => r.label)).toEqual(['坏账损失', '合计'])
  })
})

describe('filterG14DisclosureRows / note text', () => {
  it('隐藏空行；叙述不含零行', () => {
    const rows = G14_DISCLOSURE_LISTED_ROWS.map((d) => ({
      rowKey: d.rowKey,
      label: d.label,
      currentAmount: d.rowKey === 'ar' ? 10 : 0,
      priorAmount: 0,
      remark: '',
    }))
    expect(g14DisclosureHasAnyAmount(rows)).toBe(true)
    expect(filterG14DisclosureRows(rows).map((r) => r.rowKey)).toEqual(['ar'])
    const text = buildG14NoteTextFromRows(rows, 'listed', { adjudicatedAmount: 10 })
    expect(text).toContain('应收账款坏账损失')
    expect(text).not.toContain('应收票据坏账损失')
    expect(text).toContain('勾稽一致')
  })
})

describe('resolveG14NoteTemplateLabel', () => {
  it('财务担保对齐上市模板', () => {
    expect(resolveG14NoteTemplateLabel('guarantee', 'listed')).toBe('财务担保预计损失')
    expect(resolveG14NoteTemplateLabel('bad_debt', 'soe')).toBe('坏账损失')
  })
})

describe('resolveNoteDisclosureJumpTarget — G14', () => {
  it('三、信用减值损失 → G14 上市披露表', () => {
    const t = resolveNoteDisclosureJumpTarget({
      note_section: '三、信用减值损失',
      last_sync_wp_id: 'wp-g14',
      table_data: {},
    })
    expect(t?.wpCode).toBe('G14')
    expect(t?.variant).toBe('listed')
    expect(t?.sheet).toContain('上市公司')
  })

  it('八、73 → G14 国企披露表', () => {
    const t = resolveNoteDisclosureJumpTarget({
      note_section: '八、73',
      last_sync_wp_id: 'wp-g14',
      table_data: { _current_standard: 'soe' },
    })
    expect(t?.wpCode).toBe('G14')
    expect(t?.variant).toBe('soe')
  })
})
