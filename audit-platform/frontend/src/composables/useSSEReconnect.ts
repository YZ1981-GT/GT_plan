// Feature: zero-downtime-deployment, Component 7b
/**
 * 通用 SSE 断线重连 composable。
 *
 * 抽自 ImportProgress.vue 重连模式：
 * onerror → 关流 → pollFallback() 查真实状态 → 终态渲染/running 重连
 * 退避 + jitter 防重连风暴，超 maxAttempts 提示中断。
 *
 * 🔴 传输层用 `createSSE`（fetch 流，自带 `Authorization`），**不用原生 EventSource**：后者不能带请求头，
 *    而账表导入进度流 `…/ledger-import/jobs/{id}/stream` 走 `require_project_access`（只认 Bearer 头，
 *    `?token=` 也 401，2026-09-30 实测）⇒ 旧实现每次都连不上，进度全靠 pollFallback 轮询兜底。
 *    重连由本 composable 自己编排（先 poll 真实状态再决定），故 createSSE 的内置重试关掉（maxRetries: 0）。
 */
import { ref, onUnmounted } from 'vue'
import { createSSE, type SSEConnection } from '@/utils/sse'

export interface UseSSEReconnectOptions {
  url: string | (() => string)
  onMessage: (data: any) => void
  pollFallback: () => Promise<'completed' | 'failed' | 'canceled' | 'running'>
  maxAttempts?: number   // default 30
  backoffMs?: number     // default 2000
  onDisconnected?: () => void
  onReconnecting?: (attempt: number) => void
  onGaveUp?: () => void
}

export function useSSEReconnect(opts: UseSSEReconnectOptions) {
  const {
    url,
    onMessage,
    pollFallback,
    maxAttempts = 30,
    backoffMs = 2000,
    onDisconnected,
    onReconnecting,
    onGaveUp,
  } = opts

  const connected = ref(false)
  const reconnecting = ref(false)
  const gaveUp = ref(false)
  let attempts = 0
  let es: SSEConnection | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | undefined

  function getUrl(): string {
    return typeof url === 'function' ? url() : url
  }

  function connect() {
    if (es) {
      es.close()
      es = null
    }

    const conn = createSSE(getUrl(), { maxRetries: 0 })
    es = conn

    conn.onOpen(() => {
      connected.value = true
      reconnecting.value = false
      attempts = 0  // 收到连接重置 attempts
    })

    // createSSE 已按 JSON 解析 data（失败时给原始字符串），与旧 EventSource 分支语义一致
    conn.onMessage((data) => {
      attempts = 0  // 收到消息重置
      onMessage(data)
    })

    const drop = (): void => {
      if (es !== conn) return  // 已被 close() / 新连接替换：旧连接的迟到信号不触发重连
      connected.value = false
      conn.close()
      es = null
      onDisconnected?.()
      handleReconnect()
    }
    conn.onError(drop)
    // 服务端优雅关闭（滚动更新）：发 server_draining 后结束流 —— createSSE 不把正常结束当错误，
    // 须显式按断线处理（原生 EventSource 会在流结束时自动触发 onerror，这里对齐该语义）
    conn.onDraining(drop)
  }

  async function handleReconnect() {
    // First check real status via poll fallback
    try {
      const status = await pollFallback()
      if (status === 'completed' || status === 'failed' || status === 'canceled') {
        // Terminal state — render final, don't reconnect
        reconnecting.value = false
        return
      }
    } catch {
      // Poll failed, try to reconnect anyway
    }

    // Still running — attempt reconnect
    attempts++
    if (attempts > maxAttempts) {
      gaveUp.value = true
      reconnecting.value = false
      onGaveUp?.()
      return
    }

    reconnecting.value = true
    onReconnecting?.(attempts)

    // Backoff with jitter
    const jitter = Math.random() * 500
    const delay = backoffMs + jitter

    reconnectTimer = setTimeout(() => {
      connect()
    }, delay)
  }

  function close() {
    if (reconnectTimer) clearTimeout(reconnectTimer)
    if (es) {
      es.close()
      es = null
    }
    connected.value = false
    reconnecting.value = false
  }

  // Start connection
  connect()

  onUnmounted(() => {
    close()
  })

  return { connected, reconnecting, gaveUp, close, connect }
}
