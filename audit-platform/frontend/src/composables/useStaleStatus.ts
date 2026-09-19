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
 * const stale = useStaleStatus(projectId)          // year 取 projectStore.year
 * const stale = useStaleStatus(projectId, year)    // 或显式传入
 * // 模板：v-if="stale.isStale.value" 显示提示横幅
 * ```
 */
import { ref, watch, onMounted, onUnmounted, type Ref, type ComputedRef } from 'vue'
import { eventBus } from '@/utils/eventBus'
import { api } from '@/services/apiProxy'
import { useProjectStore } from '@/stores/project'

export interface StaleItem {
  id: string
  wp_code: string
  wp_name: string
  stale_reason?: string | null
}

/** 重算后的 stale 收敛结果（后端 /trial-balance/recalc 返回） */
export interface StaleResolution {
  cleared: number
  refilled: number
  kept_stale: number
}

export function useStaleStatus(
  projectId: Ref<string>,
  year?: Ref<number> | ComputedRef<number>,
) {
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
      // 不传 config：apiProxy 仅对「无 config 的纯 GET」做 in-flight 共享。
      // 此前带 validateStatus 走了非共享分支，与 DefaultLayout 的同 URL 轮询撞上
      // http.ts 的 GET 去重（abort 前一个），导致本次 check 被取消 → 横幅随机不渲染。
      const data: any = await api.get(`/api/projects/${projectId.value}/stale-summary`)
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

  /** 解析重算年度：显式入参 > projectStore.year > 上一自然年（store 惰性读取，避免脱离 pinia 报错） */
  function resolveYear(): number {
    if (year?.value) return year.value
    try {
      const storeYear = useProjectStore().year
      if (storeYear) return storeYear
    } catch { /* 无 pinia 上下文时降级 */ }
    return new Date().getFullYear() - 1
  }

  /**
   * 触发试算表全量重算并复查 stale 状态。
   *
   * 注意：后端 `POST /trial-balance/recalc` 的 `year` 是**必填** Query 参数，
   * 漏传会 422。此前这里既不传 year 又用 `validateStatus: s < 600` 吞掉了非 2xx，
   * 导致「点击重算」实际从未执行、横幅永远不消失。
   */
  async function recalc(): Promise<StaleResolution | null> {
    if (!projectId.value) return null
    loading.value = true
    try {
      const resp: any = await api.post(
        `/api/projects/${projectId.value}/trial-balance/recalc`,
        {},
        { params: { year: resolveYear() } },
      )
      // 重算完成后重新查 stale 状态
      await check()
      return (resp?.stale_resolution as StaleResolution) ?? null
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
