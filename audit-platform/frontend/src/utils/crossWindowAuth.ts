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

    const myId = getClientInstanceId()
    const timer = setTimeout(() => {
      ch.removeEventListener('message', handler)
      resolve(null)
    }, 2000)

    function handler(ev: MessageEvent<AuthMessage>) {
      const msg = ev.data
      if (msg.type === 'session-response' && msg.senderId !== myId) {
        clearTimeout(timer)
        ch!.removeEventListener('message', handler)
        resolve({ token: msg.token, refreshToken: msg.refreshToken, user: msg.user })
      }
    }
    ch.addEventListener('message', handler)

    ch.postMessage({
      type: 'session-request',
      senderId: myId,
    } satisfies AuthMessage)
  })
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

  const myId = getClientInstanceId()

  ch.addEventListener('message', (ev: MessageEvent<AuthMessage>) => {
    const msg = ev.data
    // 忽略自己发出的消息
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
          ch.postMessage({
            type: 'session-response',
            ...session,
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
