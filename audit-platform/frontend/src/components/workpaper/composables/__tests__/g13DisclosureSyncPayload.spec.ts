/**
 * G13 附注同步 payload / 章节映射
 */
import { describe, it, expect } from 'vitest'
import {
  buildG13SyncPayloads,
  buildG13MainSubTableRows,
  resolveG13NoteTemplateLabel,
} from '../g13DisclosureSyncPayload'
import { G13_MAIN_SUBTABLE, G13_NOTE_SECTION, isG13FairValueNoteSection } from '../g13NoteSectionMap'
import { G13_DISCLOSURE_LISTED_ROWS, G13_DISCLOSURE_SOE_ROWS } from '../g13Constants'
import { resolveNoteDisclosureJumpTarget } from '@/views/composables/noteDisclosureJump'

function listedSnap(partial: Record<string, { current?: number; prior?: number }> = {}) {
  return {
    rows: G13_DISCLOSURE_LISTED_ROWS.map((d) => ({
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

describe('G13_NOTE_SECTION', () => {
  it('上市/国企章节对齐模板', () => {
    expect(G13_NOTE_SECTION.listed).toBe('三、公允价值变动收益')
    expect(G13_NOTE_SECTION.soe).toBe('八、72')
    expect(isG13FairValueNoteSection('三、公允价值变动收益')).toBe(true)
    expect(isG13FairValueNoteSection('八、72')).toBe(true)
  })
})

describe('buildG13SyncPayloads', () => {
  it('上市：仅非空行 + 合计；标签对齐 note_template；不含空其中', () => {
    const payloads = buildG13SyncPayloads('wp-1', 'listed', ['listed_standalone'], listedSnap({
      trading_assets: { current: 100, prior: 80 },
      designated_fv_assets: { current: 25 },
      derivatives: { current: 0 },
    }))
    expect(payloads).toHaveLength(1)
    expect(payloads[0].section_id).toBe(G13_NOTE_SECTION.listed)
    expect(payloads[0].sheet_name).toContain('上市公司')
    const main = payloads[0].sub_table_data[G13_MAIN_SUBTABLE]
    expect(main.map((r) => r.label)).toEqual([
      '交易性金融资产（注1）',
      '其中：指定为以公允价值计量且其变动计入当期损益的金融资产',
      '合计',
    ])
    expect(main.find((r) => r.is_total)?.current_amount).toBe(100)
    expect(payloads[0].sub_table_data._note_texts?.[0]).toMatchObject({
      section: 'disclosure-note',
      text: '测试叙述',
    })
  })

  it('国企准则不适用上市 payload', () => {
    expect(buildG13SyncPayloads('wp-1', 'listed', ['soe_standalone'], listedSnap({
      trading_assets: { current: 1 },
    }))).toHaveLength(0)
  })

  it('国企 7 行模板空项省略', () => {
    const rows = G13_DISCLOSURE_SOE_ROWS.map((d) => ({
      rowKey: d.rowKey,
      label: d.label,
      currentAmount: d.rowKey === 'derivative_assets' ? 50 : 0,
      priorAmount: 0,
      remark: '',
    }))
    const payloads = buildG13SyncPayloads('wp-1', 'soe', ['soe_standalone'], {
      rows,
      noteText: '',
      adjudicatedAmount: 50,
    })
    expect(payloads[0].section_id).toBe('八、72')
    const main = buildG13MainSubTableRows(rows, 'soe')
    expect(main.map((r) => r.label)).toEqual(['衍生金融资产', '合计'])
  })
})

describe('resolveG13NoteTemplateLabel', () => {
  it('其他非流动其中项对齐模板长标签', () => {
    expect(resolveG13NoteTemplateLabel('designated_fv_other', 'listed')).toContain('计入当期损益的金融资产')
  })
})

describe('resolveNoteDisclosureJumpTarget — G13', () => {
  it('三、公允价值变动收益 → G13 上市披露表', () => {
    const t = resolveNoteDisclosureJumpTarget({
      note_section: '三、公允价值变动收益',
      last_sync_wp_id: 'wp-g13',
      table_data: {},
    })
    expect(t?.wpCode).toBe('G13')
    expect(t?.variant).toBe('listed')
    expect(t?.sheet).toContain('上市公司')
  })

  it('八、72 → G13 国企披露表', () => {
    const t = resolveNoteDisclosureJumpTarget({
      note_section: '八、72',
      table_data: { _current_standard: 'soe_standalone' },
    })
    expect(t?.wpCode).toBe('G13')
    expect(t?.variant).toBe('soe')
  })
})
