/**
 * 平台待写盘追踪器（spec d2-online-edit-platform-closure R20）。
 *
 * 锁四条：① 登记的防抖 flusher 被调用、scope 停止即注销、scope 外不登记；② 在途写入被等到、
 * 失败的写入不让 flush 整体 reject；③ flusher **同步**发起的追踪写入在同一次 flush 里被等到
 * （这正是 D2 子 Tab → 宿主 d2SaveItems 的形态）；④ H 循环的别名指向同一张注册表。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'

import * as H from '../hPendingWrites'
import {
  _pendingWriteCounts,
  flushPendingWrites,
  registerPendingFlusher,
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
  await flushPendingWrites()
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

  it('一个 flusher 抛错不阻断其余 flusher，也不让 flush reject', async () => {
    const ok = vi.fn()
    inScope(() => {
      registerPendingFlusher(() => {
        throw new Error('boom')
      })
      registerPendingFlusher(ok)
    })
    await expect(flushPendingWrites()).resolves.toBeUndefined()
    expect(ok).toHaveBeenCalledTimes(1)
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

  it('失败的写入不让 flush reject（失败由调用方自己提示）', async () => {
    const write = deferred()
    const tracked = trackPendingWrite(write.promise)
    write.reject(new Error('500'))
    await expect(tracked).rejects.toThrow('500')
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
