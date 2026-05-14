/**
 * usePresence — 在线感知 composable [enterprise-linkage 3.1]
 *
 * 30s 心跳上报当前视图 + 编辑状态，
 * 订阅 SSE presence.* 事件更新在线成员列表和编辑状态。
 *
 * @example
 * ```ts
 * const { onlineMembers, editingStates, startHeartbeat, stopHeartbeat } = usePresence(projectId, 'trial_balance')
 * ```
 */
import { ref, onMounted, onUnmounted, type Ref } from 'vue'
import { api } from '@/services/apiProxy'
import { presence as P } from '@/services/apiPaths'
import { eventBus, type SyncEventPayload } from '@/utils/eventBus'

export interface OnlineMember {
  user_id: string
  user_name: string
  avatar?: string
  view: string
}

export interface EditingState {
  user_id: string
  user_name: string
  account_code?: string
  entry_group_id?: string
  view: string
  started_at?: string
}

const HEARTBEAT_INTERVAL = 30_000 // 30s

export function usePresence(projectId: Ref<string>, viewName: string) {
  const onlineMembers = ref<OnlineMember[]>([])
  const editingStates = ref<EditingState[]>([])
  let heartbeatTimer: ReturnType<typeof setInterval> | null = null

  // ─── Heartbeat ────────────────────────────────────────────────────────────

  async function sendHeartbeat() {
    const pid = projectId.value
    if (!pid) return
    try {
      await api.post(P.heartbeat(pid), { view_name: viewName })
    } catch { /* silent retry next interval */ }
  }

  function startHeartbeat() {
    stopHeartbeat()
    sendHeartbeat()
    heartbeatTimer = setInterval(sendHeartbeat, HEARTBEAT_INTERVAL)
  }

  function stopHeartbeat() {
    if (heartbeatTimer) {
      clearInterval(heartbeatTimer)
      heartbeatTimer = null
    }
  }

  // ─── Fetch online / editing ───────────────────────────────────────────────

  async function fetchOnline() {
    const pid = projectId.value
    if (!pid) return
    try {
      const data = await api.get(P.online(pid))
      onlineMembers.value = data ?? []
    } catch { /* ignore */ }
  }

  async function fetchEditing() {
    const pid = projectId.value
    if (!pid) return
    try {
      const data = await api.get(P.editing(pid))
      editingStates.value = data ?? []
    } catch { /* ignore */ }
  }

  // ─── SSE event subscription ───────────────────────────────────────────────

  function handleSSE(payload: SyncEventPayload) {
    if (payload.project_id !== projectId.value) return
    const eventType = payload.event_type

    if (eventType.startsWith('presence.')) {
      const extra = payload.extra ?? {}

      if (eventType === 'presence.joined') {
        const member: OnlineMember = {
          user_id: extra.user_id,
          user_name: extra.user_name,
          avatar: extra.avatar,
          view: extra.view,
        }
        // Add if not already present
        if (!onlineMembers.value.find(m => m.user_id === member.user_id)) {
          onlineMembers.value = [...onlineMembers.value, member]
        }
      } else if (eventType === 'presence.left') {
        onlineMembers.value = onlineMembers.value.filter(m => m.user_id !== extra.user_id)
      } else if (eventType === 'presence.editing_started') {
        const state: EditingState = {
          user_id: extra.user_id,
          user_name: extra.user_name,
          account_code: extra.account_code,
          entry_group_id: extra.entry_group_id,
          view: extra.view,
          started_at: extra.started_at,
        }
        editingStates.value = [...editingStates.value.filter(s => s.user_id !== state.user_id), state]
      } else if (eventType === 'presence.editing_stopped') {
        editingStates.value = editingStates.value.filter(s => s.user_id !== extra.user_id)
      }
    }
  }

  // ─── Lifecycle ────────────────────────────────────────────────────────────

  onMounted(() => {
    eventBus.on('sse:sync-event', handleSSE)
    fetchOnline()
    fetchEditing()
    startHeartbeat()
  })

  onUnmounted(() => {
    eventBus.off('sse:sync-event', handleSSE)
    stopHeartbeat()
  })

  return {
    onlineMembers,
    editingStates,
    startHeartbeat,
    stopHeartbeat,
  }
}
