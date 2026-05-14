/**
 * useSSEDegradation — SSE 降级轮询 composable [enterprise-linkage 4.4]
 *
 * - SSE 断连 >10s → 橙色横幅 + 30s 轮询模式
 * - SSE 恢复 → 停止轮询 + 拉取增量事件
 *
 * Validates: Requirements 11.1, 11.2, 11.3
 */
import { ref, onMounted, onUnmounted, type Ref } from 'vue'
import { api } from '@/services/apiProxy'
import { eventBus, type SyncEventPayload } from '@/utils/eventBus'

const DISCONNECT_THRESHOLD_MS = 10_000 // 10 seconds
const POLL_INTERVAL_MS = 30_000 // 30 seconds

export function useSSEDegradation(projectId: Ref<string>) {
  const isDisconnected = ref(false)
  const isPolling = ref(false)
  const lastEventId = ref<string | null>(null)

  let lastEventTime = Date.now()
  let disconnectTimer: ReturnType<typeof setTimeout> | null = null
  let pollTimer: ReturnType<typeof setInterval> | null = null

  // ─── Track SSE events to detect disconnection ────────────────────────────

  function onSSEEvent(payload: SyncEventPayload) {
    lastEventTime = Date.now()
    // Track last event id for incremental fetch
    if (payload.extra && payload.extra.__event_id) {
      lastEventId.value = payload.extra.__event_id
    }

    // If we were disconnected, SSE is back
    if (isDisconnected.value) {
      _onSSEReconnected()
    }
  }

  // ─── Disconnect detection ────────────────────────────────────────────────

  function _checkDisconnect() {
    const elapsed = Date.now() - lastEventTime
    if (elapsed >= DISCONNECT_THRESHOLD_MS && !isDisconnected.value) {
      _onSSEDisconnected()
    }
  }

  function _onSSEDisconnected() {
    isDisconnected.value = true
    _startPolling()
  }

  function _onSSEReconnected() {
    isDisconnected.value = false
    _stopPolling()
    // Pull incremental events since last known event
    _fetchIncrementalEvents()
  }

  // ─── Polling fallback ────────────────────────────────────────────────────

  function _startPolling() {
    if (isPolling.value) return
    isPolling.value = true
    pollTimer = setInterval(_pollForUpdates, POLL_INTERVAL_MS)
    // Immediate first poll
    _pollForUpdates()
  }

  function _stopPolling() {
    isPolling.value = false
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  async function _pollForUpdates() {
    const pid = projectId.value
    if (!pid) return
    try {
      // Poll the incremental events endpoint
      const params: Record<string, string> = {}
      if (lastEventId.value) {
        params.last_event_id = lastEventId.value
      }
      await api.get(`/api/projects/${pid}/events/since`, { params })
    } catch {
      // Silent failure during polling
    }
  }

  async function _fetchIncrementalEvents() {
    const pid = projectId.value
    if (!pid) return
    try {
      const params: Record<string, string> = {}
      if (lastEventId.value) {
        params.last_event_id = lastEventId.value
      }
      await api.get(`/api/projects/${pid}/events/since`, { params })
    } catch {
      // Silent failure
    }
  }

  // ─── Lifecycle ────────────────────────────────────────────────────────────

  onMounted(() => {
    eventBus.on('sse:sync-event', onSSEEvent)
    // Check disconnect every 5 seconds
    disconnectTimer = setInterval(_checkDisconnect, 5000) as unknown as ReturnType<typeof setTimeout>
  })

  onUnmounted(() => {
    eventBus.off('sse:sync-event', onSSEEvent)
    if (disconnectTimer) {
      clearInterval(disconnectTimer as unknown as number)
      disconnectTimer = null
    }
    _stopPolling()
  })

  return {
    isDisconnected,
    isPolling,
    lastEventId,
  }
}
