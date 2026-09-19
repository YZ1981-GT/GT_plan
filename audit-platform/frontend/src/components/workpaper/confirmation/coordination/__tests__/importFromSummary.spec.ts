import { describe, expect, it } from 'vitest'
import {
  accountTypeFilter,
  defaultDiffFilter,
  defaultElectronicReplyFilter,
  defaultUnrepliedFilter,
  mapSummaryToAlternativeCompany,
} from '../importFromSummary'
import type { SummaryRow } from '../importFromSummary'

function row(partial: Partial<SummaryRow>): SummaryRow {
  return partial as SummaryRow
}

describe('importFromSummary filters', () => {
  it('unreplied filter', () => {
    expect(defaultUnrepliedFilter(row({ match_status: '未回函' }))).toBe(true)
    expect(defaultUnrepliedFilter(row({ is_replied: false, match_status: '不符' }))).toBe(true)
    expect(defaultUnrepliedFilter(row({ is_replied: false, match_status: '相符' }))).toBe(false)
    expect(defaultUnrepliedFilter(row({ is_replied: true, match_status: '相符' }))).toBe(false)
  })

  it('diff filter', () => {
    expect(defaultDiffFilter(row({ is_replied: true, amount: 100, reply_amount: 80 }))).toBe(true)
    expect(defaultDiffFilter(row({ is_replied: true, amount: 100, reply_amount: 100, match_status: '相符' }))).toBe(false)
    expect(defaultDiffFilter(row({ match_status: '不符', amount: 50, reply_amount: 50 }))).toBe(true)
  })

  it('electronic reply filter', () => {
    expect(defaultElectronicReplyFilter(row({ reply_method: '电子邮件' }))).toBe(true)
    expect(defaultElectronicReplyFilter(row({ reply_method: '传真' }))).toBe(true)
    expect(defaultElectronicReplyFilter(row({ reply_method: '原件' }))).toBe(false)
  })

  it('account type filter', () => {
    const f = accountTypeFilter(['预付账款', '应付账款'])
    expect(f(row({ account_type: '预付账款' }))).toBe(true)
    expect(f(row({ account_type: '应收账款' }))).toBe(false)
  })

  it('map to alternative company', () => {
    const c = mapSummaryToAlternativeCompany(
      row({ entity_name: '甲', confirm_index: 'F0-001', account_type: '预付账款', amount: 12 }),
      '预付账款',
    )
    expect(c.entity_name).toBe('甲')
    expect(c.confirm_index).toBe('F0-001')
    expect(c._source).toBe('auto')
    expect(c.balance.closing_balance).toBe(12)
    expect(c.balance.item_name).toBe('预付账款')
  })

  it('filters non-zero diff reconcile rows (logic)', () => {
    const rows = [
      { difference: 10, sent_amount: 100, reply_amount: 90 },
      { difference: 0, sent_amount: 50, reply_amount: 50 },
      { sent_amount: 80, reply_amount: 70 },
    ]
    const filtered = rows.filter((r) => {
      const diff = Number((r as any).difference)
      if (Number.isFinite(diff) && diff !== 0) return true
      const sent = Number(r.sent_amount) || 0
      const reply = Number(r.reply_amount) || 0
      return Math.round((sent - reply) * 100) / 100 !== 0
    })
    expect(filtered).toHaveLength(2)
  })
})
