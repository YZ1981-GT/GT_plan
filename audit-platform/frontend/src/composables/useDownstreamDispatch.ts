/**
 * useDownstreamDispatch.ts — 下游底稿通用 composable
 *
 * Feature: cross-workpaper-dispatch-persistence
 *
 * 用于 D0-4/D0-5/D0-6/D0-7 等下游底稿，在 onMounted 时拉取从 D0-1 分发来的记录，
 * 并通过 SSE 监听 DISPATCH_CREATED / DISPATCH_REVOKED 事件实现增量更新。
 *
 * 合并逻辑：跳过本地已存在 confirm_index 的行（前端去重）。
 */
import { ref, onMounted, onUnmounted, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  dispatchApi,
  type DispatchRecord,
  type DispatchTarget,
} from '@/services/dispatchApi'

export interface UseDownstreamDispatchOptions {
  /** 当前项目 ID */
  projectId: Ref<string>
  /** 当前底稿的 target 标识 (D0-4 / D0-5 / D0-6 / D0-7) */
  selfTarget: DispatchTarget
  /** 本地已有行的 confirm_index 集合（用于去重） */
  localConfirmIndices?: Ref<Set<string>>
}

export interface DownstreamDispatchReturn {
  /** 从 D0-1 带入的分发记录 */
  dispatchRecords: Ref<DispatchRecord[]>
  /** 是否正在加载 */
  loading: Ref<boolean>
  /** 手动刷新 */
  refresh: () => Promise<void>
}

export function useDownstreamDispatch(
  options: UseDownstreamDispatchOptions,
): DownstreamDispatchReturn {
  const { projectId, selfTarget, localConfirmIndices } = options

  const dispatchRecords = ref<DispatchRecord[]>([])
  const loading = ref(false)
  let eventSource: EventSource | null = null

  /**
   * 从后端加载分发记录（按 target 过滤）
   */
  async function loadRecords(): Promise<void> {
    if (!projectId.value) return
    loading.value = true
    try {
      const response = await dispatchApi.list(projectId.value, { target: selfTarget })
      // 合并逻辑：跳过本地已存在 confirm_index 的行
      const localIndices = localConfirmIndices?.value
      if (localIndices && localIndices.size > 0) {
        dispatchRecords.value = response.items.filter(
          record => !localIndices.has(record.confirm_index),
        )
      } else {
        dispatchRecords.value = response.items
      }
    } catch (e: any) {
      ElMessage.warning('加载上游分发记录失败，不影响底稿使用')
      // 不阻断底稿使用
    } finally {
      loading.value = false
    }
  }

  /**
   * SSE 事件监听 — 增量更新
   */
  function setupSSE(): void {
    if (!projectId.value) return

    try {
      const sseUrl = `/api/projects/${projectId.value}/events`
      eventSource = new EventSource(sseUrl)

      eventSource.addEventListener('message', (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data)
          const eventType = data.event_type || data.type

          // 仅处理 target 匹配的事件
          if (data.extra?.target !== selfTarget) return

          if (eventType === 'dispatch.created') {
            // 增量刷新：重新拉取
            loadRecords()
          } else if (eventType === 'dispatch.revoked') {
            // 移除被撤回的记录
            const revokedIndices = new Set(data.extra?.confirm_indices ?? [])
            dispatchRecords.value = dispatchRecords.value.filter(
              record => !revokedIndices.has(record.confirm_index),
            )
          }
        } catch {
          // 解析失败忽略
        }
      })

      eventSource.onerror = () => {
        // 浏览器 EventSource 自带重连机制（默认 3s），无需额外处理
      }
    } catch {
      // SSE 不可用时降级为不实时同步
    }
  }

  function teardownSSE(): void {
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
  }

  onMounted(() => {
    loadRecords()
    setupSSE()
  })

  onUnmounted(() => {
    teardownSSE()
  })

  return {
    dispatchRecords,
    loading,
    refresh: loadRecords,
  }
}
