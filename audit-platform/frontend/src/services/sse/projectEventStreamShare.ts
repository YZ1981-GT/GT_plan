/**
 * 同一浏览器、同一用户、同一项目的多个标签页共用一条项目事件流。
 *
 * Web Locks 可用时由浏览器原生锁选主。内网 HTTP 不是 secure context，Chrome 不提供
 * navigator.locks；此时退回 BroadcastChannel + localStorage 租约围栏，同一 origin 仍只有
 * 一个领导标签页实际连 SSE，其他标签页只收领导转发的事件。
 */

import type { ProjectTransportRecovered } from './rawEventRecovery'

export type ProjectStreamShareMessage =
  | { kind: 'event'; event: string; data: unknown; id?: string }
  | { kind: 'reconnected'; recovered: ProjectTransportRecovered; lastEventId: string | null }
  | { kind: 'degraded' }

export interface ProjectStreamShareHandlers {
  /** 本标签页成为领导：建真实连接。takeover 表示接替了先前领导。 */
  onLead: (takeover: boolean) => void
  /** 当前领导因 fallback 冲突让位：调用方必须关闭真实连接。 */
  onFollow?: () => void
  /** 跟随时收到领导转来的业务消息。 */
  onMessage: (message: ProjectStreamShareMessage) => void
}

export interface ProjectStreamShare {
  publish: (message: ProjectStreamShareMessage) => void
  close: () => void
  readonly leading: boolean
}

interface LockManagerLike {
  request: (
    name: string,
    options: { ifAvailable?: boolean; signal?: AbortSignal },
    callback: (lock: unknown) => Promise<unknown> | unknown,
  ) => Promise<unknown>
}

interface StorageLike {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
  removeItem(key: string): void
}

interface FallbackLease {
  owner: string
  expiresAt: number
}

type FallbackWireMessage = ProjectStreamShareMessage
  | { kind: '$leader-heartbeat'; owner: string; expiresAt: number }
  | { kind: '$leader-resign'; owner: string }

export const PROJECT_STREAM_SHARE_PREFIX = 'gt-project-events'
/** 选主租约 TTL。小于 SSE 重连退避，但足够让关闭标签页在约 1.5 秒内被接管。 */
export const FALLBACK_LEASE_TTL_MS = 1500
/** leader 心跳 / follower 看门狗周期。 */
export const FALLBACK_LEASE_HEARTBEAT_MS = 400

function lockManager(): LockManagerLike | null {
  const nav = (globalThis as { navigator?: { locks?: LockManagerLike } }).navigator
  const locks = nav?.locks
  return locks && typeof locks.request === 'function' ? locks : null
}

function storage(): StorageLike | null {
  try {
    const value = (globalThis as { localStorage?: StorageLike }).localStorage
    return value
      && typeof value.getItem === 'function'
      && typeof value.setItem === 'function'
      && typeof value.removeItem === 'function'
      ? value
      : null
  } catch {
    // 隐私模式或禁止 storage 的嵌入页：只能退回每标签页连接，不能假装已共享。
    return null
  }
}

