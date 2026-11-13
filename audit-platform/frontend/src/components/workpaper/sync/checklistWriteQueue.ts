import { registerPendingFlusher, trackPendingWrite } from './pendingWrites'

export interface ChecklistQueueItem {
  readonly item_id: string
}

export interface ChecklistWriteRetryOptions {
  /** 总尝试次数，包含首次请求；默认 1。 */
  readonly attempts?: number
  /** 首次重试前等待的毫秒数，后续按指数翻倍。 */
  readonly initialDelayMs?: number
}

export interface ChecklistWriteQueueOptions<T extends ChecklistQueueItem> {
  readonly readLatest: (itemId: string) => T | undefined
  /** 唯一真实 HTTP 边界。 */
  readonly persist: (items: T[]) => Promise<void>
  /** 仅用于将最新未确认的 payload 耐久化为草稿；不得在这里发 HTTP。 */
  readonly onPending?: (items: readonly T[]) => void
  /** 只在对应 generation 的成功回执确认后清理草稿。 */
  readonly onSettled?: (items: readonly T[]) => void
  /** 整批收到 4xx 时把最新 pending 载荷标为需人工处理，页面重建后也不能自动重放。 */
  readonly onRecoveryRequired?: (items: readonly T[]) => void
  /** 409/428/423/422 等确定性失败必须冻结旧快照，等待成功重新取基线。 */
  readonly blockOnError?: (error: unknown) => boolean
  /** 仅网络或 5xx 等非确定性失败使用。 */
  readonly retry?: ChecklistWriteRetryOptions
}

export interface ChecklistWriteQueue {
  mark(itemId: string): number
  markMany(itemIds: Iterable<string>): void
  flush(): Promise<void>
  pendingIds(): string[]
  generation(itemId: string): number
  /** 只能在权威 GET 成功后调用；会先废弃被冻结的旧 pending，再解除冲突冻结。 */
  resetBlockedError(): void
  /** 丢弃指定条目的本地 pending generation，不触碰服务器；冲突决策后必须先调用。 */
  discard(itemIds: Iterable<string>): void
  /** 本次成功 GET 前属于被原子拒绝批次的条目，必须逐项由用户处理，不能自动重放。 */
  requiresRecoveryDecision(itemId: string): boolean
  resolveRecoveryDecision(itemIds: Iterable<string>): void
}

type Snapshot = Array<[itemId: string, generation: number]>

function wait(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds))
}

/**
 * checklist 本地写队列：按 item 记录编辑代际，所有真实 PUT 串行，并在请求期间出现新编辑时补存。
 *
 * 成功响应只能清掉它实际保存的 generation。4xx 冲突或拒绝会冻结队列，后续屏障仍会报错，
 * 防止把同一份陈旧 if_match 重发。网络和 5xx 可在同一 CAS 基线内短退避；若退避期间有新
 * 编辑，则废弃旧快照并重新读取最新代际，绝不把旧内容再写回服务器。
 */
