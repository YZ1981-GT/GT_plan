/**
 * 合并页面异步请求的上下文守卫。
 *
 * 缓存只能隔离数据，不能阻止旧请求在切换项目、年度或节点后覆盖当前视图。
 * 每张请求票据同时保存递增序号和完整上下文快照，响应提交前必须检查两者。
 *
 * 2026-10-09 增强：集成 AbortController。startRequest() 时自动 abort 前一个飞行中的请求，
 * 返回的 ticket 包含 signal 供传给 axios / fetch。isAborted() 辅助判断取消类异常。
 */

export type ConsolRequestContext = Record<string, unknown>

export interface ConsolRequestTicket<TContext extends ConsolRequestContext> {
  sequence: number
  context: TContext
  /** 用于取消本次请求的 AbortSignal；传给 axios 的 config.signal */
  signal: AbortSignal
}

function snapshotContext<TContext extends ConsolRequestContext>(context: TContext): TContext {
  return { ...context }
}

function sameContext<TContext extends ConsolRequestContext>(
  expected: TContext,
  current: TContext,
): boolean {
  const expectedKeys = Object.keys(expected)
  const currentKeys = Object.keys(current)
  if (expectedKeys.length !== currentKeys.length) return false
  return expectedKeys.every((key) => Object.is(expected[key], current[key]))
}

/** 判断错误是否由 AbortController.abort() 引起（axios 和 fetch 均适用）。 */
export function isAborted(err: unknown): boolean {
  if (!err || typeof err !== 'object') return false
  const e = err as Record<string, unknown>
  // axios: err.code === 'ERR_CANCELED'
  if (e.code === 'ERR_CANCELED') return true
  // fetch / DOMException: err.name === 'AbortError'
  if (e.name === 'AbortError') return true
  return false
}

export function createConsolRequestGuard<TContext extends ConsolRequestContext>(
  getContext: () => TContext,
) {
  let sequence = 0
  let currentController: AbortController | null = null

  function startRequest(): ConsolRequestTicket<TContext> {
    // 取消前一个飞行中的请求
    if (currentController) {
      currentController.abort()
    }
    currentController = new AbortController()
    return {
      sequence: ++sequence,
      context: snapshotContext(getContext()),
      signal: currentController.signal,
    }
  }

  function isStale(ticket: ConsolRequestTicket<TContext>): boolean {
    return ticket.sequence !== sequence || !sameContext(ticket.context, getContext())
  }

  /** 取消当前飞行中的请求（组件卸载时调用） */
  function abort() {
    if (currentController) {
      currentController.abort()
      currentController = null
    }
  }

  return { startRequest, isStale, abort }
}
