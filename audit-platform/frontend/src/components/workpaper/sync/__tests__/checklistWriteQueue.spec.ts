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

  it('确定性冲突保留 pending，后续 flush 不重发陈旧快照，直到重新取基线后解除', async () => {
    const conflict = Object.assign(new Error('版本冲突'), { response: { status: 409 } })
    const rows = new Map([['x', { item_id: 'x', remark: 'local' }]])
    const persist = vi.fn().mockRejectedValueOnce(conflict).mockResolvedValueOnce(undefined)
    let queue!: ReturnType<typeof createChecklistWriteQueue<{ item_id: string; remark: string }>>
    const scope = effectScope()
    scope.run(() => {
      queue = createChecklistWriteQueue({
        readLatest: (id) => rows.get(id),
        persist,
        blockOnError: (error) => error === conflict,
      })
    })
    scopes.push(scope)

    queue.mark('x')
    await expect(queue.flush()).rejects.toBe(conflict)
    expect(queue.pendingIds()).toEqual(['x'])
    await expect(queue.flush()).rejects.toBe(conflict)
    expect(persist).toHaveBeenCalledTimes(1)

    // 成功 GET 解冻时会废弃冲突前 generation；只能由用户的新编辑重新 mark 后保存。
    queue.resetBlockedError()
    queue.mark('x')
    await expect(queue.flush()).resolves.toBeUndefined()
    expect(persist).toHaveBeenCalledTimes(2)
    expect(queue.pendingIds()).toEqual([])
  })
})


describe('checklist 队列的短退避', () => {
  it('网络或 5xx 在同一 CAS 快照内至多尝试三次，最终失败仍保留 pending', async () => {
    const rows = new Map([['x', { item_id: 'x', remark: 'value' }]])
    const persist = vi.fn().mockRejectedValue(new Error('503'))
    let queue!: ReturnType<typeof createChecklistWriteQueue<{ item_id: string; remark: string }>>
    const scope = effectScope()
    scope.run(() => {
      queue = createChecklistWriteQueue({
        readLatest: (id) => rows.get(id),
        persist,
        retry: { attempts: 3, initialDelayMs: 0 },
      })
    })
    scopes.push(scope)

    queue.mark('x')
    await expect(queue.flush()).rejects.toThrow('503')

    expect(persist).toHaveBeenCalledTimes(3)
    expect(queue.pendingIds()).toEqual(['x'])
  })

  it('退避期间出现新编辑时丢弃旧快照，改由最新 generation 保存', async () => {
    vi.useFakeTimers()
    try {
      const rows = new Map([['x', { item_id: 'x', remark: 'A' }]])
      const saved: string[] = []
      const persist = vi.fn(async (items: Array<{ item_id: string; remark: string }>) => {
        saved.push(items[0].remark)
        if (saved.length === 1) throw new Error('503')
      })
      let queue!: ReturnType<typeof createChecklistWriteQueue<{ item_id: string; remark: string }>>
      const scope = effectScope()
      scope.run(() => {
        queue = createChecklistWriteQueue({
          readLatest: (id) => rows.get(id),
          persist,
          retry: { attempts: 3, initialDelayMs: 500 },
        })
      })
      scopes.push(scope)

      queue.mark('x')
      const flight = queue.flush()
      await Promise.resolve()
      await Promise.resolve()
      expect(saved).toEqual(['A'])

      rows.set('x', { item_id: 'x', remark: 'B' })
      queue.mark('x')
      await vi.advanceTimersByTimeAsync(500)
      await flight

      expect(saved).toEqual(['A', 'B'])
      expect(queue.pendingIds()).toEqual([])
    } finally {
      vi.useRealTimers()
    }
  })
})


it('旧 generation 被 4xx 拒绝后，后续编辑的草稿仍保持最新 payload', async () => {
  const conflict = Object.assign(new Error('版本冲突'), { response: { status: 409 } })
  const first = deferred()
  const rows = new Map([['x', { item_id: 'x', remark: 'A' }]])
  const drafts = new Map<string, string>()
  const recovery = new Map<string, string>()
  const scope = effectScope()
  let queue!: ReturnType<typeof createChecklistWriteQueue<{ item_id: string; remark: string }>>
  scope.run(() => {
    queue = createChecklistWriteQueue({
      readLatest: (id) => rows.get(id),
      persist: async () => first.promise,
      onPending: (items) => {
        for (const item of items) drafts.set(item.item_id, item.remark)
      },
      onSettled: (items) => {
        for (const item of items) drafts.delete(item.item_id)
      },
      onRecoveryRequired: (items) => {
        for (const item of items) recovery.set(item.item_id, item.remark)
      },
      blockOnError: (error) => error === conflict,
    })
  })
  scopes.push(scope)

  queue.mark('x')
  const saving = queue.flush()
  await Promise.resolve()
  rows.set('x', { item_id: 'x', remark: 'B' })
  queue.mark('x')
  const rejected = expect(saving).rejects.toBe(conflict)
  first.reject(conflict)
  await rejected

  expect(drafts.get('x')).toBe('B')
  expect(recovery.get('x')).toBe('B')
  expect(queue.requiresRecoveryDecision('x')).toBe(true)
  rows.set('x', { item_id: 'x', remark: 'C' })
  queue.mark('x')
  expect(recovery.get('x')).toBe('C')
  expect(drafts.get('x')).toBe('B')
  expect(queue.pendingIds()).toEqual(['x'])
})