export function createChecklistWriteQueue<T extends ChecklistQueueItem>(
  options: ChecklistWriteQueueOptions<T>,
): ChecklistWriteQueue {
  const generations = new Map<string, number>()
  const pending = new Map<string, number>()
  const recoveryDecisionRequired = new Set<string>()
  const retryAttempts = Math.max(1, Math.floor(options.retry?.attempts ?? 1))
  const initialDelayMs = Math.max(0, options.retry?.initialDelayMs ?? 0)
  let nextGeneration = 0
  let flight: Promise<void> | null = null
  let hasBlockedError = false
  let blockedError: unknown

  function mark(itemId: string): number {
    const generation = ++nextGeneration
    generations.set(itemId, generation)
    pending.set(itemId, generation)
    const item = options.readLatest(itemId)
    if (item) {
      const snapshot = [{ ...item } as T]
      if (recoveryDecisionRequired.has(itemId)) options.onRecoveryRequired?.(snapshot)
      else options.onPending?.(snapshot)
    }
    return generation
  }

  function markMany(itemIds: Iterable<string>): void {
    for (const itemId of itemIds) mark(itemId)
  }

  function snapshotIsCurrent(snapshot: Snapshot): boolean {
    return snapshot.every(([itemId, generation]) => pending.get(itemId) === generation)
  }

  function latestPendingItems(): T[] {
    return [...pending.keys()].flatMap((itemId) => {
      const item = options.readLatest(itemId)
      return item ? [{ ...item } as T] : []
    })
  }

  /**
   * 返回 false 表示退避期间出现了更新的本地代际。调用方必须保留整个 snapshot，下一轮从
   * readLatest 重新构造批次，否则同批未变的 item 也会被误删 pending。
   */
  async function persistSnapshot(snapshot: Snapshot): Promise<boolean> {
    const items = snapshot.map(([itemId]) => {
      const item = options.readLatest(itemId)
      if (!item) throw new Error(`待保存的 checklist 条目 ${itemId} 在本地状态中不存在`)
      return { ...item } as T
    })

    for (let attempt = 0; attempt < retryAttempts; attempt += 1) {
      try {
        await trackPendingWrite(Promise.resolve().then(() => options.persist(items)))
        return true
      } catch (error) {
        if (options.blockOnError?.(error)) {
          hasBlockedError = true
          blockedError = error
          const recoveryItems = latestPendingItems()
          for (const item of recoveryItems) recoveryDecisionRequired.add(item.item_id)
          if (recoveryItems.length > 0) options.onRecoveryRequired?.(recoveryItems)
          throw error
        }
        if (attempt + 1 >= retryAttempts) throw error
        // 新编辑必须优先于失败快照，不能让重试反向覆盖本地最新内容。
        if (!snapshotIsCurrent(snapshot)) return false
        await wait(initialDelayMs * (2 ** attempt))
        if (!snapshotIsCurrent(snapshot)) return false
      }
    }
    return true
  }

  async function drain(): Promise<void> {
    while (pending.size > 0) {
      if (hasBlockedError) throw blockedError
      const snapshot: Snapshot = [...pending.entries()]
        .sort(([left], [right]) => left.localeCompare(right))
      const saved = await persistSnapshot(snapshot)
      if (!saved) continue
      const newer: T[] = []
      const settled: T[] = []
      for (const [itemId, savedGeneration] of snapshot) {
        const item = options.readLatest(itemId)
        if (pending.get(itemId) !== savedGeneration) {
          // A 成功时 B 已出现：persist 已用服务端回执推进版本，立即把 B 草稿基线更新为该
          // 回执版本，避免刷新后将本客户端刚保存的 A 误判为外部冲突。
          if (item) newer.push({ ...item } as T)
          continue
        }
        pending.delete(itemId)
        if (item) settled.push({ ...item } as T)
      }
      if (newer.length > 0) options.onPending?.(newer)
      if (settled.length > 0) options.onSettled?.(settled)
    }
  }

  function discard(itemIds: Iterable<string>): void {
    for (const itemId of itemIds) {
      // 失效旧 snapshot 即使仍在 flight 中，也不得在回执后结算或触发下一轮发送。
      generations.set(itemId, ++nextGeneration)
      pending.delete(itemId)
    }
  }

  function flush(): Promise<void> {
    if (flight) return flight
    if (hasBlockedError) return Promise.reject(blockedError)
    if (pending.size === 0) return Promise.resolve()
    const current = drain()
    flight = current
    void current.then(
      () => { if (flight === current) flight = null },
      () => { if (flight === current) flight = null },
    )
    return current
  }

  registerPendingFlusher(flush)

  return {
    mark,
    markMany,
    flush,
    pendingIds: () => [...pending.keys()].sort(),
    generation: (itemId: string) => generations.get(itemId) ?? 0,
    resetBlockedError: () => {
      // 成功 GET 只代表拿到了新基线，不代表旧冲突快照可以重新发送。
      // 先原子废弃整个被拒批次，恢复流程会按用户决定重新 mark 可自动保存的条目。
      if (hasBlockedError) {
        const rejectedIds = [...pending.keys()]
        for (const itemId of rejectedIds) recoveryDecisionRequired.add(itemId)
        discard(rejectedIds)
      }
      hasBlockedError = false
      blockedError = undefined
    },
    discard,
    requiresRecoveryDecision: (itemId: string) => recoveryDecisionRequired.has(itemId),
    resolveRecoveryDecision: (itemIds: Iterable<string>) => {
      for (const itemId of itemIds) recoveryDecisionRequired.delete(itemId)
    },
  }
}
