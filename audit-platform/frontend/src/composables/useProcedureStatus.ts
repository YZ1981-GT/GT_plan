/**
 * useProcedureStatus — E1A/E26A 程序完成状态三档管理（Sprint 2 Task 2.13 + 2.38）
 *
 * 核心逻辑：
 * - 三档状态：filled（助理填完）→ reviewed（L1 复核通过）→ approved（L2+ 批准）
 * - 数据来源：wp.parsed_data.procedure_status[sheet_key].{R17, R22, ...}
 * - 自动刷新：订阅 eventBus 事件（review-record:resolved / signature:created /
 *   workpaper:saved / manual-refresh）
 *
 * 完成判定（F3.2 三档晋级条件，Task 2.38 加附件+签字联动）：
 * - filled = conclusion 已填 + 附件需求满足（F6.2 7 类）+ 签字已完成
 * - reviewed = filled + L1 复核通过（A21-1 对应行标记）
 * - approved = reviewed + L2+ 批准（A22-1/A23-1 对应行标记）
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'

export type ProcedureRowStatus = 'pending' | 'filled' | 'reviewed' | 'approved' | 'not_applicable'

export interface ProcedureRow {
  /** 程序行号，如 'R17' */
  row: string
  /** 程序文本 */
  description?: string
  /** 完成状态 */
  status: ProcedureRowStatus
  /** 程序分类: 常规★/备选/IPO 应对 */
  category?: string
  /** 财务报表认定（5 项）: 存在/完整性/权利义务/准确性/列报 */
  assertions?: string[]
  /** 底稿索引号（关联底稿） */
  workpaper_refs?: string[]
  /** 完成时间戳 */
  filled_at?: string
  reviewed_at?: string
  approved_at?: string
}

export interface ProcedureStatusSummary {
  total: number
  filled: number
  reviewed: number
  approved: number
  pending: number
}

export function useProcedureStatus(projectId: string, wpId: string, sheetKey = 'e1a') {
  const rows = ref<ProcedureRow[]>([])
  const loading = ref(false)
  const lastRefresh = ref<number>(0)

  /** 三档晋级条件（F3.2） */
  const summary = computed<ProcedureStatusSummary>(() => {
    const total = rows.value.length
    const filled = rows.value.filter((r) => r.status === 'filled' || r.status === 'reviewed' || r.status === 'approved').length
    const reviewed = rows.value.filter((r) => r.status === 'reviewed' || r.status === 'approved').length
    const approved = rows.value.filter((r) => r.status === 'approved').length
    const pending = rows.value.filter((r) => r.status === 'pending').length
    return { total, filled, reviewed, approved, pending }
  })

  const filledRate = computed(() => (summary.value.total > 0 ? Math.round((summary.value.filled / summary.value.total) * 100) : 0))
  const reviewedRate = computed(() => (summary.value.total > 0 ? Math.round((summary.value.reviewed / summary.value.total) * 100) : 0))
  const approvedRate = computed(() => (summary.value.total > 0 ? Math.round((summary.value.approved / summary.value.total) * 100) : 0))

  /** 加载程序状态（从底稿 parsed_data.procedure_status 读取） */
  async function refresh() {
    if (!projectId || !wpId) return
    loading.value = true
    try {
      const detail: any = await api.get(`/api/projects/${projectId}/working-papers/${wpId}`)
      const parsed = detail?.parsed_data || {}
      const status = parsed?.procedure_status?.[sheetKey] || {}
      const list: ProcedureRow[] = []
      for (const [rowKey, info] of Object.entries(status)) {
        const i = info as any
        list.push({
          row: rowKey,
          status: (i?.status || 'pending') as ProcedureRowStatus,
          category: i?.category,
          assertions: i?.assertions,
          workpaper_refs: i?.workpaper_refs,
          filled_at: i?.filled_at,
          reviewed_at: i?.reviewed_at,
          approved_at: i?.approved_at,
          description: i?.description,
        })
      }
      // 按 row 字段（Rxx）排序
      list.sort((a, b) => {
        const aN = parseInt(a.row.replace(/^R/, ''), 10) || 0
        const bN = parseInt(b.row.replace(/^R/, ''), 10) || 0
        return aN - bN
      })
      rows.value = list
      lastRefresh.value = Date.now()
    } catch (err) {
      console.warn('[useProcedureStatus] refresh failed:', err)
    } finally {
      loading.value = false
    }
  }

  /** 标记单行状态 */
  async function markStatus(rowKey: string, status: ProcedureRowStatus, extra?: Record<string, any>) {
    try {
      await api.patch(`/api/projects/${projectId}/working-papers/${wpId}/procedure-status`, {
        sheet_key: sheetKey,
        row: rowKey,
        status,
        ...(extra || {}),
      })
      const idx = rows.value.findIndex((r) => r.row === rowKey)
      if (idx >= 0) rows.value[idx].status = status
    } catch (err) {
      console.warn('[useProcedureStatus] markStatus failed:', err)
    }
  }

  // 订阅自动刷新事件
  let unsubscribers: Array<() => void> = []
  function setupSubscriptions() {
    const handlers: Array<[string, (...args: any[]) => void]> = [
      ['workpaper:saved', () => refresh()],
      ['review-record:resolved', () => refresh()],
      ['signature:created', () => refresh()],
      ['manual-refresh', () => refresh()],
      ['procedure-status:changed', () => refresh()],
    ]
    for (const [evt, h] of handlers) {
      eventBus.on(evt as any, h)
      unsubscribers.push(() => eventBus.off(evt as any, h))
    }
  }

  onMounted(() => {
    setupSubscriptions()
    refresh()
  })
  onUnmounted(() => {
    unsubscribers.forEach((u) => u())
    unsubscribers = []
  })

  return {
    rows,
    summary,
    filledRate,
    reviewedRate,
    approvedRate,
    loading,
    lastRefresh,
    refresh,
    markStatus,
  }
}
