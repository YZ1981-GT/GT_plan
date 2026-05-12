/**
 * useStaleStatus — 跨视图 stale 状态追踪（R8-S2-03）
 *
 * 职责：
 * - 拉取项目的 stale-summary（有多少底稿 prefill_stale=true）
 * - 监听 workpaper:saved / year:changed 事件自动刷新
 * - 暴露 recalc 方法触发 trial-balance 重算
 *
 * 使用：
 * ```ts
 * const stale = useStaleStatus(projectId)
 * // 模板：v-if="stale.isStale.value" 显示提示横幅
 * ```
 */
import { ref, watch, onMounted, onUnmounted, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import { api } from '@/services/apiProxy'

export interface StaleItem {
  id: string
  wp_code: string
  wp_name: string
  stale_reason?: string | null
}

export function useStaleStatus(projectId: Ref<string>) {
  const isStale = ref(false)
  const staleCount = ref(0)
  const staleItems = ref<StaleItem[]>([])
  const lastChecked = ref<Date | null>(null)
  const loading = ref(false)

  async function check() {
    if (!projectId.value) {
      isStale.value = false
      staleCount.value = 0
      staleItems.value = []
      return
    }
    loading.value = true
    try {
      const data: any = await api.get(
        `/api/projects/${projectId.value}/stale-summary`,
        { validateStatus: (s: number) => s < 600 },
      )
      staleCount.value = data?.stale_count || 0
      staleItems.value = data?.items || []
      isStale.value = staleCount.value > 0
      lastChecked.value = new Date()
    } catch {
      // 静默忽略（网络错误不打扰用户）
    } finally {
      loading.value = false
    }
  }

  async function recalc() {
    if (!projectId.value) return
    loading.value = true
    try {
      await api.post(
        `/api/projects/${projectId.value}/trial-balance/recalc`,
        {},
        { validateStatus: (s: number) => s < 600 },
      )
      // 重算完成后重新查 stale 状态
      await check()
    } finally {
      loading.value = false
    }
  }

  function handleWorkpaperSaved() { check() }
  function handleYearChanged() { check() }

  onMounted(() => {
    check()
    eventBus.on('workpaper:saved', handleWorkpaperSaved)
    eventBus.on('year:changed', handleYearChanged)
  })

  onUnmounted(() => {
    eventBus.off('workpaper:saved', handleWorkpaperSaved)
    eventBus.off('year:changed', handleYearChanged)
  })

  // projectId 切换时自动重新检查
  watch(projectId, () => check())

  return {
    isStale,
    staleCount,
    staleItems,
    lastChecked,
    loading,
    check,
    recalc,
  }
}
