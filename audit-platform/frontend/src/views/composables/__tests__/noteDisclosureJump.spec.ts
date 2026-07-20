import { describe, expect, it } from 'vitest'
import {
  G7_DISCLOSURE_SHEET_LISTED,
  G7_DISCLOSURE_SHEET_SOE,
  isG7EquityNoteSection,
  resolveNoteDisclosureJumpTarget,
} from '../noteDisclosureJump'

describe('noteDisclosureJump', () => {
  it('detects G7 equity note sections', () => {
    expect(isG7EquityNoteSection('五、18')).toBe(true)
    expect(isG7EquityNoteSection('八、18')).toBe(true)
    expect(isG7EquityNoteSection('七、本期纳入合并报表')).toBe(true)
    expect(isG7EquityNoteSection('四、货币资金')).toBe(false)
  })

  it('prefers synced listed disclosure sheet', () => {
    const target = resolveNoteDisclosureJumpTarget({
      note_section: '五、18',
      last_sync_wp_id: 'wp-1',
      table_data: {
        _last_sync_sheet: '附注披露信息（上市公司）',
        _current_standard: 'listed',
      },
    })
    expect(target).toEqual({
      sheet: G7_DISCLOSURE_SHEET_LISTED,
      wpId: 'wp-1',
      variant: 'listed',
      reason: '同步来源 sheet',
    })
  })

  it('infers SOE disclosure sheet from 七 / 八 chapters', () => {
    expect(resolveNoteDisclosureJumpTarget({
      note_section: '八、18',
      source_template: 'soe',
    })?.sheet).toBe(G7_DISCLOSURE_SHEET_SOE)

    expect(resolveNoteDisclosureJumpTarget({
      note_section: '七、本期发生的同一控',
      table_data: { _current_standard: 'soe' },
    })?.variant).toBe('soe')
  })

  it('returns null for unrelated notes', () => {
    expect(resolveNoteDisclosureJumpTarget({
      note_section: '一、货币资金',
    })).toBeNull()
  })
})
