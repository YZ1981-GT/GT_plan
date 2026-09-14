import { describe, it, expect, vi } from 'vitest'
import {
  createK1RowNavigation,
  resolveK1DetailFocusRow,
} from '../useK1RowNavigation'

describe('useK1RowNavigation', () => {
  it('resolveK1DetailFocusRow matches by rowId first', () => {
    const rows = [
      { id: 'd1', counterparty: '甲公司' },
      { id: 'd2', counterparty: '乙公司' },
    ]
    expect(resolveK1DetailFocusRow(rows, { sheet: 'K1-2', rowId: 'd2' })?.rowId).toBe('d2')
  })

  it('resolveK1DetailFocusRow falls back to counterparty fuzzy match', () => {
    const rows = [{ id: 'd1', counterparty: '北京华为技术有限公司' }]
    const resolved = resolveK1DetailFocusRow(rows, {
      sheet: 'K1-2',
      counterparty: '华为技术',
    })
    expect(resolved?.rowId).toBe('d1')
    expect(resolved?.counterparty).toBe('北京华为技术有限公司')
  })

  it('navigateToRow stores pending focus for K1-7', () => {
    const emit = vi.fn()
    const nav = createK1RowNavigation(emit)
    nav.navigateToRow({
      sheet: 'K1-7',
      counterparty: '甲公司',
      sourceSheet: 'K1-2',
    })
    expect(emit).toHaveBeenCalledWith('K1-7')
    const focus = nav.consumeFocus('K1-7')
    expect(focus?.counterparty).toBe('甲公司')
    expect(focus?.sourceSheet).toBe('K1-2')
  })

  it('navigateToDetailRow emits sheet label and stores pending focus', () => {
    const emit = vi.fn()
    const nav = createK1RowNavigation(emit)
    nav.navigateToDetailRow({
      rowId: 'd1',
      counterparty: '甲公司',
      sourceSheet: 'K1-5',
    })
    expect(emit).toHaveBeenCalledWith('K1-2 明细表')
    const focus = nav.consumeFocus('K1-2')
    expect(focus?.counterparty).toBe('甲公司')
    expect(focus?.sourceSheet).toBe('K1-5')
    expect(nav.consumeFocus('K1-2')).toBeNull()
  })

  it('focusRow sets highlight class for matching rowId', () => {
    vi.useFakeTimers()
    const nav = createK1RowNavigation(() => {})
    nav.focusRow('d1')
    expect(nav.rowHighlightClass('d1')).toBe('k1-row-deeplink-hl')
    expect(nav.rowHighlightClass('d2')).toBe('')
    vi.advanceTimersByTime(5000)
    expect(nav.rowHighlightClass('d1')).toBe('')
    vi.useRealTimers()
  })
})
