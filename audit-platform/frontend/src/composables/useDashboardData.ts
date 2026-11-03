/**
 * useDashboardData — 合伙人仪表盘数据获取 composable
 *
 * 职责：
 * - 拉取 GET /api/projects/{pid}/dashboard/summary 聚合端点
 * - 提供 data / loading / error / lastUpdated 响应式状态
 * - 计算属性：cycleProgress / vrSummary / openReviews / timeline / trimmingOverview
 * - 自动 onMounted 调用 refresh
 * - 可选轮询（startPolling / stopPolling）
 * - 错误处理：网络错误 → error ref 赋值 + console.warn
 *
 * Validates: Requirements 1.4, 9.1
 */
import { ref, computed, onMounted, onUnmounted, type Ref, type ComputedRef } from 'vue'
import { api } from '@/services/apiProxy'

// ─── TypeScript 接口（对齐后端 Pydantic Schema） ─────────────────────────────

export interface CycleProgressItem {
  cycle: string
  cycle_name: string
  total_procedures: number
  completed_procedures: number
  trimmed_procedures: number
  progress_rate: number
}

export interface FailedRuleItem {
  rule_id: string
  rule_name: string
  details: string | null
}

export interface CycleVRStat {
  cycle: string
  blocking_failed: number
  failed_rules: FailedRuleItem[]
}

/** 非通过检查项的五态与原因（后端 CheckStatusItem，需求 16.5） */
export interface VRCheckStatusItem {
  check_name: string
  status: string
  reason: string
  branch_id?: string
  severity?: string
}

export interface VRSummaryData {
  total_rules: number
  blocking_failed: number
  /** 每项都通过才为真（与 consistency-check 同口径） */
  all_passed: boolean
  by_cycle: CycleVRStat[]
  /** 没有运行一致性检查（如项目未设置审计年度），原因在 reason */
  unavailable?: boolean
  reason?: string | null
  /** 五态计数：passed / failed / not_executed / not_applicable / error */
  status_counts?: Record<string, number>
  not_passed_checks?: VRCheckStatusItem[]
}

export interface ReviewItem {
  id: string
  review_layer: string
  summary: string
  created_at: string
  wp_code: string
  sheet_name: string | null
  cell_ref: string | null
}

export interface OpenReviewsData {
  total: number
  by_layer: Record<string, number>
  items: ReviewItem[]
}

export interface StageItem {
  name: string
  status: string
  entered_at: string | null
  completed_at: string | null
  summary: string | null
}

export interface TimelineData {
  current_stage: string
  stages: StageItem[]
}

export interface CycleTrimStat {
  cycle: string
  total: number
  trimmed: number
  rate: number
  warning: boolean
}

export interface TrimmingData {
  available: boolean
  total_procedures: number
  trimmed_count: number
  trim_rate: number
  by_cycle: CycleTrimStat[]
}

export interface DashboardSummary {
  project_name: string
  audit_year: number
  last_updated: string

  cycle_progress: CycleProgressItem[] | null
  vr_summary: VRSummaryData | null
  open_reviews: OpenReviewsData | null
  timeline: TimelineData | null
  trimming_overview: TrimmingData | null

  errors: Record<string, string> | null
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useDashboardData(projectId: Ref<string>) {
  const data = ref<DashboardSummary | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const lastUpdated = ref<string | null>(null)

  let _pollingTimer: ReturnType<typeof setInterval> | null = null

  /**
   * 手动刷新：调用聚合端点获取仪表盘数据
   */
  async function refresh(): Promise<void> {
    if (!projectId.value) return
    loading.value = true
    error.value = null
    try {
      const result = await api.get<DashboardSummary>(
        `/api/projects/${projectId.value}/dashboard/summary`,
      )
      data.value = result
      lastUpdated.value = result?.last_updated ?? new Date().toISOString()
    } catch (err: any) {
      const msg = err?.message || '仪表盘数据加载失败'
      error.value = msg
      console.warn('[useDashboardData] refresh failed:', err)
    } finally {
      loading.value = false
    }
  }

  /**
   * 启动轮询（默认不启用，需手动调用）
   */
  function startPolling(intervalMs = 30000): void {
    stopPolling()
    _pollingTimer = setInterval(() => refresh(), intervalMs)
  }

  /**
   * 停止轮询
   */
  function stopPolling(): void {
    if (_pollingTimer) {
      clearInterval(_pollingTimer)
      _pollingTimer = null
    }
  }

  // ─── 计算属性 ────────────────────────────────────────────────────────────

  const cycleProgress: ComputedRef<CycleProgressItem[]> = computed(
    () => data.value?.cycle_progress ?? [],
  )

  const vrSummary: ComputedRef<VRSummaryData | null> = computed(
    () => data.value?.vr_summary ?? null,
  )

  const openReviews: ComputedRef<ReviewItem[]> = computed(
    () => data.value?.open_reviews?.items ?? [],
  )

  const openReviewsData: ComputedRef<OpenReviewsData | null> = computed(
    () => data.value?.open_reviews ?? null,
  )

  const timeline: ComputedRef<TimelineData | null> = computed(
    () => data.value?.timeline ?? null,
  )

  const trimmingOverview: ComputedRef<TrimmingData | null> = computed(
    () => data.value?.trimming_overview ?? null,
  )

  // ─── 生命周期 ────────────────────────────────────────────────────────────

  onMounted(() => {
    refresh()
  })

  onUnmounted(() => {
    stopPolling()
  })

  return {
    data,
    loading,
    error,
    lastUpdated,
    refresh,
    startPolling,
    stopPolling,
    cycleProgress,
    vrSummary,
    openReviews,
    openReviewsData,
    timeline,
    trimmingOverview,
  }
}
