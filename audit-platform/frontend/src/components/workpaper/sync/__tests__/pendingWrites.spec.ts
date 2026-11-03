/**
 * 平台待写盘追踪器（spec d2-online-edit-platform-closure R20）。
 *
 * 锁四条：① 登记的防抖 flusher 被调用、scope 停止即注销、scope 外不登记；② 在途写入被等到，
 * 失败在全部写入结算后聚合抛出；③ flusher **同步**发起的追踪写入在同一次 flush 里被等到；
 * ④ H 循环的别名指向同一张注册表。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'

import * as H from '../hPendingWrites'
import {
  PendingWritesFlushError,
  _pendingWriteCounts,
  flushPendingWrites,
  pendingWriteBarrierActive,
  registerPendingFlusher,
  runWithPendingWriteBarrier,
  trackPendingWrite,
} from '../pendingWrites'

function deferred<T = void>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

const scopes: Array<ReturnType<typeof effectScope>> = []
function inScope(fn: () => void): ReturnType<typeof effectScope> {
  const scope = effectScope()
  scope.run(fn)
  scopes.push(scope)
  return scope
}

afterEach(async () => {
  for (const scope of scopes.splice(0)) scope.stop()
  await flushPendingWrites().catch(() => undefined)
})

describe('pendingWrites：防抖 flusher', () => {
  it('scope 内登记的 flusher 被 flush 调用；scope 停止后注销', async () => {
    const flush = vi.fn()
    const before = _pendingWriteCounts().flushers
    const scope = inScope(() => registerPendingFlusher(flush))
    expect(_pendingWriteCounts().flushers).toBe(before + 1)
    await flushPendingWrites()
    expect(flush).toHaveBeenCalledTimes(1)
    scope.stop()
    expect(_pendingWriteCounts().flushers).toBe(before)
    await flushPendingWrites()
    expect(flush).toHaveBeenCalledTimes(1)
  })

  it('scope 外调用不登记（没有可以注销它的时机）', async () => {
    const flush = vi.fn()
    const before = _pendingWriteCounts().flushers
    registerPendingFlusher(flush)
    expect(_pendingWriteCounts().flushers).toBe(before)
    await flushPendingWrites()
    expect(flush).not.toHaveBeenCalled()
  })

  it('一个 flusher 抛错不阻断其余 flusher，并在全部结算后聚合报错', async () => {
    const ok = vi.fn()
    inScope(() => {
      registerPendingFlusher(() => {
        throw new Error('boom')
      })
      registerPendingFlusher(ok)
    })
    await expect(flushPendingWrites()).rejects.toMatchObject({
      name: 'PendingWritesFlushError',
      failures: [expect.objectContaining({ source: 'flusher' })],
    })
    expect(ok).toHaveBeenCalledTimes(1)
  })

  it('flusher 与本轮在途失败一起聚合，且同一错误不重复计数', async () => {
    const write = deferred()
    void trackPendingWrite(write.promise).catch(() => undefined)
    inScope(() => registerPendingFlusher(() => {
      throw new Error('flusher')
    }))
    const barrier = flushPendingWrites()
    write.reject(new Error('in-flight'))
    let caught: unknown
    try {
      await barrier
    } catch (error) {
      caught = error
    }
    expect(caught).toBeInstanceOf(PendingWritesFlushError)
    expect((caught as PendingWritesFlushError).failures.map((f) => f.source).sort()).toEqual([
      'flusher',
      'in_flight',
    ])
    // flusher 仍登记，所以第二轮只报告它；上一轮失败不能污染后续切换。
    await expect(flushPendingWrites()).rejects.toMatchObject({
      failures: [expect.objectContaining({ source: 'flusher' })],
    })
  })

  it('并发屏障共享同一失败结果，不能由后到调用者绕过', async () => {
    const write = deferred()
    inScope(() => registerPendingFlusher(() => {
      void trackPendingWrite(write.promise).catch(() => undefined)
    }))
    const first = flushPendingWrites()
    const second = flushPendingWrites()
    const sharesPromise = second === first
    write.reject(new Error('并发保存失败'))
    const [a, b] = await Promise.allSettled([first, second])
    expect(sharesPromise).toBe(true)
    expect(a.status).toBe('rejected')
    expect(b.status).toBe('rejected')
    expect((a as PromiseRejectedResult).reason).toBe((b as PromiseRejectedResult).reason)
  })
})

describe('pendingWrites：在途写入', () => {
  it('flush 等到在途写入落地才返回', async () => {
    const write = deferred<string>()
    expect(trackPendingWrite(write.promise)).toBe(write.promise)
    let settled = false
    const done = flushPendingWrites().then(() => {
      settled = true
    })
    await Promise.resolve()
    await Promise.resolve()
    expect(settled).toBe(false)
    write.resolve('ok')
    await done
    expect(settled).toBe(true)
    expect(_pendingWriteCounts().inFlight).toBe(0)
  })

  it('本轮在途写入失败保留原 rejection，同时让正在等待的保存屏障 fail-visible', async () => {
    const write = deferred()
    const tracked = trackPendingWrite(write.promise)
    const barrier = flushPendingWrites()
    write.reject(new Error('500'))
    await expect(tracked).rejects.toThrow('500')
    await expect(barrier).rejects.toBeInstanceOf(PendingWritesFlushError)
    await expect(flushPendingWrites()).resolves.toBeUndefined()
  })

  it('flusher 同步发起的追踪写入在同一次 flush 里被等到（D2 子 Tab → 宿主 d2SaveItems 形态）', async () => {
    const write = deferred()
    const order: string[] = []
    inScope(() =>
      registerPendingFlusher(() => {
        order.push('flusher')
        void trackPendingWrite(write.promise.then(() => order.push('written')))
      }),
    )
    const done = flushPendingWrites().then(() => order.push('flushed'))
    await Promise.resolve()
    expect(order).toEqual(['flusher'])
    write.resolve()
    await done
    expect(order).toEqual(['flusher', 'written', 'flushed'])
  })
})

describe('hPendingWrites 是别名，不是第二张注册表', () => {
  it('四个名字逐一指向平台实现', () => {
    expect(H.flushHPendingWrites).toBe(flushPendingWrites)
    expect(H.registerHPendingFlusher).toBe(registerPendingFlusher)
    expect(H.trackHPendingWrite).toBe(trackPendingWrite)
    expect(H._hPendingWriteCounts).toBe(_pendingWriteCounts)
  })
})

describe('pendingWrites：完整切换 lease', () => {
  it('flush 后的投影/配置阶段仍保持 active，完成后才释放', async () => {
    const transition = deferred<string>()
    const operation = runWithPendingWriteBarrier(async () => {
      await flushPendingWrites()
      return transition.promise
    })

    expect(pendingWriteBarrierActive.value).toBe(true)
    await Promise.resolve()
    expect(pendingWriteBarrierActive.value).toBe(true)
    transition.resolve('done')
    await expect(operation).resolves.toBe('done')
    expect(pendingWriteBarrierActive.value).toBe(false)
  })

  it('并发与嵌套 lease 由深度计数，先完成的一方不会提前解冻', async () => {
    const first = deferred()
    const second = deferred()
    const a = runWithPendingWriteBarrier(() => first.promise)
    const b = runWithPendingWriteBarrier(() =>
      runWithPendingWriteBarrier(() => second.promise),
    )
    expect(pendingWriteBarrierActive.value).toBe(true)

    first.resolve()
    await a
    expect(pendingWriteBarrierActive.value).toBe(true)

    second.resolve()
    await b
    expect(pendingWriteBarrierActive.value).toBe(false)
  })

  it('过渡失败也在 finally 释放 lease', async () => {
    await expect(runWithPendingWriteBarrier(async () => {
      throw new Error('materialize failed')
    })).rejects.toThrow('materialize failed')
    expect(pendingWriteBarrierActive.value).toBe(false)
  })
})

// ─── 屏障错误文案必须可定位（design §8 残留 4） ───────────────────────────────
describe('PendingWritesFlushError 的可定位文案', () => {
  it('把原始失败原因摊进文案，不只给计数', () => {
    const error = new PendingWritesFlushError([
      { source: 'flusher', error: new Error('F2-68 保存失败：409 版本冲突') },
      { source: 'in_flight', error: { response: { data: { message: '底稿已归档，不能修改' } } } },
    ])
    expect(error.message).toContain('有 2 项内容保存失败')
    expect(error.message).toContain('409 版本冲突')
    expect(error.message).toContain('底稿已归档，不能修改')
    expect(error.reasons).toEqual([
      'F2-68 保存失败：409 版本冲突',
      '底稿已归档，不能修改',
    ])
  })

  it('同类原因去重，超过 3 类时折叠计数（文案不被撑爆）', () => {
    const many = Array.from({ length: 5 }, (_, i) => ({
      source: 'in_flight' as const,
      error: new Error(`原因${i}`),
    }))
    const dup = [
      { source: 'flusher' as const, error: new Error('同一个原因') },
      { source: 'in_flight' as const, error: new Error('同一个原因') },
    ]
    expect(new PendingWritesFlushError(dup).reasons).toEqual(['同一个原因'])
    const error = new PendingWritesFlushError(many)
    expect(error.reasons).toHaveLength(5)
    expect(error.message).toContain('另有 2 类原因')
  })

  it('取不到任何可读信息时给「未知错误」，不产出空冒号', () => {
    const error = new PendingWritesFlushError([{ source: 'in_flight', error: null }])
    expect(error.reasons).toEqual(['未知错误'])
    expect(error.message).toContain('未知错误')
    expect(error.message).not.toContain('：：')
  })
})
