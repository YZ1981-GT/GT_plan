import { describe, expect, it, vi } from 'vitest'
import { PreviewResourceScope, createWorkerLease } from '../previewResourceScope'

class FakeWorker {
  readonly postMessage = vi.fn()
  readonly terminate = vi.fn()
  readonly addEventListener = vi.fn((type: string, listener: EventListener) => {
    this.listeners[type]?.add(listener)
  })
  readonly removeEventListener = vi.fn((type: string, listener: EventListener) => {
    this.listeners[type]?.delete(listener)
  })
  private listeners: Record<string, Set<EventListener>> = {
    message: new Set(),
    error: new Set(),
  }

  emitMessage(data: unknown): void {
    const event = { data } as MessageEvent
    for (const listener of this.listeners.message) listener(event as unknown as Event)
  }

  emitError(message = 'boom'): void {
    const event = { message, error: new Error(message) } as ErrorEvent
    for (const listener of this.listeners.error) listener(event as unknown as Event)
  }

  listenerCount(type: 'message' | 'error'): number {
    return this.listeners[type].size
  }
}

function leaseFor(worker: FakeWorker, scope = new PreviewResourceScope(), isCurrent = () => true) {
  return {
    scope,
    lease: createWorkerLease(() => worker as unknown as Worker, scope, {
      deadlineMs: 100,
      generation: 1,
      isCurrent,
    }),
  }
}

describe('PreviewResourceScope', () => {
  it('releaseAll 幂等且 late-track 资源立即释放', () => {
    if (typeof URL.revokeObjectURL !== 'function') {
      ;(URL as any).revokeObjectURL = () => undefined
    }
    const revoke = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
    const scope = new PreviewResourceScope()
    const firstController = new AbortController()
    const firstWorker = { terminate: vi.fn() } as unknown as Worker
    const firstCleanup = vi.fn()
    scope.trackObjectUrl('blob:a')
    scope.trackAbortController(firstController)
    scope.trackWorker(firstWorker)
    scope.trackCleanup(firstCleanup)

    scope.releaseAll()
    scope.releaseAll()

    const lateController = new AbortController()
    const lateWorker = { terminate: vi.fn() } as unknown as Worker
    const lateCleanup = vi.fn()
    scope.trackObjectUrl('blob:late')
    scope.trackAbortController(lateController)
    scope.trackWorker(lateWorker)
    scope.trackCleanup(lateCleanup)

    expect(scope.snapshot()).toEqual({
      objectUrls: 0,
      workers: 0,
      cleanups: 0,
      controllers: 0,
      released: true,
    })
    expect(firstController.signal.aborted).toBe(true)
    expect(firstWorker.terminate).toHaveBeenCalledTimes(1)
    expect(firstCleanup).toHaveBeenCalledTimes(1)
    expect(lateController.signal.aborted).toBe(true)
    expect(lateWorker.terminate).toHaveBeenCalledTimes(1)
    expect(lateCleanup).toHaveBeenCalledTimes(1)
    expect(revoke).toHaveBeenCalledWith('blob:a')
    expect(revoke).toHaveBeenCalledWith('blob:late')
    revoke.mockRestore()
  })
})

