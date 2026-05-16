/**
 * useStaleSummaryFull — Spec A R2 多模块聚合 stale 摘要（前端 composable）
 *
 * 职责：
 * - 拉取 /api/projects/{pid}/stale-summary/full
 * - 提供 workpapers / reports / notes / misstatements 4 模块计数
 * - 订阅 6 个 eventBus 事件（debounce 500ms）
 * - 用于 PartnerSignDecision / WorkpaperList / Misstatements / Adjustments / EqcrProjectView
 *
 * 与 useStaleStatus 的区别：
 * - useStaleStatus 只聚合底稿粒度（向后兼容老 5 视图）
 * - useStaleSummaryFull 聚合 4 模块（Spec A 新视图）
 *
 * 使用：
 * ```ts
 * const { workpapers, reports, notes, misstatements, anyStale, refresh }
 *   = useStaleSummaryFull(projectId, year)
 * // <el-badge :value="workpapers.value.stale" v-if="workpapers.value.stale > 0">
 * ```
 */
import { ref, computed, watch, onMounted, onUnmounted, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import { api } from '@/services/apiProxy'

interface ModuleSummary<T = any> {
  total: number
  stale?: number
  inconsistent?: number
  recheck_needed?: number
  items: T[]
}

interface FullSummary {
  workpapers: ModuleSummary
  reports: ModuleSummary
  notes: ModuleSummary
  misstatements: ModuleSummary
  last_event_at: string | null
}

const EMPTY: FullSummary = {
  workpapers: { total: 0, stale: 0, inconsistent: 0, items: [] },
  reports: { total: 0, stale: 0, items: [] },
  notes: { total: 0, stale: 0, items: [] },
  misstatements: { total: 0, recheck_needed: 0, items: [] },
  last_event_at: null,
}

let _debounceTimer: ReturnType<typeof setTimeout> | null = null

export function useStaleSummaryFull(
  projectId: Ref<string>,
  year: Ref<number>,
  options?: { debounceMs?: number },
) {
  const debounceMs = options?.debounceMs ?? 500
  const summary = ref<FullSummary>({ ...EMPTY })
  const loading = ref(false)
  const lastChecked = ref<Date | null>(null)

  const workpapers = computed(() => summary.value.workpapers)
  const reports = computed(() => summary.value.reports)
  const notes = computed(() => summary.value.notes)
  const misstatements = computed(() => summary.value.misstatements)

  // 任一模块有 stale → anyStale=true
  const anyStale = computed(() =>
    (workpapers.value.stale ?? 0) > 0
    || (workpapers.value.inconsistent ?? 0) > 0
    || (reports.value.stale ?? 0) > 0
    || (notes.value.stale ?? 0) > 0
    || (misstatements.value.recheck_needed ?? 0) > 0,
  )

  async function refresh() {
    if (!projectId.value || !year.value) return
    loading.value = true
    try {
      const data: any = await api.get(
        `/api/projects/${projectId.value}/stale-summary/full?year=${year.value}`,
        { validateStatus: (s: number) => s < 600 },
      )
      if (data && typeof data === 'object') {
        summary.value = {
          workpapers: { total: 0, stale: 0, inconsistent: 0, items: [], ...(data.workpapers || {}) },
          reports: { total: 0, stale: 0, items: [], ...(data.reports || {}) },
          notes: { total: 0, stale: 0, items: [], ...(data.notes || {}) },
          misstatements: { total: 0, recheck_needed: 0, items: [], ...(data.misstatements || {}) },
          last_event_at: data.last_event_at ?? null,
        }
        lastChecked.value = new Date()
      }
    } catch {
      // 静默忽略（网络错误不打扰用户）
    } finally {
      loading.value = false
    }
  }

  function debouncedRefresh() {
    if (_debounceTimer) clearTimeout(_debounceTimer)
    _debounceTimer = setTimeout(() => refresh(), debounceMs)
  }

  function _onYearChanged() { refresh() }  // 切年立即刷新不防抖

  onMounted(() => {
    refresh()
    eventBus.on('workpaper:saved', debouncedRefresh)
    eventBus.on('adjustment:created', debouncedRefresh)
    eventBus.on('adjustment:updated', debouncedRefresh)
    eventBus.on('adjustment:deleted', debouncedRefresh)
    eventBus.on('materiality:changed', debouncedRefresh)
    eventBus.on('dataset:activated', debouncedRefresh)
    eventBus.on('year:changed', _onYearChanged)
  })

  onUnmounted(() => {
    if (_debounceTimer) clearTimeout(_debounceTimer)
    eventBus.off('workpaper:saved', debouncedRefresh)
    eventBus.off('adjustment:created', debouncedRefresh)
    eventBus.off('adjustment:updated', debouncedRefresh)
    eventBus.off('adjustment:deleted', debouncedRefresh)
    eventBus.off('materiality:changed', debouncedRefresh)
    eventBus.off('dataset:activated', debouncedRefresh)
    eventBus.off('year:changed', _onYearChanged)
  })

  watch([projectId, year], () => refresh())

  return {
    summary,
    workpapers,
    reports,
    notes,
    misstatements,
    anyStale,
    loading,
    lastChecked,
    refresh,
  }
}
