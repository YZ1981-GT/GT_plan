/**
 * 调整分录组定位登记表与 source_ref 解析（spec wp-deeplink-locate-residual-closure 需求 1.2）。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  adjustmentEntryGroupRegistrationCount,
  entryGroupOfHighlight,
  locateAdjustmentEntryGroup,
  registerAdjustmentEntryGroup,
} from '../adjustmentEntryGroupLocate'

const off: Array<() => void> = []
afterEach(() => { while (off.length) off.pop()!() })

describe('entryGroupOfHighlight', () => {
  it('按第一个冒号拆 source_ref，底稿 id 相同才返回 item_id', () => {
    expect(entryGroupOfHighlight('wp-1:L1-adj-RJE', 'wp-1')).toBe('L1-adj-RJE')
    expect(entryGroupOfHighlight(['wp-1:D4-4-rows', 'x'], 'wp-1')).toBe('D4-4-rows')
    expect(entryGroupOfHighlight(' wp-1 : K9-3-adj-entries ', 'wp-1')).toBe('K9-3-adj-entries')
  })

  it('别的底稿 / 不是 source_ref 形态 / 空值 ⇒ null', () => {
    expect(entryGroupOfHighlight('wp-2:L1-adj-RJE', 'wp-1')).toBeNull()
    expect(entryGroupOfHighlight('D2', 'wp-1')).toBeNull()
    expect(entryGroupOfHighlight(':D4-4-rows', 'wp-1')).toBeNull()
    expect(entryGroupOfHighlight('wp-1:', 'wp-1')).toBeNull()
    expect(entryGroupOfHighlight(undefined, 'wp-1')).toBeNull()
    expect(entryGroupOfHighlight('wp-1:D4-4-rows', '')).toBeNull()
  })
})

describe('registerAdjustmentEntryGroup / locateAdjustmentEntryGroup', () => {
  it('只问本底稿登记的页签；有一个认领即 true，后面的不再问', () => {
    const other = vi.fn(() => true)
    const first = vi.fn((id: string) => id === 'D4-4-rows')
    const second = vi.fn(() => true)
    off.push(registerAdjustmentEntryGroup(() => 'wp-2', other))
    off.push(registerAdjustmentEntryGroup(() => 'wp-1', first))
    off.push(registerAdjustmentEntryGroup(() => 'wp-1', second))
    expect(locateAdjustmentEntryGroup('wp-1', 'D4-4-rows')).toBe(true)
    expect(other).not.toHaveBeenCalled()
    expect(second).not.toHaveBeenCalled()
    expect(locateAdjustmentEntryGroup('wp-1', 'D5-3-rows')).toBe(true)
    expect(second).toHaveBeenCalledWith('D5-3-rows')
  })

  it('都不认领 / 没有登记 / 空参数 ⇒ false；注销后不再被问', () => {
    const locate = vi.fn(() => false)
    const unregister = registerAdjustmentEntryGroup(() => 'wp-1', locate)
    expect(locateAdjustmentEntryGroup('wp-1', 'X')).toBe(false)
    expect(locateAdjustmentEntryGroup('wp-9', 'X')).toBe(false)
    expect(locateAdjustmentEntryGroup('', 'X')).toBe(false)
    expect(locateAdjustmentEntryGroup('wp-1', '')).toBe(false)
    const before = adjustmentEntryGroupRegistrationCount()
    unregister()
    expect(adjustmentEntryGroupRegistrationCount()).toBe(before - 1)
    locate.mockClear()
    expect(locateAdjustmentEntryGroup('wp-1', 'X')).toBe(false)
    expect(locate).not.toHaveBeenCalled()
  })

  it('底稿 id 按问的时候的值认（页签换了底稿）', () => {
    let current = 'wp-1'
    off.push(registerAdjustmentEntryGroup(() => current, () => true))
    expect(locateAdjustmentEntryGroup('wp-1', 'X')).toBe(true)
    current = 'wp-2'
    expect(locateAdjustmentEntryGroup('wp-1', 'X')).toBe(false)
    expect(locateAdjustmentEntryGroup('wp-2', 'X')).toBe(true)
  })
})
