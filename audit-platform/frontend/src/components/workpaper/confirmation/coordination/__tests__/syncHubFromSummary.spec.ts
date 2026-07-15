import { describe, expect, it } from 'vitest'
import {
  accountTypeToHubType,
  hubStatusToRowPatch,
  rowToHubStatus,
  transitionPath,
} from '../syncHubFromSummary'
import type { ConfirmationRow } from '../../confirmationTypes'

function row(p: Partial<ConfirmationRow>): ConfirmationRow {
  return p as ConfirmationRow
}

describe('syncHubFromSummary mapping', () => {
  it('maps account types to hub confirm_type', () => {
    expect(accountTypeToHubType('应收账款')).toBe('receivable')
    expect(accountTypeToHubType('预付账款')).toBe('receivable')
    expect(accountTypeToHubType('应付账款')).toBe('payable')
    expect(accountTypeToHubType('银行存款')).toBe('bank')
    expect(accountTypeToHubType('短期借款')).toBe('loan')
  })

  it('maps row signals to hub status', () => {
    expect(rowToHubStatus(row({ match_status: '相符' }))).toBe('matched')
    expect(rowToHubStatus(row({ match_status: '不符' }))).toBe('discrepancy')
    expect(rowToHubStatus(row({ is_replied: true }))).toBe('returned')
    expect(rowToHubStatus(row({ send_date: '2025-01-01' }))).toBe('sent')
    expect(rowToHubStatus(row({}))).toBe('pending')
  })

  it('builds forward-only transition path', () => {
    expect(transitionPath('pending', 'sent')).toEqual(['sent'])
    expect(transitionPath('pending', 'matched')).toEqual(['sent', 'returned', 'matched'])
    expect(transitionPath('returned', 'discrepancy')).toEqual(['discrepancy'])
    expect(transitionPath('matched', 'sent')).toEqual([])
  })

  it('hub status patches summary row sparsely', () => {
    const p = hubStatusToRowPatch('matched', {
      book_amount: 100,
      confirmed_amount: 100,
      diff_amount: 0,
    })
    expect(p.match_status).toBe('相符')
    expect(p.is_replied).toBe(true)
    expect(p.amount).toBe(100)
    expect(p.reply_amount).toBe(100)
  })
})
