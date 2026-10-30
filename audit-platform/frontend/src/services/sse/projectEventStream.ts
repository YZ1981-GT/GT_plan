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
import type { AxiosRequestConfig } from 'axios'

import { createSSE, type SSEConnection } from '@/utils/sse'
import { events as eventPaths } from '@/services/apiPaths'
import { api } from '@/services/apiProxy'
import { useAuthStore } from '@/stores/auth'
import {
  PROJECT_TRANSPORT_RECOVERED_EVENT,
  RAW_EVENT_REPLAY_DEGRADED,
  type ProjectTransportRecovered,
} from './rawEventRecovery'
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
const _REPLAY_PAGE_SIZE = 100
const _MAX_REPLAY_PAGES = 20
const _MAX_SEEN_EVENT_IDS = 2048

interface _BufferedEvent {
  event: string
  data: unknown
  id?: string
}

interface _ReplayEvent {
  event_id: string
  event_type: string
  project_id: string
  year?: number | null
  account_codes?: string[] | null
  batch_id?: string | null
  entry_group_id?: string | null
  context?: unknown
  timestamp?: number | null
  extra?: Record<string, unknown> | null
}

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
  /** 最后一个已投递的 typed Redis Stream id（跟随标签页也从 BroadcastChannel 更新）。 */
  lastEventId: string | null
  /** replay 请求在途时暂存随后到达的 live 事件，避免 replay/live 竞态双发或乱序。 */
  replaying: boolean
  liveBuffer: _BufferedEvent[]
  /** 有界 id 去重窗：replay 与 live 交叠时同一 id 只投一次。 */
  seenIds: Set<string>
  seenIdOrder: string[]
  recoverySeq: number
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

function _streamIdParts(id: string): [bigint, bigint] | null {
  const match = /^(\d+)-(\d+)$/.exec(id)
  if (!match) return null
  try {
    return [BigInt(match[1]), BigInt(match[2])]
  } catch {
    return null
  }
}

/** Redis Stream id 数值顺序（不能用字符串比较：`99-0` 字面上大于 `100-0`）。 */
export function compareRedisStreamIds(a: string, b: string): number {
  const left = _streamIdParts(a)
  const right = _streamIdParts(b)
  if (!left || !right) return a.localeCompare(b)
  if (left[0] !== right[0]) return left[0] < right[0] ? -1 : 1
  if (left[1] !== right[1]) return left[1] < right[1] ? -1 : 1
  return 0
}

function _rememberId(st: _ProjectStream, id?: string): boolean {
  if (!id) return true
  if (st.seenIds.has(id)) return false
  st.seenIds.add(id)
  st.seenIdOrder.push(id)
  if (st.seenIdOrder.length > _MAX_SEEN_EVENT_IDS) {
    const oldest = st.seenIdOrder.shift()
    if (oldest) st.seenIds.delete(oldest)
  }
  if (!st.lastEventId || compareRedisStreamIds(st.lastEventId, id) < 0) {
    st.lastEventId = id
  }
  return true
}

function _deliver(
  projectId: string,
  st: _ProjectStream,
  item: _BufferedEvent,
  publishToFollowers = true,
): void {
  if (!item.event || !_rememberId(st, item.id)) return
  _dispatch(projectId, item.event, item.data)
  if (publishToFollowers) {
    st.share?.publish({ kind: 'event', event: item.event, data: item.data, id: item.id })
  }
}

function _replayAsLive(item: _ReplayEvent): _BufferedEvent | null {
  if (!item || typeof item.event_id !== 'string' || typeof item.event_type !== 'string') return null
  const { event_id, event_type, timestamp: _timestamp, ...data } = item
  return { event: event_type, id: event_id, data: { ...data, event_type } }
}

function _sortById(items: _BufferedEvent[]): _BufferedEvent[] {
  return items.sort((a, b) => {
    if (a.id && b.id) return compareRedisStreamIds(a.id, b.id)
    if (a.id) return -1
    if (b.id) return 1
    return 0
  })
}

async function _fetchReplay(projectId: string, anchor: string): Promise<{
  items: _BufferedEvent[]
  truncated: boolean
}> {
  const all: _BufferedEvent[] = []
  let cursor = anchor
  let truncated = false
  for (let page = 0; page < _MAX_REPLAY_PAGES; page++) {
    const replayConfig: AxiosRequestConfig & { _silent: boolean } = {
      params: { last_event_id: cursor },
      _silent: true,
    }
    const rows = await api.get<_ReplayEvent[]>(eventPaths.since(projectId), replayConfig)
    const batch = Array.isArray(rows) ? rows : []
    for (const row of batch) {
      const item = _replayAsLive(row)
      if (item) all.push(item)
    }
    if (batch.length < _REPLAY_PAGE_SIZE) break
    const next = batch[batch.length - 1]?.event_id
    if (!next || compareRedisStreamIds(next, cursor) <= 0) break
    cursor = next
    if (page === _MAX_REPLAY_PAGES - 1) truncated = true
  }
  return { items: all, truncated }
}

