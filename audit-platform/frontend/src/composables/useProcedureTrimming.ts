/**
 * useProcedureTrimming — 程序适用性裁剪 composable
 *
 * 核心功能：
 * - trimRows(rowIds, reason) → PATCH /procedure-trim action=trim
 * - revertRows(rowIds) → PATCH /procedure-trim action=revert
 * - fetchSummary() → GET /procedure-trim/summary
 * - fetchHistory(filters) → GET /procedure-trim/history
 * - 操作成功后 eventBus.emit('procedure-status:changed') 触发 sheet 导航刷新
 *
 * @see design.md — 前端 Composable 接口定义
 * @see requirements.md — Requirement 2.4, 3.3, 4.1, 5.1, 5.2
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'

// ─── 类型定义 ─────────────────────────────────────────────────────────────────

export type TrimReasonCode =
  | 'no_related_business'
  | 'low_risk_assessment'
  | 'control_test_effective'
  | 'other'

export interface TrimReason {
  reason_code: TrimReasonCode
  reason_text?: string | null
}

export interface TrimRow {
  row: string
  description?: string
  status: string
  /** 裁剪元数据（仅 not_applicable 行有值） */
  trimmed_by?: string
  trimmed_at?: string
  reason_code?: TrimReasonCode
  reason_text?: string | null
  batch_id?: string | null
  /** 程序分类 */
  category?: string
  /** 认定 */
  assertions?: string[]
  /** 循环 */
  cycle?: string
  /** 风险等级 */
  risk_level?: string
}

export interface TrimStats {
  total: number
  trimmed: number
  active: number
  trimRate: number
}

export interface TrimResult {
  ok: boolean
  action: string
  succeeded: string[]
  skipped: string[]
  failed: string[]
  message?: string | null
}

export interface CycleTrimStat {
  cycle: string
  total: number
  trimmed: number
  rate: number
  warning: boolean
}

export interface ReasonTrimStat {
  reason_code: string
  count: number
}

export interface TrimSummary {
  total_procedures: number
  trimmed_count: number
  trim_rate: number
  by_cycle: CycleTrimStat[]
  by_reason: ReasonTrimStat[]
  warnings: string[]
}

export interface TrimLogEntry {
  id: string
  action: 'trim' | 'revert'
  row_ids: string[]
  reason_code?: string | null
  reason_text?: string | null
  user_id: string
  user_name?: string | null
  created_at: string
}

export interface HistoryFilter {
  user_id?: string
  reason_code?: string
  start_date?: string
  end_date?: string
}

// ─── Composable ───────────────────────────────────────────────────────────────

