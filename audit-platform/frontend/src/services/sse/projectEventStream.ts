/**
 * projectEventStream — 项目事件流单例总线（frontend-sse-connection-consolidation）
 *
 * 每个 projectId 至多维持一条到 `/api/projects/{pid}/events/stream` 的共享 SSE 连接
 * （fetch-based `createSSE`，Authorization header 传 token，token 不入 URL），
 * 按 Event_Name fan-out 分发给订阅者。消费者（ThreeColumnLayout / useAcnr /
 * ConsolidationIndex / LineagePanel）从「各自建连接」迁为「向总线订阅特定事件名」，
 * 实现连接去重（每项目 1 条）+ 鉴权统一。
 *
 * 断线重连 / 指数退避由 `createSSE` 内部负责（单一真源）；总线做 Ref_Count_Lifecycle
 * + fan-out（异常隔离）+ 重连/降级 hook。
 *
 * Requirements: 1.*, 2.*, 3.1, 4.*
 */
import { createSSE, type SSEConnection } from '@/utils/sse'
import { events as eventPaths } from '@/services/apiPaths'
import { useAuthStore } from '@/stores/auth'
import {
  joinProjectStreamShare,
  type ProjectStreamShare,
  type ProjectStreamShareMessage,
} from './projectEventStreamShare'

export type ProjectEventHandler = (data: unknown, eventName: string) => void

export interface ProjectEventSubscription {
  close(): void
}

export interface ProjectEventSubscribeOptions {
  /** 断线重连成功（此前曾断线）时触发 —— 消费者做各自恢复（如清缓存 / poll）。 */
  onReconnect?: () => void
  /** 共享连接超重试上限降级 TTL-only 时触发 —— 消费者退回兜底。 */
  onDegraded?: () => void
}

/** 共享连接超重试上限阈值（与 createSSE maxRetries 对齐）。 */
const _MAX_RECONNECT_ATTEMPTS = 5

interface _ProjectStream {
  conn: SSEConnection | null
  listeners: Map<string, Set<ProjectEventHandler>>
  reconnectHooks: Set<() => void>
  degradedHooks: Set<() => void>
  refCount: number
  errorCount: number
  everConnected: boolean
  degraded: boolean
  /** 跨标签页共用（见 projectEventStreamShare）；null = 本标签页自己建连接。 */
  share: ProjectStreamShare | null
  /** 接替了先前的领导标签页：本次连上要按断线重连通知（期间可能漏事件）。 */
  takeover: boolean
}

/** projectId → 共享流状态（模块级单例）。 */
const _byProject = new Map<string, _ProjectStream>()

/** 通配事件名：订阅 `'*'` 收到该项目所有事件（供 ThreeColumnLayout 的 typed 事件 catch-all 保持等价）。 */
export const WILDCARD_EVENT = '*'

function _fanout(
  set: Set<ProjectEventHandler> | undefined,
  data: unknown,
  eventName: string,
): void {
  if (!set || set.size === 0) return
  // 快照迭代：handler 内若增删订阅不影响本轮；每 handler 异常隔离（R2.4）
  for (const h of Array.from(set)) {
    try {
      const result: unknown = h(data, eventName)
      // async handler 返回 Promise：catch 防 unhandled rejection（R2.4 扩展）
      if (result && typeof (result as any).catch === 'function') {
        ;(result as Promise<unknown>).catch((e) => {
          console.warn(`[projectEventStream] async handler error for "${eventName}"`, e)
        })
      }
    } catch (e) {
      console.warn(`[projectEventStream] handler error for "${eventName}"`, e)
    }
  }
}

function _dispatch(projectId: string, eventName: string, data: unknown): void {
  const st = _byProject.get(projectId)
  if (!st) return
  // 精确事件名订阅者 + 通配 '*' 订阅者（catch-all）
  _fanout(st.listeners.get(eventName), data, eventName)
  if (eventName !== WILDCARD_EVENT) {
    _fanout(st.listeners.get(WILDCARD_EVENT), data, eventName)
  }
}

function _runHooks(hooks: Set<() => void>, label: string): void {
  for (const hook of Array.from(hooks)) {
    try {
      hook()
    } catch (e) {
      console.warn(`[projectEventStream] ${label} hook error`, e)
    }
  }
}

function _markDegraded(st: _ProjectStream): void {
  if (st.degraded) return
  st.degraded = true
  st.conn?.close()
  st.conn = null
  _runHooks(st.degradedHooks, 'degraded')
}

/** 当前登录用户 id（跨标签页共用的键）；拿不到 ⇒ 不共用。 */
function _currentUserId(): string {
  try {
    return String(useAuthStore().userId ?? '')
  } catch {
    return ''
  }
}

/** 跟随时收到领导标签页转来的消息（领导自己的消息不会回到自己）。 */
function _onShareMessage(projectId: string, message: ProjectStreamShareMessage): void {
  const st = _byProject.get(projectId)
  if (!st) return
  if (message.kind === 'event') {
    _dispatch(projectId, message.event, message.data)
  } else if (message.kind === 'reconnected') {
    _runHooks(st.reconnectHooks, 'reconnect')
  } else if (message.kind === 'degraded') {
    _markDegraded(st)
  }
}

