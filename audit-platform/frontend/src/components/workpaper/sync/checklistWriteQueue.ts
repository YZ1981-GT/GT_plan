import { registerPendingFlusher, trackPendingWrite } from './pendingWrites'

export interface ChecklistQueueItem {
  readonly item_id: string
}

export interface ChecklistWriteQueueOptions<T extends ChecklistQueueItem> {
  readonly readLatest: (itemId: string) => T | undefined
  readonly persist: (items: T[]) => Promise<void>
}

export interface ChecklistWriteQueue {
  mark(itemId: string): number
  markMany(itemIds: Iterable<string>): void
  flush(): Promise<void>
  pendingIds(): string[]
  generation(itemId: string): number
}

/**
 * checklist 本地写队列：按 item 记录编辑代际，所有真实 PUT 串行，并在请求期间出现新编辑时补存。
 *
 * 成功响应只能清掉它实际保存的 generation。失败保留 pending；下一次 timer、显式保存或
 * OnlyOffice 保存屏障会重试最新快照。队列的 persist 是唯一真实 HTTP 边界，因此在这里
 * 统一纳入 pendingWrites in-flight。
 */
export function createChecklistWriteQueue<T extends ChecklistQueueItem>(
  options: ChecklistWriteQueueOptions<T>,
): ChecklistWriteQueue {
  const generations = new Map<string, number>()
  const pending = new Map<string, number>()
  let nextGeneration = 0
  let flight: Promise<void> | null = null

  function mark(itemId: string): number {
    const generation = ++nextGeneration
    generations.set(itemId, generation)
    pending.set(itemId, generation)
    return generation
  }

  function markMany(itemIds: Iterable<string>): void {
    for (const itemId of itemIds) mark(itemId)
  }

  async function drain(): Promise<void> {
    while (pending.size > 0) {
      const snapshot = [...pending.entries()].sort(([left], [right]) => left.localeCompare(right))
      const items = snapshot.map(([itemId]) => {
        const item = options.readLatest(itemId)
        if (!item) throw new Error(`待保存的 checklist 条目 ${itemId} 在本地状态中不存在`)
        return item
      })
      await trackPendingWrite(Promise.resolve().then(() => options.persist(items)))
      for (const [itemId, savedGeneration] of snapshot) {
        if (pending.get(itemId) === savedGeneration) pending.delete(itemId)
      }
    }
  }

  function flush(): Promise<void> {
    if (flight) return flight
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
  }
}
