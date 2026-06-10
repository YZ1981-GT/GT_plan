// Feature: zero-downtime-deployment, Component 7b
/**
 * 通用 SSE 断线重连 composable。
 *
 * 抽自 ImportProgress.vue 重连模式：
 * onerror → 关流 → pollFallback() 查真实状态 → 终态渲染/running 重连
 * 退避 + jitter 防重连风暴，超 maxAttempts 提示中断。
 */
import { ref, onUnmounted } from 'vue'

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
  let es: EventSource | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | undefined

  function getUrl(): string {
    return typeof url === 'function' ? url() : url
  }

  function connect() {
    if (es) {
      es.close()
      es = null
    }

    const currentUrl = getUrl()
    es = new EventSource(currentUrl)

    es.onopen = () => {
      connected.value = true
      reconnecting.value = false
      attempts = 0  // 收到连接重置 attempts
    }

    es.onmessage = (event) => {
      attempts = 0  // 收到消息重置
      try {
        const data = JSON.parse(event.data)
        onMessage(data)
      } catch {
        onMessage(event.data)
      }
    }

    es.onerror = () => {
      connected.value = false
      es?.close()
      es = null
      onDisconnected?.()
      handleReconnect()
    }
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
