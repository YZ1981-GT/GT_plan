import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import {
  accountTypeToWpHint,
  emitConfirmationCompleted,
  emitConfirmationCompletedFromSummary,
  isConfirmationInFlight,
} from '../emitConfirmationCompleted'

describe('emitConfirmationCompleted helpers', () => {
  it('maps account types to wp hints', () => {
    expect(accountTypeToWpHint('预付账款')).toBe('F1')
    expect(accountTypeToWpHint('应收账款')).toBe('D2')
    expect(accountTypeToWpHint('其他应收款')).toBe('D7')
    expect(accountTypeToWpHint('合同负债')).toBe('D5')
  })

  it('detects in-flight confirmation rows', () => {
    expect(isConfirmationInFlight({ send_date: '2025-01-01' })).toBe(true)
    expect(isConfirmationInFlight({ match_status: '未回函' })).toBe(true)
    expect(isConfirmationInFlight({ confirmation_method: '积极式' })).toBe(true)
    expect(isConfirmationInFlight({})).toBe(false)
  })

  it('dispatches window CustomEvent with detail', () => {
    const spy = vi.fn()
    window.addEventListener('confirmation:completed', spy)
    emitConfirmationCompleted({
      customerName: '甲公司',
      accountType: '预付账款',
      sourceWpCode: 'F0-1',
    })
    expect(spy).toHaveBeenCalled()
    const evt = spy.mock.calls[0][0] as CustomEvent
    expect(evt.detail.customerName).toBe('甲公司')
    expect(evt.detail.wpCode).toBe('F1')
    window.removeEventListener('confirmation:completed', spy)
  })

  it('batch emit from summary skips empty entities and adds summary metrics', () => {
    const names: string[] = []
    const handler = (e: Event) => {
      names.push((e as CustomEvent).detail.customerName)
    }
    window.addEventListener('confirmation:completed', handler)
    const n = emitConfirmationCompletedFromSummary({
      sourceWpCode: 'F0-1',
      rows: [
        { entity_name: '甲', match_status: '未回函', account_type: '预付账款' },
        { entity_name: '', send_date: '2025-01-01' },
        { entity_name: '乙', match_status: '相符', is_replied: true },
      ],
    })
    expect(n).toBe(2)
    expect(names).toContain('甲')
    expect(names).toContain('乙')
    expect(names).toContain('__summary__')
    window.removeEventListener('confirmation:completed', handler)
  })
})
