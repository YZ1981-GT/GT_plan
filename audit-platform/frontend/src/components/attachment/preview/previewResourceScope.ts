export class PreviewResourceScope {
  private objectUrls = new Set<string>()
  private controllers = new Set<AbortController>()
  private workers = new Set<Worker>()
  private cleanups = new Set<() => void>()
  private released = false

  trackObjectUrl(url: string): string {
    if (this.released) {
      try {
        URL.revokeObjectURL(url)
      } catch {
        /* ignore */
      }
      return url
    }
    this.objectUrls.add(url)
    return url
  }

  releaseObjectUrl(url: string): void {
    if (!this.objectUrls.delete(url)) return
    try {
      URL.revokeObjectURL(url)
    } catch {
      /* ignore */
    }
  }

  trackAbortController(controller: AbortController): void {
    if (this.released) {
      try {
        controller.abort()
      } catch {
        /* ignore */
      }
      return
    }
    this.controllers.add(controller)
  }

  untrackAbortController(controller: AbortController): void {
    this.controllers.delete(controller)
  }

  trackWorker(worker: Worker): void {
    if (this.released) {
      try {
        worker.terminate()
      } catch {
        /* ignore */
      }
      return
    }
    this.workers.add(worker)
  }

  untrackWorker(worker: Worker): void {
    this.workers.delete(worker)
  }

  trackCleanup(cleanup: () => void): void {
    if (this.released) {
      try {
        cleanup()
      } catch {
        /* ignore */
      }
      return
    }
    this.cleanups.add(cleanup)
  }

  untrackCleanup(cleanup: () => void): void {
    this.cleanups.delete(cleanup)
  }

  isReleased(): boolean {
    return this.released
  }

  releaseAll(): void {
    if (this.released) return
    this.released = true

    for (const controller of this.controllers) {
      try {
        controller.abort()
      } catch {
        /* ignore */
      }
    }
    this.controllers.clear()

    // Lease cleanups run before the worker fallback loop so each lease owns its
    // one-shot finalize path and terminate is called exactly once.
    const cleanupSnapshot = [...this.cleanups]
    this.cleanups.clear()
    for (const cleanup of cleanupSnapshot) {
      try {
        cleanup()
      } catch {
        /* ignore */
      }
    }

    for (const worker of this.workers) {
      try {
        worker.terminate()
      } catch {
        /* ignore */
      }
    }
    this.workers.clear()

    for (const url of this.objectUrls) {
      try {
        URL.revokeObjectURL(url)
      } catch {
        /* ignore */
      }
    }
    this.objectUrls.clear()
  }

  snapshot(): { objectUrls: number; workers: number; cleanups: number; controllers: number; released: boolean } {
    return {
      objectUrls: this.objectUrls.size,
      workers: this.workers.size,
      cleanups: this.cleanups.size,
      controllers: this.controllers.size,
      released: this.released,
    }
  }
}

export interface WorkerLeaseOptions {
  deadlineMs: number
  generation: number
  isCurrent: (generation: number) => boolean
}

function abortError(message: string): DOMException {
  return new DOMException(message, 'AbortError')
}

type WorkerEnvelope = { requestId?: unknown }

/**
 * One-shot Worker lease. Every terminal path funnels through finalize so timer,
 * listeners, scope registration and the Worker itself are released exactly once.
 */
export function createWorkerLease(
  factory: () => Worker,
  scope: PreviewResourceScope,
  opts: WorkerLeaseOptions,
): {
  post: (payload: unknown, transfer?: Transferable[]) => Promise<unknown>
  terminate: () => void
} {
  const worker = factory()
  let postStarted = false
  let settled = false
  let terminalValue: unknown
  let terminated = false
  let timer: ReturnType<typeof setTimeout> | undefined
  let onMessage: ((event: MessageEvent) => void) | undefined
  let onError: ((event: ErrorEvent) => void) | undefined
  let resolvePending: ((value: unknown) => void) | undefined
  let rejectPending: ((reason?: unknown) => void) | undefined

  const terminateWorker = () => {
    if (terminated) return
    terminated = true
    try {
      worker.terminate()
    } catch {
      /* ignore */
    }
  }

  const onScopeDispose = () => {
    finalize('reject', abortError('worker_scope_disposed'))
  }

  const finalize = (kind: 'resolve' | 'reject', value: unknown): void => {
    if (settled) return
    settled = true
    terminalValue = value
    if (timer !== undefined) clearTimeout(timer)
    if (onMessage) worker.removeEventListener('message', onMessage)
    if (onError) worker.removeEventListener('error', onError)
    scope.untrackCleanup(onScopeDispose)
    scope.untrackWorker(worker)
    terminateWorker()
    if (kind === 'resolve') resolvePending?.(value)
    else rejectPending?.(value)
  }

  if (scope.isReleased()) {
    finalize('reject', abortError('worker_scope_disposed'))
  } else {
    scope.trackWorker(worker)
    scope.trackCleanup(onScopeDispose)
  }

  const post = (payload: unknown, transfer: Transferable[] = []): Promise<unknown> => {
    if (postStarted) return Promise.reject(new Error('worker_lease_already_used'))
    postStarted = true
    if (settled) return Promise.reject(terminalValue ?? abortError('worker_lease_closed'))

    const requestId = (payload as WorkerEnvelope | null)?.requestId
    if (typeof requestId !== 'string' || requestId.length === 0) {
      const error = new Error('worker_request_id_required')
      finalize('reject', error)
      return Promise.reject(error)
    }
    if (scope.isReleased()) {
      const error = abortError('worker_scope_disposed')
      finalize('reject', error)
      return Promise.reject(error)
    }

    return new Promise((resolve, reject) => {
      resolvePending = resolve
      rejectPending = reject

      onMessage = (event: MessageEvent) => {
        const responseRequestId = (event.data as WorkerEnvelope | null)?.requestId
        if (responseRequestId !== requestId) {
          finalize('reject', new Error('worker_request_id_mismatch'))
          return
        }
        if (!opts.isCurrent(opts.generation)) {
          finalize('reject', abortError('worker_generation_stale'))
          return
        }
        finalize('resolve', event.data)
      }
      onError = (event: ErrorEvent) => {
        finalize('reject', event.error ?? new Error(event.message || 'worker_error'))
      }

      worker.addEventListener('message', onMessage)
      worker.addEventListener('error', onError)
      timer = setTimeout(() => {
        finalize('reject', new Error('worker_deadline_exceeded'))
      }, opts.deadlineMs)

      try {
        worker.postMessage(payload, transfer)
      } catch (error) {
        finalize('reject', error)
      }
    })
  }

  const terminate = () => {
    finalize('reject', abortError('worker_lease_terminated'))
  }

  return { post, terminate }
}
