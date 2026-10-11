/** 切换分段计时器（spec workpaper-sync-switch-performance 需求 1.3）：只观测、不影响切换。 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import { SWITCH_MEASURE_PREFIX, createSwitchTimer } from '../bridgeSwitchTimings'

function clock(...ticks: number[]) {
  const queue = [...ticks]
  return () => queue.shift() ?? Number.NaN
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('createSwitchTimer', () => {
  it('以切换开始为零点记各段，保留 1 位小数', () => {
    const timer = createSwitchTimer(clock(100, 112.34, 250))
    timer.begin()
    timer.mark('writes_flushed')
    const snap = timer.mark('materialized')
    expect(snap.marks).toEqual({ writes_flushed: 12.3, materialized: 150 })
  })

  it('begin 之前与 confirmed 之后的 mark 不计入（如 refresh 后的重挂载）', () => {
    const timer = createSwitchTimer(clock(0, 5, 9, 20))
    expect(timer.mark('mounted').marks).toEqual({})
    timer.begin()
    timer.mark('ready')
    timer.mark('confirmed')
    expect(timer.mark('mounted').marks).toEqual({ ready: 5, confirmed: 9 })
  })

  it('begin 清掉上一次的路径与分段', () => {
    const timer = createSwitchTimer(clock(0, 3, 10))
    timer.begin()
    timer.setPath('client')
    timer.mark('materialized')
    expect(timer.begin()).toEqual({ path: null, marks: {} })
  })

  it('发 User Timing measure（名称带前缀、detail 带路径）', () => {
    const measure = vi.spyOn(performance, 'measure')
    const timer = createSwitchTimer(clock(1, 2))
    timer.begin()
    timer.setPath('server_store_fast')
    timer.mark('materialized')
    expect(measure).toHaveBeenCalledWith(`${SWITCH_MEASURE_PREFIX}:materialized`, {
      start: 1,
      end: 2,
      detail: { path: 'server_store_fast' },
    })
  })

  it('User Timing 抛错时静默（只观测，不得打断切换）', () => {
    vi.spyOn(performance, 'measure').mockImplementation(() => {
      throw new TypeError('measure 不可用')
    })
    const timer = createSwitchTimer(clock(0, 1))
    timer.begin()
    expect(() => timer.mark('html_flushed')).not.toThrow()
    expect(timer.mark('confirmed').marks.html_flushed).toBe(1)
  })
})