function tabIdentity(): string {
  // HTTP 非安全上下文没有 crypto.randomUUID；不能因此让 fallback 永远失效。
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`
}

function leaseKey(name: string): string {
  return `${name}:lease`
}

function readLease(store: StorageLike, key: string): FallbackLease | null {
  try {
    const raw = store.getItem(key)
    if (!raw) return null
    const value = JSON.parse(raw) as Partial<FallbackLease>
    return typeof value.owner === 'string' && Number.isFinite(value.expiresAt)
      ? { owner: value.owner, expiresAt: Number(value.expiresAt) }
      : null
  } catch {
    return null
  }
}

function writeLease(store: StorageLike, key: string, lease: FallbackLease): boolean {
  try {
    store.setItem(key, JSON.stringify(lease))
    return true
  } catch {
    return false
  }
}

function clearOwnLease(store: StorageLike, key: string, owner: string): void {
  try {
    if (readLease(store, key)?.owner === owner) store.removeItem(key)
  } catch {
    // close 不能因 storage 清理失败阻止 channel/socket 关闭。
  }
}

function joinWithWebLocks(
  locks: LockManagerLike,
  name: string,
  channel: BroadcastChannel,
  handlers: ProjectStreamShareHandlers,
): ProjectStreamShare {
  const queued = new AbortController()
  let closed = false
  let leading = false
  let release: (() => void) | null = null

  channel.onmessage = (event: MessageEvent) => {
    if (closed || leading) return
    handlers.onMessage(event.data as ProjectStreamShareMessage)
  }

  const lead = (takeover: boolean): Promise<void> => new Promise<void>((resolve) => {
    if (closed) {
      resolve()
      return
    }
    leading = true
    release = resolve
    handlers.onLead(takeover)
  })

  locks.request(name, { ifAvailable: true }, (lock) => {
    if (lock) return lead(false)
    if (closed) return undefined
    locks.request(name, { signal: queued.signal }, () => lead(true)).catch(() => {
      // close() 取消排队 ⇒ AbortError，属正常退出。
    })
    return undefined
  }).catch(() => {})

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

/**
 * HTTP fallback：BroadcastChannel 传事件，localStorage 存短租约。不是“无锁就每页自连”。
 *
 * localStorage 不提供真正 CAS，所以两个初始标签页可能在同一瞬间短暂都写成功。心跳带
 * deterministic owner id；冲突时较小 id 留任，另一个关闭自己的连接。稳定后单项目只有一条
 * SSE。该短暂收敛窗比 HTTP/1.1 连接耗尽造成的数分钟阻塞小得多，且 follower 接手时一律
 * 触发 onLead(true) → replay / full refresh，避免丢事件静默化。
 */
function joinWithStorageLease(
  store: StorageLike,
  name: string,
  channel: BroadcastChannel,
  handlers: ProjectStreamShareHandlers,
): ProjectStreamShare {
  const key = leaseKey(name)
  const owner = tabIdentity()
  let closed = false
  let leading = false
  let hadLeader = false
  let lastHeartbeatAt = 0
  let timer: ReturnType<typeof setInterval> | null = null

  const announce = (kind: '$leader-heartbeat' | '$leader-resign') => {
    if (kind === '$leader-heartbeat') {
      channel.postMessage({ kind, owner, expiresAt: Date.now() + FALLBACK_LEASE_TTL_MS })
    } else {
      channel.postMessage({ kind, owner })
    }
  }

  const stepDown = () => {
    if (!leading) return
    leading = false
    handlers.onFollow?.()
  }

  const heartbeat = () => {
    if (closed) return
    const now = Date.now()
    const current = readLease(store, key)
    if (leading) {
      // 有更小 owner 抢到有效租约时让位；反之重写自己的 lease，令对方下一跳让位。
      if (current && current.owner !== owner && current.expiresAt > now && current.owner < owner) {
        stepDown()
        return
      }
      if (!writeLease(store, key, { owner, expiresAt: now + FALLBACK_LEASE_TTL_MS })) {
        // storage 在运行期失效时不能继续自称 leader，否则其他标签页永远接不了手。
        stepDown()
        return
      }
      lastHeartbeatAt = now
      announce('$leader-heartbeat')
      return
    }

    const live = current && current.expiresAt > now
    if (live) {
      hadLeader = true
      lastHeartbeatAt = now
      return
    }
    // channel 心跳可能比 storage 写慢一拍：超过 TTL 才尝试接手。
    if (!lastHeartbeatAt || now - lastHeartbeatAt >= FALLBACK_LEASE_TTL_MS) {
      tryAcquire(true)
    }
  }

  const becomeLeader = (takeover: boolean) => {
    if (closed || leading) return
    leading = true
    lastHeartbeatAt = Date.now()
    handlers.onLead(takeover)
    heartbeat()
  }

  const tryAcquire = (takeover: boolean) => {
    if (closed || leading) return
    const now = Date.now()
    const current = readLease(store, key)
    if (current && current.expiresAt > now && current.owner !== owner) {
      hadLeader = true
      lastHeartbeatAt = now
      return
    }
    if (!writeLease(store, key, { owner, expiresAt: now + FALLBACK_LEASE_TTL_MS })) {
      // storage 写不了：选择当前 tab 建连，退化为原有行为，但不宣称已共享。
      becomeLeader(takeover)
      return
    }
    // 让同 tick 的其他标签页先写 lease；回读时只由最后一个写入者成为候选 leader。
    queueMicrotask(() => {
      if (closed || leading) return
      const confirmed = readLease(store, key)
      if (confirmed?.owner === owner && confirmed.expiresAt > Date.now()) {
        becomeLeader(takeover || hadLeader)
      } else if (confirmed) {
        hadLeader = true
        lastHeartbeatAt = Date.now()
      }
    })
  }

  channel.onmessage = (event: MessageEvent) => {
    if (closed) return
    const message = event.data as FallbackWireMessage
    if (!message || typeof message !== 'object') return
    if (message.kind === '$leader-heartbeat') {
      if (message.owner === owner) return
      hadLeader = true
      lastHeartbeatAt = Date.now()
      if (leading && message.owner < owner) stepDown()
      return
    }
    if (message.kind === '$leader-resign') {
      if (!leading) {
        lastHeartbeatAt = 0
        tryAcquire(true)
      }
      return
    }
    if (!leading) handlers.onMessage(message)
  }

  timer = setInterval(heartbeat, FALLBACK_LEASE_HEARTBEAT_MS)
  tryAcquire(false)

  return {
    publish(message) {
      if (leading && !closed) channel.postMessage(message)
    },
    close() {
      if (closed) return
      closed = true
      if (timer !== null) clearInterval(timer)
      if (leading) {
        clearOwnLease(store, key, owner)
        announce('$leader-resign')
      }
      leading = false
      channel.close()
    },
    get leading() {
      return leading
    },
  }
}

/** 加入共享；优先 Web Locks，HTTP 无安全上下文时用 storage lease。 */
export function joinProjectStreamShare(
  userId: string,
  projectId: string,
  handlers: ProjectStreamShareHandlers,
): ProjectStreamShare | null {
  if (!userId || !projectId || typeof BroadcastChannel === 'undefined') return null
  const name = `${PROJECT_STREAM_SHARE_PREFIX}:${userId}:${projectId}`
  let channel: BroadcastChannel
  try {
    channel = new BroadcastChannel(name)
  } catch {
    return null
  }

  const locks = lockManager()
  if (locks !== null) return joinWithWebLocks(locks, name, channel, handlers)
  const store = storage()
  if (store !== null) return joinWithStorageLease(store, name, channel, handlers)

  channel.close()
  return null
}
