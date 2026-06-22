/**
 * useEntityVerifyData — D0-2 核实数据核心 composable
 *
 * 职责：
 * - 从 htmlData 初始化行数据（entity-verify-v1 格式）
 * - CRUD 操作（addRow / deleteRows / updateField / importRows）
 * - 进度指标（verified / pending / returned / fraud_flag 统计）
 * - buildPayload 构建持久化数据
 *
 * Validates: Tasks 2.1 ~ 2.5
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import type { EntityVerifyRow, ProgressMetrics, EntityVerifyPayload } from '../entityVerifyTypes'

// ─── ID 生成工具（不依赖 uuid 库） ──────────────────────────────────────────

function generateRowId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
}

// ─── Props 接口 ──────────────────────────────────────────────────────────────

export interface UseEntityVerifyDataProps {
  /** 响应式数据源（来自底稿的 htmlData） */
  htmlData: () => any
  /** 是否只读 */
  readonly: boolean
}

// ─── 返回接口 ────────────────────────────────────────────────────────────────

export interface UseEntityVerifyDataReturn {
  rows: Ref<EntityVerifyRow[]>
  isDirty: Ref<boolean>

  // CRUD
  addRow: () => EntityVerifyRow
  deleteRows: (ids: string[]) => void
  updateField: (rowId: string, field: string, value: any) => void
  importRows: (newRows: Partial<EntityVerifyRow>[]) => void

  // 进度指标
  progressMetrics: ComputedRef<ProgressMetrics>

  // 持久化
  buildPayload: () => EntityVerifyPayload
}

// ─── Composable 主体 ─────────────────────────────────────────────────────────

export function useEntityVerifyData(props: UseEntityVerifyDataProps): UseEntityVerifyDataReturn {
  const rows = ref<EntityVerifyRow[]>([])
  const isDirty = ref(false)

  // ─── 初始化 ─────────────────────────────────────────────────────────────────

  function initFromHtmlData(data: any) {
    if (!data || data._format !== 'entity-verify-v1') {
      rows.value = []
      return
    }
    rows.value = Array.isArray(data.rows) ? data.rows.map(ensureRowId) : []
    isDirty.value = false
  }

  /** 确保每行都有 _row_id */
  function ensureRowId(row: EntityVerifyRow): EntityVerifyRow {
    if (!row._row_id) {
      return { ...row, _row_id: generateRowId() }
    }
    return row
  }

  // 初始加载
  initFromHtmlData(props.htmlData())

  // 监听 htmlData 变化并重新初始化
  watch(
    () => props.htmlData(),
    (newData) => {
      initFromHtmlData(newData)
    },
    { deep: true }
  )

  // ─── CRUD 操作 ──────────────────────────────────────────────────────────────

  function addRow(): EntityVerifyRow {
    const maxSeq = rows.value.reduce((max, r) => Math.max(max, r.seq ?? 0), 0)
    const newRow: EntityVerifyRow = {
      _row_id: generateRowId(),
      seq: maxSeq + 1,
      _source: 'manual',
      row_status: 'ok',
    }
    rows.value.push(newRow)
    isDirty.value = true
    return newRow
  }

  function deleteRows(ids: string[]) {
    if (!ids.length) return
    const idSet = new Set(ids)
    rows.value = rows.value.filter((r) => !idSet.has(r._row_id!))
    isDirty.value = true
  }

  function updateField(rowId: string, field: string, value: any) {
    const row = rows.value.find((r) => r._row_id === rowId)
    if (!row) return
    ;(row as any)[field] = value
    isDirty.value = true
  }

  function importRows(newRows: Partial<EntityVerifyRow>[]) {
    const maxSeq = rows.value.reduce((max, r) => Math.max(max, r.seq ?? 0), 0)
    newRows.forEach((data, idx) => {
      rows.value.push({
        ...data,
        _row_id: generateRowId(),
        seq: maxSeq + idx + 1,
        _source: data._source ?? 'import',
        row_status: 'ok',
      } as EntityVerifyRow)
    })
    isDirty.value = true
  }

  // ─── 进度指标 ───────────────────────────────────────────────────────────────

  const progressMetrics = computed<ProgressMetrics>(() => {
    const total = rows.value.length
    const verified = rows.value.filter((r) => {
      // 四个 match 字段全部为 'consistent' 才算已核实
      return (
        r.name_match === 'consistent' &&
        r.address_match === 'consistent' &&
        r.contact_match === 'consistent' &&
        r.phone_match === 'consistent'
      )
    }).length
    const pending = rows.value.filter((r) => {
      return !r.name_match || r.name_match === 'pending'
    }).length
    const returned = rows.value.filter((r) => r.first_result === '退回').length
    const fraudFlag = rows.value.filter((r) => r.row_status === 'fraud_flag').length

    return {
      total_count: total,
      verified_count: verified,
      pending_count: pending,
      returned_count: returned,
      fraud_flag_count: fraudFlag,
      verify_rate: total > 0 ? (verified / total) * 100 : 0,
      return_rate: total > 0 ? (returned / total) * 100 : 0,
    }
  })

  // ─── 持久化 ─────────────────────────────────────────────────────────────────

  function buildPayload(): EntityVerifyPayload {
    return {
      _format: 'entity-verify-v1',
      rows: rows.value,
      progress_summary: progressMetrics.value,
    }
  }

  return {
    rows,
    isDirty,
    addRow,
    deleteRows,
    updateField,
    importRows,
    progressMetrics,
    buildPayload,
  }
}
