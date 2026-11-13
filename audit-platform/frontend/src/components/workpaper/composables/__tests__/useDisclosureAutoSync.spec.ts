/** D4：披露自动同步的 revision / single-flight / latest-pending / 错误恢复。 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const ui = vi.hoisted(() => ({ warning: vi.fn() }))
vi.mock('element-plus', () => ({ ElMessage: { warning: ui.warning } }))

import { useDisclosureAutoSync } from '../useDisclosureAutoSync'

const flush = async () => {
  for (let index = 0; index < 6; index++) await Promise.resolve()
}

describe('useDisclosureAutoSync', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    ui.warning.mockReset()
  })
  afterEach(() => vi.useRealTimers())

  it('连续调度防抖合并为最新 revision 的一次同步', async () => {
    const sync = vi.fn()
    const auto = useDisclosureAutoSync({ debounceMs: 100 })
    auto.scheduleAutoSync(sync)
    auto.scheduleAutoSync(sync)
    auto.scheduleAutoSync(sync)
    expect(auto.pending.value).toBe(true)
    await vi.advanceTimersByTimeAsync(99)
    expect(sync).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1)
    await flush()
    expect(sync).toHaveBeenCalledTimes(1)
    expect(auto.syncRevision.value).toBe(3)
    expect(auto.pending.value).toBe(false)
  })

  it('在飞期间只保留 latest pending，绝不并发或以旧 closure 覆盖新编辑', async () => {
    let releaseFirst!: () => void
    const firstDone = new Promise<void>((resolve) => { releaseFirst = resolve })
    const first = vi.fn(() => firstDone)
    const latest = vi.fn()
    const auto = useDisclosureAutoSync({ debounceMs: 10 })

    auto.scheduleAutoSync(first)
    await vi.advanceTimersByTimeAsync(10)
    await flush()
    expect(first).toHaveBeenCalledTimes(1)
    expect(auto.syncing.value).toBe(true)

    auto.scheduleAutoSync(latest)
    await vi.advanceTimersByTimeAsync(10)
    // 仍在 first 飞行，latest 只能排队，不能并发调用。
    expect(latest).not.toHaveBeenCalled()
    expect(auto.pending.value).toBe(true)

    releaseFirst()
    await flush()
    expect(latest).toHaveBeenCalledTimes(1)
    expect(auto.syncRevision.value).toBe(2)
    expect(auto.syncing.value).toBe(false)
    expect(auto.pending.value).toBe(false)
  })

  it('失败不向保存调用方抛出，但显式可见并可 retry', async () => {
    const first = vi.fn().mockRejectedValueOnce(new Error('网络中断')).mockResolvedValueOnce(undefined)
    const onFailed = vi.fn()
    const auto = useDisclosureAutoSync({ debounceMs: 10, onFailed })

    auto.scheduleAutoSync(first)
    await vi.advanceTimersByTimeAsync(10)
    await flush()

    expect(first).toHaveBeenCalledTimes(1)
    expect(auto.errorMessage.value).toContain('网络中断')
    expect(onFailed).toHaveBeenCalledTimes(1)
    expect(ui.warning).toHaveBeenCalledTimes(1)

    await expect(auto.retry()).resolves.toBe(true)
    expect(first).toHaveBeenCalledTimes(2)
    expect(auto.errorMessage.value).toBe('')
    expect(auto.syncRevision.value).toBe(2)
  })

  it('同一 revision 失败只提示一次，新编辑清除旧错误并改跑最新 closure', async () => {
    const failed = vi.fn().mockRejectedValue(new Error('boom'))
    const next = vi.fn()
    const auto = useDisclosureAutoSync({ debounceMs: 10 })

    auto.scheduleAutoSync(failed)
    await vi.advanceTimersByTimeAsync(10)
    await flush()
    expect(ui.warning).toHaveBeenCalledTimes(1)

    auto.scheduleAutoSync(next)
    expect(auto.errorMessage.value).toBe('')
    await vi.advanceTimersByTimeAsync(10)
    await flush()
    expect(next).toHaveBeenCalledTimes(1)
    expect(ui.warning).toHaveBeenCalledTimes(1)
  })

  it('只读态和只读判定异常都 fail closed', async () => {
    const readonly = { value: true }
    const sync = vi.fn()
    const auto = useDisclosureAutoSync({ debounceMs: 10, isReadonly: () => readonly.value })
    auto.scheduleAutoSync(sync)
    await vi.advanceTimersByTimeAsync(10)
    expect(sync).not.toHaveBeenCalled()
    expect(auto.pending.value).toBe(false)

    const broken = useDisclosureAutoSync({ debounceMs: 10, isReadonly: () => { throw new Error('gate') } })
    broken.scheduleAutoSync(sync)
    await vi.advanceTimersByTimeAsync(10)
    expect(sync).not.toHaveBeenCalled()
  })

  it('cancelPending 只取消尚未开始的最新 revision，不中断在飞请求', async () => {
    const sync = vi.fn()
    const auto = useDisclosureAutoSync({ debounceMs: 10 })
    auto.scheduleAutoSync(sync)
    auto.cancelPending()
    await vi.advanceTimersByTimeAsync(10)
    expect(sync).not.toHaveBeenCalled()
    expect(auto.pending.value).toBe(false)
  })

  it('retry 在无失败或只读态时不发请求', async () => {
    const idle = useDisclosureAutoSync()
    await expect(idle.retry()).resolves.toBe(false)

    const readonly = useDisclosureAutoSync({ isReadonly: () => true })
    readonly.scheduleAutoSync(vi.fn().mockRejectedValue(new Error('unreachable')))
    await vi.advanceTimersByTimeAsync(800)
    await expect(readonly.retry()).resolves.toBe(false)
  })
})
