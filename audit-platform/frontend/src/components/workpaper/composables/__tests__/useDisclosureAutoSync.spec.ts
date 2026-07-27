/**
 * useDisclosureAutoSync 属性测试
 * Spec: disclosure-note-linkage-completion (Req1 / Req7.1)
 * 覆盖 Property 1（防抖合并）/ 2（失败静默不抛）/ 3（只读不触发）/ 4（同源 syncFn）。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useDisclosureAutoSync } from '../useDisclosureAutoSync'

describe('useDisclosureAutoSync', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  // Property 1: 防抖合并 —— 连续多次调度在 debounceMs 内只触发一次
  it('Property1: 防抖合并连续调度为一次', () => {
    const { scheduleAutoSync } = useDisclosureAutoSync({ debounceMs: 800 })
    const syncFn = vi.fn()
    scheduleAutoSync(syncFn)
    scheduleAutoSync(syncFn)
    scheduleAutoSync(syncFn)
    expect(syncFn).not.toHaveBeenCalled() // 尚未到点
    vi.advanceTimersByTime(800)
    expect(syncFn).toHaveBeenCalledTimes(1)
  })

  it('Property1b: 两次调度间隔超过 debounceMs 各触发一次', () => {
    const { scheduleAutoSync } = useDisclosureAutoSync({ debounceMs: 500 })
    const syncFn = vi.fn()
    scheduleAutoSync(syncFn)
    vi.advanceTimersByTime(500)
    scheduleAutoSync(syncFn)
    vi.advanceTimersByTime(500)
    expect(syncFn).toHaveBeenCalledTimes(2)
  })

  // Property 2: 失败静默不抛 —— syncFn reject 时不向上抛异常
  it('Property2: syncFn reject 静默不抛', () => {
    const { scheduleAutoSync } = useDisclosureAutoSync({ debounceMs: 100 })
    const syncFn = vi.fn().mockRejectedValue(new Error('boom'))
    scheduleAutoSync(syncFn)
    // 到点触发不应抛出（异步 reject 被吞）
    expect(() => vi.advanceTimersByTime(100)).not.toThrow()
    expect(syncFn).toHaveBeenCalledTimes(1)
  })

  it('Property2b: syncFn 同步抛出也静默', () => {
    const { scheduleAutoSync } = useDisclosureAutoSync({ debounceMs: 100 })
    const syncFn = vi.fn(() => {
      throw new Error('sync boom')
    })
    scheduleAutoSync(syncFn)
    expect(() => vi.advanceTimersByTime(100)).not.toThrow()
    expect(syncFn).toHaveBeenCalledTimes(1)
  })

  // Property 3: 只读态不触发
  it('Property3: 只读态到点不调 syncFn', () => {
    const readonly = { v: true }
    const { scheduleAutoSync } = useDisclosureAutoSync({
      debounceMs: 100,
      isReadonly: () => readonly.v,
    })
    const syncFn = vi.fn()
    scheduleAutoSync(syncFn)
    vi.advanceTimersByTime(100)
    expect(syncFn).not.toHaveBeenCalled()
  })

  it('Property3b: 非只读态正常触发', () => {
    const { scheduleAutoSync } = useDisclosureAutoSync({
      debounceMs: 100,
      isReadonly: () => false,
    })
    const syncFn = vi.fn()
    scheduleAutoSync(syncFn)
    vi.advanceTimersByTime(100)
    expect(syncFn).toHaveBeenCalledTimes(1)
  })

  it('Property3c: isReadonly 判定抛错时保守跳过', () => {
    const { scheduleAutoSync } = useDisclosureAutoSync({
      debounceMs: 100,
      isReadonly: () => {
        throw new Error('gate boom')
      },
    })
    const syncFn = vi.fn()
    scheduleAutoSync(syncFn)
    expect(() => vi.advanceTimersByTime(100)).not.toThrow()
    expect(syncFn).not.toHaveBeenCalled()
  })

  // Property 4: 同源 syncFn —— 调度传入的 fn 即被调用的 fn（不重新构造）
  it('Property4: 触发的即传入的同一 syncFn', () => {
    const { scheduleAutoSync } = useDisclosureAutoSync({ debounceMs: 100 })
    const manualSync = vi.fn()
    scheduleAutoSync(manualSync)
    vi.advanceTimersByTime(100)
    expect(manualSync).toHaveBeenCalledTimes(1)
  })

  // cancelPending: onBeforeUnmount 清定时器后不触发
  it('cancelPending 清定时器后不触发', () => {
    const { scheduleAutoSync, cancelPending } = useDisclosureAutoSync({ debounceMs: 100 })
    const syncFn = vi.fn()
    scheduleAutoSync(syncFn)
    cancelPending()
    vi.advanceTimersByTime(100)
    expect(syncFn).not.toHaveBeenCalled()
  })

  it('debounceMs 缺省为 800', () => {
    const { scheduleAutoSync } = useDisclosureAutoSync()
    const syncFn = vi.fn()
    scheduleAutoSync(syncFn)
    vi.advanceTimersByTime(799)
    expect(syncFn).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1)
    expect(syncFn).toHaveBeenCalledTimes(1)
  })
})
