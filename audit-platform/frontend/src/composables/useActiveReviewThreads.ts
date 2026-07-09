/**
 * useActiveReviewThreads — 批量查询底稿活跃复核线程
 *
 * 底稿加载时调用 loadActiveThreads(wpId)，返回 reactive map:
 *   { [sectionId]: { hasThread: true, hasUnread: boolean } }
 *
 * @see .kiro/specs/audit-review-dialog/design.md §活跃线程标记
 */
import { ref, type Ref } from 'vue'
import http from '@/utils/http'

export interface ThreadMarker {
  hasThread: boolean
  hasUnread: boolean
  hasTargetedUnread?: boolean
}

export function useActiveReviewThreads() {
  const threads: Ref<Record<string, ThreadMarker>> = ref({})
  const loading = ref(false)

  async function loadActiveThreads(wpId: string): Promise<void> {
    if (!wpId) return
    loading.value = true
    try {
      const res = await http.get('/api/review-threads/active', {
        params: { wp_id: wpId },
        _silent: true,
      } as any)
      const data = res?.data?.data || res?.data || []
      const map: Record<string, ThreadMarker> = {}
      if (Array.isArray(data)) {
        for (const item of data) {
          map[item.section_id] = {
            hasThread: true,
            hasUnread: !!item.has_unread,
            hasTargetedUnread: !!item.has_targeted_unread,
          }
        }
      }
      threads.value = map
    } catch {
      // silent — 非关键功能
      threads.value = {}
    } finally {
      loading.value = false
    }
  }

  function getMarker(sectionId: string): ThreadMarker | null {
    return threads.value[sectionId] || null
  }

  function getDotColor(sectionId: string): 'blue' | 'red' | null {
    const marker = threads.value[sectionId]
    if (!marker) return null
    return (marker.hasUnread || marker.hasTargetedUnread) ? 'red' : 'blue'
  }

  return {
    threads,
    loading,
    loadActiveThreads,
    getMarker,
    getDotColor,
  }
}
