/**
 * useF2SpeExternalAdjudicated — 外部审定事件订阅
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { useF2SpeExternalAdjudicated } from '../useF2SpeExternalAdjudicated'

describe('useF2SpeExternalAdjudicated', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('refreshes on external F2 substantive:adjudicated for 1405', async () => {
    const refreshed = ref(0)
    const { dataUpdatedVisible } = useF2SpeExternalAdjudicated({
      onRefresh: () => { refreshed.value += 1 },
    })
    await nextTick()

    window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
      detail: { wpCode: 'F2', accountCodes: ['1405'], auditedAmounts: { '1405': 500 } },
    }))
    await nextTick()

    expect(refreshed.value).toBe(1)
    expect(dataUpdatedVisible.value).toBe(true)

    vi.advanceTimersByTime(3100)
    expect(dataUpdatedVisible.value).toBe(false)
  })

  it('ignores own F2-special events', async () => {
    const refreshed = ref(0)
    useF2SpeExternalAdjudicated({ onRefresh: () => { refreshed.value += 1 } })
    await nextTick()

    window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
      detail: { wpCode: 'F2-special', accountCode: '1405', auditedAmount: 100 },
    }))
    await nextTick()

    expect(refreshed.value).toBe(0)
  })
})
