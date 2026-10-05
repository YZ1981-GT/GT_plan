/**
 * 合并页面异步请求的上下文守卫。
 *
 * 缓存只能隔离数据，不能阻止旧请求在切换项目、年度或节点后覆盖当前视图。
 * 每张请求票据同时保存递增序号和完整上下文快照，响应提交前必须检查两者。
 */

export type ConsolRequestContext = Record<string, unknown>

export interface ConsolRequestTicket<TContext extends ConsolRequestContext> {
  sequence: number
  context: TContext
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

export function createConsolRequestGuard<TContext extends ConsolRequestContext>(
  getContext: () => TContext,
) {
  let sequence = 0

  function startRequest(): ConsolRequestTicket<TContext> {
    return {
      sequence: ++sequence,
      context: snapshotContext(getContext()),
    }
  }

  function isStale(ticket: ConsolRequestTicket<TContext>): boolean {
    return ticket.sequence !== sequence || !sameContext(ticket.context, getContext())
  }

  return { startRequest, isStale }
}
