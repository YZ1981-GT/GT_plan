/**
 * 截止测试样本量门槛 — 从项目 materiality 读取建议值
 * 订阅 materiality:changed 事件自动刷新（三次复盘 Fix A）
 */
import { ref, onBeforeUnmount, type Ref } from 'vue'
import http from '@/utils/http'
import { eventBus } from '@/utils/eventBus'

export function useCutoffMaterialityHint(projectId: Ref<string>) {
  const suggestedThreshold = ref<number | null>(null)
  const loading = ref(false)

  async function fetchHint(): Promise<number | null> {
    if (!projectId.value) return null
    loading.value = true
    try {
      const res = await http.get(`/api/projects/${projectId.value}/materiality`, { _silent: true } as any)
      const data = res.data?.data ?? res.data
      const perf = Number(data?.performance_materiality ?? data?.performanceMateriality ?? 0)
      const overall = Number(data?.overall_materiality ?? data?.overallMateriality ?? 0)
      const base = perf > 0 ? perf : overall
      if (base > 0) {
        suggestedThreshold.value = Math.round(base * 0.05 * 100) / 100
        return suggestedThreshold.value
      }
    } catch { /* silent */ } finally {
      loading.value = false
    }
    return null
  }

  // 订阅重要性变更事件，自动刷新门槛
  function _onMaterialityChanged(payload: { projectId: string }) {
    if (payload.projectId === projectId.value) fetchHint()
  }
  eventBus.on('materiality:changed', _onMaterialityChanged)
  onBeforeUnmount(() => { eventBus.off('materiality:changed', _onMaterialityChanged) })

  return { suggestedThreshold, loading, fetchHint }
}
