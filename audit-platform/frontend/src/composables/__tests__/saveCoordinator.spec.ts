import { describe, expect, it, vi } from 'vitest'
import { createSaveCoordinator } from '../saveCoordinator'

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

describe('createSaveCoordinator', () => {
  it('保存期间继续编辑时严格串行补存最新代际', async () => {
    const coordinator = createSaveCoordinator<string>()
    const first = deferred<boolean>()
    const revisions: number[] = []
    let active = 0
    let maxActive = 0
    const saveOnce = vi.fn(async ({ revision }: { revision: number }) => {
      revisions.push(revision)
      active += 1
      maxActive = Math.max(maxActive, active)
      if (revision === 1) await first.promise
      active -= 1
      return true
    })

    coordinator.markEdited('doc')
    const pending = coordinator.run('doc', saveOnce)
    coordinator.markEdited('doc')
    const joined = coordinator.run('doc', saveOnce)

    expect(joined).toBe(pending)
    expect(revisions).toEqual([1])
    first.resolve(true)
    await expect(pending).resolves.toBe(true)
    expect(revisions).toEqual([1, 2])
    expect(maxActive).toBe(1)
    expect(coordinator.isDirty('doc')).toBe(false)
  })

  it('显式 false 不确认代际并保留 dirty', async () => {
    const coordinator = createSaveCoordinator<string>()
    coordinator.markEdited('doc')

    await expect(coordinator.run('doc', async () => false)).resolves.toBe(false)

    expect(coordinator.isDirty('doc')).toBe(true)
    expect(coordinator.savedRevision('doc')).toBe(0)
  })

  it('异常不确认代际并原样向调用方抛出', async () => {
    const coordinator = createSaveCoordinator<string>()
    coordinator.markEdited('doc')
    const error = new Error('network')

    await expect(coordinator.run('doc', async () => { throw error })).rejects.toBe(error)
    expect(coordinator.isDirty('doc')).toBe(true)
  })

  it('明确放弃会使在途旧回执失效', async () => {
    const coordinator = createSaveCoordinator<string>()
    const gate = deferred<boolean>()
    coordinator.markEdited('doc')
    const pending = coordinator.run('doc', async ({ isCurrent }) => {
      await gate.promise
      return isCurrent()
    })

    coordinator.discard('doc')
    gate.resolve(true)

    await expect(pending).resolves.toBe(false)
    expect(coordinator.isDirty('doc')).toBe(false)
  })

  it('不同文档互不共用在途请求', async () => {
    const coordinator = createSaveCoordinator<string>()
    const a = deferred<boolean>()
    const b = deferred<boolean>()
    coordinator.markEdited('a')
    coordinator.markEdited('b')

    const saveA = coordinator.run('a', async () => a.promise)
    const saveB = coordinator.run('b', async () => b.promise)
    expect(coordinator.isSaving('a')).toBe(true)
    expect(coordinator.isSaving('b')).toBe(true)

    a.resolve(true)
    b.resolve(true)
    await expect(Promise.all([saveA, saveB])).resolves.toEqual([true, true])
  })
})