it('旧 generation 成功回执不能清除较新 generation 的草稿', async () => {
  const first = deferred()
  const second = deferred()
  const secondStarted = deferred()
  const rows = new Map([['x', { item_id: 'x', remark: 'A' }]])
  const drafts = new Map<string, string>()
  const baselines = new Map([['x', 'v1']])
  let calls = 0
  let queue!: ReturnType<typeof createChecklistWriteQueue<{ item_id: string; remark: string }>>
  const scope = effectScope()
  scope.run(() => {
    queue = createChecklistWriteQueue({
      readLatest: (id) => rows.get(id),
      persist: async () => {
        calls += 1
        if (calls === 1) {
          await first.promise
          baselines.set('x', 'v2')
          return
        }
        secondStarted.resolve()
        return second.promise
      },
      onPending: (items) => {
        for (const item of items) drafts.set(item.item_id, `${item.remark}:${baselines.get(item.item_id)}`)
      },
      onSettled: (items) => {
        for (const item of items) drafts.delete(item.item_id)
      },
    })
  })
  scopes.push(scope)

  queue.mark('x')
  const saving = queue.flush()
  await Promise.resolve()
  rows.set('x', { item_id: 'x', remark: 'B' })
  queue.mark('x')
  first.resolve()
  await secondStarted.promise

  expect(drafts.get('x')).toBe('B:v2')
  second.resolve()
  await saving
  expect(drafts.has('x')).toBe(false)
})


it('冲突决策丢弃 pending 后，即使重新获取基线并解除冻结也不会重放旧快照', async () => {
  const conflict = Object.assign(new Error('版本冲突'), { response: { status: 409 } })
  const rows = new Map([['x', { item_id: 'x', remark: '旧本地值' }]])
  const persist = vi.fn().mockRejectedValueOnce(conflict).mockResolvedValue(undefined)
  let queue!: ReturnType<typeof createChecklistWriteQueue<{ item_id: string; remark: string }>>
  const scope = effectScope()
  scope.run(() => {
    queue = createChecklistWriteQueue({
      readLatest: (id) => rows.get(id),
      persist,
      blockOnError: (error) => error === conflict,
    })
  })
  scopes.push(scope)

  queue.mark('x')
  await expect(queue.flush()).rejects.toBe(conflict)
  expect(queue.pendingIds()).toEqual(['x'])

  queue.discard(['x'])
  queue.resetBlockedError()
  await expect(queue.flush()).resolves.toBeUndefined()
  expect(queue.pendingIds()).toEqual([])
  expect(persist).toHaveBeenCalledOnce()
})


it('成功 GET 解冻前原子废弃整批冲突 pending，不能只清第一个条目', async () => {
  const conflict = Object.assign(new Error('版本冲突'), { response: { status: 409 } })
  const rows = new Map([
    ['A', { item_id: 'A', remark: '本地 A' }],
    ['B', { item_id: 'B', remark: '本地 B' }],
  ])
  const persist = vi.fn().mockRejectedValueOnce(conflict).mockResolvedValue(undefined)
  let queue!: ReturnType<typeof createChecklistWriteQueue<{ item_id: string; remark: string }>>
  const scope = effectScope()
  scope.run(() => {
    queue = createChecklistWriteQueue({
      readLatest: (id) => rows.get(id),
      persist,
      blockOnError: (error) => error === conflict,
    })
  })
  scopes.push(scope)

  queue.markMany(['A', 'B'])
  await expect(queue.flush()).rejects.toBe(conflict)
  expect(queue.pendingIds()).toEqual(['A', 'B'])

  queue.resetBlockedError()
  expect(queue.requiresRecoveryDecision('A')).toBe(true)
  expect(queue.requiresRecoveryDecision('B')).toBe(true)
  queue.resolveRecoveryDecision(['A'])
  expect(queue.requiresRecoveryDecision('A')).toBe(false)
  expect(queue.requiresRecoveryDecision('B')).toBe(true)
  await expect(queue.flush()).resolves.toBeUndefined()
  expect(queue.pendingIds()).toEqual([])
  expect(persist).toHaveBeenCalledOnce()
})