describe('createWorkerLease', () => {
  it('匹配 requestId 后 resolve，并清 listener/timer/登记且 terminate 一次', async () => {
    const worker = new FakeWorker()
    const { lease, scope } = leaseFor(worker)
    const bytes = new ArrayBuffer(4)
    const pending = lease.post({ requestId: 'req-1', bytes }, [bytes])
    expect(worker.postMessage).toHaveBeenCalledWith(
      expect.objectContaining({ requestId: 'req-1', bytes }),
      [bytes],
    )

    worker.emitMessage({ requestId: 'req-1', ok: true })
    await expect(pending).resolves.toEqual({ requestId: 'req-1', ok: true })
    expect(worker.terminate).toHaveBeenCalledTimes(1)
    expect(worker.listenerCount('message')).toBe(0)
    expect(worker.listenerCount('error')).toBe(0)
    expect(scope.snapshot()).toMatchObject({ workers: 0, cleanups: 0 })
    scope.releaseAll()
    expect(worker.terminate).toHaveBeenCalledTimes(1)
    await expect(lease.post({ requestId: 'req-2' })).rejects.toThrow('already_used')
  })

  it('响应 requestId 不匹配时拒绝并 finalize', async () => {
    const worker = new FakeWorker()
    const { lease, scope } = leaseFor(worker)
    const pending = lease.post({ requestId: 'expected' })
    worker.emitMessage({ requestId: 'other', ok: true })
    await expect(pending).rejects.toThrow('request_id_mismatch')
    expect(worker.terminate).toHaveBeenCalledTimes(1)
    expect(scope.snapshot()).toMatchObject({ workers: 0, cleanups: 0 })
  })

  it('error、deadline 和 stale message 都走同一 finalize', async () => {
    const errorWorker = new FakeWorker()
    const errorLease = leaseFor(errorWorker).lease
    const errorPending = errorLease.post({ requestId: 'error' })
    errorWorker.emitError('worker exploded')
    await expect(errorPending).rejects.toThrow('worker exploded')
    expect(errorWorker.terminate).toHaveBeenCalledTimes(1)

    const deadlineWorker = new FakeWorker()
    const deadlineScope = new PreviewResourceScope()
    const deadlineLease = createWorkerLease(() => deadlineWorker as unknown as Worker, deadlineScope, {
      deadlineMs: 5,
      generation: 1,
      isCurrent: () => true,
    })
    await expect(deadlineLease.post({ requestId: 'deadline' })).rejects.toThrow('deadline')
    expect(deadlineWorker.terminate).toHaveBeenCalledTimes(1)
    expect(deadlineScope.snapshot()).toMatchObject({ workers: 0, cleanups: 0 })

    const staleWorker = new FakeWorker()
    const staleLease = leaseFor(staleWorker, new PreviewResourceScope(), () => false).lease
    const stalePending = staleLease.post({ requestId: 'stale' })
    staleWorker.emitMessage({ requestId: 'stale', ok: true })
    await expect(stalePending).rejects.toMatchObject({ name: 'AbortError' })
    expect(staleWorker.terminate).toHaveBeenCalledTimes(1)
  })

  it('已释放 scope 上创建 lease 时只 terminate 一次，post 立即 AbortError', async () => {
    const scope = new PreviewResourceScope()
    scope.releaseAll()
    const worker = new FakeWorker()
    const lease = leaseFor(worker, scope).lease

    await expect(lease.post({ requestId: 'late' })).rejects.toMatchObject({ name: 'AbortError' })
    expect(worker.postMessage).not.toHaveBeenCalled()
    expect(worker.terminate).toHaveBeenCalledTimes(1)
    expect(scope.snapshot()).toMatchObject({ workers: 0, cleanups: 0, released: true })
  })

  it('scope dispose 与显式 terminate 立即以 AbortError 结算 pending Promise', async () => {
    const scopeWorker = new FakeWorker()
    const { lease: scopeLease, scope } = leaseFor(scopeWorker)
    const scopePending = scopeLease.post({ requestId: 'scope' })
    scope.releaseAll()
    await expect(scopePending).rejects.toMatchObject({ name: 'AbortError' })
    expect(scopeWorker.terminate).toHaveBeenCalledTimes(1)

    const manualWorker = new FakeWorker()
    const { lease: manualLease } = leaseFor(manualWorker)
    const manualPending = manualLease.post({ requestId: 'manual' })
    manualLease.terminate()
    await expect(manualPending).rejects.toMatchObject({ name: 'AbortError' })
    expect(manualWorker.terminate).toHaveBeenCalledTimes(1)
  })
})
