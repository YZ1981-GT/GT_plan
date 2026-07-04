/**
 * useF2SpeEventBus — EventBus 去重与 1405 判定
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  publishF2SpeSubstantiveAdjudicated,
  debouncedPublishF2SpeDisclosureNote,
  is1405SubstantiveEvent,
  resetF2SpeEventBusDedupState,
} from '../useF2SpeEventBus'

describe('useF2SpeEventBus', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    resetF2SpeEventBusDedupState()
  })

  afterEach(() => {
    vi.useRealTimers()
    resetF2SpeEventBusDedupState()
  })

  it('dedupes substantive:adjudicated within 2s', () => {
    const events: unknown[] = []
    const handler = (e: Event) => events.push((e as CustomEvent).detail)
    window.addEventListener('substantive:adjudicated', handler)

    const payload = { wpCode: 'F2-special' as const, accountCode: '1405' as const, auditedAmount: 100 }
    publishF2SpeSubstantiveAdjudicated(payload)
    publishF2SpeSubstantiveAdjudicated(payload)
    expect(events).toHaveLength(1)

    vi.advanceTimersByTime(2100)
    publishF2SpeSubstantiveAdjudicated(payload)
    expect(events).toHaveLength(2)

    window.removeEventListener('substantive:adjudicated', handler)
  })

  it('debounces disclosure:note-text-updated by 2s', () => {
    const events: unknown[] = []
    const handler = (e: Event) => events.push((e as CustomEvent).detail)
    window.addEventListener('disclosure:note-text-updated', handler)

    debouncedPublishF2SpeDisclosureNote('contract-cost', '结论A')
    debouncedPublishF2SpeDisclosureNote('contract-cost', '结论B')
    expect(events).toHaveLength(0)

    vi.advanceTimersByTime(2000)
    expect(events).toHaveLength(1)
    expect(events[0]).toMatchObject({
      wpCode: 'F2-special',
      section: 'contract-cost',
      text: '结论B',
    })

    window.removeEventListener('disclosure:note-text-updated', handler)
  })

  it('is1405SubstantiveEvent detects accountCode and accountCodes', () => {
    expect(is1405SubstantiveEvent({ accountCode: '1405' })).toBe(true)
    expect(is1405SubstantiveEvent({ accountCodes: ['1401', '1405'] })).toBe(true)
    expect(is1405SubstantiveEvent({ auditedAmounts: { '1405': 1000 } })).toBe(true)
    expect(is1405SubstantiveEvent({ accountCode: '1401' })).toBe(false)
  })
})