function _recoveredPayload(
  projectId: string,
  attempted: boolean,
  failed: boolean,
  truncated: boolean,
): ProjectTransportRecovered {
  return {
    event_type: PROJECT_TRANSPORT_RECOVERED_EVENT,
    project_id: projectId,
    typed_replay_complete: true,
    replay_attempted: attempted,
    replay_failed: failed,
    replay_truncated: truncated,
    raw_full_refresh_required: true,
    raw_events_without_replay: RAW_EVENT_REPLAY_DEGRADED,
  }
}

async function _recoverAfterOpen(
  projectId: string,
  st: _ProjectStream,
  conn: SSEConnection,
  seq: number,
): Promise<void> {
  const anchor = st.lastEventId ?? conn.lastEventId ?? null
  let replay: _BufferedEvent[] = []
  let failed = false
  let truncated = false
  if (anchor) {
    try {
      const result = await _fetchReplay(projectId, anchor)
      replay = result.items
      truncated = result.truncated
    } catch (error) {
      failed = true
      console.warn('[projectEventStream] typed replay failed; consumers will full-refresh', error)
    }
  }
  if (_byProject.get(projectId) !== st || seq !== st.recoverySeq) return

  for (const item of _sortById(replay)) _deliver(projectId, st, item)
  // replay 请求期间到达的 live typed 事件会与 replay 尾部重叠；按 id 排序 + 有界 Set 去重。
  // raw 事件没有 id，只能按到达顺序在 barrier 末尾发出，再由 onReconnect 做全量刷新。
  while (st.liveBuffer.length) {
    const buffered = st.liveBuffer.splice(0)
    for (const item of _sortById(buffered)) _deliver(projectId, st, item)
  }
  st.replaying = false
  const recovered = _recoveredPayload(projectId, Boolean(anchor), failed, truncated)
  _dispatch(projectId, PROJECT_TRANSPORT_RECOVERED_EVENT, recovered)
  _runHooks(st.reconnectHooks, 'reconnect')
  st.share?.publish({ kind: 'reconnected', recovered, lastEventId: st.lastEventId })
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
  st.recoverySeq++
  st.replaying = false
  st.liveBuffer.length = 0
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
    const item = { event: message.event, data: message.data, id: message.id }
    if (st.replaying) st.liveBuffer.push(item)
    else _deliver(projectId, st, item, false)
  } else if (message.kind === 'reconnected') {
    if (message.lastEventId && (!st.lastEventId || compareRedisStreamIds(st.lastEventId, message.lastEventId) < 0)) {
      st.lastEventId = message.lastEventId
    }
    _dispatch(projectId, PROJECT_TRANSPORT_RECOVERED_EVENT, message.recovered)
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
    const conn = createSSE(url, {
      maxRetries: _MAX_RECONNECT_ATTEMPTS,
      reconnectOnCleanEnd: true,
      lastEventId: st.lastEventId ?? undefined,
    })
    st.conn = conn

    conn.onMessage((data: unknown, event?: string, id?: string) => {
      // 分发键 = Event_Name（不依赖 data.event_type，修复裸事件被丢弃，R2.3）
      if (!event) return
      const item = { event, data, id }
      if (st.replaying) st.liveBuffer.push(item)
      else _deliver(projectId, st, item)
    })

    conn.onOpen(() => {
      const reconnecting = st.everConnected || st.takeover
      st.everConnected = true
      st.takeover = false
      st.errorCount = 0
      if (reconnecting) {
        // 同步置 barrier，再启动异步 /since；createSSE 的 reader 会紧接着读 live 帧，
        // 这些帧在请求完成前进入 liveBuffer，不会先于 replay 投递。
        st.replaying = true
        const seq = ++st.recoverySeq
        void _recoverAfterOpen(projectId, st, conn, seq)
      }
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
      lastEventId: null,
      replaying: false,
      liveBuffer: [],
      seenIds: new Set(),
      seenIdOrder: [],
      recoverySeq: 0,
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
        s.recoverySeq++
        s.liveBuffer.length = 0
        s.replaying = false
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
