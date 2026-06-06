/**
 * useStaleRefresh — 通用 stale 刷新范式
 *
 * 监听 eventBus 上游变更事件（trial-balance:updated / adjustment:saved / dataset:activated /
 * year:changed / project:updated），按 projectId 过滤后执行刷新或置 stale 状态。
 *
 * @example
 * ```ts
 * const { isStale, refresh } = useStaleRefresh(projectId, {
 *   mode: 'prompt',
 *   onRefresh: () => fetchReport(),
 * })
 * ```
 */
import { ref, onMounted, onUnmounted, type Ref } from 'vue'
import { eventBus, type Events } from '@/utils/eventBus'

export interface StaleRefreshOptions {
  /** 监听的事件列表（默认 5 种上游变更） */
  events?: Array<keyof Events>
  /** 'auto' = 事件到达直接调 onRefresh；'prompt' = 置 isStale=true 由页面渲染横幅 */
  mode?: 'auto' | 'prompt'
  /** 刷新回调 */
  onRefresh: () => void | Promise<void>
}

const DEFAULT_EVENTS: Array<keyof Events> = [
  'trial-balance:updated',
  'adjustment:saved',
  'dataset:activated',
  'year:changed',
  'project:updated',
]

export function useStaleRefresh(projectId: Ref<string>, options: StaleRefreshOptions) {
  const isStale = ref(false)
  const mode = options.mode ?? 'prompt'
  const events = options.events ?? DEFAULT_EVENTS

  function markFresh() { isStale.value = false }

  async function refresh() {
    try {
      await options.onRefresh()
      isStale.value = false
    } catch {
      // onRefresh 抛错保持 stale（页面 handleApiError 自行提示）
      isStale.value = true
    }
  }

  function _handler(payload: any) {
    // projectId 匹配判定（payload.projectId / payload.project_id 都接受）
    const evtPid = payload?.projectId || payload?.project_id || ''
    if (!evtPid || evtPid !== projectId.value) return

    if (mode === 'auto') {
      refresh()
    } else {
      isStale.value = true
    }
  }

  onMounted(() => {
    for (const evt of events) {
      eventBus.on(evt as any, _handler)
    }
  })

  onUnmounted(() => {
    for (const evt of events) {
      eventBus.off(evt as any, _handler)
    }
  })

  return { isStale, refresh, markFresh }
}
