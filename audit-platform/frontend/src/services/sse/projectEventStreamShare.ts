/**
 * 同一浏览器、同一用户、同一项目的多个标签页**共用一条**项目事件流。
 *
 * spec: writeback-followup-issue-closure · R8（P3「HTML 保存挂起约 5 分钟」）
 *
 * ═══ 为什么必须共用 ═══
 *
 * 前端经 HTTP/1.1 访问（开发 Vite :3030、生产 nginx `listen 80`），浏览器对同一主机最多
 * 并发 **6** 条连接，且这个上限按浏览器（profile）算、所有标签页共享。项目事件流是永不结束的
 * 长连接：每个打开项目页面的标签页各占一条 ⇒ 开到 6 个标签页，之后**任何**请求（保存、
 * 打开、轮询）都排在浏览器里等某条流断开（2026-10-23 实测：6 条流在开时 `/api/health`
 * 8 s 仍未发出，断开一条后立即返回；真栈里一次表格保存因此挂了约 5 分钟，直到开发服务器
 * 重载把所有流断掉才发出去）。
 *
 * ═══ 怎么共用 ═══
 *
 * Web Locks 选一个领导标签页：只有拿到锁的标签页真正建连接，收到的事件经 BroadcastChannel
 * 转给其他标签页；领导标签页关闭（或不再订阅）时锁自动释放，排队的下一个标签页接手并重建
 * 连接。接手（takeover）期间可能漏事件 ⇒ 接手方连上后按「断线重连」通知所有标签页做各自恢复
 * （消费者的 `onReconnect` 本来就为断线重连而写）。
 *
 * 键里带用户 id：token 存在 sessionStorage，不同标签页可能登录不同用户，事件不得跨用户转发。
 * 浏览器不支持 Web Locks / BroadcastChannel、或拿不到用户 id 时返回 `null`，调用方退回
 * 「每个标签页各自一条连接」的原行为。
 */

/** 领导标签页转给其他标签页的消息。 */
export type ProjectStreamShareMessage =
  | { kind: 'event'; event: string; data: unknown }
  | { kind: 'reconnected' }
  | { kind: 'degraded' }

export interface ProjectStreamShareHandlers {
  /** 本标签页成为领导：建真实连接。`takeover` = 接替了先前的领导（期间可能漏事件）。 */
  onLead: (takeover: boolean) => void
  /** 跟随时收到领导转来的消息。 */
  onMessage: (message: ProjectStreamShareMessage) => void
}

export interface ProjectStreamShare {
  /** 领导标签页把消息转给其他标签页（跟随时调用无效）。 */
  publish: (message: ProjectStreamShareMessage) => void
  /** 本标签页不再需要这条流：放弃排队或释放领导权（交给下一个标签页）。 */
  close: () => void
  /** 观测：当前是否领导。 */
  readonly leading: boolean
}

interface LockManagerLike {
  request: (
    name: string,
    options: { ifAvailable?: boolean; signal?: AbortSignal },
    callback: (lock: unknown) => Promise<unknown> | unknown,
  ) => Promise<unknown>
}

/** 锁名 / 频道名前缀（同一个名字）。 */
export const PROJECT_STREAM_SHARE_PREFIX = 'gt-project-events'

function lockManager(): LockManagerLike | null {
  const nav = (globalThis as { navigator?: { locks?: LockManagerLike } }).navigator
  const locks = nav?.locks
  return locks && typeof locks.request === 'function' ? locks : null
}

/** 加入共享；不支持时返回 `null`（调用方各自建连接）。 */
export function joinProjectStreamShare(
  userId: string,
  projectId: string,
  handlers: ProjectStreamShareHandlers,
): ProjectStreamShare | null {
  const locks = lockManager()
  if (!userId || !projectId || locks === null || typeof BroadcastChannel === 'undefined') return null
  const name = `${PROJECT_STREAM_SHARE_PREFIX}:${userId}:${projectId}`
  let channel: BroadcastChannel
  try {
    channel = new BroadcastChannel(name)
  } catch {
    return null
  }
  const queued = new AbortController()
  let closed = false
  let leading = false
  let release: (() => void) | null = null

  channel.onmessage = (event: MessageEvent) => {
    if (closed || leading) return
    handlers.onMessage(event.data as ProjectStreamShareMessage)
  }

  const lead = (takeover: boolean): Promise<void> =>
    new Promise<void>((resolve) => {
      if (closed) {
        resolve()
        return
      }
      leading = true
      release = resolve
      handlers.onLead(takeover)
    })

  // 先试一次「立即可得」：拿到 ⇒ 本浏览器里第一个领导；拿不到 ⇒ 已有领导，排队等接手。
  locks
    .request(name, { ifAvailable: true }, (lock) => {
      if (lock) return lead(false)
      if (closed) return undefined
      locks.request(name, { signal: queued.signal }, () => lead(true)).catch(() => {
        // close() 取消排队 ⇒ AbortError，属正常退出
      })
      return undefined
    })
    .catch(() => {})

  return {
    publish(message) {
      if (leading && !closed) channel.postMessage(message)
    },
    close() {
      if (closed) return
      closed = true
      leading = false
      queued.abort()
      release?.()
      release = null
      channel.close()
    },
    get leading() {
      return leading
    },
  }
}
