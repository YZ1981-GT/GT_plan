import { effectScope } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createChecklistWriteQueue } from '../checklistWriteQueue'
import { flushPendingWrites } from '../pendingWrites'

function deferred<T = void>() {
  let resolve!: (value: T | PromiseLike<T>) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

const scopes: Array<ReturnType<typeof effectScope>> = []
afterEach(async () => {
  for (const scope of scopes.splice(0)) scope.stop()
  await flushPendingWrites().catch(() => undefined)
})

describe('checklist generation-safe 串行保存队列', () => {
  it('请求 A 在途时编辑 B，A 成功不能清 B，随后自动补存 B', async () => {
    const first = deferred()
    const rows = new Map([['x', { item_id: 'x', remark: 'A' }]])
    const saved: string[] = []
    const persist = vi.fn(async (items: Array<{ item_id: string; remark: string }>) => {
      saved.push(items[0].remark)
      if (saved.length === 1) await first.promise
    })
    let queue!: ReturnType<typeof createChecklistWriteQueue<{ item_id: string; remark: string }>>
    const scope = effectScope()
    scope.run(() => { queue = createChecklistWriteQueue({ readLatest: (id) => rows.get(id), persist }) })
    scopes.push(scope)

    queue.mark('x')
    const flight = queue.flush()
    await Promise.resolve()
    rows.set('x', { item_id: 'x', remark: 'B' })
    queue.mark('x')
    first.resolve()
    await flight

    expect(saved).toEqual(['A', 'B'])
    expect(queue.pendingIds()).toEqual([])
  })

  it('失败保留最新 pending，重试成功后才清除', async () => {
    const rows = new Map([['x', { item_id: 'x', remark: 'value' }]])
    const persist = vi.fn()
      .mockRejectedValueOnce(new Error('500'))
      .mockResolvedValueOnce(undefined)
    let queue!: ReturnType<typeof createChecklistWriteQueue<{ item_id: string; remark: string }>>
    const scope = effectScope()
    scope.run(() => { queue = createChecklistWriteQueue({ readLatest: (id) => rows.get(id), persist }) })
    scopes.push(scope)

    queue.mark('x')
    await expect(queue.flush()).rejects.toThrow('500')
    expect(queue.pendingIds()).toEqual(['x'])
    await expect(queue.flush()).resolves.toBeUndefined()
    expect(queue.pendingIds()).toEqual([])
  })
  it('并发 flush 返回同一 flight，真实 persist 不并发', async () => {
    const hold = deferred()
    const rows = new Map([['x', { item_id: 'x', remark: 'value' }]])
    const persist = vi.fn(async () => hold.promise)
    let queue!: ReturnType<typeof createChecklistWriteQueue<{ item_id: string; remark: string }>>
    const scope = effectScope()
    scope.run(() => { queue = createChecklistWriteQueue({ readLatest: (id) => rows.get(id), persist }) })
    scopes.push(scope)

    queue.mark('x')
    const first = queue.flush()
    const second = queue.flush()
    expect(second).toBe(first)
    hold.resolve()
    await first
    expect(persist).toHaveBeenCalledOnce()
  })
})