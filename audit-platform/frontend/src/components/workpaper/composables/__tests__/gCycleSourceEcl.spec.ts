/**
 * gCycleSourceEcl — 源科目 ECL EventBus 单元测试
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  G_CYCLE_SOURCE_ECL_EVENT,
  resolveG14EclRowKey,
  publishGCycleSourceEcl,
  calcSourceEclProfitLoss,
} from '../gCycleSourceEcl'

describe('gCycleSourceEcl', () => {
  beforeEach(() => {
    vi.stubGlobal('window', {
      dispatchEvent: vi.fn(),
    })
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('resolveG14EclRowKey 支持源编码 / rowKey / wp: 索引', () => {
    expect(resolveG14EclRowKey('D2')).toBe('ar')
    expect(resolveG14EclRowKey('ar')).toBe('ar')
    expect(resolveG14EclRowKey('wp:D1-1')).toBe('notes')
    expect(resolveG14EclRowKey('D6-1')).toBe('ca')
    expect(resolveG14EclRowKey('')).toBeNull()
  })

  it('calcSourceEclProfitLoss = 计提 − |转回|', () => {
    expect(calcSourceEclProfitLoss(1000, 200)).toBe(800)
    expect(calcSourceEclProfitLoss(1000, -200)).toBe(800)
  })

  it('publishGCycleSourceEcl 派发 g-cycle:source-ecl', () => {
    publishGCycleSourceEcl('D2', 1234.5)
    expect(window.dispatchEvent).toHaveBeenCalledWith(
      expect.objectContaining({
        type: G_CYCLE_SOURCE_ECL_EVENT,
      }),
    )
    const evt = (window.dispatchEvent as ReturnType<typeof vi.fn>).mock.calls[0][0] as CustomEvent
    expect(evt.detail).toEqual({ rowKey: 'ar', source: 'D2', amount: 1234.5 })
  })
})
