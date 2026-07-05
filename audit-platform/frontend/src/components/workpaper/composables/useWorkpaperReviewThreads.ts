/**
 * useWorkpaperReviewThreads — 循环底稿通用复核线程蓝/红点（G12/G13/G14 等）
 */
import { ref, onMounted, type Ref } from 'vue'
import http from '@/utils/http'

export function useWorkpaperReviewThreads(wpId: Ref<string>) {
  const activeThreads = ref<Record<string, 'blue' | 'red'>>({})

  async function loadActiveThreads(): Promise<void> {
    if (!wpId.value) return
    try {
      const res = await http.get('/api/review-threads/active', {
        params: { wp_id: wpId.value },
        _silent: true,
      } as any)
      const threads: Array<{ section_id: string; has_unread: boolean }> =
        res.data?.data?.threads ?? res.data?.threads ?? []
      const map: Record<string, 'blue' | 'red'> = {}
      for (const t of threads) {
        if (t.section_id) {
          map[t.section_id] = t.has_unread ? 'red' : 'blue'
        }
      }
      activeThreads.value = map
    } catch {
      activeThreads.value = {}
    }
  }

  function getThreadDot(sectionId: string): 'blue' | 'red' | null {
    return activeThreads.value[sectionId] ?? null
  }

  function getRowDot(prefix: string, rowKey: string): 'blue' | 'red' | null {
    const needle = `${prefix}-${rowKey}-`
    let best: 'blue' | 'red' | null = null
    for (const [sid, dot] of Object.entries(activeThreads.value)) {
      if (!sid.startsWith(needle)) continue
      if (dot === 'red') return 'red'
      best = dot
    }
    return best
  }

  onMounted(() => { void loadActiveThreads() })

  return { activeThreads, getThreadDot, getRowDot, reload: loadActiveThreads }
}

export default useWorkpaperReviewThreads
