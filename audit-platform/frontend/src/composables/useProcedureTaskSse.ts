/**
 * 程序行任务 SSE 幂等收敛处理（procedure-delegation-notification / Task 11，Design F4）
 *
 * 需求 10.5/10.6/10.9：SSE 为 at-least-once，payload 携带 event_id。前端 **不** 把 SSE
 * payload 当状态真源，而是：
 *   1) 按 event_id LRU 幂等去重（重复/乱序事件不重复触发刷新）；
 *   2) 收到 **新** 事件后重新拉取未读数与任务列表（通过 API 收敛，丢失/重复最终一致）。
 *
 * 后端 dispatcher 通过 ``event_bus.broadcast_raw("procedure_task.event", {...})`` 广播，
 * 前端 SSE 消息形如：``{ event_type: "procedure_task.event", extra: { event_id, ... } }``
 * （见 ThreeColumnLayout onMessage → eventBus 'sse:sync-event'）。
 *
 * 本模块是进程内单例：LRU 与监听器注册表跨组件共享，保证同一 event_id 至多触发一次刷新。
 */

/** 后端 broadcast_raw 的 SSE 事件类型（与 dispatcher SSE_EVENT_TYPE 一致）。 */
export const PROCEDURE_TASK_SSE_EVENT = 'procedure_task.event'

const SEEN_MAX = 200
const _seen = new Set<string>()
const _order: string[] = []
const _refreshCbs = new Set<() => void>()

/** 提取 SSE payload 中的 event_id（兼容 raw 事件 extra 包裹与扁平形态）。 */
function extractEventId(payload: any): string | null {
  const eid = payload?.extra?.event_id ?? payload?.event_id
  return eid ? String(eid) : null
}

/** 判断是否为程序行任务 SSE 事件。 */
export function isProcedureTaskSseEvent(payload: any): boolean {
  return payload?.event_type === PROCEDURE_TASK_SSE_EVENT
}

/**
 * 摄入一条程序行任务 SSE 事件：按 event_id LRU 幂等去重。
 * @returns 是否为 **新** 事件（新事件才触发刷新回调）。缺 event_id 或重复 → false。
 */
export function ingestProcedureTaskEvent(payload: any): boolean {
  const eventId = extractEventId(payload)
  if (!eventId) return false
  if (_seen.has(eventId)) return false // 重复事件 → 不重复刷新（幂等）
  _seen.add(eventId)
  _order.push(eventId)
  while (_order.length > SEEN_MAX) {
    const evicted = _order.shift()
    if (evicted) _seen.delete(evicted)
  }
  // 收到新事件 → 触发所有已注册刷新回调（重新拉取任务列表/未读数收敛）
  _refreshCbs.forEach((cb) => {
    try {
      cb()
    } catch {
      /* 单个回调失败不影响其它 */
    }
  })
  return true
}

/**
 * 注册“收到新程序任务事件时刷新”回调（如 MyProcedureTasks 重新拉取任务列表）。
 * @returns 取消注册函数（组件卸载时调用）。
 */
export function onProcedureTaskRefresh(cb: () => void): () => void {
  _refreshCbs.add(cb)
  return () => {
    _refreshCbs.delete(cb)
  }
}

/** 测试辅助：重置 LRU 与监听器（仅供单测使用）。 */
export function _resetProcedureTaskSse(): void {
  _seen.clear()
  _order.length = 0
  _refreshCbs.clear()
}

/** 测试辅助：当前 LRU 大小。 */
export function _seenSize(): number {
  return _seen.size
}
