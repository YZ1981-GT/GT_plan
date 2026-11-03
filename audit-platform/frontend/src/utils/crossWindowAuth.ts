/**
 * 跨窗口认证同步 — BroadcastChannel + Web Locks
 *
 * 功能：
 * 1. token 刷新后广播给其他窗口（避免旧 refresh token 导致登出）
 * 2. 登出时广播给其他窗口（全部同步退出）
 * 3. 新窗口无 token 时向已有窗口请求会话
 * 4. Web Locks 保证同一时刻只有一个窗口执行 token refresh
 *
 * spec: multi-window-ledger-workbench Phase 2 Task 7
 */

import { getClientInstanceId } from './clientInstance'
import { toCloneable } from './cloneable'

// ── 消息类型 ──

export type AuthMessage =
  | { type: 'token-updated'; token: string; refreshToken: string; senderId: string }
  | { type: 'logout'; senderId: string }
  | { type: 'session-request'; senderId: string }
  | { type: 'session-response'; token: string; refreshToken: string; user: any; senderId: string }

// ── Channel 管理 ──

const CHANNEL_NAME = 'gt-auth'
let _channel: BroadcastChannel | null = null

function getChannel(): BroadcastChannel | null {
  if (typeof BroadcastChannel === 'undefined') return null
  if (!_channel) {
    try {
      _channel = new BroadcastChannel(CHANNEL_NAME)
    } catch {
      return null
    }
  }
  return _channel
}

// ── 广播 API ──

export function broadcastTokenUpdate(token: string, refreshToken: string): void {
  getChannel()?.postMessage({
    type: 'token-updated',
    token,
    refreshToken,
    senderId: getClientInstanceId(),
  } satisfies AuthMessage)
}

export function broadcastLogout(): void {
  getChannel()?.postMessage({
    type: 'logout',
    senderId: getClientInstanceId(),
  } satisfies AuthMessage)
}

/**
 * 新窗口向已有窗口请求当前会话。
 * 超时 2 秒后返回 null（说明没有已登录的窗口）。
 */
export function requestSession(): Promise<{ token: string; refreshToken: string; user: any } | null> {
  return new Promise((resolve) => {
    const ch = getChannel()
    if (!ch) { resolve(null); return }

    const timer = setTimeout(() => {
      ch.removeEventListener('message', handler)
      resolve(null)
    }, 2000)

    function handler(ev: MessageEvent<AuthMessage>) {
      const msg = ev.data
      // 按当前编号比较：窗口编号认领后可能换了新号（workpaper-multi-window-lock-gaps R1.4）
      if (msg.type === 'session-response' && msg.senderId !== getClientInstanceId()) {
        clearTimeout(timer)
        ch!.removeEventListener('message', handler)
        resolve({ token: msg.token, refreshToken: msg.refreshToken, user: msg.user })
      }
    }
    ch.addEventListener('message', handler)

    ch.postMessage({
      type: 'session-request',
      senderId: getClientInstanceId(),
    } satisfies AuthMessage)
  })
}

// ── 新标签页会话接力 ──

export type HandoffSession = { token: string; refreshToken: string; user: any }

let _handoff: Promise<void> = Promise.resolve()

/**
 * 新标签页（地址栏打开、noopener 链接）没有 opener 复制的 sessionStorage：启动时向已登录标签页要一次会话，
 * 拿到后交给 `apply` 写进本页。须在 `app.use(router)` 之前调用；路由守卫判「未登录」前用 {@link awaitSessionHandoff} 等它。
 * 🔴 原先 main.ts 挂载与要会话并行：首个导航在回执到达前就被守卫送去登录页，回执到了也停在登录页
 *    （spec attachment-confirmation-evidence-loop 浏览器走查实测；同一处另有回执带响应式 user 发不出去的缺陷）。
 */
export function startSessionHandoff(apply: (session: HandoffSession) => void | Promise<void>): Promise<void> {
  if (typeof sessionStorage !== 'undefined' && sessionStorage.getItem('token')) return _handoff
  _handoff = requestSession()
    .then(async (session) => {
      if (session) await apply(session)
    })
    .catch(() => {
      // BroadcastChannel 不可用或回执处理出错 ⇒ 当作没有已登录标签页，由路由守卫跳登录页
    })
  return _handoff
}

/** 会话接力结束（没有发起过时立即结束）。 */
export function awaitSessionHandoff(): Promise<void> {
  return _handoff
}

// ── 监听 API ──

export interface AuthEventHandlers {
  onTokenUpdate?: (token: string, refreshToken: string) => void
  onLogout?: () => void
  onSessionRequest?: () => { token: string; refreshToken: string; user: any } | null
}

let _listening = false

export function listenAuthEvents(handlers: AuthEventHandlers): void {
  if (_listening) return
  _listening = true

  const ch = getChannel()
  if (!ch) return

  ch.addEventListener('message', (ev: MessageEvent<AuthMessage>) => {
    const msg = ev.data
    // 忽略自己发出的消息。按当前编号比较：监听在启动时就装上，「复制标签页」认领后会换新号，
    // 记下旧号会把原标签页的令牌更新 / 登出广播当成自己的而丢掉（workpaper-multi-window-lock-gaps R1.4）
    const myId = getClientInstanceId()
    if (msg.senderId === myId) return

    switch (msg.type) {
      case 'token-updated':
        handlers.onTokenUpdate?.(msg.token, msg.refreshToken)
        break

      case 'logout':
        handlers.onLogout?.()
        break

      case 'session-request': {
        const session = handlers.onSessionRequest?.()
        if (session) {
          // 🔴 user 来自 Pinia state（响应式 Proxy），postMessage 结构化克隆它抛 DataCloneError ⇒ 回执发不出去、
          //    新标签页 2 秒后跳登录页（spec attachment-confirmation-evidence-loop 浏览器走查实测）。先去掉代理再发。
          ch.postMessage({
            type: 'session-response',
            ...session,
            user: toCloneable(session.user),
            senderId: myId,
          } satisfies AuthMessage)
        }
        break
      }
    }
  })
}

// ── Web Locks 单飞令牌刷新 ──

/**
 * 用 Web Locks 保证同一时刻只有一个标签页执行 token refresh。
 * 如果浏览器不支持 Web Locks，降级为不加锁直接执行。
 */
export async function singleFlightRefresh<T>(fn: () => Promise<T>): Promise<T> {
  if (typeof navigator === 'undefined' || !('locks' in navigator)) {
    return fn()
  }
  return navigator.locks.request('gt-token-refresh', fn)
}