export function useProcedureTrimming(projectId: string, wpId: string, sheetKey: string) {
  const rows = ref<TrimRow[]>([])
  const loading = ref(false)
  const trimHistory = ref<TrimLogEntry[]>([])

  const baseUrl = computed(
    () => `/api/projects/${projectId}/workpapers/${wpId}/procedure-trim`,
  )

  /** 统计摘要 */
  const stats = computed<TrimStats>(() => {
    const total = rows.value.length
    const trimmed = rows.value.filter((r) => r.status === 'not_applicable').length
    const active = total - trimmed
    const trimRate = total > 0 ? Math.round((trimmed / total) * 1000) / 10 : 0
    return { total, trimmed, active, trimRate }
  })

  /** 加载程序行列表（从底稿 parsed_data 读取） */
  async function refresh(): Promise<void> {
    if (!projectId || !wpId) return
    loading.value = true
    try {
      const detail: any = await api.get(`/api/projects/${projectId}/working-papers/${wpId}`)
      const parsed = detail?.parsed_data || {}
      const procedureStatus = parsed?.procedure_status?.[sheetKey] || {}
      const trimmingMetadata = parsed?.trimming_metadata?.[sheetKey] || {}

      const list: TrimRow[] = []
      for (const [rowKey, info] of Object.entries(procedureStatus)) {
        const i = info as any
        const meta = trimmingMetadata[rowKey] as any
        list.push({
          row: rowKey,
          description: i?.description,
          status: i?.status || 'pending',
          category: i?.category,
          assertions: i?.assertions,
          cycle: i?.cycle,
          risk_level: i?.risk_level,
          // 裁剪元数据
          trimmed_by: meta?.trimmed_by,
          trimmed_at: meta?.trimmed_at,
          reason_code: meta?.reason_code,
          reason_text: meta?.reason_text,
          batch_id: meta?.batch_id,
        })
      }
      // 按 row 字段（Rxx）排序
      list.sort((a, b) => {
        const aN = parseInt(a.row.replace(/^R/, ''), 10) || 0
        const bN = parseInt(b.row.replace(/^R/, ''), 10) || 0
        return aN - bN
      })
      rows.value = list
    } catch (err) {
      console.warn('[useProcedureTrimming] refresh failed:', err)
    } finally {
      loading.value = false
    }
  }

  /** 裁剪程序行 */
  async function trimRows(rowIds: string[], reason: TrimReason): Promise<TrimResult> {
    loading.value = true
    try {
      const result = await api.patch<TrimResult>(baseUrl.value, {
        action: 'trim',
        sheet_key: sheetKey,
        row_ids: rowIds,
        reason_code: reason.reason_code,
        reason_text: reason.reason_text || null,
      })
      // 更新本地状态
      for (const rowId of result.succeeded || []) {
        const row = rows.value.find((r) => r.row === rowId)
        if (row) {
          row.status = 'not_applicable'
          row.reason_code = reason.reason_code
          row.reason_text = reason.reason_text || null
        }
      }
      // 触发 sheet 导航刷新
      _selfEmitting = true
      eventBus.emit('procedure-status:changed', {
        projectId,
        wpId,
        sheetKey,
        row: rowIds[0] || '',
        status: 'not_applicable',
      })
      _selfEmitting = false
      return result
    } catch (err: any) {
      console.warn('[useProcedureTrimming] trimRows failed:', err)
      return { ok: false, action: 'trim', succeeded: [], skipped: [], failed: rowIds, message: err?.message }
    } finally {
      loading.value = false
    }
  }

  /** 恢复程序行 */
  async function revertRows(rowIds: string[]): Promise<TrimResult> {
    loading.value = true
    try {
      const result = await api.patch<TrimResult>(baseUrl.value, {
        action: 'revert',
        sheet_key: sheetKey,
        row_ids: rowIds,
      })
      // 更新本地状态
      for (const rowId of result.succeeded || []) {
        const row = rows.value.find((r) => r.row === rowId)
        if (row) {
          row.status = 'pending'
          row.reason_code = undefined
          row.reason_text = null
          row.trimmed_by = undefined
          row.trimmed_at = undefined
          row.batch_id = null
        }
      }
      // 触发 sheet 导航刷新
      _selfEmitting = true
      eventBus.emit('procedure-status:changed', {
        projectId,
        wpId,
        sheetKey,
        row: rowIds[0] || '',
        status: 'pending',
      })
      _selfEmitting = false
      return result
    } catch (err: any) {
      console.warn('[useProcedureTrimming] revertRows failed:', err)
      return { ok: false, action: 'revert', succeeded: [], skipped: [], failed: rowIds, message: err?.message }
    } finally {
      loading.value = false
    }
  }

  /** 获取裁剪汇总 */
  async function fetchSummary(): Promise<TrimSummary> {
    try {
      const data = await api.get<TrimSummary>(`${baseUrl.value}/summary`)
      return data
    } catch (err) {
      console.warn('[useProcedureTrimming] fetchSummary failed:', err)
      return {
        total_procedures: 0,
        trimmed_count: 0,
        trim_rate: 0,
        by_cycle: [],
        by_reason: [],
        warnings: [],
      }
    }
  }

  /** 获取裁剪操作历史 */
  async function fetchHistory(filters?: HistoryFilter): Promise<TrimLogEntry[]> {
    try {
      const params: Record<string, string> = {}
      if (filters?.user_id) params.user_id = filters.user_id
      if (filters?.reason_code) params.reason_code = filters.reason_code
      if (filters?.start_date) params.start_date = filters.start_date
      if (filters?.end_date) params.end_date = filters.end_date

      const data = await api.get<TrimLogEntry[]>(`${baseUrl.value}/history`, { params })
      trimHistory.value = data || []
      return trimHistory.value
    } catch (err) {
      console.warn('[useProcedureTrimming] fetchHistory failed:', err)
      trimHistory.value = []
      return []
    }
  }

  // 订阅自动刷新事件（跳过自身触发的事件）
  let _selfEmitting = false
  let unsubscribers: Array<() => void> = []
  function setupSubscriptions() {
    const handler = () => {
      if (_selfEmitting) return
      refresh()
    }
    eventBus.on('procedure-status:changed', handler)
    unsubscribers.push(() => eventBus.off('procedure-status:changed', handler))
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
    stats,
    loading,
    trimHistory,
    trimRows,
    revertRows,
    refresh,
    fetchSummary,
    fetchHistory,
  }
}
