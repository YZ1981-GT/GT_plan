/**
 * Sprint C.3 — useNoteAggregation composable (C.3.1)
 * 
 * Manages consolidation note aggregation state and operations.
 */
import { ref, computed } from 'vue'
import { api } from '@/services/apiProxy'
import { ElMessage } from 'element-plus'

export interface AggregationState {
  isAggregating: boolean
  lastAggregatedAt: string | null
  staleSections: string[]
}

export function useNoteAggregation(projectId: () => string, year: () => number) {
  const state = ref<AggregationState>({
    isAggregating: false,
    lastAggregatedAt: null,
    staleSections: [],
  })

  async function reaggregate() {
    state.value.isAggregating = true
    try {
      await api.post(`/api/disclosure-notes/${projectId()}/${year()}/reaggregate`)
      state.value.staleSections = []
      state.value.lastAggregatedAt = new Date().toISOString()
      ElMessage.success('重新汇总完成')
    } catch (e: any) {
      ElMessage.error(e?.message || '汇总失败')
    } finally {
      state.value.isAggregating = false
    }
  }

  function markStale(sectionIds: string[]) {
    const set = new Set([...state.value.staleSections, ...sectionIds])
    state.value.staleSections = [...set]
  }

  const hasStale = computed(() => state.value.staleSections.length > 0)

  return { state, reaggregate, markStale, hasStale }
}