/** 建立项目共享 SSE 连接（fetch-based createSSE：Authorization header，token 不入 URL）。 */
function _ensureConnection(projectId: string): void {
  const st = _byProject.get(projectId)
  if (!st || st.degraded || st.conn) return
  try {
    // eventPaths.stream → /api/projects/{pid}/events/stream（无 token= query，R3.1）
    const url = eventPaths.stream(projectId)
    const conn = createSSE(url, { maxRetries: _MAX_RECONNECT_ATTEMPTS })
    st.conn = conn

    conn.onMessage((data: unknown, event?: string) => {
      // 分发键 = Event_Name（不依赖 data.event_type，修复裸事件被丢弃，R2.3）
      if (!event) return
      _dispatch(projectId, event, data)
      st.share?.publish({ kind: 'event', event, data })
    })

    conn.onOpen(() => {
      if (st.everConnected || st.takeover) {
        // 断线重连成功 / 接替了别的标签页 → 通知订阅者恢复（R4.2），跟随的标签页一并恢复
        _runHooks(st.reconnectHooks, 'reconnect')
        st.share?.publish({ kind: 'reconnected' })
      }
      st.everConnected = true
      st.takeover = false
      st.errorCount = 0
    })

    conn.onError(() => {
      st.errorCount++
      // createSSE 重试上限后仍失败 → 降级 TTL-only（R4.3/R4.4；staleness 由消费者兜底约束）
      if (st.errorCount > _MAX_RECONNECT_ATTEMPTS && !st.degraded) {
        _markDegraded(st)
        st.share?.publish({ kind: 'degraded' })
        console.warn(
          `[projectEventStream] 项目 ${projectId} SSE 重连失败超过 ${_MAX_RECONNECT_ATTEMPTS} 次，降级为 TTL-only（停止重试）`,
        )
      }
    })
  } catch {
    // createSSE 不可用 → 靠各消费者兜底（poll / TTL），R4.5
  }
}

/**
 * 订阅项目某事件名。按 projectId 引用计数复用单一共享连接，返回 cleanup。
 * 无 projectId / eventName → no-op（R1.5）。
 */
export function subscribeProjectEvent(
  projectId: string,
  eventName: string,
  handler: ProjectEventHandler,
  options: ProjectEventSubscribeOptions = {},
): ProjectEventSubscription {
  if (!projectId || !eventName) {
    return { close() {} }
  }
  let st = _byProject.get(projectId)
  if (!st) {
    st = {
      conn: null,
      listeners: new Map(),
      reconnectHooks: new Set(),
      degradedHooks: new Set(),
      refCount: 0,
      errorCount: 0,
      everConnected: false,
      degraded: false,
      share: null,
      takeover: false,
    }
    _byProject.set(projectId, st)
    const created = st
    // 同用户同项目的多个标签页共用一条连接（HTTP/1.1 每主机 6 连接上限，见 projectEventStreamShare）
    created.share = joinProjectStreamShare(_currentUserId(), projectId, {
      onLead: (takeover) => {
        if (_byProject.get(projectId) !== created) return
        created.takeover = takeover
        _ensureConnection(projectId)
      },
      onMessage: (message) => _onShareMessage(projectId, message),
    })
  }

  let set = st.listeners.get(eventName)
  if (!set) {
    set = new Set()
    st.listeners.set(eventName, set)
  }
  set.add(handler)
  if (options.onReconnect) st.reconnectHooks.add(options.onReconnect)
  if (options.onDegraded) st.degradedHooks.add(options.onDegraded)
  st.refCount++

  // 共用时由领导权回调建连接（跟随的标签页不建）；不共用才在这里直接建
  if (!st.conn && !st.degraded && st.share === null) {
    _ensureConnection(projectId)
  }

  let closed = false
  return {
    close() {
      if (closed) return
      closed = true
      const s = _byProject.get(projectId)
      if (!s) return
      const ss = s.listeners.get(eventName)
      if (ss) {
        ss.delete(handler)
        if (ss.size === 0) s.listeners.delete(eventName)
      }
      if (options.onReconnect) s.reconnectHooks.delete(options.onReconnect)
      if (options.onDegraded) s.degradedHooks.delete(options.onDegraded)
      s.refCount--
      if (s.refCount <= 0) {
        s.conn?.close()
        // 释放领导权（排队的下一个标签页接手）或放弃排队
        s.share?.close()
        _byProject.delete(projectId)
      }
    },
  }
}

/** 观测：某项目共享连接是否已降级 TTL-only。 */
export function isProjectStreamDegraded(projectId: string): boolean {
  return _byProject.get(projectId)?.degraded ?? false
}

/** 观测：某项目当前订阅计数（测试/调试用）。 */
export function _getProjectRefCount(projectId: string): number {
  return _byProject.get(projectId)?.refCount ?? 0
}
