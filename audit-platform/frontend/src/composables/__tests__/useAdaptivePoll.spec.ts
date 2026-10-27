/**
 * 自适应轮询（spec procedure-chain-hardening-and-java-contracts R17）：有进行中的任务每 5 秒、没有每 30 秒；
 * 页面隐藏暂停、可见立即查；poke 立即查且不叠出第二条链。
 * 顶栏导入指示器与项目概览面板原先固定每 5 秒 setInterval，没有导入任务时也一直查。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'
import { POLL_ACTIVE_MS, POLL_IDLE_MS, useAdaptivePoll } from '../useAdaptivePoll'

let hidden = false
beforeEach(() => {
  hidden = false
  Object.defineProperty(document, 'hidden', { configurable: true, get: () => hidden })
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
})
afterEach(() => {
  vi.useRealTimers()
})

function setHidden(v: boolean) {
  hidden = v
  document.dispatchEvent(new Event('visibilitychange'))
}

describe('useAdaptivePoll', () => {
  it('没有进行中的任务：查一次后 30 秒才再查（原先 5 秒）', async () => {
    const tick = vi.fn().mockResolvedValue(false)
    const p = useAdaptivePoll(tick)
    p.start()
    await vi.advanceTimersByTimeAsync(0)
    expect(tick).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(POLL_IDLE_MS - 1)
    expect(tick).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1)
    expect(tick).toHaveBeenCalledTimes(2)
    p.dispose()
  })

  it('有进行中的任务：每 5 秒；任务结束后回到 30 秒', async () => {
    const tick = vi.fn().mockResolvedValueOnce(true).mockResolvedValueOnce(true).mockResolvedValue(false)
    const p = useAdaptivePoll(tick)
    p.start()
    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(POLL_ACTIVE_MS)
    expect(tick).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(POLL_ACTIVE_MS)
    expect(tick).toHaveBeenCalledTimes(3)  // 第 3 次返回 false
    await vi.advanceTimersByTimeAsync(POLL_ACTIVE_MS)
    expect(tick).toHaveBeenCalledTimes(3)
    await vi.advanceTimersByTimeAsync(POLL_IDLE_MS - POLL_ACTIVE_MS)
    expect(tick).toHaveBeenCalledTimes(4)
    p.dispose()
  })

  it('页面隐藏时不查；重新可见立即查一次并恢复', async () => {
    const tick = vi.fn().mockResolvedValue(true)
    const p = useAdaptivePoll(tick)
    p.start()
    await vi.advanceTimersByTimeAsync(0)
    setHidden(true)
    await vi.advanceTimersByTimeAsync(POLL_IDLE_MS * 3)
    expect(tick).toHaveBeenCalledTimes(1)
    setHidden(false)
    await vi.advanceTimersByTimeAsync(0)
    expect(tick).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(POLL_ACTIVE_MS)
    expect(tick).toHaveBeenCalledTimes(3)
    p.dispose()
  })

  it('poke：立即查一次，作废等待中的那一轮（不叠出第二条链）', async () => {
    const tick = vi.fn().mockResolvedValue(false)
    const p = useAdaptivePoll(tick)
    p.start()
    await vi.advanceTimersByTimeAsync(10_000)
    p.poke()
    await vi.advanceTimersByTimeAsync(0)
    expect(tick).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(POLL_IDLE_MS - 1)
    expect(tick).toHaveBeenCalledTimes(2)  // 原链 20 秒后那一轮已作废
    await vi.advanceTimersByTimeAsync(1)
    expect(tick).toHaveBeenCalledTimes(3)
    p.dispose()
  })

  it('stop 之后晚到的结果不续链；未 start 时 poke 不查', async () => {
    let release!: (v: boolean) => void
    const tick = vi.fn(() => new Promise<boolean>((r) => { release = r }))
    const p = useAdaptivePoll(tick)
    p.poke()
    expect(tick).not.toHaveBeenCalled()
    p.start()
    await vi.advanceTimersByTimeAsync(0)
    p.stop()
    release(true)
    await vi.advanceTimersByTimeAsync(POLL_IDLE_MS * 2)
    expect(tick).toHaveBeenCalledTimes(1)
    p.dispose()
  })

  it('tick 抛错按空闲处理（30 秒后再查），不中断轮询', async () => {
    const tick = vi.fn().mockRejectedValueOnce(new Error('network')).mockResolvedValue(false)
    const p = useAdaptivePoll(tick)
    p.start()
    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(POLL_IDLE_MS)
    expect(tick).toHaveBeenCalledTimes(2)
    p.dispose()
  })

  it('在 effect scope 里创建：scope 结束自动停止并移除可见性监听', async () => {
    const tick = vi.fn().mockResolvedValue(true)
    const remove = vi.spyOn(document, 'removeEventListener')
    const scope = effectScope()
    const p = scope.run(() => useAdaptivePoll(tick))!
    p.start()
    await vi.advanceTimersByTimeAsync(0)
    scope.stop()
    expect(remove).toHaveBeenCalledWith('visibilitychange', expect.any(Function))
    await vi.advanceTimersByTimeAsync(POLL_IDLE_MS)
    expect(tick).toHaveBeenCalledTimes(1)
    setHidden(true)
    setHidden(false)
    await vi.advanceTimersByTimeAsync(0)
    expect(tick).toHaveBeenCalledTimes(1)
    remove.mockRestore()
  })
})

describe('导入进度轮询的两个使用方（源码守卫）', () => {
  it('顶栏与项目概览面板都改用 useAdaptivePoll，不再固定 5 秒 setInterval；提交导入后 poke', async () => {
    const fs = await import('node:fs')
    const path = await import('node:path')
    const src = path.resolve(__dirname, '..', '..')
    const read = (rel: string) => fs.readFileSync(path.join(src, rel), 'utf-8')
    const layout = read('layouts/ThreeColumnLayout.vue')
    const panel = read('components/layout/DetailProjectPanel.vue')
    expect(layout).toMatch(/useAdaptivePoll\(pollImportQueue\)/)
    // 顶栏没有挂载用例：至少钉住「进行中返回 true、追踪中出错按进行中节奏」这两处决定节奏的返回值
    const fn = layout.slice(layout.indexOf('async function pollImportQueue'), layout.indexOf('const importPoll = useAdaptivePoll'))
    expect(fn).toMatch(/trackedProjectId\.value = trackId\s*\n\s*\}\s*\n\s*return true/)
    expect(fn).toMatch(/return !!trackedProjectId\.value/)
    expect(panel).toMatch(/useAdaptivePoll\(pollImportStatus\)/)
    for (const s of [layout, panel]) {
      expect(s).not.toMatch(/setInterval\(poll/)
      expect(s).toMatch(/eventBus\.on\('ledger-import:submitted'/)
      expect(s).toMatch(/eventBus\.off\('ledger-import:submitted'/)
    }
    for (const rel of ['components/ledger-import/LedgerImportDialog.vue', 'views/LedgerImportPage.vue']) {
      const s = read(rel)
      const at = s.indexOf('jobId.value = (res as { job_id: string }).job_id')
      expect(at, rel).toBeGreaterThan(0)
      expect(s.slice(at, at + 200), rel).toMatch(/eventBus\.emit\('ledger-import:submitted'/)
    }
  })
})
