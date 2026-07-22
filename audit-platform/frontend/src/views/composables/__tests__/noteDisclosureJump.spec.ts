import { describe, expect, it } from 'vitest'
import {
  G7_DISCLOSURE_SHEET_LISTED,
  G7_DISCLOSURE_SHEET_SOE,
  G10_DISCLOSURE_SHEET_LISTED,
  G10_DISCLOSURE_SHEET_SOE,
  isG7EquityNoteSection,
  isG10TradingLiabilityNoteSection,
  isG14CreditImpairmentNoteSection,
  resolveNoteDisclosureJumpTarget,
} from '../noteDisclosureJump'

describe('noteDisclosureJump', () => {
  it('detects G7 equity note sections', () => {
    expect(isG7EquityNoteSection('五、18')).toBe(true)
    expect(isG7EquityNoteSection('八、18')).toBe(true)
    expect(isG7EquityNoteSection('七、本期纳入合并报表')).toBe(true)
    expect(isG7EquityNoteSection('四、货币资金')).toBe(false)
  })

  it('detects G10 trading liability note sections', () => {
    expect(isG10TradingLiabilityNoteSection('五、34')).toBe(true)
    expect(isG10TradingLiabilityNoteSection('八、35')).toBe(true)
    expect(isG10TradingLiabilityNoteSection('五、18')).toBe(false)
  })

  it('detects G14 credit impairment note sections', () => {
    expect(isG14CreditImpairmentNoteSection('三、信用减值损失')).toBe(true)
    expect(isG14CreditImpairmentNoteSection('八、73')).toBe(true)
    expect(isG14CreditImpairmentNoteSection('八、72')).toBe(false)
  })

  it('infers G14 listed disclosure from 三、信用减值损失', () => {
    const target = resolveNoteDisclosureJumpTarget({
      note_section: '三、信用减值损失',
      last_sync_wp_id: 'wp-g14',
    })
    expect(target?.wpCode).toBe('G14')
    expect(target?.variant).toBe('listed')
  })

  it('infers G14 SOE disclosure from 八、73', () => {
    expect(resolveNoteDisclosureJumpTarget({
      note_section: '八、73',
      source_template: 'soe',
    })?.wpCode).toBe('G14')
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
      wpCode: 'G7',
    })
  })

  it('infers G10 listed disclosure from 五、34', () => {
    const target = resolveNoteDisclosureJumpTarget({
      note_section: '五、34',
      last_sync_wp_id: 'wp-g10',
      table_data: { _last_sync_sheet: G10_DISCLOSURE_SHEET_LISTED },
    })
    expect(target?.sheet).toBe(G10_DISCLOSURE_SHEET_LISTED)
    expect(target?.wpCode).toBe('G10')
  })

  it('infers G10 SOE disclosure from 八、34', () => {
    expect(resolveNoteDisclosureJumpTarget({
      note_section: '八、34',
      source_template: 'soe',
    })?.sheet).toBe(G10_DISCLOSURE_SHEET_SOE)
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

  it('infers H10 listed disclosure from 三、资产处置收益', () => {
    const target = resolveNoteDisclosureJumpTarget({
      note_section: '三、资产处置收益',
      last_sync_wp_id: 'wp-h10',
    })
    expect(target?.wpCode).toBe('H10')
    expect(target?.variant).toBe('listed')
    expect(target?.sheet).toBe('附注披露信息（上市公司）')
  })

  it('infers H10 SOE disclosure from 八、75', () => {
    const target = resolveNoteDisclosureJumpTarget({
      note_section: '八、75',
      source_template: 'soe',
    })
    expect(target?.wpCode).toBe('H10')
    expect(target?.variant).toBe('soe')
    expect(target?.sheet).toBe('附注披露信息（国有企业）')
  })

  it('returns null for unrelated notes', () => {
    expect(resolveNoteDisclosureJumpTarget({
      note_section: '一、货币资金',
    })).toBeNull()
  })
})
