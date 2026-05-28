/**
 * Property 13: autoSave 不丢失不变量 [V3 Req 12.5]
 *
 * **Validates: Requirements 12.3**
 *
 * 不变量：
 * P13.1: 默认间隔 60s 触发 doSave
 * P13.2: 10 次 recordEdit 后间隔缩短到 30s
 * P13.3: 保存失败立即重试 1 次，仍失败则 isSaveFailed=true
 * P13.4: beforeunload 触发 sendBeacon
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'

// Mock vue lifecycle hooks
vi.mock('vue', async () => {
  const actual = await vi.importActual('vue')
  return {
    ...actual as any,
    onMounted: (fn: () => void) => fn(),
    onUnmounted: (_fn: () => void) => { /* no-op in test */ },
  }
})

// Mock api
vi.mock('@/services/apiProxy', () => ({
  api: { post: vi.fn() },
}))

import { useWorkpaperAutoSave } from '../useWorkpaperAutoSave'

describe('Property 13: autoSave 不丢失不变量', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    // Mock navigator.sendBeacon
    Object.defineProperty(globalThis.navigator, 'sendBeacon', {
      value: vi.fn(() => true),
      writable: true,
      configurable: true,
    })
    // Remove any leftover beforeunload listeners
    ;(window as any).removeAllListeners?.('beforeunload')
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
    // Clean up all beforeunload listeners by replacing with fresh ones
    const listeners = (window as any).__beforeunloadListeners || []
    listeners.forEach((fn: any) => window.removeEventListener('beforeunload', fn))
  })

  it('P13.1: 默认间隔 60s 触发 doSave', async () => {
    const saveFn = vi.fn().mockResolvedValue(undefined)
    const { isDirty, markDirty } = useWorkpaperAutoSave(saveFn, 60_000)

    markDirty()
    expect(isDirty.value).toBe(true)

    // 59s 不触发
    await vi.advanceTimersByTimeAsync(59_000)
    expect(saveFn).not.toHaveBeenCalled()

    // 60s 触发
    await vi.advanceTimersByTimeAsync(1_000)
    expect(saveFn).toHaveBeenCalledTimes(1)
  })

  it('P13.2: 10 次 recordEdit 后间隔缩短到 30s', async () => {
    const saveFn = vi.fn().mockResolvedValue(undefined)
    const { recordEdit, currentIntervalMs } = useWorkpaperAutoSave(saveFn, 60_000)

    // 初始间隔 60s
    expect(currentIntervalMs.value).toBe(60_000)

    // 触发 10 次编辑
    for (let i = 0; i < 10; i++) {
      recordEdit()
    }

    // 间隔应缩短到 30s
    expect(currentIntervalMs.value).toBe(30_000)
  })

  it('P13.3: 保存失败立即重试 1 次，仍失败则 isSaveFailed=true', async () => {
    const saveFn = vi.fn()
      .mockRejectedValueOnce(new Error('network error'))
      .mockRejectedValueOnce(new Error('network error again'))
    const { isDirty, markDirty, doSave, isSaveFailed } = useWorkpaperAutoSave(saveFn, 60_000)

    markDirty()
    await doSave()

    // 调用了 2 次（原始 + 重试）
    expect(saveFn).toHaveBeenCalledTimes(2)
    // 仍失败
    expect(isSaveFailed.value).toBe(true)
    // 数据仍标记为 dirty（未成功保存）
    expect(isDirty.value).toBe(true)
  })

  it('P13.3b: 保存失败重试成功则 isSaveFailed=false', async () => {
    const saveFn = vi.fn()
      .mockRejectedValueOnce(new Error('network error'))
      .mockResolvedValueOnce(undefined)
    const { markDirty, doSave, isSaveFailed, isDirty } = useWorkpaperAutoSave(saveFn, 60_000)

    markDirty()
    await doSave()

    // 重试成功
    expect(saveFn).toHaveBeenCalledTimes(2)
    expect(isSaveFailed.value).toBe(false)
    expect(isDirty.value).toBe(false)
  })

  it('P13.4: beforeunload 触发 sendBeacon', () => {
    const saveFn = vi.fn().mockResolvedValue(undefined)
    const beaconUrl = '/api/workpapers/123/save'
    const serializeForBeacon = vi.fn(() => JSON.stringify({ data: 'test' }))

    const { markDirty } = useWorkpaperAutoSave(saveFn, 60_000, undefined, {
      saveBeaconUrl: beaconUrl,
      serializeForBeacon,
    })

    markDirty()

    // 触发 beforeunload
    window.dispatchEvent(new Event('beforeunload'))

    expect(navigator.sendBeacon).toHaveBeenCalledWith(beaconUrl, JSON.stringify({ data: 'test' }))
  })

  it('P13.4b: 非 dirty 时 beforeunload 不触发 sendBeacon', () => {
    // Fresh sendBeacon mock for this test
    const sendBeaconMock = vi.fn(() => true)
    Object.defineProperty(globalThis.navigator, 'sendBeacon', {
      value: sendBeaconMock,
      writable: true,
      configurable: true,
    })

    const saveFn = vi.fn().mockResolvedValue(undefined)
    const beaconUrl = '/api/workpapers/456/save'
    const serializeForBeacon = vi.fn(() => JSON.stringify({ data: 'test2' }))

    // 不调用 markDirty
    useWorkpaperAutoSave(saveFn, 60_000, undefined, {
      saveBeaconUrl: beaconUrl,
      serializeForBeacon,
    })

    // 触发 beforeunload — isDirty=false 时不应调用 sendBeacon
    window.dispatchEvent(new Event('beforeunload'))

    // 检查这个特定 URL 没有被调用
    const calls = sendBeaconMock.mock.calls.filter(
      (call: any[]) => call[0] === beaconUrl,
    )
    expect(calls).toHaveLength(0)
  })

  it('P13.1b: 保存成功后 editCount 重置 + 间隔恢复', async () => {
    const saveFn = vi.fn().mockResolvedValue(undefined)
    const { recordEdit, doSave, currentIntervalMs } = useWorkpaperAutoSave(saveFn, 60_000)

    // 触发 10 次编辑 → 快速模式
    for (let i = 0; i < 10; i++) recordEdit()
    expect(currentIntervalMs.value).toBe(30_000)

    // 保存成功
    await doSave()

    // 间隔恢复
    expect(currentIntervalMs.value).toBe(60_000)
  })
})
